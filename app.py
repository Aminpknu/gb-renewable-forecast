"""Public Dash application for GB embedded wind and solar forecasting."""

from __future__ import annotations

import os

import dash
from dash import Dash, dcc, html


app = Dash(
    __name__,
    use_pages=True,
    pages_folder="pages",
    suppress_callback_exceptions=True,
    title="GB Renewable Forecast",
    update_title="Updating forecast view…",
)
server = app.server


@server.get("/healthz")
def health_check() -> tuple[str, int]:
    """Lightweight Render health endpoint without data or model loading."""

    return "ok", 200


NAVIGATION = [
    ("Forecast", "/"),
    ("Performance", "/performance"),
    ("History", "/history"),
    ("Methodology", "/methodology"),
]

app.layout = html.Div(
    [
        html.Header(
            html.Div(
                [
                    dcc.Link(
                        [
                            html.Span("GB Renewable Forecast", className="brand-title"),
                            html.Span(
                                "Day-ahead embedded wind & solar generation forecasting",
                                className="brand-subtitle",
                            ),
                        ],
                        href="/",
                        className="brand-link",
                        title="Go to the day-ahead forecast",
                    ),
                    html.Nav(
                        [
                            dcc.Link(label, href=path, className="nav-link")
                            for label, path in NAVIGATION
                        ],
                        className="top-nav",
                        **{"aria-label": "Primary navigation"},
                    ),
                ],
                className="header-inner",
            ),
            className="site-header",
        ),
        html.Main(dash.page_container, className="page-shell"),
        html.Footer(
            [
                html.Span("GB embedded generation forecasting"),
                html.Span("Portfolio and research demonstration"),
            ],
            className="site-footer",
        ),
    ],
    className="app-root",
)


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8050")),
        debug=False,
    )
