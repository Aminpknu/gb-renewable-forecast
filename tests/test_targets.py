"""Tests for capacity-factor target construction."""

import pandas as pd

from src.features.targets import add_capacity_factors


def test_capacity_factor_calculation_does_not_clip() -> None:
    frame = pd.DataFrame(
        {
            "embedded_wind_generation_mw": [50.0, 120.0],
            "embedded_wind_capacity_mw": [100.0, 100.0],
            "embedded_solar_generation_mw": [0.0, 25.0],
            "embedded_solar_capacity_mw": [100.0, 100.0],
        }
    )
    result = add_capacity_factors(frame)
    assert result["wind_cf"].tolist() == [0.5, 1.2]
    assert result["solar_cf"].tolist() == [0.0, 0.25]
