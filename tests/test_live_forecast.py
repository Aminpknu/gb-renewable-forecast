"""Offline tests for the production-style live forecast pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import requests

import src.forecast_tomorrow as live
from src.data.open_meteo import (
    CachedRun,
    parse_multiple_location_response,
    select_following_local_day,
)
from src.data.weather_config import EXPECTED_API_UNITS, HOURLY_VARIABLES, load_weather_locations
from src.features.weather_features import (
    SOLAR_FEATURES,
    WIND_FEATURES,
    build_half_hour_features,
    load_model_metadata,
    ordered_feature_matrix,
    settlement_frame_for_target_date,
)
from src.features.spatial_features import location_feature_columns


def _ten_location_payload(run_date: str = "2025-01-15") -> list[dict[str, Any]]:
    locations = load_weather_locations()
    times = pd.date_range(f"{run_date}T00:00:00Z", periods=49, freq="h")
    payload: list[dict[str, Any]] = []
    for index, location in enumerate(locations):
        hourly: dict[str, Any] = {"time": times.strftime("%Y-%m-%dT%H:%M").tolist()}
        for variable in HOURLY_VARIABLES:
            if variable == "temperature_2m":
                values = [5.0 + index / 10] * 49
            elif variable == "pressure_msl":
                values = [1010.0 + index] * 49
            elif variable == "wind_speed_100m":
                values = [7.0 + index / 10] * 49
            elif variable == "wind_direction_100m":
                values = [220.0 + index] * 49
            elif variable == "cloud_cover":
                values = [50.0] * 49
            else:
                values = [0.0] * 49
            hourly[variable] = values
        payload.append(
            {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "elevation": 50.0,
                "hourly_units": {"time": "iso8601", **EXPECTED_API_UNITS},
                "hourly": hourly,
            }
        )
    return payload


def test_model_metadata_and_required_model_files() -> None:
    metadata = load_model_metadata()
    assert live.WIND_MODEL_PATH.is_file()
    assert live.SOLAR_MODEL_PATH.is_file()
    assert live.WIND_MODEL_PATH.stat().st_size > 0
    assert live.SOLAR_MODEL_PATH.stat().st_size > 0
    assert metadata["wind_model"]["algorithm"] == "XGBoost"
    assert metadata["solar_model"]["algorithm"] == "XGBoost"


def test_feature_order_contract() -> None:
    metadata = load_model_metadata()
    location_names = [location.name for location in load_weather_locations()]
    spatial = location_feature_columns(location_names)
    assert metadata["wind_model"]["features"][: len(WIND_FEATURES)] == WIND_FEATURES
    assert metadata["solar_model"]["features"][: len(SOLAR_FEATURES)] == SOLAR_FEATURES
    assert metadata["wind_model"]["features"][len(WIND_FEATURES) :] == spatial["wind"]
    assert metadata["solar_model"]["features"][len(SOLAR_FEATURES) :] == spatial["solar"]
    columns = metadata["wind_model"]["features"] + [
        column for column in metadata["solar_model"]["features"]
        if column not in metadata["wind_model"]["features"]
    ]
    frame = pd.DataFrame({column: [1.0] for column in columns})
    wind = ordered_feature_matrix(frame, metadata, "wind_model")
    solar = ordered_feature_matrix(frame, metadata, "solar_model")
    assert wind.columns.tolist() == metadata["wind_model"]["features"]
    assert solar.columns.tolist() == metadata["solar_model"]["features"]


def test_historical_feature_parity_regression() -> None:
    root = Path(__file__).resolve().parents[1]
    raw_path = root / "data/raw/weather/ecmwf_ifs_hres/run_20250115T0000Z.json"
    dataset_path = root / "data/processed/ml_dataset.csv"
    if not raw_path.is_file() or not dataset_path.is_file():
        pytest.skip("Local ignored historical artefacts are required for parity regression.")
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    run_init = "2025-01-15T00:00:00Z"
    hourly = select_following_local_day(
        parse_multiple_location_response(payload, load_weather_locations(), run_init),
        run_init,
    )
    actual = build_half_hour_features(
        hourly, settlement_frame_for_target_date("2025-01-16")
    )
    expected = pd.read_csv(dataset_path)
    expected = expected.loc[
        expected["settlement_date"].astype(str).str[:10].eq("2025-01-16")
    ].copy()
    expected["valid_time_utc"] = pd.to_datetime(expected["valid_time_utc"], utc=True)
    metadata = load_model_metadata()
    features = list(
        dict.fromkeys(
            metadata["wind_model"]["features"] + metadata["solar_model"]["features"]
        )
    )
    merged = actual.merge(
        expected[["valid_time_utc", *features]],
        on="valid_time_utc",
        suffixes=("_actual", "_expected"),
        validate="one_to_one",
    )
    assert len(actual) == len(expected) == len(merged) == 48
    for feature in features:
        np.testing.assert_allclose(
            merged[f"{feature}_actual"],
            merged[f"{feature}_expected"],
            rtol=1e-12,
            atol=1e-10,
        )


@pytest.mark.parametrize(
    ("target_date", "expected_periods"),
    [
        ("2025-01-16", 48),
        ("2025-03-30", 46),
        ("2025-10-26", 50),
    ],
)
def test_live_settlement_period_counts(target_date: str, expected_periods: int) -> None:
    frame = settlement_frame_for_target_date(target_date)
    assert len(frame) == expected_periods
    assert not frame["valid_time_utc"].duplicated().any()


def test_live_weather_parsing_with_mocked_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _ten_location_payload()

    def fake_fetch(*_args: Any, **_kwargs: Any) -> CachedRun:
        return CachedRun(payload, Path("mock-live-run.json"), False)

    monkeypatch.setattr(live, "fetch_run", fake_fetch)
    context = live.resolve_forecast_context("2025-01-15")
    selected, path, reused = live._read_live_weather(context)
    assert len(selected) == 250
    assert selected["location_name"].nunique() == 10
    assert path == Path("mock-live-run.json")
    assert not reused


def test_capacity_parsing_prefers_target_then_latest_on_or_before_target() -> None:
    payload = {
        "success": True,
        "result": {
            "records": [
                {"SETTLEMENT_DATE": "2026-08-08", "EMBEDDED_WIND_CAPACITY": "7000", "EMBEDDED_SOLAR_CAPACITY": "19000"},
                {"SETTLEMENT_DATE": "2026-08-10", "EMBEDDED_WIND_CAPACITY": "7100", "EMBEDDED_SOLAR_CAPACITY": "19100"},
                {"SETTLEMENT_DATE": "2026-09-09", "EMBEDDED_WIND_CAPACITY": "7200", "EMBEDDED_SOLAR_CAPACITY": "19200"},
            ]
        },
    }
    target = live.parse_neso_capacity_payload(payload, "2026-08-10")
    historical = live.parse_neso_capacity_payload(payload, "2026-08-11")
    assert target.wind_capacity_mw == historical.wind_capacity_mw == 7100
    assert target.solar_capacity_mw == historical.solar_capacity_mw == 19100
    assert target.capacity_source_date == historical.capacity_source_date == pd.Timestamp("2026-08-10").date()
    assert target.capacity_source == "NESO Daily Demand Update"


def test_capacity_fallback_has_explicit_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailedSession:
        def get(self, *_args: Any, **_kwargs: Any) -> None:
            raise requests.ConnectionError("offline")

    fallback = live.CapacitySelection(
        7000.0,
        19000.0,
        "historical_fallback: local official NESO target dataset",
        pd.Timestamp("2026-06-30").date(),
    )
    monkeypatch.setattr(live, "load_local_capacity_fallback", lambda _target_date=None: fallback)
    with pytest.warns(RuntimeWarning, match="local official NESO"):
        selected = live.fetch_live_capacities(
            pd.Timestamp("2026-08-10").date(), session=FailedSession()  # type: ignore[arg-type]
        )
    assert selected == fallback
    assert selected.capacity_source.startswith("historical_fallback")


def test_cf_clipping_mw_conversion_and_energy() -> None:
    clipped = live.clip_capacity_factor([-0.2, 0.5, 1.3])
    np.testing.assert_array_equal(clipped, [0.0, 0.5, 1.0])
    np.testing.assert_array_equal(
        live.capacity_factor_to_mw(clipped, 1000.0), [0.0, 500.0, 1000.0]
    )
    assert live.daily_energy_mwh([100.0] * 48) == 2400.0
    assert live.daily_energy_mwh([100.0] * 46) == 2300.0
    assert live.daily_energy_mwh([100.0] * 50) == 2500.0


def test_output_schema() -> None:
    context = live.resolve_forecast_context("2026-08-09")
    settlements = settlement_frame_for_target_date(context.target_date)
    capacity = live.CapacitySelection(
        7000.0, 19000.0, "NESO Daily Demand Update", context.target_date
    )
    output = live.build_forecast_output(
        settlements,
        context,
        capacity,
        np.full(len(settlements), 0.5),
        np.full(len(settlements), 0.25),
        pd.Timestamp("2026-08-09T08:00:00Z"),
    )
    assert output.columns.tolist() == live.OUTPUT_COLUMNS
    assert len(output) == 48
    assert output["wind_forecast_mw"].eq(3500.0).all()
    assert output["solar_forecast_mw"].eq(4750.0).all()
