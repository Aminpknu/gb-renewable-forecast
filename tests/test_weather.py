"""Tests for archived Open-Meteo forecast ingestion and leakage controls."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import datetime, timezone

import pandas as pd
import pytest

from src.data.build_weather import (
    derive_mvp_run_dates,
    filter_excluded_run_dates,
)
from src.data.open_meteo import (
    RateLimitError,
    WeatherResponseError,
    expected_following_day_times,
    fetch_run,
    nominal_issue_time,
    normalize_run_init,
    parse_multiple_location_response,
    rate_limit_wait_seconds,
    retry_after_seconds,
    select_following_local_day,
)
from src.data.weather_config import (
    EXPECTED_API_UNITS,
    HOURLY_VARIABLES,
    WEATHER_MODEL_API_IDENTIFIER,
    WeatherLocation,
    load_weather_locations,
)
from src.data.weather_validation import duplicate_weather_mask, validate_single_run


@pytest.fixture
def two_locations() -> tuple[WeatherLocation, ...]:
    return (
        WeatherLocation("North", 57.0, -4.0),
        WeatherLocation("South", 51.5, -0.1),
    )


def _location_payload(latitude: float, longitude: float) -> dict[str, Any]:
    times = pd.date_range("2025-01-15T00:00:00Z", periods=49, freq="h")
    hourly: dict[str, Any] = {"time": times.strftime("%Y-%m-%dT%H:%M").tolist()}
    for variable in HOURLY_VARIABLES:
        if variable == "temperature_2m":
            hourly[variable] = [5.0] * len(times)
        elif variable == "pressure_msl":
            hourly[variable] = [1010.0] * len(times)
        elif variable == "wind_speed_100m":
            hourly[variable] = [8.0] * len(times)
        elif variable == "wind_direction_100m":
            hourly[variable] = [240.0] * len(times)
        elif variable == "cloud_cover":
            hourly[variable] = [60.0] * len(times)
        else:
            hourly[variable] = [0.0] * len(times)
    return {
        "latitude": latitude,
        "longitude": longitude,
        "elevation": 50.0,
        "hourly_units": {"time": "iso8601", **EXPECTED_API_UNITS},
        "hourly": hourly,
    }


@pytest.fixture
def multiple_location_payload(
    two_locations: tuple[WeatherLocation, ...],
) -> list[dict[str, Any]]:
    return [
        _location_payload(location.latitude, location.longitude)
        for location in two_locations
    ]


def test_weather_location_configuration_loads_ten_unique_sites() -> None:
    locations = load_weather_locations()
    assert len(locations) == 10
    assert len({location.name for location in locations}) == 10
    assert locations[0].name == "Inverness"


def test_multiple_location_response_and_valid_times_parse(
    multiple_location_payload: list[dict[str, Any]],
    two_locations: tuple[WeatherLocation, ...],
) -> None:
    frame = parse_multiple_location_response(
        multiple_location_payload, two_locations, "2025-01-15T00:00:00Z"
    )
    assert len(frame) == 98
    assert set(frame["location_name"]) == {"North", "South"}
    assert str(frame["valid_time_utc"].dtype) == "datetime64[us, UTC]"
    assert frame["valid_time_utc"].min() == pd.Timestamp("2025-01-15T00:00:00Z")
    assert frame["valid_time_utc"].max() == pd.Timestamp("2025-01-17T00:00:00Z")


def test_run_initialization_and_nominal_issue_time_are_distinct() -> None:
    run = normalize_run_init("2025-07-15T00:00:00Z")
    issue = nominal_issue_time(run)
    assert run == pd.Timestamp("2025-07-15T00:00:00Z")
    assert issue.isoformat() == "2025-07-15T09:00:00+01:00"
    assert issue.tz_convert("UTC") == pd.Timestamp("2025-07-15T08:00:00Z")


def test_nominal_issue_time_remains_09_local_on_spring_transition() -> None:
    issue = nominal_issue_time("2024-03-31T00:00:00Z")
    assert issue.isoformat() == "2024-03-31T09:00:00+01:00"
    assert issue.tz_convert("UTC") == pd.Timestamp("2024-03-31T08:00:00Z")


def test_following_day_selection_and_lead_time(
    multiple_location_payload: list[dict[str, Any]],
    two_locations: tuple[WeatherLocation, ...],
) -> None:
    parsed = parse_multiple_location_response(
        multiple_location_payload, two_locations, "2025-01-15T00:00:00Z"
    )
    selected = select_following_local_day(parsed, "2025-01-15T00:00:00Z")
    assert len(selected) == 50
    assert selected["target_date"].dt.strftime("%Y-%m-%d").unique().tolist() == [
        "2025-01-16"
    ]
    assert selected["forecast_lead_hours"].min() == 24
    assert selected["forecast_lead_hours"].max() == 48
    assert selected.groupby("location_name")["is_interpolation_boundary"].sum().eq(1).all()


def test_leakage_validation_passes_for_archived_following_day_forecast(
    multiple_location_payload: list[dict[str, Any]],
    two_locations: tuple[WeatherLocation, ...],
) -> None:
    parsed = parse_multiple_location_response(
        multiple_location_payload, two_locations, "2025-01-15T00:00:00Z"
    )
    selected = select_following_local_day(parsed, "2025-01-15T00:00:00Z")
    report = validate_single_run(selected, "2025-01-15T00:00:00Z", two_locations)
    assert report["passed"]
    assert sum(report["leakage_violation_counts"].values()) == 0


def test_missing_api_variable_is_detected(
    multiple_location_payload: list[dict[str, Any]],
    two_locations: tuple[WeatherLocation, ...],
) -> None:
    del multiple_location_payload[0]["hourly"]["pressure_msl"]
    with pytest.raises(WeatherResponseError, match="pressure_msl"):
        parse_multiple_location_response(
            multiple_location_payload, two_locations, "2025-01-15T00:00:00Z"
        )


def test_weather_duplicate_detection(
    multiple_location_payload: list[dict[str, Any]],
    two_locations: tuple[WeatherLocation, ...],
) -> None:
    parsed = parse_multiple_location_response(
        multiple_location_payload, two_locations, "2025-01-15T00:00:00Z"
    )
    duplicated = pd.concat([parsed.iloc[[0]], parsed.iloc[[0]], parsed.iloc[[1]]])
    assert duplicate_weather_mask(duplicated).tolist() == [True, True, False]


def test_spring_dst_target_day_has_24_hour_boundaries() -> None:
    times = expected_following_day_times("2025-03-30")
    assert len(times) == 24
    assert times[0] == pd.Timestamp("2025-03-30T00:00:00Z")
    assert times[-1] == pd.Timestamp("2025-03-30T23:00:00Z")
    local = times.tz_convert("Europe/London")
    assert not local.hour.tolist().count(1)


def test_autumn_dst_target_day_has_26_hour_boundaries() -> None:
    times = expected_following_day_times("2025-10-26")
    assert len(times) == 26
    assert times[0] == pd.Timestamp("2025-10-25T23:00:00Z")
    assert times[-1] == pd.Timestamp("2025-10-27T00:00:00Z")
    local_labels = times.tz_convert("Europe/London").strftime("%Y-%m-%d %H:%M")
    assert (local_labels == "2025-10-26 01:00").sum() == 2


def test_cached_run_is_reused_without_http_call(
    monkeypatch: pytest.MonkeyPatch,
    multiple_location_payload: list[dict[str, Any]],
    two_locations: tuple[WeatherLocation, ...],
) -> None:
    monkeypatch.setattr(Path, "is_file", lambda _path: True)
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda _path, **_kwargs: __import__("json").dumps(multiple_location_payload),
    )

    class NoNetworkSession:
        def get(self, *_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("HTTP must not be called for an existing cache file")

    cached = fetch_run(
        "2025-01-15T00:00:00Z",
        two_locations,
        Path("unused-cache"),
        session=NoNetworkSession(),  # type: ignore[arg-type]
    )
    assert cached.reused
    assert cached.payload == multiple_location_payload
    assert WEATHER_MODEL_API_IDENTIFIER == "ecmwf_ifs"


def test_retry_after_and_exponential_backoff_are_explicit() -> None:
    now = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
    assert retry_after_seconds("120", now=now) == 120
    assert retry_after_seconds("Wed, 15 Jan 2025 12:02:00 GMT", now=now) == 120
    assert rate_limit_wait_seconds(None, attempt=2, jitter_seconds=1.0) == 61.0
    assert rate_limit_wait_seconds("30", attempt=4, jitter_seconds=1.0) == 31.0


def test_http_429_is_retried_once_then_cached(
    monkeypatch: pytest.MonkeyPatch,
    multiple_location_payload: list[dict[str, Any]],
    two_locations: tuple[WeatherLocation, ...],
) -> None:
    import json
    import src.data.open_meteo as open_meteo

    output = Path("not-present-weather-cache.json")
    monkeypatch.setattr(open_meteo, "cache_path", lambda *_args: output)
    monkeypatch.setattr(Path, "is_file", lambda _path: False)
    monkeypatch.setattr(Path, "mkdir", lambda _path, **_kwargs: None)
    monkeypatch.setattr(open_meteo, "_write_raw_cache", lambda *_args: None)
    monkeypatch.setattr(open_meteo.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(open_meteo.random, "uniform", lambda *_args: 1.0)

    class Response:
        def __init__(self, status_code: int, payload: Any = None) -> None:
            self.status_code = status_code
            self.headers = {}
            self._payload = payload
            self.content = json.dumps(payload).encode("utf-8") if payload is not None else b"{}"

        def json(self) -> Any:
            return self._payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise AssertionError("Only the final success response should be raised.")

    class Session:
        def __init__(self) -> None:
            self.responses = [Response(429), Response(200, multiple_location_payload)]

        def get(self, *_args: Any, **_kwargs: Any) -> Response:
            return self.responses.pop(0)

    cached = fetch_run(
        "2025-01-15T00:00:00Z",
        two_locations,
        Path("unused"),
        session=Session(),  # type: ignore[arg-type]
    )
    assert not cached.reused
    assert cached.rate_limit_retries == 1


def test_sustained_http_429_raises_rate_limit_error(
    monkeypatch: pytest.MonkeyPatch,
    two_locations: tuple[WeatherLocation, ...],
) -> None:
    import src.data.open_meteo as open_meteo

    monkeypatch.setattr(open_meteo, "cache_path", lambda *_args: Path("not-present.json"))
    monkeypatch.setattr(Path, "is_file", lambda _path: False)
    monkeypatch.setattr(Path, "mkdir", lambda _path, **_kwargs: None)

    class Response:
        status_code = 429
        headers: dict[str, str] = {}

    class Session:
        def get(self, *_args: Any, **_kwargs: Any) -> Response:
            return Response()

    with pytest.raises(RateLimitError, match="Sustained"):
        fetch_run(
            "2025-01-15T00:00:00Z",
            two_locations,
            Path("unused"),
            session=Session(),  # type: ignore[arg-type]
            max_rate_limit_retries=0,
        )


def test_official_archive_exclusion_is_listed_and_not_processed(
    tmp_path: Path,
) -> None:
    target_path = tmp_path / "mvp_target_dates.csv"
    pd.DataFrame(
        {
            "settlement_date": pd.date_range(
                "2024-04-01", "2025-08-31", freq="D"
            )
        }
    ).to_csv(target_path, index=False)

    all_mvp_runs, exclusions = derive_mvp_run_dates(target_path)
    available_runs = filter_excluded_run_dates(all_mvp_runs, exclusions)
    excluded_target_dates = {item["target_date"] for item in exclusions}
    excluded_run_dates = {
        pd.Timestamp(item["required_weather_run_init_utc"]) for item in exclusions
    }

    assert len(all_mvp_runs) == 518
    assert len(available_runs) == 513
    assert excluded_target_dates == {
        "2025-08-06",
        "2025-08-07",
        "2025-08-08",
        "2025-08-09",
        "2025-08-10",
    }
    assert excluded_run_dates == set(
        pd.date_range("2025-08-05T00:00:00Z", "2025-08-09T00:00:00Z", freq="D")
    )
    assert pd.Timestamp("2025-08-05T00:00:00Z") not in available_runs
    included_target_dates = set((available_runs + pd.Timedelta(days=1)).date)
    assert pd.Timestamp("2025-08-06").date() not in included_target_dates
