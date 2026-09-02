"""Production-style live GB embedded wind and solar day-ahead inference."""

from __future__ import annotations

import argparse
import json
import os
import warnings
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.data.build_weather import CACHE_DIRECTORY as HISTORICAL_WEATHER_CACHE
from src.data.open_meteo import (
    OfficialArchiveUnavailableError,
    cache_path,
    create_retry_session,
    fetch_run,
    parse_multiple_location_response,
    select_following_local_day,
)
from src.data.weather_config import (
    LOCAL_TIMEZONE,
    WEATHER_MODEL,
    WEATHER_MODEL_API_IDENTIFIER,
    load_weather_locations,
)
from src.data.weather_validation import validate_single_run
from src.features.weather_features import (
    build_half_hour_features,
    load_model_metadata,
    ordered_feature_matrix,
    settlement_frame_for_target_date,
)

MODEL_DIRECTORY = PROJECT_ROOT / "models"
WIND_MODEL_PATH = MODEL_DIRECTORY / "wind_xgboost.joblib"
SOLAR_MODEL_PATH = MODEL_DIRECTORY / "solar_xgboost.joblib"
MODEL_METADATA_PATH = MODEL_DIRECTORY / "model_metadata.json"
LIVE_WEATHER_CACHE = PROJECT_ROOT / "data" / "raw" / "weather" / "live"
LOCAL_NESO_TARGETS = (
    PROJECT_ROOT / "data" / "interim" / "neso_embedded_wind_solar_targets.csv"
)
FORECAST_DIRECTORY = PROJECT_ROOT / "outputs" / "forecasts"
FIGURE_PATH = PROJECT_ROOT / "outputs" / "figures" / "latest_day_ahead_forecast.png"

NESO_DAILY_DEMAND_ENDPOINT = "https://api.neso.energy/api/3/action/datastore_search"
NESO_DAILY_DEMAND_RESOURCE_ID = "177f6fa4-ae49-4182-81ea-0c6b35f26ca6"

OUTPUT_COLUMNS = [
    "forecast_created_utc",
    "nominal_forecast_issue_time_local",
    "weather_run_init_utc",
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
    "weather_model",
    "capacity_source",
    "capacity_source_date",
]


@dataclass(frozen=True)
class ForecastContext:
    """Explicit issue, run initialization, and target-day timestamps."""

    issue_date: date
    nominal_forecast_issue_time_local: pd.Timestamp
    weather_run_init_utc: pd.Timestamp
    target_date: date


@dataclass(frozen=True)
class CapacitySelection:
    """Official or explicitly identified fallback embedded capacities."""

    wind_capacity_mw: float
    solar_capacity_mw: float
    capacity_source: str
    capacity_source_date: date


def resolve_forecast_context(
    issue_date: str | date | pd.Timestamp | None = None,
    now_utc: pd.Timestamp | None = None,
) -> ForecastContext:
    """Resolve the nominal 09:00 local issue and following local target day."""
    if issue_date is None:
        now = now_utc if now_utc is not None else pd.Timestamp.now(tz="UTC")
        day = now.tz_convert(LOCAL_TIMEZONE).date()
    else:
        day = pd.Timestamp(issue_date).date()
    local_issue = (pd.Timestamp(day) + pd.Timedelta(hours=9)).tz_localize(
        LOCAL_TIMEZONE
    )
    run_init = pd.Timestamp(day).tz_localize("UTC")
    target = (pd.Timestamp(day) + pd.Timedelta(days=1)).date()
    return ForecastContext(day, local_issue, run_init, target)


def _read_live_weather(
    context: ForecastContext,
    session: requests.Session | None = None,
) -> tuple[pd.DataFrame, Path, bool]:
    """Reuse an appropriate immutable cache or retrieve the selected live run."""
    locations = load_weather_locations()
    historical_path = cache_path(HISTORICAL_WEATHER_CACHE, context.weather_run_init_utc)
    cache_directory = (
        HISTORICAL_WEATHER_CACHE if historical_path.is_file() else LIVE_WEATHER_CACHE
    )
    cached = fetch_run(
        context.weather_run_init_utc,
        locations,
        cache_directory,
        session=session,
    )
    parsed = parse_multiple_location_response(
        cached.payload, locations, context.weather_run_init_utc
    )
    selected = select_following_local_day(parsed, context.weather_run_init_utc)
    validation = validate_single_run(selected, context.weather_run_init_utc, locations)
    if not validation.get("passed", False):
        raise ValueError(f"Live weather run failed validation: {validation}")
    return selected, cached.path, cached.reused


