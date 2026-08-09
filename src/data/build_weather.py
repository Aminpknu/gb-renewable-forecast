"""Build leakage-safe Stage 3 archived ECMWF IFS HRES weather data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.data.open_meteo import (
    WeatherResponseError,
    cache_path,
    create_retry_session,
    fetch_run,
    parse_multiple_location_response,
    select_following_local_day,
)
from src.data.weather_config import (
    EXPECTED_API_UNITS,
    FORECAST_HOURS,
    HOURLY_VARIABLES,
    LOCAL_TIMEZONE,
    NOMINAL_ISSUE_HOUR_LOCAL,
    OPEN_METEO_SINGLE_RUNS_ENDPOINT,
    RUN_HOUR_UTC,
    VARIABLE_COLUMN_MAP,
    WEATHER_MODEL,
    WEATHER_MODEL_API_IDENTIFIER,
    WEATHER_SOURCE,
    WeatherLocation,
    load_weather_locations,
)
from src.data.weather_validation import build_weather_quality_summary, validate_single_run

TARGET_DATA_PATH = PROJECT_ROOT / "data" / "interim" / "neso_embedded_wind_solar_targets.csv"
RAW_WEATHER_ROOT = PROJECT_ROOT / "data" / "raw" / "weather"
CACHE_DIRECTORY = RAW_WEATHER_ROOT / "ecmwf_ifs_hres"
INTERIM_WEATHER_DIRECTORY = PROJECT_ROOT / "data" / "interim" / "weather"
OUTPUT_WEATHER_PATH = INTERIM_WEATHER_DIRECTORY / "ecmwf_ifs_hres_day_ahead_hourly.csv"
METRICS_DIRECTORY = PROJECT_ROOT / "outputs" / "metrics"
FIGURES_DIRECTORY = PROJECT_ROOT / "outputs" / "figures"
SAMPLE_RUN_INIT = pd.Timestamp("2025-01-15T00:00:00Z")
EXCLUDED_TARGET_DATES_PATH = RAW_WEATHER_ROOT / "excluded_target_dates.json"
MVP_FIRST_TARGET_DATE = pd.Timestamp("2024-04-01")
MVP_LAST_TARGET_DATE = pd.Timestamp("2025-08-31")

OUTPUT_COLUMNS = [
    "location_name",
    "latitude",
    "longitude",
    "api_grid_latitude",
    "api_grid_longitude",
    "api_grid_elevation_m",
    "weather_source",
    "weather_model",
    "weather_model_api_identifier",
    "weather_run_init_utc",
    "nominal_forecast_issue_time_local",
    "target_date",
    "valid_time_utc",
    "valid_time_local",
    "forecast_lead_hours",
    "is_interpolation_boundary",
    *VARIABLE_COLUMN_MAP.values(),
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_cache_metadata(path: Path, attempts: int = 6) -> tuple[int, str]:
    """Read size and hash with retries for transient OneDrive visibility delays."""
    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            return path.stat().st_size, _sha256(path)
        except OSError as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2**attempt))
    assert last_error is not None
    raise last_error


def derive_required_run_dates(target_path: Path = TARGET_DATA_PATH) -> pd.DatetimeIndex:
    """Derive 00 UTC run initializations solely from unique NESO target dates."""
    target_dates = pd.to_datetime(
        pd.read_csv(target_path, usecols=["settlement_date"])["settlement_date"],
        errors="raise",
    ).drop_duplicates()
    run_dates = (target_dates - pd.Timedelta(days=1)).sort_values()
    return pd.DatetimeIndex(run_dates).tz_localize("UTC")


def load_excluded_target_dates() -> list[dict[str, Any]]:
    """Load explicit official-archive exclusions used by the MVP dataset."""
    if not EXCLUDED_TARGET_DATES_PATH.is_file():
        return []
    return json.loads(EXCLUDED_TARGET_DATES_PATH.read_text(encoding="utf-8"))


def derive_mvp_run_dates(
    target_path: Path = TARGET_DATA_PATH,
) -> tuple[pd.DatetimeIndex, list[dict[str, Any]]]:
    """Return all required MVP run dates and their documented exclusions."""
    run_dates = derive_required_run_dates(target_path)
    first_run = (MVP_FIRST_TARGET_DATE - pd.Timedelta(days=1)).tz_localize("UTC")
    last_run = (MVP_LAST_TARGET_DATE - pd.Timedelta(days=1)).tz_localize("UTC")
    selected = run_dates[(run_dates >= first_run) & (run_dates <= last_run)]
    return selected, load_excluded_target_dates()


def filter_excluded_run_dates(
    run_dates: pd.DatetimeIndex,
    exclusions: list[dict[str, Any]],
) -> pd.DatetimeIndex:
    """Remove only explicitly documented unavailable runs from processing."""
    excluded_run_keys = {
        pd.Timestamp(item["required_weather_run_init_utc"]).isoformat()
        for item in exclusions
    }
    return pd.DatetimeIndex(
        [run_init for run_init in run_dates if run_init.isoformat() not in excluded_run_keys]
    )


def validate_mvp_coverage(
    frame: pd.DataFrame,
    exclusions: list[dict[str, Any]],
    locations: tuple[WeatherLocation, ...],
) -> dict[str, Any]:
    """Validate complete MVP target-day coverage except documented source gaps."""
    expected_dates = pd.DatetimeIndex(
        pd.date_range(MVP_FIRST_TARGET_DATE, MVP_LAST_TARGET_DATE, freq="D")
    )
    excluded_dates = pd.DatetimeIndex(
        pd.to_datetime([item["target_date"] for item in exclusions])
    )
    actual_dates = pd.DatetimeIndex(pd.to_datetime(frame["target_date"]).unique()).sort_values()
    unexplained_missing = expected_dates.difference(actual_dates).difference(excluded_dates)
    unexpected_dates = actual_dates.difference(expected_dates)
    excluded_dates_present = actual_dates.intersection(excluded_dates)
    location_counts = frame.groupby("target_date")["location_name"].nunique()
    incomplete_location_dates = location_counts[location_counts.ne(len(locations))]
    boundary_counts = frame.groupby(
        ["weather_run_init_utc", "location_name"]
    )["is_interpolation_boundary"].sum()
    invalid_boundary_groups = int(boundary_counts.ne(1).sum())
    passed = not (
        len(unexplained_missing)
        or len(unexpected_dates)
        or len(excluded_dates_present)
        or len(incomplete_location_dates)
        or invalid_boundary_groups
    )
    return {
        "passed": passed,
        "modelling_period": {
            "first_target_date": MVP_FIRST_TARGET_DATE.date().isoformat(),
            "last_target_date": MVP_LAST_TARGET_DATE.date().isoformat(),
        },
        "expected_target_day_count": len(expected_dates),
        "included_target_day_count": len(actual_dates),
        "excluded_target_dates": [value.date().isoformat() for value in excluded_dates],
        "unexplained_missing_target_dates": [
            value.date().isoformat() for value in unexplained_missing
        ],
        "unexpected_target_dates": [value.date().isoformat() for value in unexpected_dates],
        "excluded_dates_present_in_clean_data": [
            value.date().isoformat() for value in excluded_dates_present
        ],
        "incomplete_location_dates": {
            pd.Timestamp(target_date).date().isoformat(): int(count)
            for target_date, count in incomplete_location_dates.items()
        },
        "invalid_interpolation_boundary_group_count": invalid_boundary_groups,
    }


def _inventory_entry(
    run_init: pd.Timestamp,
    status: str,
    **details: Any,
) -> dict[str, Any]:
    return {
        "run_init_utc": run_init.isoformat(),
        "target_date": (run_init + pd.Timedelta(days=1)).date().isoformat(),
        "status": status,
        **details,
    }


def retrieve_and_validate_run(
    run_init: pd.Timestamp,
    locations: tuple[WeatherLocation, ...],
    session: requests.Session,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fetch, parse, select, and validate one archived run."""
    cached = fetch_run(run_init, locations, CACHE_DIRECTORY, session=session)
    parsed = parse_multiple_location_response(cached.payload, locations, run_init)
    selected = select_following_local_day(parsed, run_init)
    validation = validate_single_run(selected, run_init, locations)
    validation_summary = {
        "passed": validation["passed"],
        "expected_rows_per_location": validation["expected_rows_per_location"],
        "duplicate_count": validation["duplicate_count"],
        "missing_value_count": sum(validation["missing_values"].values()),
        "physical_suspicion_count": sum(
            validation["physical_suspicion_counts"].values()
        ),
        "leakage_violation_count": sum(
            validation["leakage_violation_counts"].values()
        ),
        "incomplete_location_count": len(validation["incomplete_locations"]),
    }
    file_size, file_hash = _stable_cache_metadata(cached.path)
    entry = _inventory_entry(
        run_init,
        "success",
        cache_file=str(cached.path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        cache_reused=cached.reused,
        rate_limit_retries=cached.rate_limit_retries,
        file_size_bytes=file_size,
        sha256=file_hash,
        validation=validation_summary,
    )
    return selected, entry


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, allow_nan=False) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    last_error: OSError | None = None
    for attempt in range(6):
        try:
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(path)
            return
        except OSError as error:
            last_error = error
            try:
                if temporary.exists():
                    temporary.unlink()
            except OSError:
                pass
            if attempt < 5:
                time.sleep(0.5 * (2**attempt))
    assert last_error is not None
    raise last_error


