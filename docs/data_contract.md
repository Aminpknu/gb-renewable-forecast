# Forecast data contract

## Project

**GB Embedded Wind & Solar Day-Ahead Forecasting**

## Forecast product

Produce separate forecasts of:

1. GB estimated embedded wind generation.
2. GB estimated embedded solar generation.

Forecasts cover every 30-minute settlement period of the following calendar day. Wind and solar are separate targets and will be modelled and evaluated separately.

## Time contract

- `settlement_date`: local GB electricity-market day and the date component of the canonical market key.
- `settlement_period`: sequential half-hour market period within `settlement_date`; daylight-saving days may have 46 or 50 periods rather than 48.
- `valid_time_local`: start of the settlement period in `Europe/London`, including its UTC offset.
- `valid_time_utc`: the same instant expressed in UTC.
- `forecast_issue_time`: timestamp at which a forecast is produced and its input information set is fixed.
- Forecast lead time: elapsed duration from `forecast_issue_time` to the forecast's valid time.

The canonical observation key is (`settlement_date`, `settlement_period`). Stage 2 contains historical target observations only, so it has no `forecast_issue_time`. Future weather and modelling stages **must** distinguish forecast issue time from valid time and may use only information available at issue time.

## Evaluation contract

Evaluation will be chronological. Random train/test splitting will not be used. Simple wind and solar baselines must be established before machine-learning models are evaluated.

## Archived weather forecast contract

Stage 3 uses individual **ECMWF IFS HRES 9 km** forecasts from the official Open-Meteo Single Runs API (`https://single-runs-api.open-meteo.com/v1/forecast`). The exact API model identifier is `ecmwf_ifs`. This is an archived model-run product, not Open-Meteo's stitched historical-weather product and not realised or reanalysis weather.

For target local calendar day D:

- select the ECMWF run initialized at 00:00 UTC on D−1;
- record that initialization as `weather_run_init_utc`;
- record the distinct nominal project issue time as 09:00 `Europe/London` on D−1 in `nominal_forecast_issue_time_local`;
- retain hourly valid times covering all of local day D plus the closing local-midnight boundary needed for later interpolation; and
- calculate `forecast_lead_hours` from model-run initialization to valid time.

Initialization time identifies the model cycle. It is not the model's public availability time and is not interchangeable with the nominal issue time. The 00 UTC cycle is selected because it is initialized sufficiently before the nominal 09:00 local issue and prevents use of a later run.

Weather is sampled at ten fixed representative GB locations defined in `config/weather_locations.json`. These are geographic sampling points and are **not** claimed to be renewable-capacity-weighted sites. UTC is the canonical weather time; `valid_time_local` is also retained with `Europe/London` daylight-saving rules. Hourly weather will be interpolated to the NESO half-hour UTC valid times only in Stage 4.

### Portfolio MVP archive scope and exclusions

The accepted archived-weather modelling period is 2024-04-01 through 2025-08-31. Later archived forecasts are intentionally not required for the portfolio MVP. Official source exclusions are recorded in `data/raw/weather/excluded_target_dates.json`; excluded days are absent from the clean dataset and are never filled or synthesized.

The documented exclusions are target dates 2025-08-06 through 2025-08-10. Four required ECMWF IFS HRES 00 UTC runs were reported as `modelRunUnavailable` by the official Single Runs API. The remaining run reproducibly returned nulls for six required weather variables at all ten locations. Consistent-model integrity and leakage safety take precedence over silently substituting another model, run cycle, realised weather, interpolation, or synthetic data.

## Live inference contract

For an issue date D, live inference records a nominal issue at 09:00 `Europe/London`, selects only the ECMWF IFS HRES run initialized at 00:00 UTC on D, and forecasts every physical settlement period of local calendar day D+1. A missing 00 UTC run is a hard failure; later model cycles, other weather models, realised weather, and synthetic substitution are prohibited.

Live feature engineering uses the same reusable functions as Stage 4: direction vectors are calculated before interpolation; hourly values are interpolated separately within each target date; ten locations are aggregated identically; calendar features use local time; and feature columns are ordered from `models/model_metadata.json`.

Embedded wind and solar capacities come from the official NESO Daily Demand Update resource. Target-date capacities are preferred, otherwise the latest valid published capacities are used. If the live source is unavailable, only the latest valid capacity from the project's local official NESO target dataset may be used, with an explicit warning and fallback provenance. NESO generation forecasts are never model features.

Saved model capacity-factor predictions are bounded to [0, 1] and converted to MW using the selected positive capacities. Solar generation is forced to zero only where the same live weather feature matrix reports no incoming shortwave radiation. Energy summaries integrate each settlement-period MW value over 0.5 hours, including 46- and 50-period DST days.