def _normalise_capacity_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "".join(character if character.isalnum() else "_" for character in key)
        .strip("_")
        .upper(): value
        for key, value in record.items()
    }


def parse_neso_capacity_payload(
    payload: dict[str, Any],
    target_date: date | str | pd.Timestamp,
) -> CapacitySelection:
    """Select target-date or latest valid capacities from NESO CKAN records."""
    if not payload.get("success"):
        raise ValueError("NESO Daily Demand Update response was not successful.")
    records = payload.get("result", {}).get("records", [])
    rows: list[dict[str, Any]] = []
    for raw_record in records:
        record = _normalise_capacity_record(raw_record)
        raw_date = record.get("SETTLEMENT_DATE")
        wind = pd.to_numeric(record.get("EMBEDDED_WIND_CAPACITY"), errors="coerce")
        solar = pd.to_numeric(record.get("EMBEDDED_SOLAR_CAPACITY"), errors="coerce")
        parsed_date = pd.to_datetime(raw_date, errors="coerce")
        if pd.notna(parsed_date) and pd.notna(wind) and pd.notna(solar):
            if float(wind) > 0 and float(solar) > 0:
                rows.append(
                    {
                        "date": pd.Timestamp(parsed_date).date(),
                        "wind": float(wind),
                        "solar": float(solar),
                    }
                )
    if not rows:
        raise ValueError("NESO Daily Demand Update contained no valid positive capacities.")
    target = pd.Timestamp(target_date).date()
    target_rows = [row for row in rows if row["date"] == target]
    if target_rows:
        selected = target_rows[-1]
    else:
        historical_rows = [row for row in rows if row["date"] <= target]
        if not historical_rows:
            raise ValueError("NESO Daily Demand Update contains no capacity record on or before the target date.")
        selected = max(historical_rows, key=lambda row: row["date"])
    return CapacitySelection(
        selected["wind"],
        selected["solar"],
        "NESO Daily Demand Update",
        selected["date"],
    )


