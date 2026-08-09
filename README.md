# GB Embedded Wind & Solar Day-Ahead Forecasting

A reproducible Python forecasting system for Great Britain's **embedded** wind and solar generation. It combines official NESO generation and capacity data with leakage-safe ECMWF IFS HRES weather forecasts, produces every half-hour settlement period of the following UK calendar day, and presents operational outputs in a public-facing Plotly Dash application.

## Live Demo

**[Open the live GB Renewable Forecast dashboard](https://gb-renewable-forecast.onrender.com)**

The dashboard provides:
- Live day-ahead embedded wind and solar generation forecasts
- Half-hourly forecast values and capacity factors
- Historical forecast-vs-actual performance
- Locked out-of-sample model evaluation
- Methodology and data-source documentation

> Note: The app is hosted on Render's free tier, so the first load after a period of inactivity may take around a minute while the service wakes up.

## Headline Results

The selected models were chosen on a chronological validation period. The results below come from the previously untouched June–August 2025 test period and were locked before production refitting.

| Target | Model | Test MAE | Test R2 | Skill vs monthly climatology |
|---|---|---:|---:|---:|
| Embedded wind generation | XGBoost | 296.6 MW | 0.868 | 66.4% lower MAE |
| Embedded solar generation | ExtraTrees | 425.4 MW | 0.955 | 42.0% lower MAE |

The system forecasts embedded generation only; it is not a forecast of all GB renewable output.

## What the system does

```text
ECMWF archived/live weather forecast
              |
              v
Leakage-safe half-hour feature engineering
              |
              v
Separate wind and solar ML models
              |
              v
Predicted capacity factor (bounded for inference)
              |
              v
Official NESO embedded capacity
              |
              v
46 / 48 / 50-period day-ahead MW forecast
```

Operational convention:

- nominal issue time: 09:00 `Europe/London`;
- weather run: issue-date 00 UTC ECMWF IFS HRES;
- target: every physical settlement period of the following local calendar day; and
- production models: XGBoost for wind and ExtraTrees for solar.

The forecast CLI and dashboard are intentionally separate. `python -m src.forecast_tomorrow` retrieves official inputs, loads the saved models, and writes small forecast outputs. The Dash process displays those outputs without loading the large estimators or calling live APIs during navigation.

## Data Sources

- **Generation and capacity:** official National Energy System Operator (NESO) Historic Demand Data and Daily Demand Update.
- **Weather:** ECMWF IFS HRES 9 km through the official Open-Meteo Single Runs API, using the exact API identifier `ecmwf_ifs`.
- **Weather sampling:** ten fixed representative GB locations. They are not claimed to be renewable-capacity-weighted sites.

Raw downloads are preserved locally with provenance and are excluded from the public repository.

## Leakage-safe backtesting

Historical features use individual archived weather forecasts that could have been available at the nominal forecast issue time. Realised future weather and Open-Meteo's stitched historical-weather product are not substituted. Weather-run initialization, nominal issue time, forecast valid time, and settlement time remain explicit and distinct.

Evaluation is chronological:

- training: 1 April 2024 to 31 March 2025;
- validation: 1 April 2025 to 31 May 2025; and
- untouched test: 1 June 2025 to 31 August 2025.

The usable modelling archive spans 1 April 2024 to 31 August 2025. Five individual official-source exclusions—6 to 10 August 2025—are documented in `data/raw/weather/excluded_target_dates.json`. No alternative model, later run cycle, realised weather, or synthetic rows were used to fill them. The production fit uses 24,624 half-hour rows across 513 available target days.

## Dashboard

The Plotly Dash Pages application provides:

- a live-output forecast page with KPI cards, an interactive chart, full settlement table, and CSV download;
- a performance page sourced from locked untouched-test metrics;
- a date-selectable historical explorer containing only real test dates; and
- a recruiter-friendly methodology and limitations page.

It supports 46-, 48-, and 50-settlement-period target days and exposes `server = app.server` for deployment.

## Repository Structure

```text
app.py                         Dash entrypoint
pages/                         Forecast, performance, history, methodology
app_utils/                     Cached loaders, figures, formatting and theme
assets/styles.css              Responsive application styling
config/weather_locations.json  Ten representative GB locations
src/data/                      NESO/weather ingestion and validation
src/features/                  Shared training/inference features
src/models/                    Training workflow retained for reproducibility
src/forecast_tomorrow.py       Production-style live inference CLI
models/                        Production models and metadata
outputs/forecasts/             Small public latest-forecast outputs
outputs/metrics/               Locked test metrics and predictions
tests/                         Offline transformation, inference and app tests
render.yaml                    Render service definition (not deployed)
.github/workflows/             Prepared daily forecast automation
```

Large raw archives, modelling datasets, caches, and general generated outputs remain ignored.

## Run Locally

PowerShell example:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Generate or replay a day-ahead forecast:

```powershell
python -m src.forecast_tomorrow
python -m src.forecast_tomorrow --issue-date 2026-08-09
```

Launch the dashboard:

```powershell
python app.py
```

Open `http://127.0.0.1:8050`. A future Linux deployment can start the app with `gunicorn app:server`.

The saved models were verified with Python 3.12.13, NumPy 2.5.1, pandas 3.0.5, scikit-learn 1.9.0, XGBoost 3.4.0, and joblib 1.5.3. The solar estimator uses lossless joblib lzma level-3 compression; prediction equivalence and packaging details are recorded in `docs/model_packaging.md`.

## Testing

Run all offline tests with:

```powershell
python -m pytest -q
```

Routine tests use mocked API payloads where network behaviour matters. Importing or navigating the Dash app does not call Open-Meteo or NESO.

## Deployment Preparation

`render.yaml` defines a free-plan-compatible Python web service with a health check and `gunicorn app:server` start command; it has not been deployed. The prepared GitHub Actions workflow uses two UTC schedules plus a `Europe/London` local-hour gate so only one daily run proceeds across GMT/BST. It persists only the small dashboard forecast CSV and summary JSON.

The compressed 99,540,687-byte solar artefact is below GitHub's normal per-file limit, so Git LFS is not required. The workflow uses ordinary checkout and does not stage raw live weather responses.

## Limitations

- Weather uses ten representative GB locations rather than renewable-capacity-weighted grid cells.
- Forecasts cover embedded wind and solar generation, not all transmission-connected renewable generation.
- Accuracy varies by weather regime and individual day.
- The application displays the most recently generated output; it does not claim continuous operational availability.
- This is a portfolio and research demonstration, not a production trading forecast.

## Disclaimer

This project is for portfolio, educational, and research purposes. It is not trading, operational dispatch, or investment advice.

## Project Status

Stages 1–7 are complete. Stage 8 adds the tested local Dash application, lossless model packaging, and deployment/automation preparation. No GitHub remote, external deployment, SQL service, or paid cloud resource has been created.
