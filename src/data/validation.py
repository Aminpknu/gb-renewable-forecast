"""Reusable quality checks for historical embedded-generation targets."""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from src.data.neso import CLEAN_REQUIRED_COLUMNS, validate_required_columns
from src.data.settlement import expected_period_count

MARKET_KEY = ["settlement_date", "settlement_period"]
MODEL_COLUMNS = [
    *CLEAN_REQUIRED_COLUMNS,
    "valid_time_local",
    "valid_time_utc",
    "wind_cf",
    "solar_cf",
]


def duplicate_record_mask(frame: pd.DataFrame) -> pd.Series:
    """Mark every row participating in a duplicate canonical market key."""
    validate_required_columns(frame, MARKET_KEY)
    return frame.duplicated(MARKET_KEY, keep=False)


def _numeric_summary(series: pd.Series) -> dict[str, float | int | None]:
    finite = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    description = finite.describe(percentiles=[0.01, 0.25, 0.5, 0.75, 0.99])
    return {
        str(key): None if pd.isna(value) else float(value)
        for key, value in description.items()
    }


def _extreme_observation(frame: pd.DataFrame, column: str, largest: bool) -> dict[str, Any] | None:
    finite = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    if finite.notna().sum() == 0:
        return None
    index = finite.idxmax() if largest else finite.idxmin()
    row = frame.loc[index]
    technology = column.removesuffix("_cf")
    return {
        "settlement_date": pd.Timestamp(row["settlement_date"]).date().isoformat(),
        "settlement_period": int(row["settlement_period"]),
        column: float(row[column]),
        "generation_mw": float(row[f"embedded_{technology}_generation_mw"]),
        "capacity_mw": float(row[f"embedded_{technology}_capacity_mw"]),
    }


def build_quality_summary(frame: pd.DataFrame) -> dict[str, Any]:
    """Run required checks without repairing, clipping, or dropping observations."""
    validate_required_columns(frame, MODEL_COLUMNS)
    duplicate_rows = duplicate_record_mask(frame)
    duplicate_excess = frame.duplicated(MARKET_KEY, keep="first")

    missing_by_day: dict[str, list[int]] = {}
    unexpected_by_day: dict[str, list[int]] = {}
    abnormal_days: set[str] = set()
    period_counts = frame.groupby("settlement_date", dropna=False).size()

    for settlement_date, group in frame.dropna(subset=["settlement_date"]).groupby(
        "settlement_date"
    ):
        date_label = pd.Timestamp(settlement_date).date().isoformat()
        numeric_periods = pd.to_numeric(group["settlement_period"], errors="coerce")
        observed = {
            int(value)
            for value in numeric_periods.dropna()
            if float(value).is_integer()
        }
        expected = set(range(1, expected_period_count(settlement_date) + 1))
        missing = sorted(expected - observed)
        unexpected = sorted(observed - expected)
        if missing:
            missing_by_day[date_label] = missing
        if unexpected:
            unexpected_by_day[date_label] = unexpected
        if missing or unexpected or group.duplicated(MARKET_KEY).any():
            abnormal_days.add(date_label)

    valid_utc = frame["valid_time_utc"].dropna()
    source_differences = valid_utc.diff()
    sorted_unique_differences = valid_utc.sort_values().drop_duplicates().diff().dropna()
    expected_delta = pd.Timedelta(minutes=30)

    missing_values = {
        column: int(frame[column].isna().sum()) for column in MODEL_COLUMNS
    }
    monthly_means = (
        frame.assign(month=frame["settlement_date"].dt.to_period("M").astype(str))
        .groupby("month")[["wind_cf", "solar_cf"]]
        .mean()
    )

    summary: dict[str, Any] = {
        "date_range": {
            "first": frame["settlement_date"].min().date().isoformat(),
            "last": frame["settlement_date"].max().date().isoformat(),
        },
        "total_rows": int(len(frame)),
        "observations_by_year": {
            str(int(year)): int(count)
            for year, count in frame.groupby(frame["settlement_date"].dt.year).size().items()
        },
        "period_count_distribution": {
            str(int(period_count)): int(day_count)
            for period_count, day_count in sorted(Counter(period_counts).items())
        },
        "quality_checks": {
            "duplicate_key_row_count": int(duplicate_rows.sum()),
            "duplicate_record_count": int(duplicate_excess.sum()),
            "days_with_missing_periods": len(missing_by_day),
            "missing_period_count": int(sum(map(len, missing_by_day.values()))),
            "missing_periods_by_day": missing_by_day,
            "unexpected_periods_by_day": unexpected_by_day,
            "abnormal_settlement_day_count": len(abnormal_days),
            "abnormal_settlement_days": sorted(abnormal_days),
            "missing_values": missing_values,
            "negative_wind_generation_count": int(
                (frame["embedded_wind_generation_mw"] < 0).sum()
            ),
            "negative_solar_generation_count": int(
                (frame["embedded_solar_generation_mw"] < 0).sum()
            ),
            "nonpositive_wind_capacity_count": int(
                (frame["embedded_wind_capacity_mw"] <= 0).sum()
            ),
            "nonpositive_solar_capacity_count": int(
                (frame["embedded_solar_capacity_mw"] <= 0).sum()
            ),
            "impossible_timestamp_count": int(frame["impossible_timestamp"].sum()),
            "non_monotonic_utc_timestamp_count": int(
                (source_differences < pd.Timedelta(0)).sum()
            ),
            "unexpected_utc_discontinuity_count": int(
                (sorted_unique_differences != expected_delta).sum()
            ),
            "duplicate_utc_timestamp_count": int(valid_utc.duplicated().sum()),
            "wind_cf_below_zero_count": int((frame["wind_cf"] < 0).sum()),
            "wind_cf_above_one_count": int((frame["wind_cf"] > 1).sum()),
            "solar_cf_below_zero_count": int((frame["solar_cf"] < 0).sum()),
            "solar_cf_above_one_count": int((frame["solar_cf"] > 1).sum()),
        },
        "descriptive_statistics": {
            column: _numeric_summary(frame[column])
            for column in [
                "embedded_wind_generation_mw",
                "embedded_wind_capacity_mw",
                "embedded_solar_generation_mw",
                "embedded_solar_capacity_mw",
                "wind_cf",
                "solar_cf",
            ]
        },
        "capacity_factor_extremes": {
            "wind_smallest": _extreme_observation(frame, "wind_cf", largest=False),
            "wind_largest": _extreme_observation(frame, "wind_cf", largest=True),
            "solar_smallest": _extreme_observation(frame, "solar_cf", largest=False),
            "solar_largest": _extreme_observation(frame, "solar_cf", largest=True),
        },
        "monthly_mean_capacity_factors": {
            month: {
                "wind_cf": float(row["wind_cf"]),
                "solar_cf": float(row["solar_cf"]),
            }
            for month, row in monthly_means.iterrows()
        },
    }
    return summary
