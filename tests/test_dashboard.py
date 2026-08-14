"""Offline tests for the Stage 8 Dash presentation layer."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import joblib
import pandas as pd
import pytest
import requests

from app_utils.data_loading import (
    available_historical_dates,
    clear_loader_caches,
    load_forecast_summary,
    load_historical_predictions,
    load_latest_forecast,
)


def _text_content(component) -> str:
    if component is None:
        return ""
    if isinstance(component, (str, int, float)):
        return str(component)
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        return " ".join(_text_content(child) for child in children)
    return _text_content(children)


def test_00_app_import_and_page_layouts_do_not_call_apis_or_load_models(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Dashboard import/navigation attempted external or model access.")

    monkeypatch.setattr(requests, "get", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(joblib, "load", forbidden)

    application = importlib.import_module("app")
    import dash

    pages = {entry["path"]: entry for entry in dash.page_registry.values()}
    assert set(pages) == {"/", "/performance", "/history", "/scenarios", "/methodology"}
    for page in pages.values():
        layout = page["layout"]
        rendered = layout() if callable(layout) else layout
        assert rendered is not None
    assert application.server is application.app.server


def test_latest_forecast_loader_parses_timestamps(tmp_path: Path):
    path = tmp_path / "forecast.csv"
    frame = pd.DataFrame(
        {
            "forecast_created_utc": [
                "2025-10-25T09:00:00+0000",
                "2025-10-25T09:00:00+0000",
            ],
            "target_date": ["2025-10-26", "2025-10-26"],
            "settlement_period": [1, 2],
            "valid_time_local": [
                "2025-10-26T00:00:00+0100",
                "2025-10-26T00:30:00+0100",
            ],
            "valid_time_utc": [
                "2025-10-25T23:00:00+0000",
                "2025-10-25T23:30:00+0000",
            ],
            "wind_pred_cf": [0.2, 0.3],
            "wind_forecast_mw": [100.0, 150.0],
            "wind_capacity_mw": [500.0, 500.0],
            "solar_pred_cf": [0.0, 0.0],
            "solar_forecast_mw": [0.0, 0.0],
            "solar_capacity_mw": [1_000.0, 1_000.0],
        }
    )
    frame.to_csv(path, index=False)
    clear_loader_caches()
    loaded = load_latest_forecast(path)
    assert len(loaded) == 2
    assert str(loaded["valid_time_utc"].dtype) == "datetime64[us, UTC]"
    assert str(loaded["valid_time_local"].dt.tz) == "Europe/London"


def test_forecast_summary_loader(tmp_path: Path):
    path = tmp_path / "summary.json"
    expected = {"target_date": "2026-08-10", "settlement_period_count": 48}
    path.write_text(json.dumps(expected), encoding="utf-8")
    clear_loader_caches()
    assert load_forecast_summary(path) == expected


def test_historical_predictions_loader_and_real_date_selector():
    predictions = load_historical_predictions()
    dates = available_historical_dates(predictions)
    assert dates[0] == "2025-06-01"
    assert dates[-1] == "2025-08-31"
    assert len(dates) == 87
    assert not {
        "2025-08-06",
        "2025-08-07",
        "2025-08-08",
        "2025-08-09",
        "2025-08-10",
    }.intersection(dates)


def test_missing_forecast_produces_graceful_empty_state(tmp_path: Path):
    from pages.forecast import build_forecast_content

    rendered = build_forecast_content(
        tmp_path / "missing.csv", tmp_path / "missing-summary.json"
    )
    text = _text_content(rendered)
    assert "Forecast output unavailable" in text
    assert "python -m src.forecast_tomorrow" in text


@pytest.mark.parametrize("row_count", [46, 48, 50])
def test_forecast_table_supports_dst_day_lengths(row_count: int):
    from pages.forecast import forecast_table_frame

    timestamps = pd.date_range("2025-01-01", periods=row_count, freq="30min", tz="UTC")
    frame = pd.DataFrame(
        {
            "valid_time_local": timestamps.tz_convert("Europe/London"),
            "settlement_period": range(1, row_count + 1),
            "wind_forecast_mw": 100.0,
            "wind_pred_cf": 0.2,
            "solar_forecast_mw": 50.0,
            "solar_pred_cf": 0.1,
        }
    )
    assert len(forecast_table_frame(frame)) == row_count


def test_locked_dashboard_metrics_match_metadata_and_metric_file():
    from app_utils.data_loading import load_final_test_metrics, load_model_metadata
    from pages.performance import performance_metric_payload

    metadata = load_model_metadata()
    metrics = load_final_test_metrics().set_index("Technology")
    payload = performance_metric_payload()

    assert payload["wind"]["model"] == "XGBoost"
    assert payload["solar"]["model"] == "ExtraTrees"
    assert payload["wind"]["mae_mw"] == pytest.approx(296.6429929443603)
    assert payload["solar"]["mae_mw"] == pytest.approx(425.4104243049358)
    assert payload["wind"]["mae_mw"] == pytest.approx(metrics.loc["Wind", "MAE_MW"])
    assert payload["solar"]["mae_mw"] == pytest.approx(metrics.loc["Solar", "MAE_MW"])
    assert payload["wind"]["r2"] == metadata["wind_model"]["locked_test_R2"]
    assert payload["solar"]["r2"] == metadata["solar_model"]["locked_test_R2"]


def test_forecast_download_callback_uses_public_csv():
    from pages.forecast import download_forecast

    payload = download_forecast(1)
    assert payload["filename"] == "latest_forecast.csv"
    assert payload["base64"] is True
