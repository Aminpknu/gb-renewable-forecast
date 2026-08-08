"""Target transformations for embedded wind and solar generation."""

from __future__ import annotations

import pandas as pd

CAPACITY_FACTOR_INPUTS = {
    "wind_cf": (
        "embedded_wind_generation_mw",
        "embedded_wind_capacity_mw",
    ),
    "solar_cf": (
        "embedded_solar_generation_mw",
        "embedded_solar_capacity_mw",
    ),
}


def add_capacity_factors(frame: pd.DataFrame) -> pd.DataFrame:
    """Calculate observed capacity factors without clipping source observations."""
    required = {
        column
        for generation_and_capacity in CAPACITY_FACTOR_INPUTS.values()
        for column in generation_and_capacity
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Missing capacity-factor input columns: {missing}")

    result = frame.copy()
    for target, (generation, capacity) in CAPACITY_FACTOR_INPUTS.items():
        result[target] = result[generation] / result[capacity]
    return result
