"""Open-Meteo Single Runs API caching and response parsing."""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.data.weather_config import (
    EXPECTED_API_UNITS,
    FORECAST_HOURS,
    HOURLY_VARIABLES,
    LOCAL_TIMEZONE,
    NOMINAL_ISSUE_HOUR_LOCAL,
    OPEN_METEO_SINGLE_RUNS_ENDPOINT,
    VARIABLE_COLUMN_MAP,
    WEATHER_MODEL,
    WEATHER_MODEL_API_IDENTIFIER,
    WEATHER_SOURCE,
    WeatherLocation,
)


class WeatherResponseError(ValueError):
    """Raised when an archived weather response violates the data contract."""


class RateLimitError(requests.HTTPError):
    """Raised after a polite bounded sequence of HTTP 429 responses."""


class OfficialArchiveUnavailableError(WeatherResponseError):
    """Raised when the official API identifies a requested model run as unavailable."""


@dataclass(frozen=True)
class CachedRun:
    """A parsed raw response and its cache status."""

    payload: Any
    path: Path
    reused: bool
    rate_limit_retries: int = 0


def _read_cached_payload(path: Path, attempts: int = 6) -> Any:
    """Read a OneDrive-backed cache file with bounded transient retries."""
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2**attempt))
    assert last_error is not None
    raise last_error


def _write_raw_cache(path: Path, raw_bytes: bytes, attempts: int = 6) -> None:
    """Atomically preserve raw bytes with bounded retries for synced filesystems."""
    temporary = path.with_suffix(".json.part")
    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            temporary.write_bytes(raw_bytes)
            temporary.replace(path)
            if not path.is_file():
                raise FileNotFoundError(f"Cache file not visible after atomic replace: {path}")
            return
        except OSError as error:
            last_error = error
            try:
                if temporary.exists():
                    temporary.unlink()
            except OSError:
                pass
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2**attempt))
    assert last_error is not None
    raise last_error


def create_retry_session() -> requests.Session:
    """Create a conservative retrying HTTP session for serial archive requests."""
    retry = Retry(
        total=7,
        connect=7,
        read=7,
        status=7,
        backoff_factor=1.5,
        # HTTP 429 is handled explicitly in fetch_run so a sustained rate limit
        # stops the retrieval pass instead of being hidden inside urllib3.
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        # fetch_run parses and honours Retry-After for 429 itself.
        respect_retry_after_header=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "gb-renewable-forecasting-research/1.0"})
    return session


