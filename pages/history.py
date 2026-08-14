"""Backward-compatible redirect for the former Forecast vs Actual page."""

from __future__ import annotations

import dash
from dash import dcc, html

FORECAST_VS_ACTUAL_URL = "/performance?view=forecast-vs-actual"

dash.register_page(
    __name__,
    path="/history",
    name="Forecast vs Actual compatibility route",
    title="Opening Forecast Performance | GB Renewable Forecast",
    order=4,
)


def layout() -> html.Div:
    """Send legacy links to the integrated Forecast vs Actual view."""

    return html.Div(
        [
            dcc.Location(
                id="history-compatibility-redirect",
                href=FORECAST_VS_ACTUAL_URL,
                refresh=True,
            ),
            html.P("Opening Forecast vs Actual within Forecast Performance…"),
        ],
        className="empty-state",
    )


def history_day_payload(selected_date: str) -> tuple:
    """Preserve the former helper import while delegating to Performance."""

    from pages.performance import history_day_payload as integrated_payload

    return integrated_payload(selected_date)


__all__ = ["FORECAST_VS_ACTUAL_URL", "history_day_payload", "layout"]
