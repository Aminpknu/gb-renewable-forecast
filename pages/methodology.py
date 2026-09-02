"""Web-native models, data, validation, and provenance guide."""

from __future__ import annotations

from pathlib import Path

import dash
from dash import dcc, html

from app_utils.data_loading import load_final_test_metrics, load_model_metadata
from src.scenarios.repository import load_active_scenarios, load_scenario_assumptions


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DB_PATH = PROJECT_ROOT / "data" / "scenarios" / "scenario_explorer.sqlite"

SOURCE_INFORMED_ASSUMPTIONS = {
    "discount_rate",
    "carbon_value",
    "electricity_lrvc",
    "gas_lrvc",
    "heat_pump_cop",
    "gas_heating_efficiency",
    "electricity_emissions_factor",
}

ASSUMPTION_LABELS = {
    "number_homes": "Portfolio homes",
    "useful_heat_per_home": "Useful heat per home",
    "electric_heat_share": "Electric heat share",
    "low_carbon_gas_heat_share": "Low-carbon-gas heat share",
    "heat_pump_cop": "Heat-pump COP",
    "gas_heating_efficiency": "Gas-heating efficiency",
    "electricity_lrvc": "Electricity LRVC",
    "gas_lrvc": "Natural-gas LRVC benchmark",
    "low_carbon_gas_cost": "Low-carbon-gas cost",
    "electricity_emissions_factor": "Electricity emissions factor",
    "low_carbon_gas_emissions_factor": "Low-carbon-gas emissions factor",
    "carbon_value": "Carbon appraisal value",
    "heat_pump_capex": "Heat-pump CAPEX",
    "low_carbon_gas_capex": "Low-carbon-gas CAPEX",
    "heat_pump_lifetime": "Heat-pump lifetime",
    "low_carbon_gas_lifetime": "Low-carbon-gas lifetime",
    "discount_rate": "Discount rate",
    "peak_heat_kw_per_home": "Peak heat per home proxy",
}

ASSUMPTION_ROLES = {
    "number_homes": "Sets the illustrative portfolio scale.",
    "useful_heat_per_home": "Converts homes into annual useful heat.",
    "electric_heat_share": "Allocates useful heat to heat pumps.",
    "low_carbon_gas_heat_share": "Allocates useful heat to gas heating.",
    "heat_pump_cop": "Converts electric useful heat into electricity demand.",
    "gas_heating_efficiency": "Converts gas useful heat into gas demand.",
    "electricity_lrvc": "Prices annual electricity consumption.",
    "gas_lrvc": "Background natural-gas benchmark; not a model cost input.",
    "low_carbon_gas_cost": "Prices annual low-carbon-gas consumption.",
    "electricity_emissions_factor": "Converts electricity demand into emissions.",
    "low_carbon_gas_emissions_factor": "Converts gas demand into emissions.",
    "carbon_value": "Monetises emissions in social annual cost.",
    "heat_pump_capex": "Sets heat-pump investment per electric-heated home.",
    "low_carbon_gas_capex": "Sets gas-system investment per gas-heated home.",
    "heat_pump_lifetime": "Annualises heat-pump investment through CRF.",
    "low_carbon_gas_lifetime": "Annualises gas-system investment through CRF.",
    "discount_rate": "Converts stored percent to the CRF decimal rate.",
    "peak_heat_kw_per_home": "Builds the illustrative electricity peak proxy.",
}

