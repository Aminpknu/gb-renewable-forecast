"""Validated, cached local-file loaders for the Dash presentation layer."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LATEST_FORECAST_PATH = PROJECT_ROOT / "outputs" / "forecasts" / "latest_forecast.csv"
FORECAST_SUMMARY_PATH = (
    PROJECT_ROOT / "outputs" / "forecasts" / "latest_forecast_summary.json"
)
FINAL_TEST_PREDICTIONS_PATH = (
    PROJECT_ROOT / "outputs" / "metrics" / "final_test_predictions.csv"
)
DAILY_TEST_METRICS_PATH = PROJECT_ROOT / "outputs" / "metrics" / "daily_test_metrics.csv"
FINAL_TEST_METRICS_PATH = PROJECT_ROOT / "outputs" / "metrics" / "final_test_metrics.csv"
MODEL_METADATA_PATH = PROJECT_ROOT / "models" / "model_metadata.json"

FORECAST_REQUIRED_COLUMNS = {
    "forecast_created_utc",
    "target_date",
    "settlement_period",
    "valid_time_local",
    "valid_time_utc",
    "wind_pred_cf",
    "wind_forecast_mw",
    "wind_capacity_mw",
    "solar_pred_cf",
    "solar_forecast_mw",
    "solar_capacity_mw",
}

HISTORICAL_REQUIRED_COLUMNS = {
    "settlement_date",
    "settlement_period",
    "valid_time_utc",
    "embedded_wind_generation_mw",
    "embedded_solar_generation_mw",
    "wind_pred_mw",
    "solar_pred_mw",
}


class DashboardDataError(RuntimeError):
    """Raised when a dashboard input exists but violates its data contract."""


def _fingerprint(path: Path) -> tuple[str, int, int]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Dashboard input not found: {resolved}")
    stat = resolved.stat()
    return str(resolved), stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=16)
def _read_csv_cached(path_string: str, _mtime_ns: int, _size: int) -> pd.DataFrame:
    return pd.read_csv(path_string)


@lru_cache(maxsize=16)
def _read_json_cached(path_string: str, _mtime_ns: int, _size: int) -> dict[str, Any]:
    with Path(path_string).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise DashboardDataError(f"Expected a JSON object in {path_string}.")
    return payload


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise DashboardDataError(f"{label} is missing required columns: {missing}")


def load_latest_forecast(path: Path | str = LATEST_FORECAST_PATH) -> pd.DataFrame:
    """Load the current Stage 7 forecast with canonical London timestamps."""

    path = Path(path)
    frame = _read_csv_cached(*_fingerprint(path)).copy()
    _require_columns(frame, FORECAST_REQUIRED_COLUMNS, "Latest forecast")
    frame["forecast_created_utc"] = pd.to_datetime(frame["forecast_created_utc"], utc=True)
    frame["valid_time_utc"] = pd.to_datetime(frame["valid_time_utc"], utc=True)
    frame["valid_time_local"] = frame["valid_time_utc"].dt.tz_convert("Europe/London")
    frame["target_date"] = pd.to_datetime(frame["target_date"]).dt.date
    frame = frame.sort_values("valid_time_utc").reset_index(drop=True)
    if frame["settlement_period"].duplicated().any():
        raise DashboardDataError("Latest forecast contains duplicate settlement periods.")
    return frame


def load_forecast_summary(path: Path | str = FORECAST_SUMMARY_PATH) -> dict[str, Any]:
    """Load the Stage 7 forecast summary JSON."""

    return dict(_read_json_cached(*_fingerprint(Path(path))))


def load_historical_predictions(
    path: Path | str = FINAL_TEST_PREDICTIONS_PATH,
) -> pd.DataFrame:
    """Load locked untouched-test predictions for the historical explorer."""

    frame = _read_csv_cached(*_fingerprint(Path(path))).copy()
    _require_columns(frame, HISTORICAL_REQUIRED_COLUMNS, "Historical predictions")
    frame["settlement_date"] = pd.to_datetime(frame["settlement_date"]).dt.date
    frame["valid_time_utc"] = pd.to_datetime(frame["valid_time_utc"], utc=True)
    frame["valid_time_local"] = frame["valid_time_utc"].dt.tz_convert("Europe/London")
    return frame.sort_values("valid_time_utc").reset_index(drop=True)


def load_daily_test_metrics(path: Path | str = DAILY_TEST_METRICS_PATH) -> pd.DataFrame:
    """Load locked daily test-period error summaries."""

    frame = _read_csv_cached(*_fingerprint(Path(path))).copy()
    required = {
        "settlement_date",
        "wind_mae_mw",
        "solar_mae_mw",
        "wind_bias_mw",
        "solar_bias_mw",
    }
    _require_columns(frame, required, "Daily test metrics")
    frame["settlement_date"] = pd.to_datetime(frame["settlement_date"])
    return frame.sort_values("settlement_date").reset_index(drop=True)


def load_final_test_metrics(path: Path | str = FINAL_TEST_METRICS_PATH) -> pd.DataFrame:
    """Load locked aggregate untouched-test metrics."""

    frame = _read_csv_cached(*_fingerprint(Path(path))).copy()
    required = {
        "Technology",
        "Model",
        "MAE_MW",
        "R2",
        "Baseline_MAE_MW",
        "Skill_vs_baseline_pct",
    }
    _require_columns(frame, required, "Final test metrics")
    return frame


def load_model_metadata(path: Path | str = MODEL_METADATA_PATH) -> dict[str, Any]:
    """Load the authoritative production model and locked-metric contract."""

    return dict(_read_json_cached(*_fingerprint(Path(path))))


def available_historical_dates(frame: pd.DataFrame | None = None) -> list[str]:
    """Return only dates that are genuinely present in locked predictions."""

    if frame is None:
        frame = load_historical_predictions()
    values = pd.to_datetime(frame["settlement_date"]).dt.strftime("%Y-%m-%d")
    return sorted(values.unique().tolist())


def clear_loader_caches() -> None:
    """Clear local file caches, primarily for tests and explicit refreshes."""

    _read_csv_cached.cache_clear()
    _read_json_cached.cache_clear()
