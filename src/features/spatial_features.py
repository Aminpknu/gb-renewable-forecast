"""Deterministic location-resolved weather features for V2 forecasting."""

from __future__ import annotations

import re
import pandas as pd

WIND_LOCATION_VARIABLES = {
    "wind_speed_100m_ms": "loc_wind_speed_ms",
    "wind_dir_sin": "loc_wind_dir_sin",
    "wind_dir_cos": "loc_wind_dir_cos",
}
SOLAR_LOCATION_VARIABLES = {
    "shortwave_radiation_instant_wm2": "loc_radiation_wm2",
    "cloud_cover_pct": "loc_cloud_pct",
}


def sanitise_location_name(name: str) -> str:
    """Return a stable lowercase identifier suitable for feature columns."""
    value = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    if not value:
        raise ValueError(f"Location name cannot be sanitised: {name!r}")
    return value


def location_feature_columns(location_names: list[str] | tuple[str, ...]) -> dict[str, list[str]]:
    """Return the authoritative V2 wind and solar location feature order."""
    slugs = [sanitise_location_name(name) for name in location_names]
    if len(slugs) != len(set(slugs)):
        raise ValueError("Sanitised weather-location names collide.")
    wind = [f"{prefix}__{slug}" for prefix in WIND_LOCATION_VARIABLES.values() for slug in slugs]
    solar = [f"{prefix}__{slug}" for prefix in SOLAR_LOCATION_VARIABLES.values() for slug in slugs]
    return {"wind": wind, "solar": solar}

def build_spatial_weather_features(
    weather_30m: pd.DataFrame,
    location_names: list[str] | tuple[str, ...],
) -> pd.DataFrame:
    """Pivot half-hour location weather into one deterministic row per UTC valid time."""
    required = {"valid_time_utc", "location_name", *WIND_LOCATION_VARIABLES, *SOLAR_LOCATION_VARIABLES}
    missing = sorted(required.difference(weather_30m.columns))
    if missing:
        raise ValueError(f"Spatial weather input is missing columns: {missing}")
    ordered_names = list(location_names)
    if set(weather_30m["location_name"].unique()) != set(ordered_names):
        raise ValueError("Weather locations do not match the authoritative location configuration.")
    if weather_30m.duplicated(["valid_time_utc", "location_name"]).any():
        raise ValueError("Duplicate location/valid-time rows detected before spatial pivot.")
    slugs = {name: sanitise_location_name(name) for name in ordered_names}
    result = weather_30m[["valid_time_utc"]].drop_duplicates().sort_values("valid_time_utc").reset_index(drop=True)
    for source, prefix in {**WIND_LOCATION_VARIABLES, **SOLAR_LOCATION_VARIABLES}.items():
        wide = weather_30m.pivot(index="valid_time_utc", columns="location_name", values=source)
        wide = wide.reindex(columns=ordered_names)
        if wide.isna().any().any():
            raise ValueError(f"Spatial pivot produced missing values for {source}.")
        wide.columns = [f"{prefix}__{slugs[name]}" for name in ordered_names]
        result = result.merge(wide.reset_index(), on="valid_time_utc", how="left", validate="one_to_one")
    expected = location_feature_columns(ordered_names)
    required_features = expected["wind"] + expected["solar"]
    if result[required_features].isna().any().any():
        raise ValueError("Spatial feature frame contains missing values.")
    return result