def retry_after_seconds(
    header_value: str | None,
    now: datetime | None = None,
) -> float | None:
    """Parse an HTTP Retry-After delta or date into non-negative seconds."""
    if not header_value:
        return None
    try:
        return max(0.0, float(header_value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(header_value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        reference = now or datetime.now(timezone.utc)
        return max(0.0, (retry_at - reference).total_seconds())


def rate_limit_wait_seconds(
    retry_after_header: str | None,
    attempt: int,
    jitter_seconds: float | None = None,
) -> float:
    """Return a polite Retry-After or exponential-backoff delay with jitter."""
    if attempt < 0:
        raise ValueError("Retry attempt cannot be negative.")
    retry_after = retry_after_seconds(retry_after_header)
    base_delay = retry_after if retry_after is not None else min(300.0, 15.0 * 2**attempt)
    jitter = random.uniform(0.5, 2.5) if jitter_seconds is None else jitter_seconds
    return base_delay + max(0.0, jitter)


def normalize_run_init(run_init: str | pd.Timestamp) -> pd.Timestamp:
    """Return a UTC timestamp and enforce the selected daily 00 UTC cycle."""
    timestamp = pd.Timestamp(run_init)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    if timestamp.minute != 0 or timestamp.second != 0 or timestamp.hour != 0:
        raise ValueError(f"Expected a 00 UTC run initialization, received {timestamp}.")
    return timestamp


def build_request_params(
    run_init: str | pd.Timestamp,
    locations: tuple[WeatherLocation, ...],
) -> dict[str, str | int]:
    """Build the reproducible ten-coordinate ECMWF IFS HRES request."""
    run_timestamp = normalize_run_init(run_init)
    return {
        "latitude": ",".join(str(location.latitude) for location in locations),
        "longitude": ",".join(str(location.longitude) for location in locations),
        "hourly": ",".join(HOURLY_VARIABLES),
        "models": WEATHER_MODEL_API_IDENTIFIER,
        "run": run_timestamp.strftime("%Y-%m-%dT%H:%M"),
        "forecast_hours": FORECAST_HOURS,
        "timezone": "GMT",
        "wind_speed_unit": "ms",
        "temperature_unit": "celsius",
    }


def cache_path(cache_directory: Path, run_init: str | pd.Timestamp) -> Path:
    """Return the immutable cache filename for a model initialization."""
    timestamp = normalize_run_init(run_init)
    return cache_directory / f"run_{timestamp.strftime('%Y%m%dT0000Z')}.json"


def fetch_run(
    run_init: str | pd.Timestamp,
    locations: tuple[WeatherLocation, ...],
    cache_directory: Path,
    session: requests.Session | None = None,
    timeout_seconds: int = 120,
    max_rate_limit_retries: int = 4,
    maximum_rate_limit_wait_seconds: float = 300.0,
) -> CachedRun:
    """Load a cached raw run or download it atomically without overwriting cache."""
    output = cache_path(cache_directory, run_init)
    if output.is_file():
        return CachedRun(
            payload=_read_cached_payload(output),
            path=output,
            reused=True,
            rate_limit_retries=0,
        )

    cache_directory.mkdir(parents=True, exist_ok=True)
    request_session = session or create_retry_session()
    rate_limit_retries = 0
    while True:
        response = request_session.get(
            OPEN_METEO_SINGLE_RUNS_ENDPOINT,
            params=build_request_params(run_init, locations),
            timeout=timeout_seconds,
        )
        if response.status_code != 429:
            break
        retry_after = response.headers.get("Retry-After")
        if rate_limit_retries >= max_rate_limit_retries:
            raise RateLimitError(
                "Sustained Open-Meteo HTTP 429 response sequence; retrieval pass stopped.",
                response=response,
            )
        wait_seconds = rate_limit_wait_seconds(retry_after, rate_limit_retries)
        if wait_seconds > maximum_rate_limit_wait_seconds:
            raise RateLimitError(
                f"Open-Meteo requested Retry-After of {wait_seconds:.1f}s, exceeding "
                f"the bounded per-request wait of {maximum_rate_limit_wait_seconds:.1f}s; "
                "retrieval pass stopped.",
                response=response,
            )
        rate_limit_retries += 1
        print(
            f"HTTP 429 for {normalize_run_init(run_init).date()}; waiting "
            f"{wait_seconds:.1f}s before retry {rate_limit_retries}/"
            f"{max_rate_limit_retries}.",
            flush=True,
        )
        time.sleep(wait_seconds)
    response.raise_for_status()
    response_text = response.content.decode("utf-8", errors="replace")
    if "modelRunUnavailable" in response_text:
        raise OfficialArchiveUnavailableError(response_text)
    payload = response.json()
    raw_bytes = response.content
    # Confirm bytes and parsed payload agree before preserving the response unchanged.
    if json.loads(raw_bytes) != payload:
        raise WeatherResponseError("Response bytes and decoded JSON payload disagree.")
    _write_raw_cache(output, raw_bytes)
    return CachedRun(
        payload=payload,
        path=output,
        reused=False,
        rate_limit_retries=rate_limit_retries,
    )


def nominal_issue_time(run_init: str | pd.Timestamp) -> pd.Timestamp:
    """Return nominal 09:00 Europe/London issue time for the run calendar date."""
    run_timestamp = normalize_run_init(run_init)
    local_wall_time = pd.Timestamp(run_timestamp.date()) + pd.Timedelta(
        hours=NOMINAL_ISSUE_HOUR_LOCAL
    )
    return local_wall_time.tz_localize(LOCAL_TIMEZONE)


def intended_target_date(run_init: str | pd.Timestamp) -> date:
    """Return the following local calendar date targeted by a run."""
    return (normalize_run_init(run_init) + pd.Timedelta(days=1)).date()


def expected_following_day_times(target_date: date | str | pd.Timestamp) -> pd.DatetimeIndex:
    """Return local-hour boundaries for a target day, including its closing boundary."""
    day = pd.Timestamp(target_date).normalize()
    start_local = day.tz_localize(LOCAL_TIMEZONE)
    end_local = (day + pd.Timedelta(days=1)).tz_localize(LOCAL_TIMEZONE)
    return pd.date_range(start_local, end_local, freq="h", inclusive="both").tz_convert("UTC")


def parse_multiple_location_response(
    payload: Any,
    locations: tuple[WeatherLocation, ...],
    run_init: str | pd.Timestamp,
) -> pd.DataFrame:
    """Parse a multi-coordinate response into one row per location and valid hour."""
    responses = payload if isinstance(payload, list) else [payload]
    if len(responses) != len(locations):
        raise WeatherResponseError(
            f"Expected {len(locations)} location responses, received {len(responses)}."
        )
    run_timestamp = normalize_run_init(run_init)
    frames: list[pd.DataFrame] = []
    for location, response in zip(locations, responses, strict=True):
        hourly = response.get("hourly", {})
        units = response.get("hourly_units", {})
        missing_variables = sorted(set(HOURLY_VARIABLES).difference(hourly))
        if "time" not in hourly or missing_variables:
            raise WeatherResponseError(
                f"{location.name} response missing hourly fields: {missing_variables}"
            )
        wrong_units = {
            variable: {"expected": expected, "actual": units.get(variable)}
            for variable, expected in EXPECTED_API_UNITS.items()
            if units.get(variable) != expected
        }
        if wrong_units:
            raise WeatherResponseError(f"Unexpected units for {location.name}: {wrong_units}")

        valid_time_utc = pd.to_datetime(hourly["time"], utc=True, errors="coerce")
        row_count = len(valid_time_utc)
        values: dict[str, Any] = {
            "location_name": [location.name] * row_count,
            "latitude": [location.latitude] * row_count,
            "longitude": [location.longitude] * row_count,
            "api_grid_latitude": [response.get("latitude")] * row_count,
            "api_grid_longitude": [response.get("longitude")] * row_count,
            "api_grid_elevation_m": [response.get("elevation")] * row_count,
            "weather_source": [WEATHER_SOURCE] * row_count,
            "weather_model": [WEATHER_MODEL] * row_count,
            "weather_model_api_identifier": [WEATHER_MODEL_API_IDENTIFIER] * row_count,
            "weather_run_init_utc": [run_timestamp] * row_count,
            "nominal_forecast_issue_time_local": [nominal_issue_time(run_timestamp)] * row_count,
            "valid_time_utc": valid_time_utc,
        }
        for api_name, clean_name in VARIABLE_COLUMN_MAP.items():
            variable_values = hourly[api_name]
            if len(variable_values) != row_count:
                raise WeatherResponseError(
                    f"{location.name} {api_name} length does not match hourly time."
                )
            values[clean_name] = variable_values
        frames.append(pd.DataFrame(values))

    result = pd.concat(frames, ignore_index=True)
    result["valid_time_local"] = result["valid_time_utc"].dt.tz_convert(LOCAL_TIMEZONE)
    result["forecast_lead_hours"] = (
        result["valid_time_utc"] - result["weather_run_init_utc"]
    ).dt.total_seconds() / 3600
    return result


def select_following_local_day(
    frame: pd.DataFrame,
    run_init: str | pd.Timestamp,
) -> pd.DataFrame:
    """Select the following local day plus its closing interpolation boundary."""
    target_date = intended_target_date(run_init)
    expected_times = expected_following_day_times(target_date)
    selected = frame.loc[frame["valid_time_utc"].isin(expected_times)].copy()
    selected["target_date"] = pd.Timestamp(target_date)
    selected["is_interpolation_boundary"] = selected["valid_time_utc"].eq(
        expected_times[-1]
    )
    return selected
