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
