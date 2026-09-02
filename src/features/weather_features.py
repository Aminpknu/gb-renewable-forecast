"""Shared leakage-safe weather features for training and live inference."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.data.settlement import construct_settlement_timestamps, expected_period_count
from src.data.weather_config import load_weather_locations
from src.features.spatial_features import build_spatial_weather_features, location_feature_columns

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_METADATA_PATH = PROJECT_ROOT / "models" / "model_metadata.json"
LOCAL_TIMEZONE = "Europe/London"

INTERPOLATION_COLUMNS = [
    "temperature_2m_c",
    "pressure_msl_hpa",
    "wind_speed_100m_ms",
    "cloud_cover_pct",
    "shortwave_radiation_instant_wm2",
    "wind_dir_sin",
    "wind_dir_cos",
]

WIND_FEATURES = [
    "wind_speed_mean",
    "wind_speed_max",
    "wind_speed_std",
    "temperature_mean",
    "temperature_std",
    "pressure_mean",
    "wind_dir_sin_mean",
    "wind_dir_cos_mean",
    "hour_sin",
    "hour_cos",
    "doy_sin",
    "doy_cos",
]

SOLAR_FEATURES = [
    "radiation_mean",
    "radiation_max",
    "radiation_std",
    "cloud_mean",
    "cloud_std",
    "temperature_mean",
    "hour_sin",
    "hour_cos",
    "doy_sin",
    "doy_cos",
]


def load_model_metadata(path: Path = DEFAULT_MODEL_METADATA_PATH) -> dict[str, Any]:
    """Load and minimally validate the production feature-order contract."""
    metadata = json.loads(path.read_text(encoding="utf-8"))
    for model_key in ("wind_model", "solar_model"):
        features = metadata.get(model_key, {}).get("features")
        if not isinstance(features, list) or not features or len(features) != len(set(features)):
            raise ValueError(f"Invalid feature contract for {model_key}.")
    return metadata


def add_wind_direction_components(hourly_weather: pd.DataFrame) -> pd.DataFrame:
    """Convert direction degrees to vector components before interpolation."""
    result = hourly_weather.copy()
    theta = np.deg2rad(result["wind_direction_100m_deg"])
    result["wind_dir_sin"] = np.sin(theta)
    result["wind_dir_cos"] = np.cos(theta)
    return result


def settlement_frame_for_target_date(target_date: str | pd.Timestamp) -> pd.DataFrame:
    """Create every physical GB half-hour period for one local target date."""
    day = pd.Timestamp(target_date).normalize()
    count = expected_period_count(day)
    frame = pd.DataFrame(
        {
            "settlement_date": [day] * count,
            "settlement_period": range(1, count + 1),
        }
    )
    timestamps = construct_settlement_timestamps(
        frame["settlement_date"], frame["settlement_period"]
    )
    if timestamps["impossible_timestamp"].any():
        raise ValueError(f"Could not construct settlement timestamps for {day.date()}.")
    frame["valid_time_local"] = timestamps["valid_time_local"]
    frame["valid_time_utc"] = timestamps["valid_time_utc"]
    return frame


def interpolate_hourly_weather(
    hourly_weather: pd.DataFrame,
    target_settlements: pd.DataFrame,
) -> pd.DataFrame:
    """Interpolate within each location and local target date independently."""
    weather = add_wind_direction_components(hourly_weather)
    required = {"location_name", "target_date", "valid_time_utc", *INTERPOLATION_COLUMNS}
    missing = sorted(required.difference(weather.columns))
    if missing:
        raise ValueError(f"Hourly weather is missing columns: {missing}")

    weather["valid_time_utc"] = pd.to_datetime(weather["valid_time_utc"], utc=True)
    weather["target_date"] = pd.to_datetime(weather["target_date"]).dt.normalize()
    settlements = target_settlements.copy()
    settlements["settlement_date"] = pd.to_datetime(
        settlements["settlement_date"]
    ).dt.normalize()
    settlements["valid_time_utc"] = pd.to_datetime(
        settlements["valid_time_utc"], utc=True
    )

    interpolated_groups: list[pd.DataFrame] = []
    for (location, target_date), group in weather.groupby(
        ["location_name", "target_date"], sort=False
    ):
        target_times = (
            settlements.loc[
                settlements["settlement_date"].eq(target_date), "valid_time_utc"
            ]
            .drop_duplicates()
            .sort_values()
        )
        if target_times.empty:
            continue
        group = (
            group.sort_values("valid_time_utc")
            .drop_duplicates("valid_time_utc")
            .set_index("valid_time_utc")
        )
        combined_index = group.index.union(pd.DatetimeIndex(target_times)).sort_values()
        interpolated = (
            group[INTERPOLATION_COLUMNS]
            .reindex(combined_index)
            .interpolate(method="time")
            .reindex(pd.DatetimeIndex(target_times))
        )
        interpolated["location_name"] = location
        interpolated["target_date"] = target_date
        interpolated["valid_time_utc"] = interpolated.index
        interpolated_groups.append(interpolated.reset_index(drop=True))

    if not interpolated_groups:
        raise ValueError("No hourly weather groups matched the requested target dates.")
    result = pd.concat(interpolated_groups, ignore_index=True)
    if result[INTERPOLATION_COLUMNS].isna().any().any():
        raise ValueError("Interpolation produced missing required weather values.")
    return result


def aggregate_weather_locations(weather_30m: pd.DataFrame) -> pd.DataFrame:
    """Apply the exact Stage 4 ten-location GB aggregation."""
    return (
        weather_30m.groupby("valid_time_utc")
        .agg(
            wind_speed_mean=("wind_speed_100m_ms", "mean"),
            wind_speed_max=("wind_speed_100m_ms", "max"),
            wind_speed_std=("wind_speed_100m_ms", "std"),
            temperature_mean=("temperature_2m_c", "mean"),
            temperature_std=("temperature_2m_c", "std"),
            pressure_mean=("pressure_msl_hpa", "mean"),
            cloud_mean=("cloud_cover_pct", "mean"),
            cloud_std=("cloud_cover_pct", "std"),
            radiation_mean=("shortwave_radiation_instant_wm2", "mean"),
            radiation_max=("shortwave_radiation_instant_wm2", "max"),
            radiation_std=("shortwave_radiation_instant_wm2", "std"),
            wind_dir_sin_mean=("wind_dir_sin", "mean"),
            wind_dir_cos_mean=("wind_dir_cos", "mean"),
        )
        .reset_index()
    )


def add_calendar_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the exact Stage 4 local-time cyclic calendar features."""
    result = frame.copy()
    valid_time_utc = pd.to_datetime(result["valid_time_utc"], utc=True)
    local_time = valid_time_utc.dt.tz_convert(LOCAL_TIMEZONE)
    hour_decimal = local_time.dt.hour + local_time.dt.minute / 60
    day_of_year = local_time.dt.dayofyear
    result["hour_sin"] = np.sin(2 * np.pi * hour_decimal / 24)
    result["hour_cos"] = np.cos(2 * np.pi * hour_decimal / 24)
    result["doy_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    result["doy_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)
    result["month"] = local_time.dt.month
    return result