FORECAST_TERMS = (
    ("Embedded generation", "Small-scale generation connected within distribution networks and represented in NESO embedded-generation data; it is not all GB renewable output."),
    ("Day-ahead forecast", "A prediction issued today for every settlement period of the following UK local calendar day."),
    ("Settlement period", "A numbered 30-minute GB electricity-market interval. A local day can contain 46, 48 or 50 periods around clock changes."),
    ("Issue time", "The nominal time when this project makes its forecast: 09:00 Europe/London."),
    ("Weather-run initialization", "The time the numerical weather model run begins. This project uses the issue-day ECMWF 00 UTC run; it is distinct from issue time."),
    ("Valid time", "The timestamp for which a weather value or generation forecast applies."),
    ("Capacity factor", "Generation divided by installed capacity, expressed as a unitless fraction."),
    ("Predicted MW", "The model-predicted capacity factor multiplied by embedded capacity."),
    ("Actual MW", "The later observed NESO estimated embedded generation used only as the evaluation target."),
    ("MAE", "Mean absolute error: the average magnitude of forecast errors in MW."),
    ("Bias", "Mean forecast-minus-actual error in MW; positive bias means average overprediction."),
    ("R²", "The proportion of observed variation explained relative to predicting the test-set mean; higher is better."),
    ("Skill versus baseline", "The percentage reduction in MAE relative to monthly climatology; positive skill means the model improves on the baseline."),
)

SCENARIO_TERMS = (
    ("Useful heat", "Heat delivered to homes before accounting for technology conversion efficiency, measured in MWh/year."),
    ("COP", "Heat-pump coefficient of performance: useful heat delivered per unit of electricity consumed."),
    ("Gas-heating efficiency", "Useful heat delivered divided by gas energy consumed."),
    ("LRVC", "Long-run variable cost: an energy cost benchmark in GBP/MWh."),
    ("CAPEX", "Initial technology capital expenditure, shown in GBP and kept separate from annual costs."),
    ("CRF", "Capital recovery factor: converts an investment into an equivalent annual cost using a discount rate and lifetime."),
    ("Financial annual cost", "Annual energy cost plus annualised technology CAPEX, in GBP/year."),
    ("Carbon impact", "Physical emissions multiplied by the carbon appraisal value, in GBP/year."),
    ("Social annual cost", "Financial annual cost plus monetised carbon impact, in GBP/year."),
    ("Electricity peak proxy", "A simplified portfolio peak-demand indicator in MW, not a network power-flow result."),
    ("Gas-network-utilisation proxy", "Gas throughput relative to the model's illustrative reference throughput, in percent—not physical GB network capacity."),
    ("One-at-a-time sensitivity", "A deterministic test that changes one assumption while holding every other input fixed."),
)

SCENARIO_EQUATIONS = (
    ("Total useful heat", r"Q_{total}=N_{homes}\times q_{home}", "Multiplies the number of homes [homes] by useful heat per home [MWh/home/year] to obtain annual useful heat [MWh/year].", "N_homes: homes; q_home: MWh/home/year; Q_total: MWh/year."),
    ("Heat allocation", r"Q_e=s_eQ_{total},\quad Q_g=s_gQ_{total},\quad s_e+s_g=1", "Allocates annual useful heat between electric and low-carbon-gas technologies using unitless pathway shares.", "s_e, s_g: unitless shares; Q_e, Q_g and Q_total: MWh/year."),
    ("Final energy demand", r"E_e=\frac{Q_e}{COP},\quad E_g=\frac{Q_g}{\eta_g}", "Accounts for heat-pump performance and gas-heating efficiency to calculate purchased electricity and gas.", "COP and eta_g: unitless; E_e and E_g: MWh/year."),
    ("Annual energy cost", r"C_{energy}=E_eP_e+E_gP_g", "Prices annual electricity and low-carbon-gas demand.", "P_e and P_g: GBP/MWh; C_energy: GBP/year."),
    ("Capital recovery factor", r"CRF=\frac{r(1+r)^n}{(1+r)^n-1}", "Converts an upfront investment into an equivalent annual stream.", "r: decimal discount rate; n: years; CRF: annual unitless factor."),
    ("Annualised CAPEX", r"C_{CAPEX,annual}=I_{HP}CRF_{HP}+I_{gas}CRF_{gas}", "Annualises heat-pump and gas-system investments separately before adding them.", "I_HP and I_gas: GBP; CRF: per year; C_CAPEX,annual: GBP/year."),
    ("Emissions", r"Emissions=E_eEF_e+E_gEF_g", "Applies technology-specific emissions factors to annual energy demand.", "EF_e and EF_g: tCO2e/MWh; Emissions: tCO2e/year."),
    ("Financial annual cost", r"C_{financial}=C_{energy}+C_{CAPEX,annual}", "Combines recurring energy cost and annualised investment without monetised carbon.", "All C terms: GBP/year."),
    ("Social annual cost", r"C_{social}=C_{financial}+Emissions\times V_{carbon}", "Adds monetised carbon impact; changing carbon value does not change physical emissions.", "V_carbon: GBP/tCO2e; C_social: GBP/year."),
    ("Electricity peak proxy", r"P_{peak}=\frac{N_e q_{peak}}{COP\times1000}", "Estimates a portfolio electricity peak proxy from electric-heated homes and coincident peak heat.", "N_e: homes; q_peak: kW/home; P_peak: MW."),
    ("Gas utilisation proxy", r"U_g=\frac{E_g}{E_{g,reference}}\times100", "Compares gas demand with the illustrative reference throughput; it is not physical network utilisation.", "E_g and E_g,reference: MWh/year; U_g: percent."),
)


