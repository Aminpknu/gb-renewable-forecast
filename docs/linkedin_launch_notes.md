# LinkedIn launch notes

- **Project:** GB Embedded Wind & Solar Day-Ahead Forecasting
- **Motivation:** Build an operationally credible, leakage-safe forecast for every half-hour settlement period of the following UK calendar day.
- **Technical stack:** Python, pandas, scikit-learn, XGBoost, Plotly Dash, pytest, GitHub Actions preparation, and Render preparation.
- **Data sources:** Official NESO embedded generation/capacity data and ECMWF IFS HRES 9 km forecasts through the Open-Meteo Single Runs API.
- **Forecast setup:** Daily 00 UTC weather run, nominal 09:00 Europe/London issue, ten representative GB locations, separate wind and solar capacity-factor models, conversion to MW with official embedded capacities.
- **Untouched-test results:** Wind XGBoost — 296.6 MW MAE, R2 0.868, 66.4% lower MAE than monthly climatology. Solar ExtraTrees — 425.4 MW MAE, R2 0.955, 42.0% lower MAE than monthly climatology.
- **Live demo:** [deployment pending]
- **GitHub:** [publication pending]

Three concise lessons:

1. Forecast-run initialization and valid time must remain separate to prevent subtle weather leakage.
2. GB daylight-saving days require 46/48/50-period-safe timestamp and interface design.
3. A useful public app can display generated outputs without loading large ML models into the web process.

Scope note: the target is **GB embedded wind and solar generation**, not total GB renewable generation.
