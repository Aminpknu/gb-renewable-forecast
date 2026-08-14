"""Offline integration tests for the Scenario Explorer Dash page."""

from __future__ import annotations

import importlib
import shutil
import sqlite3
from pathlib import Path

import pytest
import requests

from src.scenarios.calculations import calculate_scenario
from src.scenarios.repository import load_active_scenarios
from src.scenarios.repository import load_scenario_assumptions


@pytest.fixture
def scenario_page():
    importlib.import_module("app")
    return importlib.import_module("pages.scenarios")


def _walk_components(component):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk_components(child)
    elif children is not None:
        yield from _walk_components(children)


def _copy_database(source: Path, tmp_path: Path) -> Path:
    destination = tmp_path / "scenario_explorer.sqlite"
    shutil.copy2(source, destination)
    return destination


def test_scenario_page_route_and_three_database_options(scenario_page) -> None:
    import dash

    page = next(entry for entry in dash.page_registry.values() if entry["path"] == "/scenarios")
    rendered = page["layout"]()
    components = list(_walk_components(rendered))
    selector = next(component for component in components if getattr(component, "id", None) == "scenario-selector")

    assert page["name"] == "Scenarios"
    assert [option["label"] for option in selector.options] == [
        "Electrification-led",
        "Whole-system hybrid",
        "Low-carbon gas-led",
    ]
    assert selector.value == scenario_page.default_scenario_id()


def test_exactly_six_adjustable_controls_and_no_gas_lrvc(scenario_page) -> None:
    rendered = scenario_page.layout()
    control_ids = [
        component.id
        for component in _walk_components(rendered)
        if isinstance(getattr(component, "id", None), str)
        and component.id.startswith("scenario-input-")
    ]

    assert len(control_ids) == 6
    assert set(control_ids) == {
        f"scenario-input-{name}" for name in scenario_page.ADJUSTABLE_FIELDS
    }
    assert "scenario-input-gas_lrvc" not in control_ids


def test_default_hybrid_page_payload_matches_validated_result(scenario_page) -> None:
    scenario_id = scenario_page.default_scenario_id()
    values = scenario_page.scenario_default_values(scenario_id)
    payload = scenario_page.scenario_page_payload(
        scenario_id,
        dict(zip(scenario_page.ADJUSTABLE_FIELDS, values)),
    )

    assert payload["scenario"]["scenario_name"] == "Whole-system hybrid"
    assert payload["results"]["financial_annual_cost_gbp"] == pytest.approx(
        1_139_555_247.4669936
    )
    assert payload["results"]["social_annual_cost_gbp"] == pytest.approx(
        1_259_429_056.990803
    )


def test_adjusting_electricity_cost_changes_cost_not_emissions(scenario_page) -> None:
    scenario_id = scenario_page.default_scenario_id()
    defaults = dict(
        zip(scenario_page.ADJUSTABLE_FIELDS, scenario_page.scenario_default_values(scenario_id))
    )
    baseline = scenario_page.scenario_page_payload(scenario_id, defaults)
    adjusted_values = dict(defaults)
    adjusted_values["electricity_lrvc"] += 10
    adjusted = scenario_page.scenario_page_payload(scenario_id, adjusted_values)

    expected_cost_change = baseline["results"]["electricity_demand_mwh"] * 10
    assert adjusted["results"]["financial_annual_cost_gbp"] == pytest.approx(
        baseline["results"]["financial_annual_cost_gbp"] + expected_cost_change
    )
    assert adjusted["results"]["annual_emissions_tco2e"] == pytest.approx(
        baseline["results"]["annual_emissions_tco2e"]
    )


