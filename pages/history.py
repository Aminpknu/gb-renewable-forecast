"""Interactive historical test-period explorer."""

from __future__ import annotations

import pandas as pd
from dash import Input, Output, callback, dcc, html

import dash
from app_utils.data_loading import available_historical_dates, load_historical_predictions
from app_utils.figures import historical_generation_figure

dash.register_page(
    __name__,
    path="/history",
    name="History",
    title="Historical Explorer | GB Renewable Forecast",
    order=2,
)


def history_day_payload(selected_date: str) -> tuple:
    """Return both figures and error metrics for one real test date."""

    predictions = load_historical_predictions()
    selected = pd.Timestamp(selected_date).date()
    day = predictions.loc[predictions["settlement_date"] == selected].copy()
    if day.empty:
        raise ValueError(f"No locked test predictions exist for {selected_date}.")

    wind_error = day["wind_pred_mw"] - day["embedded_wind_generation_mw"]
    solar_error = day["solar_pred_mw"] - day["embedded_solar_generation_mw"]
    return (
        historical_generation_figure(day, technology="wind"),
        historical_generation_figure(day, technology="solar"),
        f"{wind_error.abs().mean():,.1f} MW",
        f"{wind_error.mean():+,.1f} MW",
        f"{solar_error.abs().mean():,.1f} MW",
        f"{solar_error.mean():+,.1f} MW",
    )


def layout() -> html.Div:
    dates = available_historical_dates()
    default_date = dates[-1]
    wind_figure, solar_figure, wind_mae, wind_bias, solar_mae, solar_bias = (
        history_day_payload(default_date)
    )
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.P("Untouched test period", className="eyebrow"),
                            html.H1("Explore forecast behaviour by day"),
                            html.P(
                                "Historical explorer uses the locked June–August 2025 test period. Only dates with real archived-weather inputs and model predictions are available.",
                                className="page-lede",
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Label("Test date", htmlFor="history-date", className="input-label"),
                            dcc.Dropdown(
                                id="history-date",
                                options=[{"label": date, "value": date} for date in dates],
                                value=default_date,
                                clearable=False,
                                searchable=True,
                            ),
                        ],
                        className="date-control",
                    ),
                ],
                className="history-heading",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.P("Wind daily MAE"),
                            html.Strong(wind_mae, id="history-wind-mae"),
                        ],
                        className="mini-kpi",
                    ),
                    html.Div(
                        [
                            html.P("Wind daily bias"),
                            html.Strong(wind_bias, id="history-wind-bias"),
                        ],
                        className="mini-kpi",
                    ),
                    html.Div(
                        [
                            html.P("Solar daily MAE"),
                            html.Strong(solar_mae, id="history-solar-mae"),
                        ],
                        className="mini-kpi",
                    ),
                    html.Div(
                        [
                            html.P("Solar daily bias"),
                            html.Strong(solar_bias, id="history-solar-bias"),
                        ],
                        className="mini-kpi",
                    ),
                ],
                className="mini-kpi-grid",
            ),
            html.Section(
                dcc.Graph(
                    id="history-wind-figure",
                    figure=wind_figure,
                    config={"displayModeBar": False, "responsive": True},
                ),
                className="panel chart-panel",
            ),
            html.Section(
                dcc.Graph(
                    id="history-solar-figure",
                    figure=solar_figure,
                    config={"displayModeBar": False, "responsive": True},
                ),
                className="panel chart-panel",
            ),
            html.P(
                "Bias is forecast minus actual generation; positive values indicate overprediction.",
                className="section-note",
            ),
        ],
        className="page-stack",
    )


@callback(
    Output("history-wind-figure", "figure"),
    Output("history-solar-figure", "figure"),
    Output("history-wind-mae", "children"),
    Output("history-wind-bias", "children"),
    Output("history-solar-mae", "children"),
    Output("history-solar-bias", "children"),
    Input("history-date", "value"),
)
def update_history(selected_date: str) -> tuple:
    return history_day_payload(selected_date)
