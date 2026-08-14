"""Clean-build tests for the offline Scenario Explorer database script."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.create_scenario_database import build_scenario_database
from src.scenarios.calculations import calculate_scenario
from src.scenarios.repository import load_active_scenarios, load_scenario_assumptions


EXPECTED_TABLES = {"scenarios", "scenario_assumptions", "scenario_results"}
PROJECT_DATABASE = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "scenarios"
    / "scenario_explorer.sqlite"
)


def test_scenario_database_builds_cleanly_in_isolated_path(tmp_path: Path) -> None:
    database_path = tmp_path / "data" / "scenarios" / "scenario_explorer.sqlite"
    built_path = build_scenario_database(database_path)

    assert built_path == database_path.resolve()
    assert built_path.is_file()

    with sqlite3.connect(built_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(scenario_assumptions)"
            ).fetchall()
        }
        assumption_count = connection.execute(
            "SELECT COUNT(*) FROM scenario_assumptions"
        ).fetchone()[0]
        metadata_gaps = connection.execute(
            """
            SELECT COUNT(*)
            FROM scenario_assumptions
            WHERE unit IS NULL OR source_note IS NULL OR is_user_adjustable NOT IN (0, 1)
            """
        ).fetchone()[0]
        built_scenarios = connection.execute(
            "SELECT scenario_id, scenario_name, description, is_active FROM scenarios ORDER BY scenario_id"
        ).fetchall()
        built_assumptions = connection.execute(
            """
            SELECT assumption_id, scenario_id, assumption_name, value, unit,
                   source_note, reference_year, price_base_year, is_user_adjustable
            FROM scenario_assumptions
            ORDER BY assumption_id
            """
        ).fetchall()

    with sqlite3.connect(PROJECT_DATABASE) as connection:
        project_scenarios = connection.execute(
            "SELECT scenario_id, scenario_name, description, is_active FROM scenarios ORDER BY scenario_id"
        ).fetchall()
        project_assumptions = connection.execute(
            """
            SELECT assumption_id, scenario_id, assumption_name, value, unit,
                   source_note, reference_year, price_base_year, is_user_adjustable
            FROM scenario_assumptions
            ORDER BY assumption_id
            """
        ).fetchall()

    assert EXPECTED_TABLES.issubset(tables)
    assert {
        "assumption_id",
        "scenario_id",
        "assumption_name",
        "value",
        "unit",
        "source_note",
        "reference_year",
        "price_base_year",
        "is_user_adjustable",
    }.issubset(columns)
    assert assumption_count == 54
    assert metadata_gaps == 0
    assert built_scenarios == project_scenarios
    assert built_assumptions == project_assumptions

    scenarios = load_active_scenarios(built_path)
    assert [scenario["scenario_name"] for scenario in scenarios] == [
        "Electrification-led",
        "Whole-system hybrid",
        "Low-carbon gas-led",
    ]

    expected_financial_costs = (
        1_239_765_372.325853,
        1_139_555_247.4669936,
        1_039_345_122.608134,
    )
    for scenario, expected_cost in zip(scenarios, expected_financial_costs, strict=True):
        bundle = load_scenario_assumptions(built_path, int(scenario["scenario_id"]))
        assert len(bundle["records"]) == 18
        assert {"heat_pump_cop", "discount_rate", "electricity_lrvc"}.issubset(
            bundle["values"]
        )
        result = calculate_scenario(
            bundle["values"], scenario_name=str(scenario["scenario_name"])
        )
        assert result["financial_annual_cost_gbp"] == pytest.approx(
            expected_cost, rel=1e-12
        )
