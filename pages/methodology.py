"""Recruiter-friendly explanation of the leakage-safe methodology."""

from dash import html

import dash

dash.register_page(
    __name__,
    path="/methodology",
    name="Methodology",
    title="Methodology | GB Renewable Forecast",
    order=3,
)


def _section(number: str, title: str, content) -> html.Section:
    children = [html.P(number, className="method-number"), html.H2(title)]
    if isinstance(content, list):
        children.extend(content)
    else:
        children.append(content)
    return html.Section(children, className="method-section")


def layout() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.P("Scientific design", className="eyebrow"),
                    html.H1("A leakage-safe day-ahead forecasting workflow"),
                    html.P(
                        "The methodology keeps the operational information set explicit while remaining reproducible and inspectable.",
                        className="page-lede",
                    ),
                ],
                className="page-heading",
            ),
            html.Div(
                [
                    _section(
                        "01",
                        "Objective",
                        html.P(
                            "Forecast GB embedded wind and solar generation for every settlement period of the following UK calendar day. Wind and solar are separate targets."
                        ),
                    ),
                    _section(
                        "02",
                        "Data",
                        [
                            html.P(
                                "Generation and capacity observations come from the National Energy System Operator (NESO). Weather inputs are ECMWF IFS HRES 9 km forecasts accessed through the Open-Meteo Single Runs API."
                            ),
                            html.P(
                                "Weather is sampled at 10 representative GB locations; these are not claimed to be renewable-capacity-weighted sites."
                            ),
                        ],
                    ),
                    _section(
                        "03",
                        "Forecast timing",
                        html.Dl(
                            [
                                html.Dt("Nominal issue time"),
                                html.Dd("09:00 Europe/London"),
                                html.Dt("Weather run"),
                                html.Dd("00 UTC ECMWF IFS HRES from the issue-date calendar day"),
                                html.Dt("Target"),
                                html.Dd("Every settlement period of the following local calendar day"),
                            ],
                            className="method-definitions",
                        ),
                    ),
                    _section(
                        "04",
                        "Leakage prevention",
                        html.Ul(
                            [
                                html.Li("Historical inputs use archived weather forecasts, not realised future weather."),
                                html.Li("Weather-run initialization, nominal issue time, and valid time remain distinct."),
                                html.Li("Train, validation, and test splits are chronological; random splitting is never used."),
                                html.Li("The consistent 00 UTC run is never silently replaced with a later cycle or another model."),
                            ]
                        ),
                    ),
                    _section(
                        "05",
                        "Modelling",
                        html.P(
                            "Wind uses XGBoost and solar uses ExtraTrees. Both predict capacity factor, which is physically bounded for inference and converted to MW using official embedded capacities. Observed historical capacity factors remain unaltered."
                        ),
                    ),
                    _section(
                        "06",
                        "Evaluation split",
                        [
                            html.Dl(
                                [
                                    html.Dt("Training"),
                                    html.Dd("1 Apr 2024 – 31 Mar 2025"),
                                    html.Dt("Validation"),
                                    html.Dd("1 Apr 2025 – 31 May 2025"),
                                    html.Dt("Test"),
                                    html.Dd("1 Jun 2025 – 31 Aug 2025"),
                                ],
                                className="method-definitions",
                            ),
                            html.P(
                                "Five individual official-source exclusions—6, 7, 8, 9 and 10 August 2025—are recorded in project provenance. The required consistent archived runs were unavailable or invalid; no substitute data were invented."
                            ),
                        ],
                    ),
                    _section(
                        "07",
                        "Limitations",
                        html.Ul(
                            [
                                html.Li("Ten representative locations are used instead of renewable-capacity-weighted weather grid cells."),
                                html.Li("The target is embedded generation, not all transmission-connected renewable generation in GB."),
                                html.Li("This is a portfolio and research demonstration, not a production trading forecast."),
                                html.Li("Accuracy varies across weather regimes and individual days."),
                            ]
                        ),
                    ),
                ],
                className="method-grid",
            ),
        ],
        className="page-stack",
    )
