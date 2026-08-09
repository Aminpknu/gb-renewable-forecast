"""Quality and leakage checks for archived weather forecast runs."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from src.data.open_meteo import expected_following_day_times, intended_target_date, normalize_run_init
from src.data.weather_config import (
    VARIABLE_COLUMN_MAP,
    WEATHER_MODEL,
    WEATHER_MODEL_API_IDENTIFIER,
    WEATHER_SOURCE,
    WeatherLocation,
)

WEATHER_VALUE_COLUMNS = tuple(VARIABLE_COLUMN_MAP.values())
WEATHER_KEY = ["weather_run_init_utc", "location_name", "valid_time_utc"]
FORBIDDEN_TARGET_COLUMNS = {
    "settlement_date",
    "settlement_period",
    "embedded_wind_generation_mw",
    "embedded_wind_capacity_mw",
    "embedded_solar_generation_mw",
    "embedded_solar_capacity_mw",
    "wind_cf",
    "solar_cf",
}

REQUIRED_WEATHER_COLUMNS = {
    "location_name",
    "latitude",
    "longitude",
    "weather_source",
    "weather_model",
    "weather_model_api_identifier",
    "weather_run_init_utc",
    "nominal_forecast_issue_time_local",
    "valid_time_utc",
    "valid_time_local",
    "forecast_lead_hours",
    "target_date",
    "is_interpolation_boundary",
    *WEATHER_VALUE_COLUMNS,
}


def missing_weather_columns(frame: pd.DataFrame) -> list[str]:
    """Return required clean weather columns absent from a frame."""
    return sorted(REQUIRED_WEATHER_COLUMNS.difference(frame.columns))


def duplicate_weather_mask(frame: pd.DataFrame) -> pd.Series:
    """Mark all duplicated archived-run/location/valid-time records."""
    missing = sorted(set(WEATHER_KEY).difference(frame.columns))
    if missing:
        raise ValueError(f"Cannot detect weather duplicates; missing columns: {missing}")
    return frame.duplicated(WEATHER_KEY, keep=False)


def physical_suspicion_counts(frame: pd.DataFrame) -> dict[str, int]:
    """Flag physically suspicious weather values without altering observations."""
    checks = {
        "temperature_below_minus_60_c": frame["temperature_2m_c"] < -60,
        "temperature_above_60_c": frame["temperature_2m_c"] > 60,
        "pressure_below_850_hpa": frame["pressure_msl_hpa"] < 850,
        "pressure_above_1100_hpa": frame["pressure_msl_hpa"] > 1100,
        "negative_wind_speed": frame["wind_speed_100m_ms"] < 0,
        "wind_speed_above_100_ms": frame["wind_speed_100m_ms"] > 100,
        "wind_direction_below_zero": frame["wind_direction_100m_deg"] < 0,
        "wind_direction_above_360": frame["wind_direction_100m_deg"] > 360,
        "cloud_cover_below_zero": frame["cloud_cover_pct"] < 0,
        "cloud_cover_above_100": frame["cloud_cover_pct"] > 100,
        "negative_shortwave_radiation": frame["shortwave_radiation_wm2"] < 0,
        "shortwave_radiation_above_1500_wm2": frame["shortwave_radiation_wm2"] > 1500,
        "negative_instant_shortwave_radiation": frame[
            "shortwave_radiation_instant_wm2"
        ]
        < 0,
        "instant_shortwave_radiation_above_1500_wm2": frame[
            "shortwave_radiation_instant_wm2"
        ]
        > 1500,
    }
    return {name: int(mask.fillna(False).sum()) for name, mask in checks.items()}


def validate_single_run(
    frame: pd.DataFrame,
    run_init: str | pd.Timestamp,
    locations: tuple[WeatherLocation, ...],
) -> dict[str, Any]:
    """Validate one selected following-day run and return explicit issue counts."""
    missing_columns = missing_weather_columns(frame)
    if missing_columns:
        return {"passed": False, "missing_columns": missing_columns}

    run_timestamp = normalize_run_init(run_init)
    expected_location_names = {location.name for location in locations}
    actual_location_names = set(frame["location_name"].unique())
    expected_times = expected_following_day_times(intended_target_date(run_timestamp))

    missing_locations = sorted(expected_location_names - actual_location_names)
    extra_locations = sorted(actual_location_names - expected_location_names)
    incomplete_locations: dict[str, dict[str, Any]] = {}
    non_monotonic_location_count = 0
    for location in locations:
        location_rows = frame.loc[frame["location_name"].eq(location.name)]
        actual_times = pd.DatetimeIndex(location_rows["valid_time_utc"].dropna().unique())
        missing_times = expected_times.difference(actual_times)
        extra_times = actual_times.difference(expected_times)
        if len(missing_times) or len(extra_times) or len(location_rows) != len(expected_times):
            incomplete_locations[location.name] = {
                "expected_rows": len(expected_times),
                "actual_rows": len(location_rows),
                "missing_valid_times_utc": [value.isoformat() for value in missing_times],
                "extra_valid_times_utc": [value.isoformat() for value in extra_times],
            }
        if not location_rows["valid_time_utc"].is_monotonic_increasing:
            non_monotonic_location_count += 1

    missing_values = {
        column: int(frame[column].isna().sum())
        for column in sorted(REQUIRED_WEATHER_COLUMNS)
    }
    physical_counts = physical_suspicion_counts(frame)
    forbidden_present = sorted(FORBIDDEN_TARGET_COLUMNS.intersection(frame.columns))
    duplicate_count = int(frame.duplicated(WEATHER_KEY).sum())
    leakage_counts = {
        "run_not_before_valid_time": int(
            (frame["weather_run_init_utc"] >= frame["valid_time_utc"]).sum()
        ),
        "wrong_run_initialization": int(
            frame["weather_run_init_utc"].ne(run_timestamp).sum()
        ),
        "wrong_run_cycle_hour": int(
            frame["weather_run_init_utc"].dt.hour.ne(0).sum()
        ),
        "wrong_weather_source": int(frame["weather_source"].ne(WEATHER_SOURCE).sum()),
        "wrong_weather_model": int(frame["weather_model"].ne(WEATHER_MODEL).sum()),
        "wrong_model_api_identifier": int(
            frame["weather_model_api_identifier"].ne(WEATHER_MODEL_API_IDENTIFIER).sum()
        ),
        "forbidden_target_columns_present": len(forbidden_present),
    }

    issue_total = (
        len(missing_locations)
        + len(extra_locations)
        + len(incomplete_locations)
        + non_monotonic_location_count
        + duplicate_count
        + sum(missing_values.values())
        + sum(physical_counts.values())
        + sum(leakage_counts.values())
    )
    return {
        "passed": issue_total == 0,
        "run_init_utc": run_timestamp.isoformat(),
        "target_date": intended_target_date(run_timestamp).isoformat(),
        "expected_locations": len(locations),
        "actual_locations": len(actual_location_names),
        "expected_rows_per_location": len(expected_times),
        "missing_locations": missing_locations,
        "extra_locations": extra_locations,
        "incomplete_locations": incomplete_locations,
        "non_monotonic_location_count": non_monotonic_location_count,
        "duplicate_count": duplicate_count,
        "missing_values": missing_values,
        "physical_suspicion_counts": physical_counts,
        "leakage_violation_counts": leakage_counts,
        "forbidden_target_columns": forbidden_present,
    }


def build_weather_quality_summary(
    frame: pd.DataFrame,
    inventory: list[dict[str, Any]],
    locations: tuple[WeatherLocation, ...],
) -> dict[str, Any]:
    """Summarize complete archive coverage, data quality, and leakage checks."""
    successful = [item for item in inventory if item["status"] == "success"]
    failed = [item for item in inventory if item["status"] == "failed"]
    missing = [item for item in inventory if item["status"] == "missing"]
    requested_runs = [item["run_init_utc"] for item in inventory]
    successful_runs = [item["run_init_utc"] for item in successful]
    failed_runs = [item["run_init_utc"] for item in failed]

    duplicate_count = int(frame.duplicated(WEATHER_KEY).sum())
    missing_values = {
        column: int(frame[column].isna().sum())
        for column in sorted(REQUIRED_WEATHER_COLUMNS)
    }
    leakage_counts = {
        "run_not_before_valid_time": int(
            (frame["weather_run_init_utc"] >= frame["valid_time_utc"]).sum()
        ),
        "wrong_run_cycle_hour": int(frame["weather_run_init_utc"].dt.hour.ne(0).sum()),
        "wrong_weather_source": int(frame["weather_source"].ne(WEATHER_SOURCE).sum()),
        "wrong_weather_model": int(frame["weather_model"].ne(WEATHER_MODEL).sum()),
        "wrong_model_api_identifier": int(
            frame["weather_model_api_identifier"].ne(WEATHER_MODEL_API_IDENTIFIER).sum()
        ),
        "forbidden_target_columns_present": len(
            FORBIDDEN_TARGET_COLUMNS.intersection(frame.columns)
        ),
    }
    lead_times = frame["forecast_lead_hours"]
    record_counts = frame.groupby("location_name").size()
    date_coverage = frame.groupby("location_name")["valid_time_utc"].agg(["min", "max"])
    incomplete_runs = [
        item["run_init_utc"]
        for item in successful
        if not item.get("validation", {}).get("passed", False)
    ]
    expected_locations = {location.name for location in locations}
    missing_locations = sorted(expected_locations - set(record_counts.index))

    return {
        "requested_run_count": len(requested_runs),
        "successful_run_count": len(successful_runs),
        "failed_run_count": len(failed_runs),
        "missing_run_count": len(missing),
        "requested_runs_utc": requested_runs,
        "successful_runs_utc": successful_runs,
        "failed_or_missing_runs": [
            {
                "run_init_utc": item["run_init_utc"],
                "status": item["status"],
                "error": item.get("error"),
            }
            for item in [*failed, *missing]
        ],
        "incomplete_following_day_runs": incomplete_runs,
        "total_rows": int(len(frame)),
        "duplicate_count": duplicate_count,
        "missing_columns": missing_weather_columns(frame),
        "missing_values": missing_values,
        "missing_locations": missing_locations,
        "physical_suspicion_counts": physical_suspicion_counts(frame),
        "leakage_violation_counts": leakage_counts,
        "forecast_lead_hours": {
            "min": float(lead_times.min()),
            "median": float(lead_times.median()),
            "max": float(lead_times.max()),
            "distribution": {
                str(float(value)): int(count)
                for value, count in sorted(Counter(lead_times).items())
            },
        },
        "valid_time_utc_range": {
            "first": frame["valid_time_utc"].min().isoformat(),
            "last": frame["valid_time_utc"].max().isoformat(),
        },
        "record_count_by_location": {
            location: int(count) for location, count in record_counts.items()
        },
        "date_coverage_by_location": {
            location: {
                "first_valid_time_utc": row["min"].isoformat(),
                "last_valid_time_utc": row["max"].isoformat(),
            }
            for location, row in date_coverage.iterrows()
        },
    }