dash.register_page(
    __name__,
    path="/methodology",
    name="Models, Data & Validation",
    title="Models, Data & Validation | GB Renewable Forecast",
    order=4,
)


def guide_data(db_path: str | Path = SCENARIO_DB_PATH) -> dict[str, object]:
    """Load authoritative forecast evidence and scenario metadata for the guide."""

    metadata = load_model_metadata()
    metrics = load_final_test_metrics().set_index("Technology")
    scenarios = load_active_scenarios(db_path)
    scenario_rows = []
    for scenario in scenarios:
        bundle = load_scenario_assumptions(db_path, int(scenario["scenario_id"]))
        values = bundle["values"]
        scenario_rows.append(
            {
                **scenario,
                "electric_share": float(values["electric_heat_share"]),
                "gas_share": float(values["low_carbon_gas_heat_share"]),
            }
        )

    reference_bundle = load_scenario_assumptions(db_path, 2)
    assumption_rows = []
    for record in reference_bundle["records"]:
        name = str(record["assumption_name"])
        assumption_rows.append(
            {
                **record,
                "display_name": ASSUMPTION_LABELS[name],
                "evidence_type": (
                    "Source-informed" if name in SOURCE_INFORMED_ASSUMPTIONS else "Illustrative"
                ),
                "role": ASSUMPTION_ROLES[name],
            }
        )

    return {
        "metadata": metadata,
        "metrics": {
            "wind": {
                "model": metadata["wind_model"]["algorithm"],
                "mae_mw": float(metrics.loc["Wind", "MAE_MW"]),
                "r2": float(metrics.loc["Wind", "R2"]),
                "skill_pct": float(metrics.loc["Wind", "Skill_vs_baseline_pct"]),
            },
            "solar": {
                "model": metadata["solar_model"]["algorithm"],
                "mae_mw": float(metrics.loc["Solar", "MAE_MW"]),
                "r2": float(metrics.loc["Solar", "R2"]),
                "skill_pct": float(metrics.loc["Solar", "Skill_vs_baseline_pct"]),
            },
        },
        "scenarios": scenario_rows,
        "assumptions": assumption_rows,
    }


def _section_heading(eyebrow: str, title: str, intro: str | None = None) -> html.Div:
    children = [html.P(eyebrow, className="eyebrow"), html.H2(title)]
    if intro:
        children.append(html.P(intro, className="section-intro"))
    return html.Div(children, className="section-heading")


def _definition_grid(items: tuple[tuple[str, str], ...]) -> html.Dl:
    children = []
    for term, definition in items:
        children.extend([html.Dt(term), html.Dd(definition)])
    return html.Dl(children, className="guide-definition-grid")


def _workflow(title: str, steps: tuple[str, ...], accent: str) -> html.Article:
    track = []
    for index, step in enumerate(steps):
        track.append(html.Div(step, className="workflow-step"))
        if index < len(steps) - 1:
            track.append(html.Span("→", className="workflow-arrow", **{"aria-hidden": "true"}))
    return html.Article(
        [html.H3(title), html.Div(track, className="workflow-track")],
        className=f"workflow-card {accent}",
    )


