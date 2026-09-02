# LinkedIn launch notes

- **Project:** GB Embedded Wind & Solar Day-Ahead Forecasting
- **Motivation:** Build an operationally credible, leakage-safe forecast for every half-hour settlement period of the following UK calendar day.
- **Technical stack:** Python, pandas, scikit-learn, XGBoost, Plotly Dash, pytest, GitHub Actions preparation, and Render preparation.
- **Data sources:** Official NESO embedded generation/capacity data and ECMWF IFS HRES 9 km forecasts through the Open-Meteo Single Runs API.
- **Forecast setup:** Daily 00 UTC weather run, nominal 09:00 Europe/London issue, ten representative GB locations, separate wind and solar capacity-factor models, conversion to MW with official embedded capacities.
- **Locked V2 test results (Apr–Jun 2026):** Wind spatial XGBoost — 239.1 MW MAE, R2 0.912, 70.0% lower MAE than monthly half-hour climatology. Solar spatial XGBoost — 385.5 MW MAE, R2 0.974, 58.0% lower MAE than climatology.
- **Live demo:** [deployment pending]
- **GitHub:** [publication pending]

Three concise lessons:

1. Forecast-run initialization and valid time must remain separate to prevent subtle weather leakage.
2. GB daylight-saving days require 46/48/50-period-safe timestamp and interface design.
3. A useful public app can display generated outputs without loading large ML models into the web process.

Scope note: the target is **GB embedded wind and solar generation**, not total GB renewable generation.