def validate_sample(
    locations: tuple[WeatherLocation, ...],
    session: requests.Session,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """Run the mandatory 2025-01-15 gate before historical retrieval."""
    sample, inventory_entry = retrieve_and_validate_run(
        SAMPLE_RUN_INIT, locations, session
    )
    report = validate_single_run(sample, SAMPLE_RUN_INIT, locations)
    report.update(
        {
            "weather_model": WEATHER_MODEL,
            "weather_model_api_identifier": WEATHER_MODEL_API_IDENTIFIER,
            "request_run": SAMPLE_RUN_INIT.isoformat(),
            "cache_reused": inventory_entry["cache_reused"],
            "cache_file": inventory_entry["cache_file"],
        }
    )
    _write_json(METRICS_DIRECTORY / "weather_sample_validation.json", report)
    if not report["passed"]:
        raise WeatherResponseError(
            "Mandatory archived-run sample validation failed; full download stopped."
        )
    return sample, inventory_entry, report


def download_required_runs(
    run_dates: pd.DatetimeIndex,
    locations: tuple[WeatherLocation, ...],
    max_workers: int = 1,
    cache_only: bool = False,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Retrieve runs serially with cache reuse, throttling, and failure logging."""
    frames: list[pd.DataFrame] = []
    inventory: list[dict[str, Any]] = []
    failure_log = RAW_WEATHER_ROOT / "download_failures.log"
    if max_workers != 1:
        raise ValueError("Archived weather retrieval must remain serial.")

    process_dates: list[pd.Timestamp] = []
    for run_init in run_dates:
        if cache_only and not cache_path(CACHE_DIRECTORY, run_init).is_file():
            inventory.append(
                _inventory_entry(
                    run_init,
                    "missing",
                    error=(
                        "Raw cache absent; not requested in cache-only completion pass "
                        "after sustained Open-Meteo HTTP 429 responses."
                    ),
                )
            )
        else:
            process_dates.append(run_init)
    if cache_only:
        print(
            f"Cache-only pass: cached={len(process_dates)}, "
            f"missing={len(run_dates) - len(process_dates)}",
            flush=True,
        )

    def retrieve(run_init: pd.Timestamp) -> tuple[pd.DataFrame, dict[str, Any]]:
        with create_retry_session() as worker_session:
            result = retrieve_and_validate_run(run_init, locations, worker_session)
            if not result[1]["cache_reused"]:
                time.sleep(0.75)
            return result

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures: dict[Future[tuple[pd.DataFrame, dict[str, Any]]], pd.Timestamp] = {
            executor.submit(retrieve, run_init): run_init for run_init in process_dates
        }
        for position, future in enumerate(as_completed(futures), start=1):
            run_init = futures[future]
            try:
                frame, entry = future.result()
                frames.append(frame)
                inventory.append(entry)
            except (requests.RequestException, WeatherResponseError, ValueError, OSError) as error:
                entry = _inventory_entry(
                    run_init,
                    "failed",
                    error_type=type(error).__name__,
                    error=str(error),
                )
                inventory.append(entry)
                failure_log.parent.mkdir(parents=True, exist_ok=True)
                with failure_log.open("a", encoding="utf-8") as log:
                    log.write(f"{datetime.now(timezone.utc).isoformat()} {entry}\n")
                print(f"FAILED {run_init.isoformat()}: {error}", flush=True)

            if position % 10 == 0 or position == len(process_dates):
                inventory.sort(key=lambda item: item["run_init_utc"])
                successes = sum(item["status"] == "success" for item in inventory)
                failures = len(inventory) - successes
                print(
                    f"Processed {position}/{len(process_dates)} available runs; "
                    f"success={successes}, failed={failures}",
                    flush=True,
                )
                _write_json(RAW_WEATHER_ROOT / "run_inventory.json", inventory)

    if not frames:
        raise RuntimeError("No archived weather runs were successfully processed.")
    result = pd.concat(frames, ignore_index=True)
    location_order = {location.name: index for index, location in enumerate(locations)}
    result["_location_order"] = result["location_name"].map(location_order)
    result = result.sort_values(
        ["weather_run_init_utc", "valid_time_utc", "_location_order"], kind="stable"
    ).drop(columns="_location_order")
    result = result.reset_index(drop=True)
    return result, inventory


def _save_clean_weather(frame: pd.DataFrame) -> None:
    output = frame.loc[:, OUTPUT_COLUMNS].copy()
    output["target_date"] = output["target_date"].dt.strftime("%Y-%m-%d")
    OUTPUT_WEATHER_PATH.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(
        OUTPUT_WEATHER_PATH,
        index=False,
        date_format="%Y-%m-%dT%H:%M:%S%z",
    )


def _save_diagnostic_figures(sample: pd.DataFrame) -> None:
    FIGURES_DIRECTORY.mkdir(parents=True, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")
    for column, title, ylabel, filename in (
        (
            "wind_speed_100m_ms",
            "ECMWF IFS HRES 100 m Wind-Speed Forecasts — 16 January 2025",
            "Wind speed at 100 m (m/s)",
            "weather_sample_wind_speed_100m.png",
        ),
        (
            "shortwave_radiation_wm2",
            "ECMWF IFS HRES Shortwave-Radiation Forecasts — 16 January 2025",
            "Shortwave radiation (W/m²)",
            "weather_sample_shortwave_radiation.png",
        ),
    ):
        figure, axis = plt.subplots(figsize=(11, 5))
        for location_name, rows in sample.groupby("location_name", sort=False):
            axis.plot(rows["valid_time_local"], rows[column], label=location_name)
        axis.set_title(title)
        axis.set_xlabel("Valid time (Europe/London)")
        axis.set_ylabel(ylabel)
        axis.legend(ncol=2, fontsize=8)
        figure.autofmt_xdate()
        figure.tight_layout()
        figure.savefig(FIGURES_DIRECTORY / filename, dpi=140)
        plt.close(figure)


def _write_quality_report(summary: dict[str, Any]) -> None:
    _write_json(METRICS_DIRECTORY / "weather_quality_summary.json", summary)
    lead = summary["forecast_lead_hours"]
    lines = [
        "# Archived weather quality summary",
        "",
        f"- Requested runs: {summary['requested_run_count']}",
        f"- Successful runs: {summary['successful_run_count']}",
        f"- Failed runs: {summary['failed_run_count']}",
        f"- Missing runs: {summary['missing_run_count']}",
        f"- Clean rows: {summary['total_rows']:,}",
        f"- Duplicate records: {summary['duplicate_count']}",
        f"- Incomplete runs: {len(summary['incomplete_following_day_runs'])}",
        f"- Lead hours (min/median/max): {lead['min']}/{lead['median']}/{lead['max']}",
        f"- Leakage violations: {sum(summary['leakage_violation_counts'].values())}",
        "",
        "## Records by representative location",
        "",
    ]
    lines.extend(
        f"- {name}: {count:,}"
        for name, count in summary["record_count_by_location"].items()
    )
    lines.extend(["", "## Missing values", ""])
    lines.extend(
        f"- `{column}`: {count}"
        for column, count in summary["missing_values"].items()
    )
    lines.extend(["", "## Physically suspicious values", ""])
    lines.extend(
        f"- `{check}`: {count}"
        for check, count in summary["physical_suspicion_counts"].items()
    )
    if "mvp_coverage_validation" in summary:
        coverage = summary["mvp_coverage_validation"]
        period = coverage["modelling_period"]
        lines.extend(
            [
                "",
                "## MVP modelling coverage",
                "",
                f"- Period: {period['first_target_date']} to {period['last_target_date']}",
                f"- Calendar target days: {coverage['expected_target_day_count']}",
                f"- Included target days: {coverage['included_target_day_count']}",
                "- Documented official archive exclusions: "
                + ", ".join(coverage["excluded_target_dates"]),
                f"- Unexplained missing target dates: {len(coverage['unexplained_missing_target_dates'])}",
                "- Excluded dates present in clean data: "
                f"{len(coverage['excluded_dates_present_in_clean_data'])}",
            ]
        )
    if summary["failed_or_missing_runs"]:
        lines.extend(["", "## Failed or missing runs", ""])
        status_counts: dict[str, int] = {}
        for item in summary["failed_or_missing_runs"]:
            status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
        lines.extend(
            f"- {status}: {count}" for status, count in sorted(status_counts.items())
        )
        lines.extend(
            [
                "- Full date-level details: `data/raw/weather/run_inventory.json` and `weather_quality_summary.json`.",
                "- Retrieval stopped after sustained HTTP 429 responses; no substitute weather product was used.",
            ]
        )
    (METRICS_DIRECTORY / "weather_quality_summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _write_source_manifest(
    locations: tuple[WeatherLocation, ...],
    run_dates: pd.DatetimeIndex,
    inventory: list[dict[str, Any]],
) -> None:
    payload = {
        "source": WEATHER_SOURCE,
        "endpoint": OPEN_METEO_SINGLE_RUNS_ENDPOINT,
        "weather_model": WEATHER_MODEL,
        "exact_model_api_identifier": WEATHER_MODEL_API_IDENTIFIER,
        "archive_data_access_description": (
            "Individual archived model runs selected by UTC initialization using the "
            "Open-Meteo Single Runs API; not stitched historical weather or reanalysis."
        ),
        "retrieval_date_utc": datetime.now(timezone.utc).isoformat(),
        "variables": list(HOURLY_VARIABLES),
        "units": EXPECTED_API_UNITS,
        "locations": [
            {
                "name": location.name,
                "latitude": location.latitude,
                "longitude": location.longitude,
            }
            for location in locations
        ],
        "location_note": (
            "Fixed representative GB sampling locations; not claimed to be "
            "renewable-capacity-weighted sites."
        ),
        "run_convention": f"daily {RUN_HOUR_UTC:02d}:00 UTC",
        "nominal_project_forecast_issue_time": (
            f"{NOMINAL_ISSUE_HOUR_LOCAL:02d}:00 {LOCAL_TIMEZONE}"
        ),
        "request_template": {
            "models": WEATHER_MODEL_API_IDENTIFIER,
            "run": "{YYYY-MM-DD}T00:00",
            "forecast_hours": FORECAST_HOURS,
            "timezone": "GMT",
            "wind_speed_unit": "ms",
            "temperature_unit": "celsius",
            "hourly": ",".join(HOURLY_VARIABLES),
            "latitude": "comma-separated values from config/weather_locations.json",
            "longitude": "comma-separated values from config/weather_locations.json",
        },
        "requested_run_count": len(run_dates),
        "first_requested_run_utc": run_dates.min().isoformat(),
        "last_requested_run_utc": run_dates.max().isoformat(),
        "successful_run_count": sum(item["status"] == "success" for item in inventory),
        "failed_run_count": sum(item["status"] == "failed" for item in inventory),
        "missing_run_count": sum(item["status"] == "missing" for item in inventory),
        "official_archive_unavailable_count": sum(
            item["status"] == "official_archive_unavailable" for item in inventory
        ),
        "excluded_target_dates_file": "data/raw/weather/excluded_target_dates.json",
        "portfolio_mvp_archive_scope": (
            "Target dates 2024-04-01 through 2025-08-31 only; later archived "
            "forecasts are intentionally not required for the portfolio MVP."
        ),
        "run_inventory_file": "data/raw/weather/run_inventory.json",
    }
    _write_json(RAW_WEATHER_ROOT / "source_manifest.json", payload)


def build_stage_3_weather(
    sample_only: bool = False,
    cache_only: bool = False,
    mvp_only: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any] | None]:
    """Validate the mandatory sample, then build the full archived weather dataset."""
    locations = load_weather_locations()
    METRICS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    session = create_retry_session()
    sample, sample_entry, sample_report = validate_sample(locations, session)
    print("Sample validation passed.", flush=True)
    _save_diagnostic_figures(sample)
    if sample_only:
        return sample, None

    exclusions: list[dict[str, Any]] = []
    all_requested_run_dates = derive_required_run_dates()
    if mvp_only:
        all_requested_run_dates, exclusions = derive_mvp_run_dates()
    run_dates = filter_excluded_run_dates(all_requested_run_dates, exclusions)
    weather, inventory = download_required_runs(
        run_dates, locations, max_workers=1, cache_only=cache_only
    )
    inventory.extend(
        _inventory_entry(
            pd.Timestamp(item["required_weather_run_init_utc"]),
            "official_archive_unavailable",
            error_type="OfficialArchiveUnavailableError",
            error=item["api_error"],
            exclusion=item,
        )
        for item in exclusions
    )
    inventory.sort(key=lambda item: item["run_init_utc"])
    _write_json(RAW_WEATHER_ROOT / "run_inventory.json", inventory)
    summary = build_weather_quality_summary(weather, inventory, locations)
    summary["sample_validation"] = sample_report
    if mvp_only:
        summary["mvp_coverage_validation"] = validate_mvp_coverage(
            weather, exclusions, locations
        )
        if not summary["mvp_coverage_validation"]["passed"]:
            raise WeatherResponseError("MVP coverage validation failed; clean dataset not saved.")
    _save_clean_weather(weather)
    _write_quality_report(summary)
    _write_source_manifest(locations, all_requested_run_dates, inventory)
    return weather, summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-only", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--mvp-only", action="store_true")
    arguments = parser.parse_args()
    weather_data, weather_summary = build_stage_3_weather(
        arguments.sample_only, arguments.cache_only, arguments.mvp_only
    )
    if weather_summary is not None:
        print(f"Clean rows: {len(weather_data)}")
        print("First five cleaned rows:")
        print(weather_data.loc[:, OUTPUT_COLUMNS].head().to_string(index=False))
        print("Last five cleaned rows:")
        print(weather_data.loc[:, OUTPUT_COLUMNS].tail().to_string(index=False))