def _roadmap_card(part: str, title: str, summary: str, href: str, accent: str) -> html.Article:
    return html.Article(
        [
            html.P(part, className="roadmap-part-label"),
            html.H3(title),
            html.P(summary),
            html.A(f"Go to {part}", href=href, className="roadmap-link"),
        ],
        className=f"roadmap-card {accent}",
    )


def _metric_card(label: str, metric: dict[str, object], accent: str) -> html.Article:
    return html.Article(
        [
            html.Div([html.Strong(label), html.Span(str(metric["model"]))], className="guide-metric-head"),
            html.Div(f"{float(metric['mae_mw']):,.1f} MW MAE", className="guide-metric-value"),
            html.Div(
                [
                    html.Span(f"R² {float(metric['r2']):.3f}"),
                    html.Span(f"{float(metric['skill_pct']):.1f}% lower MAE than climatology"),
                ],
                className="guide-metric-meta",
            ),
        ],
        className=f"guide-metric-card {accent}",
    )


def _equation_card(title: str, equation: str, interpretation: str, symbols: str) -> html.Article:
    return html.Article(
        [
            html.H4(title),
            dcc.Markdown(f"$${equation}$$", mathjax=True, className="equation-markdown"),
            html.P(interpretation),
            html.P([html.Strong("Symbols and units: "), symbols], className="symbol-note"),
        ],
        className="equation-card",
    )


def _scenario_cards(scenarios: list[dict[str, object]]) -> html.Div:
    cards = []
    for scenario in scenarios:
        cards.append(
            html.Article(
                [
                    html.H3(str(scenario["scenario_name"])),
                    html.Div(
                        [
                            html.Strong(f"{float(scenario['electric_share']):.0%} electric heat"),
                            html.Span(f"{float(scenario['gas_share']):.0%} low-carbon gas"),
                        ],
                        className="pathway-shares",
                    ),
                    html.P(str(scenario["description"])),
                ],
                className="pathway-card",
            )
        )
    return html.Div(cards, className="pathway-grid")


def _format_assumption_value(record: dict[str, object]) -> str:
    name = str(record["assumption_name"])
    if name in {"electric_heat_share", "low_carbon_gas_heat_share"}:
        return "Varies by pathway"
    value = float(record["value"])
    if value >= 1000:
        return f"{value:,.0f}"
    return f"{value:,.3f}".rstrip("0").rstrip(".")


def _assumption_table(records: list[dict[str, object]]) -> html.Div:
    headers = ("Assumption", "Value", "Unit", "Type", "Control", "Reference", "Price base", "Source / rationale", "Role")
    rows = []
    for record in records:
        rows.append(
            html.Tr(
                [
                    html.Td(record["display_name"]),
                    html.Td(_format_assumption_value(record)),
                    html.Td(record["unit"] or "—"),
                    html.Td(record["evidence_type"]),
                    html.Td("Adjustable" if record["is_user_adjustable"] else "Fixed"),
                    html.Td(record["reference_year"] or "—"),
                    html.Td(record["price_base_year"] or "—"),
                    html.Td(record["source_note"] or "—"),
                    html.Td(record["role"]),
                ]
            )
        )
    return html.Div(
        html.Table(
            [html.Thead(html.Tr([html.Th(header, scope="col") for header in headers])), html.Tbody(rows)],
            className="data-table provenance-table",
        ),
        className="table-scroll",
    )


