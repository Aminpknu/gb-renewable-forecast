"""Interactive UK heat and energy-network transition scenario page."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import dash
from dash import Input, Output, callback, dcc, html

from src.scenarios.calculations import calculate_scenario
from src.scenarios.repository import (
    load_active_scenarios,
    load_adjustable_assumptions,
    load_scenario_assumptions,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DB_PATH = PROJECT_ROOT / "data" / "scenarios" / "scenario_explorer.sqlite"

ADJUSTABLE_FIELDS = (
    "electricity_lrvc",
    "low_carbon_gas_cost",
    "carbon_value",
    "discount_rate",
    "heat_pump_capex",
    "low_carbon_gas_capex",
)

CONTROL_LABELS = {
    "electricity_lrvc": "Electricity LRVC (£/MWh)",
    "low_carbon_gas_cost": "Low-carbon gas cost (£/MWh)",
    "carbon_value": "Carbon value (£/tCO2e)",
    "discount_rate": "Discount rate (%)",
    "heat_pump_capex": "Heat-pump CAPEX (£/home)",
    "low_carbon_gas_capex": "Low-carbon-gas CAPEX (£/home)",
}

CONTROL_STEPS = {
    "electricity_lrvc": 1,
    "low_carbon_gas_cost": 1,
    "carbon_value": 1,
    "discount_rate": 0.1,
    "heat_pump_capex": 100,
    "low_carbon_gas_capex": 100,
}

dash.register_page(
    __name__,
    path="/scenarios",
    name="Scenarios",
    title="UK Energy Transition Scenarios | GB Renewable Forecast",
    order=3,
)


def _scenario_lookup(db_path: str | Path = SCENARIO_DB_PATH) -> dict[int, dict[str, object]]:
    return {
        int(scenario["scenario_id"]): scenario
        for scenario in load_active_scenarios(db_path)
    }


def default_scenario_id(db_path: str | Path = SCENARIO_DB_PATH) -> int:
    """Return the active Whole-system hybrid scenario ID from SQLite."""

    for scenario in load_active_scenarios(db_path):
        if scenario["scenario_name"] == "Whole-system hybrid":
            return int(scenario["scenario_id"])
    raise ValueError("The active Whole-system hybrid scenario is missing from SQLite.")


def adjustable_records(
    scenario_id: int, db_path: str | Path = SCENARIO_DB_PATH
) -> list[dict[str, object]]:
    """Return the six page controls, preserving their SQLite metadata."""

    records_by_name = {
        str(record["assumption_name"]): record
        for record in load_adjustable_assumptions(db_path, scenario_id)
    }
    missing = [name for name in ADJUSTABLE_FIELDS if name not in records_by_name]
    if missing:
        raise ValueError(f"Scenario {scenario_id} is missing adjustable assumptions: {missing}")
    return [records_by_name[name] for name in ADJUSTABLE_FIELDS]


def scenario_default_values(
    scenario_id: int, db_path: str | Path = SCENARIO_DB_PATH
) -> tuple[float, ...]:
    """Return the six SQLite defaults in stable control order."""

    return tuple(float(record["value"]) for record in adjustable_records(scenario_id, db_path))


def scenario_page_payload(
    scenario_id: int,
    overrides: Mapping[str, float],
    db_path: str | Path = SCENARIO_DB_PATH,
) -> dict[str, object]:
    """Calculate one in-memory page state from SQLite defaults and UI overrides."""

    scenarios = _scenario_lookup(db_path)
    if scenario_id not in scenarios:
        raise ValueError(f"Active scenario ID {scenario_id} does not exist.")

    missing = [name for name in ADJUSTABLE_FIELDS if name not in overrides]
    if missing:
        raise ValueError(f"Missing adjustable values: {missing}")

    assumption_bundle = load_scenario_assumptions(db_path, scenario_id)
    assumptions = dict(assumption_bundle["values"])
    for name in ADJUSTABLE_FIELDS:
        value = overrides[name]
        if value is None:
            raise ValueError(f"{CONTROL_LABELS[name]} requires a numeric value.")
        assumptions[name] = float(value)

    scenario = scenarios[scenario_id]
    results = calculate_scenario(
        assumptions,
        scenario_name=str(scenario["scenario_name"]),
    )
    metadata = adjustable_records(scenario_id, db_path)
    for record in metadata:
        record["value"] = assumptions[str(record["assumption_name"])]

    return {
        "scenario": scenario,
        "assumptions": assumptions,
        "adjustable_metadata": metadata,
        "results": results,
    }


def _kpi_card(label: str, value: str, detail: str = "") -> html.Div:
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


def _format_kpis(results: Mapping[str, float]) -> list[html.Div]:
    return [
        _kpi_card(
            "Financial annual cost",
            f"£{results['financial_annual_cost_gbp'] / 1e9:.2f} bn/year",
        ),
        _kpi_card(
            "Social annual cost",
            f"£{results['social_annual_cost_gbp'] / 1e9:.2f} bn/year",
            "Includes monetised carbon impact",
        ),
        _kpi_card(
            "Annual emissions",
            f"{results['annual_emissions_tco2e'] / 1e6:.3f} MtCO2e/year",
        ),
        _kpi_card(
            "Initial investment",
            f"£{results['initial_investment_gbp'] / 1e9:.2f} bn",
        ),
        _kpi_card(
            "Electricity peak proxy",
            f"{results['electricity_peak_mw']:,.0f} MW",
            "Strategic proxy, not a network forecast",
        ),
        _kpi_card(
            "Gas-network utilisation proxy",
            f"{results['gas_network_utilisation_pct']:.1f}%",
            "Relative to the model's reference throughput",
        ),
    ]


def _format_pathway(payload: Mapping[str, object]) -> list:
    scenario = payload["scenario"]
    assumptions = payload["assumptions"]
    results = payload["results"]
    return [
        html.P(str(scenario["description"]), className="section-intro scenario-description"),
        html.Dl(
            [
                _context_item("Electric heat share", f"{assumptions['electric_heat_share'] * 100:.0f}%"),
                _context_item(
                    "Low-carbon-gas heat share",
                    f"{assumptions['low_carbon_gas_heat_share'] * 100:.0f}%",
                ),
                _context_item(
                    "Electricity demand",
                    f"{results['electricity_demand_mwh'] / 1e6:.2f} TWh/year",
                ),
                _context_item(
                    "Low-carbon-gas demand",
                    f"{results['low_carbon_gas_demand_mwh'] / 1e6:.2f} TWh/year",
                ),
            ],
            className="context-grid scenario-context-grid",
        ),
    ]


def _metadata_value(value: object, suffix: str) -> str:
    return "Not specified" if value is None else f"{value}{suffix}"


def _format_sources(records: list[dict[str, object]]) -> list[html.Div]:
    items = []
    for record in records:
        name = str(record["assumption_name"])
        items.append(
            html.Div(
                [
                    html.Strong(CONTROL_LABELS[name]),
                    html.Span(f"{float(record['value']):,.2f} {record['unit'] or ''}".strip()),
                    html.Span(
                        "Reference year: " + _metadata_value(record["reference_year"], ""),
                        className="source-meta",
                    ),
                    html.Span(
                        "Price base: " + _metadata_value(record["price_base_year"], ""),
                        className="source-meta",
                    ),
                    html.P(record["source_note"] or "No source note recorded.", className="source-note"),
                ],
                className="assumption-source-item",
            )
        )
    return items


def _control(record: dict[str, object]) -> html.Div:
    name = str(record["assumption_name"])
    default = float(record["value"])
    return html.Div(
        [
            html.Label(CONTROL_LABELS[name], htmlFor=f"scenario-input-{name}", className="input-label"),
            dcc.Input(
                id=f"scenario-input-{name}",
                type="number",
                value=default,
                min=0,
                max=max(default * 3, 1),
                step=CONTROL_STEPS[name],
                debounce=False,
                className="scenario-number-input",
            ),
        ],
        className="scenario-control",
    )


def layout() -> html.Div:
    scenarios = load_active_scenarios(SCENARIO_DB_PATH)
    selected_id = default_scenario_id(SCENARIO_DB_PATH)
    records = adjustable_records(selected_id, SCENARIO_DB_PATH)
    defaults = {name: value for name, value in zip(ADJUSTABLE_FIELDS, scenario_default_values(selected_id))}
    payload = scenario_page_payload(selected_id, defaults, SCENARIO_DB_PATH)

    return html.Div(
        [
            html.Div(
                [
                    html.P("Strategic analysis", className="eyebrow"),
                    html.H1("UK Heat and Energy Network Transition Explorer"),
                    html.P(
                        "An interactive techno-economic comparison of electrification, hybrid and low-carbon-gas pathways",
                        className="page-lede",
                    ),
                    html.P(
                        "The tool compares simplified illustrative 2050 heat-decarbonisation pathways for an illustrative portfolio of one million homes.",
                        className="scenario-scope",
                    ),
                    html.P(
                        "These are simplified illustrative scenarios informed by published UK energy-transition evidence. They do not reproduce NESO’s full Future Energy Scenarios methodology and should not be interpreted as forecasts or investment recommendations.",
                        className="scenario-disclaimer",
                    ),
                ],
                className="page-heading scenario-heading",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Label("Scenario pathway", htmlFor="scenario-selector", className="input-label"),
                            dcc.Dropdown(
                                id="scenario-selector",
                                options=[
                                    {"label": scenario["scenario_name"], "value": scenario["scenario_id"]}
                                    for scenario in scenarios
                                ],
                                value=selected_id,
                                clearable=False,
                                searchable=False,
                            ),
                        ],
                        className="scenario-selector",
                    ),
                    html.Button(
                        "Reset to defaults",
                        id="scenario-reset-button",
                        type="button",
                        className="button-primary",
                    ),
                ],
                className="panel scenario-toolbar",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.P("Adjustable assumptions", className="eyebrow"),
                            html.H2("Test the economic inputs"),
                            html.P(
                                "Changes are calculated in memory and are not written back to SQLite.",
                                className="section-intro",
                            ),
                        ],
                        className="section-heading",
                    ),
                    html.Div([_control(record) for record in records], className="scenario-control-grid"),
                ],
                className="panel context-panel",
            ),
            html.Div(_format_kpis(payload["results"]), id="scenario-kpis", className="scenario-kpi-grid"),
            html.Section(
                [
                    html.Div(
                        [html.P("Selected pathway", className="eyebrow"), html.H2("Energy-system context")],
                        className="section-heading",
                    ),
                    html.Div(_format_pathway(payload), id="scenario-pathway-details"),
                ],
                className="panel context-panel",
            ),
            html.Details(
                [
                    html.Summary("Assumptions and sources"),
                    html.Div(
                        _format_sources(payload["adjustable_metadata"]),
                        id="scenario-source-details",
                        className="assumption-source-grid",
                    ),
                ],
                className="panel scenario-details",
            ),
        ],
        className="page-stack",
    )


@callback(
    *[Output(f"scenario-input-{name}", "value") for name in ADJUSTABLE_FIELDS],
    Input("scenario-selector", "value"),
    Input("scenario-reset-button", "n_clicks"),
)
def refresh_scenario_defaults(scenario_id: int, _reset_clicks: int | None) -> tuple[float, ...]:
    """Refresh all six controls from the selected scenario's SQLite defaults."""

    return scenario_default_values(scenario_id, SCENARIO_DB_PATH)


@callback(
    Output("scenario-kpis", "children"),
    Output("scenario-pathway-details", "children"),
    Output("scenario-source-details", "children"),
    Input("scenario-selector", "value"),
    *[Input(f"scenario-input-{name}", "value") for name in ADJUSTABLE_FIELDS],
)
def update_scenario_outputs(scenario_id: int, *values: float) -> tuple[list, list, list]:
    """Recalculate display values in memory from the six current controls."""

    overrides = dict(zip(ADJUSTABLE_FIELDS, values))
    payload = scenario_page_payload(scenario_id, overrides, SCENARIO_DB_PATH)
    return (
        _format_kpis(payload["results"]),
        _format_pathway(payload),
        _format_sources(payload["adjustable_metadata"]),
    )
