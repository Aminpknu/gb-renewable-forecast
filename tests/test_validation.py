"""Tests for required columns and duplicate reporting."""

import pandas as pd
import pytest

from src.data.neso import normalize_neso_frame, validate_required_columns
from src.data.validation import duplicate_record_mask


def test_duplicate_detection_marks_all_rows_in_duplicate_key() -> None:
    frame = pd.DataFrame(
        {
            "settlement_date": pd.to_datetime(["2024-01-01"] * 3),
            "settlement_period": [1, 1, 2],
        }
    )
    assert duplicate_record_mask(frame).tolist() == [True, True, False]


def test_required_column_validation_reports_missing_columns() -> None:
    frame = pd.DataFrame({"settlement_date": ["2024-01-01"]})
    with pytest.raises(ValueError, match="settlement_period"):
        validate_required_columns(frame, ["settlement_date", "settlement_period"])


def test_neso_mixed_source_date_formats_are_unambiguous() -> None:
    frame = pd.DataFrame(
        {
            "SETTLEMENT_DATE": ["02-JAN-2024", "2026-01-02"],
            "SETTLEMENT_PERIOD": [1, 1],
            "EMBEDDED_WIND_GENERATION": [1, 1],
            "EMBEDDED_WIND_CAPACITY": [2, 2],
            "EMBEDDED_SOLAR_GENERATION": [1, 1],
            "EMBEDDED_SOLAR_CAPACITY": [2, 2],
        }
    )
    normalized = normalize_neso_frame(frame)
    assert normalized["settlement_date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2024-01-02",
        "2026-01-02",
    ]