def load_local_capacity_fallback(
    target_date: date | str | pd.Timestamp | None = None,
    path: Path = LOCAL_NESO_TARGETS,
) -> CapacitySelection:
    """Load the latest valid local NESO capacities on or before a target date."""
    frame = pd.read_csv(
        path,
        usecols=[
            "settlement_date",
            "embedded_wind_capacity_mw",
            "embedded_solar_capacity_mw",
        ],
    )
    frame["settlement_date"] = pd.to_datetime(frame["settlement_date"], errors="coerce")
    for column in ("embedded_wind_capacity_mw", "embedded_solar_capacity_mw"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    valid = frame.loc[
        frame["settlement_date"].notna()
        & frame["embedded_wind_capacity_mw"].gt(0)
        & frame["embedded_solar_capacity_mw"].gt(0)
    ].sort_values("settlement_date")
    if target_date is not None:
        target = pd.Timestamp(target_date).normalize()
        valid = valid.loc[valid["settlement_date"].dt.normalize() <= target]
    if valid.empty:
        raise ValueError("Local NESO target data contains no valid positive capacity on or before the target date.")
    row = valid.iloc[-1]
    return CapacitySelection(
        float(row["embedded_wind_capacity_mw"]),
        float(row["embedded_solar_capacity_mw"]),
        "historical_fallback: local official NESO target dataset",
        pd.Timestamp(row["settlement_date"]).date(),
    )


def fetch_live_capacities(
    target_date: date,
    session: requests.Session | None = None,
) -> CapacitySelection:
    """Fetch official NESO capacities, falling back explicitly to local official data."""
    request_session = session or create_retry_session()
    try:
        response = request_session.get(
            NESO_DAILY_DEMAND_ENDPOINT,
            params={
                "resource_id": NESO_DAILY_DEMAND_RESOURCE_ID,
                "limit": 10000,
            },
            timeout=90,
        )
        response.raise_for_status()
        return parse_neso_capacity_payload(response.json(), target_date)
    except (requests.RequestException, ValueError, KeyError, json.JSONDecodeError) as error:
        warnings.warn(
            f"NESO Daily Demand Update unavailable or invalid ({error}); using the "
            "latest capacity on or before the target date in the local official NESO dataset.",
            RuntimeWarning,
            stacklevel=2,
        )
        return load_local_capacity_fallback(target_date)


def clip_capacity_factor(values: Any) -> np.ndarray:
    """Physically bound model predictions without altering historical observations."""
    return np.clip(np.asarray(values, dtype=float), 0.0, 1.0)


def capacity_factor_to_mw(capacity_factor: Any, capacity_mw: float) -> np.ndarray:
    """Convert bounded capacity-factor predictions to MW."""
    if capacity_mw <= 0:
        raise ValueError("Installed capacity must be positive.")
    return clip_capacity_factor(capacity_factor) * float(capacity_mw)


def daily_energy_mwh(forecast_mw: Any) -> float:
    """Integrate half-hour MW values into daily MWh, including DST days."""
    return float(np.asarray(forecast_mw, dtype=float).sum() * 0.5)


def load_production_models() -> tuple[Any, Any, dict[str, Any]]:
    """Load saved production models and enforce metadata/estimator feature contracts."""
    for path in (WIND_MODEL_PATH, SOLAR_MODEL_PATH, MODEL_METADATA_PATH):
        if not path.is_file():
            raise FileNotFoundError(f"Required production artefact is missing: {path}")
    metadata = load_model_metadata(MODEL_METADATA_PATH)
    wind_model = joblib.load(WIND_MODEL_PATH)
    solar_model = joblib.load(SOLAR_MODEL_PATH)
    for model, key in ((wind_model, "wind_model"), (solar_model, "solar_model")):
        estimator_features = getattr(model, "feature_names_in_", None)
        expected = metadata[key]["features"]
        if estimator_features is not None and list(estimator_features) != expected:
            raise ValueError(f"Saved {key} feature names do not match model metadata.")
        if getattr(model, "n_features_in_", len(expected)) != len(expected):
            raise ValueError(f"Saved {key} feature count does not match model metadata.")
    return wind_model, solar_model, metadata


def build_forecast_output(
    features: pd.DataFrame,
    context: ForecastContext,
    capacity: CapacitySelection,
    wind_pred_cf: Any,
    solar_pred_cf: Any,
    forecast_created_utc: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Build and validate the stable live forecast output schema."""
    created = forecast_created_utc or pd.Timestamp.now(tz="UTC")
    result = features[
        ["settlement_period", "valid_time_local", "valid_time_utc"]
    ].copy()
    result.insert(0, "target_date", context.target_date.isoformat())
    result.insert(0, "weather_run_init_utc", context.weather_run_init_utc)
    result.insert(
        0,
        "nominal_forecast_issue_time_local",
        context.nominal_forecast_issue_time_local,
    )
    result.insert(0, "forecast_created_utc", created)
    result["wind_pred_cf"] = clip_capacity_factor(wind_pred_cf)
    result["wind_forecast_mw"] = capacity_factor_to_mw(
        result["wind_pred_cf"], capacity.wind_capacity_mw
    )
    result["wind_capacity_mw"] = capacity.wind_capacity_mw
    result["solar_pred_cf"] = clip_capacity_factor(solar_pred_cf)
    result["solar_forecast_mw"] = capacity_factor_to_mw(
        result["solar_pred_cf"], capacity.solar_capacity_mw
    )
    result["solar_capacity_mw"] = capacity.solar_capacity_mw
    result["weather_model"] = WEATHER_MODEL
    result["capacity_source"] = capacity.capacity_source
    result["capacity_source_date"] = capacity.capacity_source_date.isoformat()
    result = result.loc[:, OUTPUT_COLUMNS]
    if result["valid_time_utc"].duplicated().any():
        raise ValueError("Forecast output contains duplicate UTC valid times.")
    if result.isna().any().any():
        raise ValueError("Forecast output contains missing values.")
    return result


def build_forecast_summary(
    forecast: pd.DataFrame,
    context: ForecastContext,
    capacity: CapacitySelection,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Summarize peak power, half-hour energy, provenance, and locked metrics."""
    wind_peak = forecast.loc[forecast["wind_forecast_mw"].idxmax()]
    solar_peak = forecast.loc[forecast["solar_forecast_mw"].idxmax()]
    return {
        "nominal_forecast_issue_time_local": context.nominal_forecast_issue_time_local.isoformat(),
        "weather_run_init_utc": context.weather_run_init_utc.isoformat(),
        "target_date": context.target_date.isoformat(),
        "settlement_period_count": int(len(forecast)),
        "weather_model": WEATHER_MODEL,
        "weather_model_api_identifier": WEATHER_MODEL_API_IDENTIFIER,
        "capacity_source": capacity.capacity_source,
        "capacity_source_date": capacity.capacity_source_date.isoformat(),
        "wind_capacity_mw": capacity.wind_capacity_mw,
        "solar_capacity_mw": capacity.solar_capacity_mw,
        "peak_wind_mw": float(wind_peak["wind_forecast_mw"]),
        "peak_wind_valid_time_local": pd.Timestamp(
            wind_peak["valid_time_local"]
        ).isoformat(),
        "peak_solar_mw": float(solar_peak["solar_forecast_mw"]),
        "peak_solar_valid_time_local": pd.Timestamp(
            solar_peak["valid_time_local"]
        ).isoformat(),
        "total_forecast_wind_energy_mwh": daily_energy_mwh(
            forecast["wind_forecast_mw"]
        ),
        "total_forecast_solar_energy_mwh": daily_energy_mwh(
            forecast["solar_forecast_mw"]
        ),
        "models": {
            "wind": metadata["wind_model"]["algorithm"],
            "solar": metadata["solar_model"]["algorithm"],
        },
        "locked_historical_test_metrics": {
            "wind": {
                key: value
                for key, value in metadata["wind_model"].items()
                if key.startswith("locked_test_")
            },
            "solar": {
                key: value
                for key, value in metadata["solar_model"].items()
                if key.startswith("locked_test_")
            },
        },
    }


def _atomic_write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, date_format="%Y-%m-%dT%H:%M:%S%z")
    temporary.replace(path)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _save_forecast_figure(forecast: pd.DataFrame) -> None:
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(11, 5))
    axis.plot(
        forecast["valid_time_local"],
        forecast["wind_forecast_mw"],
        label="Embedded wind forecast",
        linewidth=2,
    )
    axis.plot(
        forecast["valid_time_local"],
        forecast["solar_forecast_mw"],
        label="Embedded solar forecast",
        linewidth=2,
    )
    axis.set_title(f"GB Embedded Wind and Solar Day-Ahead Forecast — {forecast['target_date'].iloc[0]}")
    axis.set_xlabel("Target time (Europe/London)")
    axis.set_ylabel("Forecast generation (MW)")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.autofmt_xdate()
    figure.tight_layout()
    figure.savefig(FIGURE_PATH, dpi=160)
    plt.close(figure)


