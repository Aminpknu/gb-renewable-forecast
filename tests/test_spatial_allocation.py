from __future__ import annotations

import pandas as pd

from src.features.spatial_allocation import (
    build_spatial_forecast_allocation,
    load_spatial_capacity_weights,
)


def test_spatial_weights_cover_ten_zones_and_sum_to_one() -> None:
    weights = load_spatial_capacity_weights()
    assert weights["zone"].nunique() == 10
    totals = weights.groupby("technology_group")["proxy_share"].sum()
    assert abs(float(totals["wind"]) - 1.0) < 1e-9
    assert abs(float(totals["solar"]) - 1.0) < 1e-9


def test_spatial_allocation_reconciles_to_national_forecast() -> None:
    weights = load_spatial_capacity_weights()
    zones = weights.loc[weights["technology_group"].eq("wind"), "zone"].tolist()
    times = pd.date_range("2026-09-03T00:00:00Z", periods=2, freq="30min")
    rows = []
    for t in times:
        for i, zone in enumerate(zones):
            rows.append({
                "valid_time_utc": t, "location_name": zone,
                "wind_speed_100m_ms": 5.0 + i,
                "shortwave_radiation_instant_wm2": 100.0 + 10 * i,
            })
    weather = pd.DataFrame(rows)
    national = pd.DataFrame({
        "target_date": ["2026-09-03"] * 2,
        "settlement_period": [1, 2],
        "valid_time_local": times.tz_convert("Europe/London"),
        "valid_time_utc": times,
        "wind_forecast_mw": [1000.0, 1200.0],
        "solar_forecast_mw": [500.0, 600.0],
        "wind_capacity_mw": [6000.0, 6000.0],
        "solar_capacity_mw": [24000.0, 24000.0],
    })
    result = build_spatial_forecast_allocation(weather, national, weights)
    assert len(result) == 20
    grouped = result.groupby("settlement_period").agg(
        wind=("zone_wind_forecast_mw", "sum"),
        solar=("zone_solar_forecast_mw", "sum"),
    )
    assert grouped["wind"].round(6).tolist() == [1000.0, 1200.0]
    assert grouped["solar"].round(6).tolist() == [500.0, 600.0]
    assert result.groupby("settlement_period")["zone"].nunique().tolist() == [10, 10]
