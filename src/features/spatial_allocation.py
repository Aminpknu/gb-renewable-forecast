"""Reconcile national V2 renewable forecasts into ten indicative spatial zones."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WEIGHTS_PATH = PROJECT_ROOT / "config" / "spatial_capacity_weights.csv"


def load_spatial_capacity_weights(path: Path = DEFAULT_WEIGHTS_PATH) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"technology_group", "zone", "proxy_capacity_mw", "project_count", "proxy_share"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Spatial capacity weights are missing columns: {missing}")
    for technology in ("wind", "solar"):
        selected = frame.loc[frame["technology_group"].eq(technology)]
        if len(selected) != 10 or not np.isclose(selected["proxy_share"].sum(), 1.0, atol=1e-9):
            raise ValueError(f"Spatial {technology} weights must contain ten zones summing to one.")
    return frame


def _normalised_signal(weather: pd.DataFrame, weights: pd.DataFrame, technology: str) -> pd.DataFrame:
    selected = weights.loc[weights["technology_group"].eq(technology), ["zone", "proxy_share"]].copy()
    frame = weather.merge(selected, left_on="location_name", right_on="zone", how="left", validate="many_to_one")
    if frame["proxy_share"].isna().any():
        raise ValueError("Weather locations do not match spatial capacity-weight zones.")
    if technology == "wind":
        signal = np.maximum(pd.to_numeric(frame["wind_speed_100m_ms"], errors="raise").to_numpy(float), 0.0) ** 3
    else:
        signal = np.maximum(pd.to_numeric(frame["shortwave_radiation_instant_wm2"], errors="raise").to_numpy(float), 0.0)
    frame["raw_signal"] = frame["proxy_share"].to_numpy(float) * signal
    group_total = frame.groupby("valid_time_utc")["raw_signal"].transform("sum")
    fallback = frame["proxy_share"] / frame.groupby("valid_time_utc")["proxy_share"].transform("sum")
    frame["allocation_share"] = np.where(group_total.gt(1e-12), frame["raw_signal"] / group_total, fallback)
    return frame[["valid_time_utc", "zone", "allocation_share"]]


def build_spatial_forecast_allocation(
    weather_30m: pd.DataFrame,
    national_forecast: pd.DataFrame,
    weights: pd.DataFrame | None = None,
) -> pd.DataFrame:
    weights = load_spatial_capacity_weights() if weights is None else weights.copy()
    required_weather = {"valid_time_utc", "location_name", "wind_speed_100m_ms", "shortwave_radiation_instant_wm2"}
    missing = sorted(required_weather.difference(weather_30m.columns))
    if missing:
        raise ValueError(f"Spatial allocation weather is missing columns: {missing}")
    weather = weather_30m.copy()
    weather["valid_time_utc"] = pd.to_datetime(weather["valid_time_utc"], utc=True)
    if weather.duplicated(["valid_time_utc", "location_name"]).any():
        raise ValueError("Duplicate location/time rows in spatial allocation weather.")
    wind = _normalised_signal(weather, weights, "wind").rename(
        columns={"allocation_share": "wind_share"}
    )
    solar = _normalised_signal(weather, weights, "solar").rename(
        columns={"allocation_share": "solar_share"}
    )
    result = wind.merge(
        solar, on=["valid_time_utc", "zone"], how="inner", validate="one_to_one"
    )
    national = national_forecast.copy()
    national["valid_time_utc"] = pd.to_datetime(national["valid_time_utc"], utc=True)
    keep = [
        "target_date", "settlement_period", "valid_time_local", "valid_time_utc",
        "wind_forecast_mw", "solar_forecast_mw", "wind_capacity_mw", "solar_capacity_mw",
    ]
    result = result.merge(
        national[keep], on="valid_time_utc", how="left", validate="many_to_one"
    )
    if result[["settlement_period", "wind_forecast_mw", "solar_forecast_mw"]].isna().any().any():
        raise ValueError("Spatial allocation could not align all national forecast periods.")

    wind_proxy = weights.loc[
        weights["technology_group"].eq("wind"), ["zone", "proxy_share"]
    ].rename(columns={"proxy_share": "wind_capacity_proxy_share"})
    solar_proxy = weights.loc[
        weights["technology_group"].eq("solar"), ["zone", "proxy_share"]
    ].rename(columns={"proxy_share": "solar_capacity_proxy_share"})
    result = result.merge(wind_proxy, on="zone", validate="many_to_one")
    result = result.merge(solar_proxy, on="zone", validate="many_to_one")
    result["zone_wind_forecast_mw"] = result["wind_share"] * result["wind_forecast_mw"]
    result["zone_solar_forecast_mw"] = result["solar_share"] * result["solar_forecast_mw"]
    result["zone_wind_capacity_proxy_mw"] = (
        result["wind_capacity_proxy_share"] * result["wind_capacity_mw"]
    )
    result["zone_solar_capacity_proxy_mw"] = (
        result["solar_capacity_proxy_share"] * result["solar_capacity_mw"]
    )
    result["zone_total_forecast_mw"] = (
        result["zone_wind_forecast_mw"] + result["zone_solar_forecast_mw"]
    )
    result["zone_total_capacity_proxy_mw"] = (
        result["zone_wind_capacity_proxy_mw"] + result["zone_solar_capacity_proxy_mw"]
    )

    check = result.groupby("valid_time_utc", as_index=False).agg(
        allocated_wind_mw=("zone_wind_forecast_mw", "sum"),
        allocated_solar_mw=("zone_solar_forecast_mw", "sum"),
        national_wind_mw=("wind_forecast_mw", "first"),
        national_solar_mw=("solar_forecast_mw", "first"),
    )
    if not np.allclose(check["allocated_wind_mw"], check["national_wind_mw"], atol=1e-6):
        raise AssertionError("Spatial wind allocation does not reconcile to the national forecast.")
    if not np.allclose(check["allocated_solar_mw"], check["national_solar_mw"], atol=1e-6):
        raise AssertionError("Spatial solar allocation does not reconcile to the national forecast.")
    columns = [
        "target_date", "settlement_period", "valid_time_local", "valid_time_utc", "zone",
        "wind_share", "solar_share", "zone_wind_forecast_mw", "zone_solar_forecast_mw",
        "zone_total_forecast_mw", "zone_wind_capacity_proxy_mw", "zone_solar_capacity_proxy_mw",
        "zone_total_capacity_proxy_mw", "wind_capacity_proxy_share", "solar_capacity_proxy_share",
    ]
    return result[columns].sort_values(["settlement_period", "zone"]).reset_index(drop=True)