def run_live_forecast(
    issue_date: str | None = None,
    session: requests.Session | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Run one live/replay forecast without retraining or changing model selection."""
    context = resolve_forecast_context(issue_date)
    weather, _, _ = _read_live_weather(context, session=session)
    settlements = settlement_frame_for_target_date(context.target_date)
    features = build_half_hour_features(weather, settlements)
    wind_model, solar_model, metadata = load_production_models()
    wind_matrix = ordered_feature_matrix(features, metadata, "wind_model")
    solar_matrix = ordered_feature_matrix(features, metadata, "solar_model")
    wind_pred_cf = clip_capacity_factor(wind_model.predict(wind_matrix))
    solar_pred_cf = clip_capacity_factor(solar_model.predict(solar_matrix))
    solar_pred_cf = np.where(features["radiation_mean"].to_numpy() <= 0, 0.0, solar_pred_cf)
    capacity = fetch_live_capacities(context.target_date, session=session)
    forecast = build_forecast_output(
        features, context, capacity, wind_pred_cf, solar_pred_cf
    )
    summary = build_forecast_summary(forecast, context, capacity, metadata)

    dated_path = FORECAST_DIRECTORY / f"forecast_{context.target_date.isoformat()}.csv"
    latest_path = FORECAST_DIRECTORY / "latest_forecast.csv"
    summary_path = FORECAST_DIRECTORY / "latest_forecast_summary.json"
    _atomic_write_csv(dated_path, forecast)
    _atomic_write_csv(latest_path, forecast)
    _atomic_write_json(summary_path, summary)
    _save_forecast_figure(forecast)
    return forecast, summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the GB embedded wind and solar forecast for the following "
            "Europe/London calendar day using the selected 00 UTC ECMWF IFS run."
        )
    )
    parser.add_argument(
        "--issue-date",
        help="Reproducible issue date in YYYY-MM-DD format; defaults to today in Europe/London.",
    )
    arguments = parser.parse_args()
    try:
        forecast, summary = run_live_forecast(arguments.issue_date)
    except OfficialArchiveUnavailableError as error:
        raise SystemExit(
            "Required ECMWF IFS HRES 00 UTC run is unavailable; no substitute was used. "
            f"Official response: {error}"
        ) from error
    print(forecast.head().to_string(index=False))
    print(forecast.tail().to_string(index=False))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
