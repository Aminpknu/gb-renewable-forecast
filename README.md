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
- Weather observations for exploratory analysis and quality control.
- Archived numerical weather forecasts that represent weather information available at the forecast issue time for model development and backtesting.

Weather-source licensing, coverage, and retrieval methods will be documented before weather ingestion is implemented.

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

Observed capacity factors are calculated as estimated embedded generation divided by the corresponding NESO embedded capacity. Observations are quality-checked and reported without clipping. The canonical key is settlement date plus settlement period; timezone-aware `Europe/London` and UTC valid times explicitly preserve 46-period spring and 50-period autumn daylight-saving days.

No weather data has been ingested, no forecasting models have been trained, and no forecasting results exist yet.
