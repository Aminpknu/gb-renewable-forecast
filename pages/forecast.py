"""Landing page for the latest Stage 7 day-ahead forecast."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from dash import Input, Output, callback, dcc, html

import dash
from app_utils.data_loading import (
    FORECAST_SUMMARY_PATH,
    LATEST_FORECAST_PATH,
    DashboardDataError,
    load_forecast_summary,
    load_latest_forecast,
)
from app_utils.figures import forecast_figure
from app_utils.formatting import (
    format_date,
    format_energy_mwh,
    format_local_time,
    format_power_mw,
)

dash.register_page(
    __name__,
    path="/",
    name="Forecast",
    title="Day-ahead Forecast | GB Renewable Forecast",
    order=0,
)


def _kpi_card(label: str, value: str, detail: str) -> html.Div:
    return html.Div(
        [
            html.Div(label, className="kpi-label"),
            html.Div(value, className="kpi-value"),
            html.Div(detail, className="kpi-detail"),
        ],
        className="kpi-card",
    )


def _context_item(label: str, value: str) -> html.Div:
    return html.Div(
        [html.Dt(label, className="context-label"), html.Dd(value, className="context-value")],
        className="context-item",
    )


def forecast_table_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Prepare a readable table for any valid settlement-day length."""

    return pd.DataFrame(
        {
            "Local time": frame["valid_time_local"].map(format_local_time),
            "Settlement period": frame["settlement_period"].astype(int),
            "Wind MW": frame["wind_forecast_mw"].round(1),
            "Wind CF": frame["wind_pred_cf"].round(3),
            "Solar MW": frame["solar_forecast_mw"].round(1),
            "Solar CF": frame["solar_pred_cf"].round(3),
        }
    )


def _forecast_table(frame: pd.DataFrame) -> html.Div:
    headers = [html.Th(column, scope="col") for column in frame.columns]
    rows = [
        html.Tr([html.Td(value) for value in row])
        for row in frame.itertuples(index=False, name=None)
    ]
    return html.Div(
        html.Table(
            [html.Thead(html.Tr(headers)), html.Tbody(rows)],
            id="forecast-table",
            className="data-table",
        ),
        className="table-scroll",
    )


def _empty_state(message: str | None = None) -> html.Div:
    detail = message or "The latest forecast outputs have not been generated in this environment."
    return html.Div(
        [
            html.P("Forecast output unavailable", className="empty-title"),
            html.P(detail, className="empty-copy"),
            html.P("Generate the current day-ahead forecast with:", className="empty-copy"),
            html.Code("python -m src.forecast_tomorrow", className="command-block"),
        ],
        className="empty-state",
        role="status",
    )


def build_forecast_content(
    forecast_path: Path | str = LATEST_FORECAST_PATH,
    summary_path: Path | str = FORECAST_SUMMARY_PATH,
) -> html.Div:
    """Build forecast content, returning a professional empty state on failure."""

    try:
        frame = load_latest_forecast(forecast_path)
        summary = load_forecast_summary(summary_path)
        table = forecast_table_frame(frame)
        created = pd.Timestamp(frame["forecast_created_utc"].iloc[0])
        issue = pd.Timestamp(summary["nominal_forecast_issue_time_local"])
        run = pd.Timestamp(summary["weather_run_init_utc"])
        target = summary["target_date"]
        summary["models"]["wind"]
        summary["models"]["solar"]
    except (FileNotFoundError, DashboardDataError, ValueError, KeyError) as error:
        return _empty_state(str(error))

    status = html.Div(
        [
            html.Span(f"Forecast target: {format_date(target)}"),
            html.Span(f"Forecast generated: {created.strftime('%d %b %Y %H:%M UTC')}"),
            html.Span(f"Weather run: ECMWF IFS HRES {run.strftime('%H:%M UTC')}"),
        ],
        className="status-strip",
        role="status",
    )

    return html.Div(
        [
            status,
            html.Div(
                [
                    _kpi_card(
                        "Peak wind generation",
                        format_power_mw(summary["peak_wind_mw"]),
                        format_local_time(summary["peak_wind_valid_time_local"]),
                    ),
                    _kpi_card(
                        "Peak solar generation",
                        format_power_mw(summary["peak_solar_mw"]),
                        format_local_time(summary["peak_solar_valid_time_local"]),
                    ),
                    _kpi_card(
                        "Forecast wind energy",
                        format_energy_mwh(summary["total_forecast_wind_energy_mwh"]),
                        f"{len(frame)} settlement periods",
                    ),
                    _kpi_card(
                        "Forecast solar energy",
                        format_energy_mwh(summary["total_forecast_solar_energy_mwh"]),
                        f"Target {format_date(target)}",
                    ),
                ],
                className="kpi-grid",
            ),
            html.Section(
                dcc.Graph(
                    figure=forecast_figure(frame),
                    config={"displayModeBar": False, "responsive": True},
                    className="chart",
                ),
                className="panel chart-panel",
                **{"aria-label": "Wind and solar day-ahead forecast chart"},
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.P("Forecast context", className="eyebrow"),
                            html.H2("Model and source contract"),
                            html.P(
                                "The dashboard presents Stage 7 outputs; it does not call live APIs or load models during page navigation.",
                                className="section-intro",
                            ),
                        ],
                        className="section-heading",
                    ),
                    html.Dl(
                        [
                            _context_item("Weather", summary["weather_model"]),
                            _context_item("Weather run initialization", run.strftime("%d %b %Y %H:%M UTC")),
                            _context_item("Nominal issue", issue.strftime("%d %b %Y %H:%M %Z")),
                            _context_item("Wind capacity", format_power_mw(summary["wind_capacity_mw"])),
                            _context_item("Solar capacity", format_power_mw(summary["solar_capacity_mw"])),
                            _context_item("Capacity source", summary["capacity_source"]),
                            _context_item("Capacity source date", format_date(summary["capacity_source_date"])),
                            _context_item("Wind model", summary["models"]["wind"]),
                            _context_item("Solar model", summary["models"]["solar"]),
                        ],
                        className="context-grid",
                    ),
                ],
                className="panel context-panel",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.P("Half-hour detail", className="eyebrow"),
                                    html.H2(f"All {len(frame)} settlement periods"),
                                ]
                            ),
                            html.Button(
                                "Download forecast CSV",
                                id="forecast-download-button",
                                className="button-primary",
                                type="button",
                            ),
                            dcc.Download(id="forecast-download"),
                        ],
                        className="section-heading-row",
                    ),
                    _forecast_table(table),
                ],
                className="panel table-panel",
            ),
        ],
        className="page-stack",
    )


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.P("Operational outlook", className="eyebrow"),
                    html.H1("Tomorrow's embedded generation forecast"),
                    html.P(
                        "Half-hourly GB embedded wind and solar generation, built from a consistent 00 UTC archived/live weather-run convention.",
                        className="page-lede",
                    ),
                ],
                className="page-heading",
            ),
            build_forecast_content(),
        ]
    )


@callback(
    Output("forecast-download", "data"),
    Input("forecast-download-button", "n_clicks"),
    prevent_initial_call=True,
)
def download_forecast(_n_clicks: int | None) -> dict[str, Any]:
    """Download the exact Stage 7 latest forecast CSV."""

    return dcc.send_file(str(LATEST_FORECAST_PATH), filename="latest_forecast.csv")
