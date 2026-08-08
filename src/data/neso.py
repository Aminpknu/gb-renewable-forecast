"""NESO Historic Demand Data normalization and completeness checks."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from src.data.settlement import expected_period_count

NESO_DATASET_PAGE = "https://www.neso.energy/data-portal/historic-demand-data"
NESO_RESOURCES = {
    2024: {
        "filename": "demanddata_2024.csv",
        "url": "https://api.neso.energy/dataset/8f2fe0af-871c-488d-8bad-960426f24601/resource/f6d02c0f-957b-48cb-82ee-09003f2ba759/download/demanddata_2024.csv",
    },
    2025: {
        "filename": "demanddata_2025.csv",
        "url": "https://api.neso.energy/dataset/8f2fe0af-871c-488d-8bad-960426f24601/resource/b2bde559-3455-4021-b179-dfe60c0337b0/download/demanddata_2025.csv",
    },
    2026: {
        "filename": "demanddataupdate_2026.csv",
        "url": "https://api.neso.energy/dataset/8f2fe0af-871c-488d-8bad-960426f24601/resource/8a4a771c-3929-4e56-93ad-cdf13219dea5/download/demanddataupdate_2026.csv",
    },
}

RAW_TO_CLEAN_COLUMNS = {
    "SETTLEMENT_DATE": "settlement_date",
    "SETTLEMENT_PERIOD": "settlement_period",
    "EMBEDDED_WIND_GENERATION": "embedded_wind_generation_mw",
    "EMBEDDED_WIND_CAPACITY": "embedded_wind_capacity_mw",
    "EMBEDDED_SOLAR_GENERATION": "embedded_solar_generation_mw",
    "EMBEDDED_SOLAR_CAPACITY": "embedded_solar_capacity_mw",
}

CLEAN_REQUIRED_COLUMNS = tuple(RAW_TO_CLEAN_COLUMNS.values())


def validate_required_columns(
    frame: pd.DataFrame, required_columns: Iterable[str]
) -> None:
    """Raise a clear error when a required column is absent."""
    missing = sorted(set(required_columns).difference(frame.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def normalize_neso_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Select and normalize the required NESO target columns."""
    validate_required_columns(frame, RAW_TO_CLEAN_COLUMNS)
    result = frame.loc[:, list(RAW_TO_CLEAN_COLUMNS)].rename(
        columns=RAW_TO_CLEAN_COLUMNS
    )
    raw_dates = result["settlement_date"].astype("string").str.strip()
    iso_dates = raw_dates.str.fullmatch(r"\d{4}-\d{2}-\d{2}", na=False)
    parsed_dates = pd.Series(pd.NaT, index=result.index, dtype="datetime64[ns]")
    parsed_dates.loc[iso_dates] = pd.to_datetime(
        raw_dates.loc[iso_dates], format="%Y-%m-%d", errors="coerce"
    )
    parsed_dates.loc[~iso_dates] = pd.to_datetime(
        raw_dates.loc[~iso_dates], format="%d-%b-%Y", errors="coerce"
    )
    result["settlement_date"] = parsed_dates.dt.normalize()
    for column in CLEAN_REQUIRED_COLUMNS[1:]:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def load_neso_sources(paths: Iterable[Path]) -> pd.DataFrame:
    """Read and concatenate NESO CSV files without modifying the sources."""
    normalized = []
    for path in paths:
        raw = pd.read_csv(path)
        normalized.append(normalize_neso_frame(raw))
    if not normalized:
        raise ValueError("No NESO source files were supplied.")
    return pd.concat(normalized, ignore_index=True)


def month_is_complete(frame: pd.DataFrame, month: pd.Period) -> bool:
    """Return whether every expected settlement key exists exactly once in a month."""
    month_start = month.start_time.normalize()
    month_end = month.end_time.normalize()
    month_rows = frame.loc[frame["settlement_date"].between(month_start, month_end)]
    if month_rows.empty:
        return False
    if month_rows.duplicated(["settlement_date", "settlement_period"]).any():
        return False

    expected_keys: set[tuple[pd.Timestamp, int]] = set()
    for day in pd.date_range(month_start, month_end, freq="D"):
        expected_keys.update(
            (day, period) for period in range(1, expected_period_count(day) + 1)
        )
    actual_keys = {
        (date_value, int(period))
        for date_value, period in month_rows[
            ["settlement_date", "settlement_period"]
        ].itertuples(index=False, name=None)
        if pd.notna(date_value) and pd.notna(period) and float(period).is_integer()
    }
    return actual_keys == expected_keys


def detect_latest_complete_month(frame: pd.DataFrame) -> pd.Period:
    """Identify the latest calendar month with a complete physical period set."""
    valid_dates = frame["settlement_date"].dropna()
    if valid_dates.empty:
        raise ValueError("Cannot detect a complete month without valid settlement dates.")
    candidate_months = sorted(valid_dates.dt.to_period("M").unique(), reverse=True)
    for month in candidate_months:
        if month_is_complete(frame, month):
            return month
    raise ValueError("No complete settlement month was found in the supplied data.")