def layout() -> html.Div:
    data = guide_data()
    metrics = data["metrics"]
    metadata = data["metadata"]
    scenarios = data["scenarios"]
    assumptions = data["assumptions"]

    forecast_flow = _workflow(
        "How the forecast is produced",
        (
            "Archived/live ECMWF forecasts",
            "Leakage-safe features",
            "Wind spatial XGBoost / solar spatial XGBoost",
            "Predicted capacity factor",
            "NESO embedded capacity",
            "Day-ahead forecast in MW",
        ),
        "forecast-workflow",
    )
    scenario_flow = _workflow(
        "How the scenario results are produced",
        (
            "SQLite assumptions",
            "Read-only repository",
            "Python calculations",
            "Scenario inputs",
            "Costs / emissions / network proxies",
            "Sensitivity",
        ),
        "scenario-workflow",
    )

    return html.Div(
        [
            html.Div(
                [
                    html.P("Technical transparency", className="eyebrow"),
                    html.H1("Models, Data & Validation Guide"),
                    html.P(
                        "A practical guide to what each model does, how it works, and how far its conclusions can be taken.",
                        className="page-lede",
                    ),
                ],
                className="page-heading",
            ),
            html.Section(
                [
                    _section_heading(
                        "Start here",
                        "How to read this guide",
                        "This page explains the app in three parts.",
                    ),
                    html.Nav(
                        [
                            _roadmap_card(
                                "Part A",
                                "Day-ahead renewable forecasting",
                                "How the app estimates tomorrow's half-hourly embedded wind and solar generation.",
                                "#forecasting",
                                "forecast-roadmap",
                            ),
                            html.Span("→", className="roadmap-arrow", **{"aria-hidden": "true"}),
                            _roadmap_card(
                                "Part B",
                                "2050 energy-transition scenario analysis",
                                "How the app explores what different heat-transition choices could imply.",
                                "#scenario-analysis",
                                "scenario-roadmap",
                            ),
                            html.Span("→", className="roadmap-arrow", **{"aria-hidden": "true"}),
                            _roadmap_card(
                                "Part C",
                                "Reproducibility & technical evidence",
                                "How both models are kept transparent, testable and separate.",
                                "#reproducibility",
                                "shared-roadmap",
                            ),
                        ],
                        className="roadmap-flow",
                        **{"aria-label": "Guide roadmap"},
                    ),
                    html.P(
                        "The forecasting model predicts an observable future outcome. The scenario model explores what-if pathways. They share one application, but they are separate analytical models.",
                        className="separation-note",
                    ),
                ],
                id="model-scope",
                className="guide-section",
            ),
            html.Section(
                [
                    html.Div(
                        [html.P("Part A", className="part-label"), html.H2("Day-ahead renewable forecasting")],
                        className="part-divider forecast-divider",
                    ),
                    html.Div(
                        [
                            _section_heading("The question", "What does the forecasting model predict?"),
                            html.P("It estimates GB embedded wind and solar generation in MW for every 30-minute settlement period of the following UK local calendar day."),
                            forecast_flow,
                        ],
                        className="guide-subsection",
                    ),
                    html.Div(
                        [
                            _section_heading("Inputs and timing", "What data does it use?"),
                            html.Article(
                                [
                                    html.Dl(
                                        [
                                            html.Dt("Generation / capacity"), html.Dd("National Energy System Operator (NESO)"),
                                            html.Dt("Weather"), html.Dd("ECMWF IFS HRES 9 km via Open-Meteo Single Runs"),
                                            html.Dt("Sampling"), html.Dd("Ten representative GB locations"),
                                            html.Dt("Nominal issue"), html.Dd("09:00 Europe/London"),
                                            html.Dt("Weather run"), html.Dd("Issue-day 00 UTC"),
                                            html.Dt("Target"), html.Dd("Following UK local calendar day"),
                                            html.Dt("Resolution"), html.Dd("30 minutes; 46, 48 or 50 periods"),
                                        ],
                                        className="method-definitions",
                                    ),
                                ],
                                className="guide-subpanel",
                            ),
                        ],
                        className="guide-subsection",
                    ),
                    html.Div(
                        [
                            _section_heading("Model formulation", "How does the model turn weather into a generation forecast?"),
                            html.Article(
                                [
                                    dcc.Markdown(
                                        r"$$\widehat{G}_t\;[\mathrm{MW}]=\widehat{CF}_t\;[-]\times K_t\;[\mathrm{MW}]$$",
                                        mathjax=True,
                                        className="equation-markdown hero-equation",
                                    ),
                                    html.P([html.Strong("Symbols: "), "Ĝₜ is predicted generation in MW; CF̂ₜ is predicted capacity factor, a unitless fraction; Kₜ is official embedded capacity in MW; t is the settlement-period valid time."]),
                                    html.P(f"Wind uses {metadata['wind_model']['algorithm']}; solar uses {metadata['solar_model']['algorithm']}. Each model predicts capacity factor, which is then converted to MW using embedded capacity."),
                                ],
                                className="guide-subpanel",
                            ),
                            html.Details(
                                [html.Summary("Forecasting terminology"), _definition_grid(FORECAST_TERMS)],
                                className="guide-details panel",
                            ),
                        ],
                        className="guide-subsection",
                    ),
                    html.Div(
                        [
                            _section_heading("Locked test evidence", "How accurate is it?", "The figures below come from the previously untouched chronological test period."),
                            html.Div([_metric_card("Wind", metrics["wind"], "wind-accent"), _metric_card("Solar", metrics["solar"], "solar-accent")], className="guide-metric-grid"),
                            html.Details(
                                [
                                    html.Summary("How the validation metrics are calculated"),
                                    html.Div(
                                        [
                                            _equation_card("MAE", r"MAE=\frac{1}{n}\sum_{t=1}^{n}|\widehat{G}_t-G_t|", "Average absolute forecast error; it shows how far predictions were from actual generation, regardless of direction.", "Ĝ_t and G_t: predicted and actual MW; n: settlement-period observations; MAE: MW."),
                                            _equation_card("Bias", r"Bias=\frac{1}{n}\sum_{t=1}^{n}(\widehat{G}_t-G_t)", "Average signed error; positive values mean overprediction and negative values mean underprediction.", "Ĝ_t and G_t: MW; Bias: MW."),
                                            _equation_card("R²", r"R^2=1-\frac{\sum_t(G_t-\widehat{G}_t)^2}{\sum_t(G_t-\overline{G})^2}", "Compares squared model error with variation around the observed mean.", "Ḡ: mean actual MW; R²: unitless."),
                                            _equation_card("Skill versus baseline", r"Skill=\left(1-\frac{MAE_{model}}{MAE_{baseline}}\right)\times100", "Shows the percentage reduction in MAE relative to monthly climatology.", "Both MAEs: MW; Skill: percent."),
                                        ],
                                        className="equation-grid validation-equations",
                                    ),
                                ],
                                className="guide-details panel",
                            ),
                        ],
                        id="forecast-validation",
                        className="guide-subsection",
                    ),
                    html.Div(
                        [
                            _section_heading("Observed evidence", "What did the model predict, and what actually happened?"),
                            html.P("The locked half-hourly predictions can be compared directly with the later NESO observations for real test dates."),
                            html.Div([dcc.Link("Open Forecast Performance", href="/performance", className="button-primary guide-button"), dcc.Link("Open Forecast vs Actual view", href="/performance?view=forecast-vs-actual", className="guide-text-link")], className="guide-link-row"),
                            html.P("Forecast vs Actual shows predicted and observed wind and solar generation, together with daily MAE and bias.", className="section-note"),
                        ],
                        className="validation-callout guide-subsection",
                    ),
                    html.Div(
                        [
                            _section_heading("Evaluation design", "How do we avoid data leakage?"),
                            html.Ul(
                                [
                                    html.Li("Backtests use archived weather forecasts; realised future weather is not a predictor."),
                                    html.Li("All development folds and the locked test are chronological; there is no random split."),
                                    html.Li("Hyperparameters and model families are selected only on four expanding development folds; final metrics use the locked Apr–Jun 2026 test."),
                                    html.Li("Monthly half-hour climatology fitted only on development data remains the baseline comparison."),
                                    html.Li("The five Aug 2025 archive gaps and the reproducible 24 Jun 2026 temperature gap are excluded explicitly rather than filled or substituted."),
                                    html.Li("46-, 48- and 50-period local days are handled explicitly."),
                                    html.Li("Locked test predictions remain committed and inspectable."),
                                    html.Li("An aborted first evaluator read occurred after candidate freeze and before any holdout predictions or metrics were produced; the incident is documented in docs/locked_test_access_incident.json."),
                                ],
                                className="trust-checklist",
                            ),
                            html.Dl([html.Dt("Development"), html.Dd("1 Apr 2024 – 31 Mar 2026"), html.Dt("Selection"), html.Dd("Four expanding chronological folds"), html.Dt("Locked test"), html.Dd("1 Apr 2026 – 30 Jun 2026; 90 usable days")], className="method-definitions compact-splits"),
                        ],
                        className="trust-panel guide-subsection",
                    ),
                    html.Div(
                        [
                            _section_heading("Boundaries", "What are the forecasting limitations?"),
                            html.Ul(
                                [
                                    html.Li("The target is embedded wind and solar, not all GB renewable generation."),
                                    html.Li("Weather is represented by ten representative locations."),
                                    html.Li("Accuracy varies by day and weather regime."),
                                    html.Li("This is not a production trading or dispatch forecast."),
                                ]
                            ),
                        ],
                        className="limitation-panel forecast-limitations guide-subsection",
                    ),
                ],
                id="forecasting",
                className="guide-part forecast-part",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.P("Part B", className="part-label"),
                            html.H2("2050 energy-transition scenario analysis"),
                            html.P("This model is for strategic exploration, not prediction. It compares three simplified 2050 heat pathways for an illustrative portfolio of one million homes."),
                        ],
                        className="part-divider scenario-divider",
                    ),
                    html.Div(
                        [
                            _section_heading("Pathways", "What are the three scenarios?", "They are directional modelling choices, not probabilities, official NESO projections, or forecasts of what will happen in 2050."),
                            _scenario_cards(scenarios),
                        ],
                        className="guide-subsection",
                    ),
                    html.Div(
                        [
                            _section_heading("Scenario design", "What changes between scenarios?"),
                            html.Div(
                                [
                                    html.Article([html.H3("What changes"), html.P("The share of useful heat supplied by electricity and low-carbon gas: 80/20, 50/50 or 20/80.")], className="guide-subpanel"),
                                    html.Article([html.H3("What stays fixed by default"), html.P("The one-million-home boundary, heat demand, technology performance, energy prices, emissions factors, CAPEX, lifetimes, discount rate and peak-heat proxy.")], className="guide-subpanel"),
                                ],
                                className="guide-two-column",
                            ),
                            html.Details([html.Summary("Scenario terminology"), _definition_grid(SCENARIO_TERMS)], className="guide-details panel"),
                        ],
                        className="guide-subsection",
                    ),
                    html.Div(
                        [
                            _section_heading("Calculation flow", "How are the outputs calculated?"),
                            scenario_flow,
                            html.P("The equations below document the existing pure calculation module; this page does not reimplement them.", className="section-note"),
                            html.Div(
                                [
                                    html.Details([html.Summary("Energy"), html.Div([_equation_card(*equation) for equation in SCENARIO_EQUATIONS[0:4]], className="equation-grid scenario-equations")], className="guide-details panel"),
                                    html.Details([html.Summary("Investment"), html.Div([_equation_card(*equation) for equation in SCENARIO_EQUATIONS[4:6]], className="equation-grid scenario-equations")], className="guide-details panel"),
                                    html.Details([html.Summary("Emissions and costs"), html.Div([_equation_card(*equation) for equation in SCENARIO_EQUATIONS[6:9]], className="equation-grid scenario-equations")], className="guide-details panel"),
                                    html.Details([html.Summary("Network proxies"), html.Div([_equation_card(*equation) for equation in SCENARIO_EQUATIONS[9:11]], className="equation-grid scenario-equations")], className="guide-details panel"),
                                ],
                                className="scenario-equation-groups",
                            ),
                        ],
                        className="guide-subsection",
                    ),
                    html.Div(
                        [
                            _section_heading("Assumptions", "Which inputs come from published sources, and which are modelling choices?", "Values and source notes come from the SQLite database. Shared values below use the hybrid record; pathway shares are shown in the scenario cards."),
                            html.Div(
                                [
                                    html.Article([html.H3("Source-informed inputs"), html.P("Discount rate, carbon appraisal value, electricity and natural-gas LRVC benchmarks, heat-pump COP, gas-heating efficiency, and the electricity emissions factor.")], className="provenance-class source-informed"),
                                    html.Article([html.H3("Illustrative modelling choices"), html.P("Portfolio size and heat demand, pathway shares, low-carbon-gas cost and emissions, technology CAPEX and lifetimes, and the peak-heat proxy.")], className="provenance-class illustrative"),
                                ],
                                className="guide-two-column provenance-summary",
                            ),
                            html.Details([html.Summary("View complete assumption register"), _assumption_table(assumptions)], className="guide-details panel"),
                        ],
                        id="scenario-assumptions",
                        className="guide-subsection",
                    ),
                    html.Div(
                        [
                            _section_heading("Assumption exposure", "How does the sensitivity analysis work?"),
                            html.P("One input is changed to -20%, its current value, and +20% while every other input stays fixed. The existing model then recalculates social annual cost."),
                            html.P("This is a deterministic exposure check. It is not Monte Carlo analysis, does not assign probabilities, and does not test interactions between inputs."),
                            dcc.Link("Open the Scenario Explorer", href="/scenarios", className="button-primary guide-button"),
                        ],
                        className="sensitivity-explainer guide-subsection",
                    ),
                    html.Div(
                        [
                            _section_heading("Boundaries", "What are the scenario limitations?"),
                            html.Ul(
                                [
                                    html.Li("This is annual illustrative portfolio analysis, not a forecast or optimisation."),
                                    html.Li("It is not investment advice, power-flow modelling, or gas hydraulic modelling."),
                                    html.Li("It has no regional network constraints or assigned scenario probabilities."),
                                    html.Li("It does not reproduce NESO Future Energy Scenarios."),
                                ]
                            ),
                            html.Blockquote("100% gas-network utilisation means 100% of the model's illustrative reference throughput. It does not mean the physical GB gas network has reached maximum capacity.", className="proxy-callout"),
                        ],
                        className="limitation-panel scenario-limitations guide-subsection",
                    ),
                ],
                id="scenario-analysis",
                className="guide-part scenario-part",
            ),
            html.Section(
                [
                    html.Div([html.P("Part C", className="part-label"), html.H2("Reproducibility & technical evidence")], className="part-divider shared-divider"),
                    _section_heading("Shared engineering evidence", "How the models are kept transparent and reproducible"),
                    html.Div(
                        [
                            html.Div([html.Span(item) for item in ("Python", "Dash / Plotly", "pandas / NumPy", "scikit-learn / XGBoost", "SQL / SQLite", "pytest", "GitHub Actions", "Render")], className="technology-tags"),
                            html.Ul(
                                [
                                    html.Li("The deployed Dash app opens the scenario database read-only; user changes are calculated in memory."),
                                    html.Li("Offline scripts handle database creation and validated result storage."),
                                    html.Li("Locked test predictions are committed and can be inspected."),
                                    html.Li("Calculation, data-access and presentation code remain separate."),
                                    html.Li("The scenario database can be rebuilt and checked in an isolated temporary location."),
                                    html.Li("App navigation displays existing outputs and never trains models."),
                                    html.Li("The complete automated suite contains 102 passing offline tests, with one local-artifact parity test skipped when its ignored inputs are absent."),
                                ],
                                className="repro-list",
                            ),
                        ],
                        className="repro-panel",
                    ),
                ],
                id="reproducibility",
                className="guide-part shared-part",
            ),
        ],
        className="page-stack methodology-guide",
    )
