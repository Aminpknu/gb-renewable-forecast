"""Tests for deterministic V2 location-resolved weather features."""

import pandas as pd
import pytest

from src.features.spatial_features import (
    build_spatial_weather_features,
    location_feature_columns,
    sanitise_location_name,
)


def test_location_feature_order_and_names() -> None:
    names = ["Inverness", "Edinburgh", "London"]
    columns = location_feature_columns(names)
    assert columns["wind"][:3] == [
        "loc_wind_speed_ms__inverness",
        "loc_wind_speed_ms__edinburgh",
        "loc_wind_speed_ms__london",
    ]
    assert columns["solar"][-3:] == [
        "loc_cloud_pct__inverness",
        "loc_cloud_pct__edinburgh",
        "loc_cloud_pct__london",
    ]
    assert sanitise_location_name("North East") == "north_east"


def test_sanitised_location_collision_is_rejected() -> None:
    with pytest.raises(ValueError, match="collide"):
        location_feature_columns(["A-B", "A B"])


def test_spatial_pivot_preserves_authoritative_location_order() -> None:
    times = pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z"])
    rows = []
    for t in times:
        for name, base in (("North", 1.0), ("South", 2.0)):
            rows.append({"valid_time_utc": t, "location_name": name,
                         "wind_speed_100m_ms": base, "wind_dir_sin": base / 10,
                         "wind_dir_cos": base / 20, "shortwave_radiation_instant_wm2": 100 * base,
                         "cloud_cover_pct": 20 * base})
    result = build_spatial_weather_features(pd.DataFrame(rows), ["North", "South"])
    assert result.columns.tolist()[1:] == location_feature_columns(["North", "South"])["wind"] + location_feature_columns(["North", "South"])["solar"]
    assert result.loc[0, "loc_wind_speed_ms__north"] == 1.0
    assert result.loc[0, "loc_wind_speed_ms__south"] == 2.0
    assert result.loc[0, "loc_radiation_wm2__south"] == 200.0