def build_half_hour_features(
    hourly_weather: pd.DataFrame,
    target_settlements: pd.DataFrame,
    expected_location_count: int = 10,
) -> pd.DataFrame:
    """Build the shared half-hour production feature frame for one target day."""
    interpolated = interpolate_hourly_weather(hourly_weather, target_settlements)
    location_counts = interpolated.groupby("valid_time_utc")["location_name"].nunique()
    if not location_counts.eq(expected_location_count).all():
        raise ValueError(
            "Weather location coverage mismatch: "
            f"expected {expected_location_count}, observed {sorted(location_counts.unique())}."
        )
    if interpolated.duplicated(["location_name", "valid_time_utc"]).any():
        raise ValueError("Duplicate location/valid-time weather rows detected.")
    aggregate = aggregate_weather_locations(interpolated)
    location_names = [location.name for location in load_weather_locations()]
    spatial = build_spatial_weather_features(interpolated, location_names)
    result = target_settlements.merge(
        aggregate, on="valid_time_utc", how="left", validate="one_to_one"
    )
    result = result.merge(spatial, on="valid_time_utc", how="left", validate="one_to_one")
    result = add_calendar_features(result)
    spatial_columns = location_feature_columns(location_names)
    all_features = sorted(
        set(WIND_FEATURES + SOLAR_FEATURES + spatial_columns["wind"] + spatial_columns["solar"])
    )
    if result[all_features].isna().any().any():
        raise ValueError("Feature matrix contains missing values.")
    return result


def ordered_feature_matrix(
    frame: pd.DataFrame,
    metadata: dict[str, Any],
    model_key: str,
) -> pd.DataFrame:
    """Select feature columns in the exact authoritative metadata order."""
    features = metadata[model_key]["features"]
    missing = [feature for feature in features if feature not in frame.columns]
    if missing:
        raise ValueError(f"Missing {model_key} production features: {missing}")
    matrix = frame.loc[:, features]
    if matrix.columns.tolist() != features:
        raise ValueError(f"{model_key} feature order does not match metadata.")
    if matrix.isna().any().any():
        raise ValueError(f"{model_key} feature matrix contains null values.")
    return matrix
