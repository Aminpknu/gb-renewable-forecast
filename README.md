# GB Embedded Wind & Solar Day-Ahead Forecasting

## Purpose

This project will provide a reproducible energy data science pipeline for forecasting embedded wind and solar generation in Great Britain. It is intended to demonstrate professional practice in power-data processing, time-series forecasting, leakage-safe machine learning, evaluation, and software engineering.

## Forecasting objective

Produce separate forecasts of Great Britain embedded wind generation and embedded solar generation for every settlement period in the next calendar day.

- **Forecast horizon:** next calendar day
- **Temporal resolution:** 30 minutes (normally 48 periods; 46/50 on GB daylight-saving transition days)
- **Targets:** separate wind and solar generation forecasts

Forecast issue time and forecast valid time will be represented explicitly throughout the pipeline.

## Data sources

The project uses or is expected to use:

- Official NESO Historic Demand Data for estimated embedded wind and solar generation and embedded capacity. Stage 2 covers 1 April 2024 to 30 June 2026, the latest complete month detected in the downloaded 2026 source.
- Historical installed wind and solar capacity from the same NESO files for target normalisation and interpretation.
- Individual ECMWF IFS HRES 9 km archived forecasts from the official Open-Meteo Single Runs API, selected with the exact model identifier `ecmwf_ifs` and explicit 00 UTC run initialization.
- Official NESO Daily Demand Update for live embedded wind and solar capacity, with an explicit local-official-data fallback when the live source is unavailable.

The weather inputs are archived or live model forecasts, not realised/reanalysis weather.

## Live day-ahead forecast

Run the production-style inference pipeline with:

```powershell
python -m src.forecast_tomorrow
python -m src.forecast_tomorrow --issue-date 2026-08-09
```

The command uses the issue-date 00 UTC ECMWF IFS HRES run for every settlement period of the following `Europe/London` calendar day. It loads the saved XGBoost wind and ExtraTrees solar models without retraining, applies the shared Stage 4 feature functions in metadata order, retrieves official NESO embedded capacities, and writes a dated CSV, `latest_forecast.csv`, a JSON summary, and one diagnostic figure. DST days produce 46 or 50 rows automatically.

## Planned modelling stages

1. Define the forecast issue schedule, valid periods, targets, and evaluation protocol.
2. Ingest and validate generation, capacity, calendar, and archived weather-forecast data.
3. Establish simple leakage-safe baseline forecasts.
4. Engineer wind and solar features separately using only information available at issue time.
5. Train candidate machine-learning models with chronological validation.
6. Evaluate wind and solar forecasts separately against the baselines.
7. Package reproducible forecasting and reporting workflows.
8. Later, add data storage, automation, continuous integration, and an interactive application when explicitly requested.

## Reproducibility principles

- Preserve raw source data unchanged and record its provenance.
- Keep timestamps, timezones, forecast issue times, and valid times explicit.
- Prevent target and weather-information leakage.
- Use chronological train, validation, and test periods rather than random splits.
- Keep transformations in reusable, tested Python modules.
- Record dependencies, configuration, modelling assumptions, and evaluation definitions.
- Investigate and report missing, invalid, or physically suspicious observations rather than silently changing them.

## Current project status

- **Stage 1 — project setup: complete.** Repository structure, dependencies, development instructions, and import smoke testing are in place.
- **Stage 2 — NESO target ingestion: complete.** Official NESO Historic Demand Data for 2024–2026 has been preserved with hashes and provenance. The cleaned target dataset contains estimated embedded wind/solar generation, capacity, and observed capacity factors from 1 April 2024 through the latest complete month, June 2026.
- **Stage 3 — archived weather ingestion: complete for the portfolio MVP with documented source exclusions.** The clean hourly dataset covers target dates from 1 April 2024 through 31 August 2025 at ten representative GB locations, using 513 validated daily 00 UTC ECMWF IFS HRES runs. Five target dates (6–10 August 2025) are explicitly excluded in `data/raw/weather/excluded_target_dates.json`: four required runs were reported as `modelRunUnavailable`, while the 7 August run reproducibly returned nulls for six required variables. No alternative model, run cycle, realised weather, interpolation, or synthetic rows were substituted. Later archived forecasts are intentionally outside the portfolio MVP scope.
- **Stages 4–7A — modelling: complete.** Leakage-safe half-hour weather features, chronological splits, baselines, model comparison, locked untouched-test evaluation, and production fitting are complete. The selected production models are XGBoost for wind and ExtraTrees for solar. Locked test MAE is 296.643 MW for wind and 425.410 MW for solar; these metrics are preserved in `models/model_metadata.json` and are not recalculated by live inference.
- **Stage 7B — live inference: complete.** Training and serving share the same weather transformations. Historical parity for 16 January 2025 matches all features to floating-point precision. The live CLI preserves distinct model-run initialization, nominal issue, and valid times; uses official live weather and capacity sources; validates feature order and physical ranges; and produces DST-safe forecasts and summaries without retraining.

Observed capacity factors are calculated as estimated embedded generation divided by the corresponding NESO embedded capacity. Observations are quality-checked and reported without clipping. The canonical key is settlement date plus settlement period; timezone-aware `Europe/London` and UTC valid times explicitly preserve 46-period spring and 50-period autumn daylight-saving days.

Weather model initialization, nominal project issue time, and forecast valid time remain separate fields. The weather inputs are individual archived forecasts rather than realised/reanalysis weather or Open-Meteo's stitched historical-weather product. The ten locations are representative sampling points, not renewable-capacity-weighted sites. Hourly weather is interpolated independently within each local target day to the canonical half-hour settlement timestamps.

The live pipeline is implemented and tested. Streamlit, SQL, GitHub Actions, and later application stages have not started.

## Model compatibility

The saved production artefacts were verified with Python 3.12.13, NumPy 2.5.1, pandas 3.0.5, scikit-learn 1.9.0, XGBoost 3.4.0, and joblib 1.5.3. These versions are recorded in `models/model_metadata.json`; broad dependency upgrades should be avoided when loading the saved models.
