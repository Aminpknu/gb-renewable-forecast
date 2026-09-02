"""Locked untouched-test performance page."""

from __future__ import annotations

from urllib.parse import parse_qs

import pandas as pd
from dash import Input, Output, callback, dcc, html

import dash
from app_utils.data_loading import (
    available_historical_dates,
    load_daily_test_metrics,
    load_final_test_metrics,
    load_historical_predictions,
    load_model_metadata,
)
from app_utils.figures import (
    daily_error_figure,
    historical_generation_figure,
    model_vs_baseline_figure,
)

dash.register_page(
    __name__,
    path="/performance",
    name="Forecast Performance",
    title="Day-ahead Forecast Performance | GB Renewable Forecast",
    order=1,
)


OVERALL_VIEW = "overall"
FORECAST_VS_ACTUAL_VIEW = "forecast-vs-actual"


def performance_metric_payload() -> dict[str, dict[str, float | str]]:
    """Return the locked performance values displayed by the page."""

    metadata = load_model_metadata()
    return {
        "wind": {
            "model": metadata["wind_model"]["algorithm"],
            "mae_mw": metadata["wind_model"]["locked_test_MAE_MW"],
            "r2": metadata["wind_model"]["locked_test_R2"],
            "skill_pct": metadata["wind_model"]["locked_test_skill_vs_baseline_pct"],
        },
        "solar": {
            "model": metadata["solar_model"]["algorithm"],
            "mae_mw": metadata["solar_model"]["locked_test_MAE_MW"],
            "r2": metadata["solar_model"]["locked_test_R2"],
            "skill_pct": metadata["solar_model"]["locked_test_skill_vs_baseline_pct"],
        },
    }


def _model_card(label: str, values: dict[str, float | str], class_name: str) -> html.Div:
    return html.Article(
        [
            html.Div([html.Span(label), html.Span(values["model"])], className="model-card-head"),
            html.Div(f"{float(values['mae_mw']):,.1f} MW", className="model-mae"),
            html.Div("Mean absolute error", className="model-mae-label"),
            html.Div(
                [
                    html.Div([html.Strong(f"{float(values['r2']):.3f}"), html.Span("R²")]),
                    html.Div(
                        [
                            html.Strong(f"{float(values['skill_pct']):.1f}%"),
                            html.Span("lower MAE than monthly climatology"),
                        ]
                    ),
                ],
                className="model-card-stats",
            ),
        ],
        className=f"model-card {class_name}",
    )


def _metrics_table(frame) -> html.Div:
    headers = [html.Th(column, scope="col") for column in frame.columns]
    rows = [
        html.Tr([html.Td(value) for value in row])
        for row in frame.itertuples(index=False, name=None)
    ]
    return html.Div(
        html.Table(
            [html.Thead(html.Tr(headers)), html.Tbody(rows)],
            className="data-table",
        ),
        className="table-scroll",
    )