def test_reset_and_scenario_change_reload_database_defaults(
    scenario_page, tmp_path: Path, monkeypatch
) -> None:
    database = _copy_database(scenario_page.SCENARIO_DB_PATH, tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            UPDATE scenario_assumptions
            SET value = 150.0
            WHERE scenario_id = 1 AND assumption_name = 'electricity_lrvc'
            """
        )
        connection.commit()

    monkeypatch.setattr(scenario_page, "SCENARIO_DB_PATH", database)
    electrification_defaults = scenario_page.refresh_scenario_defaults(1, None)
    hybrid_defaults = scenario_page.refresh_scenario_defaults(2, None)
    reset_defaults = scenario_page.refresh_scenario_defaults(1, 1)

    assert electrification_defaults[0] == pytest.approx(150.0)
    assert hybrid_defaults[0] == pytest.approx(122.73)
    assert reset_defaults == electrification_defaults


def test_page_calculation_does_not_modify_sqlite(scenario_page, tmp_path: Path) -> None:
    database = _copy_database(scenario_page.SCENARIO_DB_PATH, tmp_path)
    scenario_id = scenario_page.default_scenario_id(database)
    defaults = scenario_page.scenario_default_values(scenario_id, database)
    before = database.read_bytes()

    scenario_page.scenario_page_payload(
        scenario_id,
        dict(zip(scenario_page.ADJUSTABLE_FIELDS, defaults)),
        database,
    )

    assert database.read_bytes() == before


def test_active_scenario_names_are_loaded_from_repository(scenario_page) -> None:
    scenarios = load_active_scenarios(scenario_page.SCENARIO_DB_PATH)
    assert len(scenarios) == 3
    assert all(scenario["scenario_name"] for scenario in scenarios)


def test_both_comparison_charts_are_present(scenario_page) -> None:
    rendered = scenario_page.layout()
    components = {
        component.id: component
        for component in _walk_components(rendered)
        if isinstance(getattr(component, "id", None), str)
    }

    assert "scenario-cost-comparison-chart" in components
    assert "scenario-tradeoffs-chart" in components
    assert len(components["scenario-cost-comparison-chart"].figure.data) == 3
    assert len(components["scenario-tradeoffs-chart"].figure.data) == 3


def test_default_comparison_reproduces_all_validated_scenarios(scenario_page) -> None:
    comparison = scenario_page.default_comparison_data().set_index("scenario_name")

    assert comparison.index.tolist() == [
        "Electrification-led",
        "Whole-system hybrid",
        "Low-carbon gas-led",
    ]
    expected = {
        "Electrification-led": (1_239_765_372.325853, 1_289_420_610.4210913, 8_800_000_000),
        "Whole-system hybrid": (1_139_555_247.4669936, 1_259_429_056.990803, 7_000_000_000),
        "Low-carbon gas-led": (1_039_345_122.608134, 1_229_437_503.560515, 5_200_000_000),
    }
    for name, (financial, social, investment) in expected.items():
        assert comparison.loc[name, "financial_annual_cost_gbp"] == pytest.approx(financial)
        assert comparison.loc[name, "social_annual_cost_gbp"] == pytest.approx(social)
        assert comparison.loc[name, "initial_investment_gbp"] == pytest.approx(investment)


def test_comparison_figures_contain_all_three_scenarios(scenario_page) -> None:
    comparison = scenario_page.default_comparison_data()
    cost_figure = scenario_page.scenario_cost_investment_figure(comparison)
    tradeoff_figure = scenario_page.scenario_trade_offs_figure(comparison)
    expected_names = comparison["scenario_name"].tolist()

    assert all(list(trace.x) == expected_names for trace in cost_figure.data)
    assert all(list(trace.y) == expected_names for trace in tradeoff_figure.data)
    assert tradeoff_figure.layout.xaxis.title.text == "MtCO2e/year"
    assert tradeoff_figure.layout.xaxis2.title.text == "MW"
    assert tradeoff_figure.layout.xaxis3.title.text == "%"


def test_sensitivity_matches_minus_base_and_plus_twenty_percent(scenario_page) -> None:
    scenario_id = scenario_page.default_scenario_id()
    defaults = dict(
        zip(scenario_page.ADJUSTABLE_FIELDS, scenario_page.scenario_default_values(scenario_id))
    )
    sensitivity = scenario_page.scenario_sensitivity_data(scenario_id, defaults)
    electricity = sensitivity.set_index("parameter").loc["electricity_lrvc"]
    complete = dict(load_scenario_assumptions(scenario_page.SCENARIO_DB_PATH, scenario_id)["values"])
    low = dict(complete)
    high = dict(complete)
    low["electricity_lrvc"] = defaults["electricity_lrvc"] * 0.8
    high["electricity_lrvc"] = defaults["electricity_lrvc"] * 1.2

    assert electricity["low_parameter_value"] == pytest.approx(defaults["electricity_lrvc"] * 0.8)
    assert electricity["base_parameter_value"] == pytest.approx(defaults["electricity_lrvc"])
    assert electricity["high_parameter_value"] == pytest.approx(defaults["electricity_lrvc"] * 1.2)
    assert electricity["low_social_annual_cost_gbp"] == pytest.approx(
        calculate_scenario(low)["social_annual_cost_gbp"]
    )
    assert electricity["high_social_annual_cost_gbp"] == pytest.approx(
        calculate_scenario(high)["social_annual_cost_gbp"]
    )


def test_sensitivity_changes_only_one_parameter_at_a_time(scenario_page, monkeypatch) -> None:
    scenario_id = scenario_page.default_scenario_id()
    defaults = dict(
        zip(scenario_page.ADJUSTABLE_FIELDS, scenario_page.scenario_default_values(scenario_id))
    )
    original = scenario_page.calculate_scenario
    calls = []

    def recording_calculation(assumptions, **kwargs):
        calls.append(dict(assumptions))
        return original(assumptions, **kwargs)

    monkeypatch.setattr(scenario_page, "calculate_scenario", recording_calculation)
    scenario_page.scenario_sensitivity_data(scenario_id, defaults)
    base = calls[0]

    assert len(calls) == 1 + 2 * len(scenario_page.SENSITIVITY_FIELDS)
    for parameter, low_call, high_call in zip(
        scenario_page.SENSITIVITY_FIELDS, calls[1::2], calls[2::2]
    ):
        assert [key for key in base if low_call[key] != base[key]] == [parameter]
        assert [key for key in base if high_call[key] != base[key]] == [parameter]


def test_carbon_value_sensitivity_changes_social_cost_not_emissions(scenario_page) -> None:
    scenario_id = scenario_page.default_scenario_id()
    defaults = dict(
        zip(scenario_page.ADJUSTABLE_FIELDS, scenario_page.scenario_default_values(scenario_id))
    )
    carbon = scenario_page.scenario_sensitivity_data(scenario_id, defaults).set_index(
        "parameter"
    ).loc["carbon_value"]

    assert carbon["low_social_annual_cost_gbp"] != pytest.approx(
        carbon["base_social_annual_cost_gbp"]
    )
    assert carbon["high_social_annual_cost_gbp"] != pytest.approx(
        carbon["base_social_annual_cost_gbp"]
    )
    assert carbon["low_annual_emissions_tco2e"] == pytest.approx(
        carbon["base_annual_emissions_tco2e"]
    )
    assert carbon["high_annual_emissions_tco2e"] == pytest.approx(
        carbon["base_annual_emissions_tco2e"]
    )


def _default_sensitivity_for(scenario_page, scenario_id: int):
    defaults = dict(
        zip(scenario_page.ADJUSTABLE_FIELDS, scenario_page.scenario_default_values(scenario_id))
    )
    return scenario_page.scenario_sensitivity_data(scenario_id, defaults).set_index("parameter")


def test_electricity_cost_sensitivity_is_larger_for_electricity_heavy_pathway(scenario_page) -> None:
    electrification = _default_sensitivity_for(scenario_page, 1)
    gas_led = _default_sensitivity_for(scenario_page, 3)
    assert electrification.loc["electricity_lrvc", "max_absolute_change_gbp_m"] > gas_led.loc[
        "electricity_lrvc", "max_absolute_change_gbp_m"
    ]


def test_gas_cost_sensitivity_is_larger_for_gas_heavy_pathway(scenario_page) -> None:
    electrification = _default_sensitivity_for(scenario_page, 1)
    gas_led = _default_sensitivity_for(scenario_page, 3)
    assert gas_led.loc["low_carbon_gas_cost", "max_absolute_change_gbp_m"] > electrification.loc[
        "low_carbon_gas_cost", "max_absolute_change_gbp_m"
    ]


def test_strategic_summary_is_deterministic_changes_and_avoids_claims(
    scenario_page, monkeypatch
) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Strategic summary attempted an external API call.")

    monkeypatch.setattr(requests, "get", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    scenario_id = scenario_page.default_scenario_id()
    defaults = dict(
        zip(scenario_page.ADJUSTABLE_FIELDS, scenario_page.scenario_default_values(scenario_id))
    )
    comparison = scenario_page.default_comparison_data()
    baseline_payload = scenario_page.scenario_page_payload(scenario_id, defaults)
    baseline_sensitivity = scenario_page.scenario_sensitivity_data(scenario_id, defaults)
    baseline_summary = scenario_page.strategic_summary(
        baseline_payload, comparison, baseline_sensitivity
    )

    adjusted_values = dict(defaults)
    adjusted_values["carbon_value"] *= 4
    adjusted_payload = scenario_page.scenario_page_payload(scenario_id, adjusted_values)
    adjusted_sensitivity = scenario_page.scenario_sensitivity_data(scenario_id, adjusted_values)
    adjusted_summary = scenario_page.strategic_summary(
        adjusted_payload, comparison, adjusted_sensitivity
    )

    assert baseline_summary != adjusted_summary
    assert "assumption" in baseline_summary.lower()
    assert "optimal" not in baseline_summary.lower()
    assert "best" not in baseline_summary.lower()


def test_comparison_sensitivity_and_summary_do_not_modify_sqlite(
    scenario_page, tmp_path: Path
) -> None:
    database = _copy_database(scenario_page.SCENARIO_DB_PATH, tmp_path)
    scenario_id = scenario_page.default_scenario_id(database)
    defaults = dict(
        zip(
            scenario_page.ADJUSTABLE_FIELDS,
            scenario_page.scenario_default_values(scenario_id, database),
        )
    )
    before = database.read_bytes()

    comparison = scenario_page.default_comparison_data(database)
    payload = scenario_page.scenario_page_payload(scenario_id, defaults, database)
    sensitivity = scenario_page.scenario_sensitivity_data(scenario_id, defaults, database)
    scenario_page.strategic_summary(payload, comparison, sensitivity)

    assert database.read_bytes() == before
