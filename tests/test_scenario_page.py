"""Offline integration tests for the Scenario Explorer Dash page."""

from __future__ import annotations

import importlib
import shutil
import sqlite3
from pathlib import Path

import pytest

from src.scenarios.repository import load_active_scenarios


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