def _overall_performance_content() -> html.Div:
    """Build the locked aggregate test-period performance view."""

    payload = performance_metric_payload()
    metrics = load_final_test_metrics()
    daily = load_daily_test_metrics()
    wind_bias = daily["wind_bias_mw"].mean()
    solar_bias = daily["solar_bias_mw"].mean()
    table = metrics.loc[
        :, ["Technology", "Model", "MAE_MW", "R2", "Baseline_MAE_MW", "Skill_vs_baseline_pct"]
    ].copy()
    table.columns = ["Technology", "Model", "MAE MW", "R²", "Baseline MAE MW", "Skill %"]
    for column in ["MAE MW", "Baseline MAE MW", "Skill %"]:
        table[column] = table[column].round(1)
    table["R²"] = table["R²"].round(3)

    return html.Div(
        [
            html.Div(
                [
                    _model_card("Wind", payload["wind"], "wind-accent"),
                    _model_card("Solar", payload["solar"], "solar-accent"),
                ],
                className="model-card-grid",
            ),
            html.Section(
                dcc.Graph(
                    figure=model_vs_baseline_figure(metrics),
                    config={"displayModeBar": False, "responsive": True},
                ),
                className="panel chart-panel",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.P("Audit table", className="eyebrow"),
                            html.H2("Locked aggregate metrics"),
                        ],
                        className="section-heading",
                    ),
                    _metrics_table(table),
                ],
                className="panel table-panel",
            ),
            html.Section(
                [
                    dcc.Graph(
                        figure=daily_error_figure(daily),
                        config={"displayModeBar": False, "responsive": True},
                    ),
                    html.Div(
                        [
                            html.Div(
                                [html.Strong(f"{wind_bias:+.2f} MW"), html.Span("Wind mean bias")],
                                className="bias-stat",
                            ),
                            html.Div(
                                [html.Strong(f"{solar_bias:+.2f} MW"), html.Span("Solar mean bias")],
                                className="bias-stat",
                            ),
                            html.P(
                                "Positive bias means the model overpredicted generation on average. Daily errors vary materially with weather regime.",
                                className="section-note",
                            ),
                        ],
                        className="bias-row",
                    ),
                ],
                className="panel chart-panel",
            ),
        ],
        className="page-stack",
    )


def history_day_payload(selected_date: str) -> tuple:
    """Return both figures and error metrics for one real untouched-test date."""

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


def _forecast_vs_actual_content() -> html.Div:
    """Build the existing single-day historical inspection view."""

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
                            html.H2("Forecast vs actual by day"),
                            html.P(
                                "Historical explorer uses the locked April–June 2026 V2 test period (90 usable target days). Only dates with real archived-weather inputs and frozen-model predictions are available.",
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
                    html.Div([html.P("Wind daily MAE"), html.Strong(wind_mae, id="history-wind-mae")], className="mini-kpi"),
                    html.Div([html.P("Wind daily bias"), html.Strong(wind_bias, id="history-wind-bias")], className="mini-kpi"),
                    html.Div([html.P("Solar daily MAE"), html.Strong(solar_mae, id="history-solar-mae")], className="mini-kpi"),
                    html.Div([html.P("Solar daily bias"), html.Strong(solar_bias, id="history-solar-bias")], className="mini-kpi"),
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
        className="page-stack performance-view",
    )


def performance_view_from_search(search: str | None) -> str:
    """Select the requested performance view from a Dash URL query string."""

    requested = parse_qs((search or "").lstrip("?")).get("view", [OVERALL_VIEW])[0]
    if requested == FORECAST_VS_ACTUAL_VIEW:
        return FORECAST_VS_ACTUAL_VIEW
    return OVERALL_VIEW


def layout(view: str | None = None, **_query_parameters: str) -> html.Div:
    selected_view = performance_view_from_search(f"?view={view}" if view else None)
    return html.Div(
        [
            html.Div(
                [
                    html.P("Locked evaluation", className="eyebrow"),
                    html.H1("Day-ahead Forecast Performance"),
                    html.P(
                        "See how the wind and solar forecasting models performed across the full untouched test period, then inspect what they predicted and what actually happened on individual days.",
                        className="page-lede",
                    ),
                ],
                className="page-heading",
            ),
            dcc.Tabs(
                [
                    dcc.Tab(
                        _overall_performance_content(),
                        label="Overall performance",
                        value=OVERALL_VIEW,
                        className="performance-tab",
                        selected_className="performance-tab performance-tab--selected",
                    ),
                    dcc.Tab(
                        _forecast_vs_actual_content(),
                        label="Forecast vs actual",
                        value=FORECAST_VS_ACTUAL_VIEW,
                        className="performance-tab",
                        selected_className="performance-tab performance-tab--selected",
                    ),
                ],
                id="performance-view-tabs",
                value=selected_view,
                className="performance-tabs",
                content_className="performance-tab-content",
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
    """Update the locked daily figures and errors within Forecast Performance."""

    return history_day_payload(selected_date)
