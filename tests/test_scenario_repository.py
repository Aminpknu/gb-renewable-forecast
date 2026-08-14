"""Tests for read-only Scenario Explorer SQLite access."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.scenarios.repository import (
    load_active_scenarios,
    load_adjustable_assumptions,
    load_scenario_assumptions,
    load_scenario_results,
)


@pytest.fixture
def scenario_database(tmp_path: Path) -> Path:
    """Create an isolated database matching the existing project schema."""

    database_path = tmp_path / "scenario_explorer.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE scenarios (
                scenario_id INTEGER PRIMARY KEY,
                scenario_name TEXT NOT NULL,
                description TEXT,
                is_active INTEGER NOT NULL
            );
            CREATE TABLE scenario_assumptions (
                assumption_id INTEGER PRIMARY KEY,
                scenario_id INTEGER NOT NULL,
                assumption_name TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT,
                source_note TEXT,
                reference_year INTEGER,
                price_base_year INTEGER,
                is_user_adjustable INTEGER,
                FOREIGN KEY (scenario_id) REFERENCES scenarios(scenario_id)
            );
            CREATE TABLE scenario_results (
                result_id INTEGER PRIMARY KEY,
                scenario_id INTEGER NOT NULL,
                run_label TEXT NOT NULL,
                financial_cost_gbp_year REAL,
                social_cost_gbp_year REAL,
                annual_emissions_tco2e REAL,
                initial_investment_gbp REAL,
                electricity_peak_mw REAL,
                gas_throughput_mwh REAL,
                gas_utilisation_pct REAL,
                calculated_at TEXT,
                FOREIGN KEY (scenario_id) REFERENCES scenarios(scenario_id)
            );
            """
        )
        connection.executemany(
            "INSERT INTO scenarios VALUES (?, ?, ?, ?)",
            [
                (1, "Electrification-led", "Strong electrification of heat.", 1),
                (2, "Whole-system hybrid", "A mixed energy system.", 1),
                (3, "Low-carbon gas-led", "Continued gas-network use.", 1),
                (4, "Inactive example", "Not shown in the app.", 0),
            ],
        )
        connection.executemany(
            """
            INSERT INTO scenario_assumptions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 1, "discount_rate", 3.5, "%", "Scenario assumption", 2050, 2024, 1),
                (2, 1, "heat_pump_cop", 2.8, "ratio", "Technology assumption", 2050, None, 0),
                (3, 1, "electricity_lrvc", 122.73, "GBP/MWh", "Cost assumption", 2050, 2024, 1),
                (4, 1, "number_homes", 1_000_000, "homes", "Scope assumption", 2050, None, 0),
            ],
        )
        connection.executemany(
            """
            INSERT INTO scenario_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 1, "default_2050", 1_239_765_372.325853, 1_289_420_610.4210913,
                 124_761.90476190476, 8_800_000_000, 1_428.5714285714287,
                 2_380_952.380952381, 25.0, "2026-01-01T00:00:00+00:00"),
                (2, 2, "default_2050", 1_139_555_247.4669936, 1_259_429_056.990803,
                 301_190.4761904762, 7_000_000_000, 892.857142857143,
                 5_952_380.952380952, 62.5, "2026-01-01T00:00:00+00:00"),
                (3, 3, "default_2050", 1_039_345_122.608134, 1_229_437_503.560515,
                 477_619.04761904763, 5_200_000_000, 357.14285714285717,
                 9_523_809.523809524, 100.0, "2026-01-01T00:00:00+00:00"),
            ],
        )

    return database_path


def test_active_scenarios_load_in_expected_order(scenario_database: Path) -> None:
    scenarios = load_active_scenarios(scenario_database)

    assert [scenario["scenario_id"] for scenario in scenarios] == [1, 2, 3]
    assert [scenario["scenario_name"] for scenario in scenarios] == [
        "Electrification-led",
        "Whole-system hybrid",
        "Low-carbon gas-led",
    ]


def test_scenario_assumptions_include_values_and_metadata(scenario_database: Path) -> None:
    assumptions = load_scenario_assumptions(scenario_database, 1)

    assert assumptions["values"]["heat_pump_cop"] == pytest.approx(2.8)
    assert assumptions["values"]["discount_rate"] == pytest.approx(3.5)
    assert assumptions["values"]["electricity_lrvc"] == pytest.approx(122.73)
    assert assumptions["records"][0]["unit"] == "%"
    assert assumptions["records"][0]["source_note"] == "Scenario assumption"


def test_adjustable_assumptions_are_filtered_from_sqlite(scenario_database: Path) -> None:
    adjustable = load_adjustable_assumptions(scenario_database, 1)

    assert [record["assumption_name"] for record in adjustable] == [
        "discount_rate",
        "electricity_lrvc",
    ]
    assert all("price_base_year" in record for record in adjustable)


def test_default_results_include_scenario_names_from_join(scenario_database: Path) -> None:
    results = load_scenario_results(scenario_database)

    assert len(results) == 3
    assert results[0]["scenario_name"] == "Electrification-led"
    assert results[0]["financial_cost_gbp_year"] == pytest.approx(1_239_765_372.325853)
    assert results[2]["gas_utilisation_pct"] == pytest.approx(100.0)


def test_missing_database_path_has_clear_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.sqlite"
    with pytest.raises(FileNotFoundError, match="Scenario database does not exist"):
        load_active_scenarios(missing_path)


def test_unknown_scenario_id_has_clear_error(scenario_database: Path) -> None:
    with pytest.raises(ValueError, match="Scenario ID 999 does not exist"):
        load_scenario_assumptions(scenario_database, 999)


def test_repository_reads_do_not_modify_database(scenario_database: Path) -> None:
    before = scenario_database.read_bytes()

    load_active_scenarios(scenario_database)
    load_scenario_assumptions(scenario_database, 1)
    load_adjustable_assumptions(scenario_database, 1)
    load_scenario_results(scenario_database)

    assert scenario_database.read_bytes() == before
