"""Create the lightweight Scenario Explorer SQLite database.

The default command builds the project database in ``data/scenarios``. The
callable ``build_scenario_database`` function accepts another path so tests can
prove a clean build without touching the committed runtime database.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "scenarios" / "scenario_explorer.sqlite"

SCENARIOS = (
    (1, "Electrification-led", "A pathway with strong electrification of heat and reduced gas-network use.", 1),
    (2, "Whole-system hybrid", "A pathway combining electrification with continued use of low-carbon gases.", 1),
    (3, "Low-carbon gas-led", "A pathway with greater continued use of the gas network supported by biomethane and other low-carbon gases.", 1),
)

# start ID, name, scenario values, unit, source note, reference year,
# price-base year, adjustable flag. These are the validated prototype values.
ASSUMPTION_GROUPS = (
    (1, "discount_rate", (3.5, 3.5, 3.5), "%", "HM Treasury Green Book 2026", None, None, 1),
    (4, "carbon_value", (398.0, 398.0, 398.0), "GBP/tCO2e", "DESNZ Green Book carbon appraisal value", 2050, 2022, 1),
    (7, "heat_pump_cop", (2.8, 2.8, 2.8), "ratio", "DESNZ Warm Homes Plan Technical Annex 2026 - CODE assumption", None, None, 0),
    (10, "gas_heating_efficiency", (0.84, 0.84, 0.84), "ratio", "DESNZ Warm Homes Plan Technical Annex 2026 - gas boiler efficiency", None, None, 0),
    (13, "electricity_lrvc", (122.73, 122.73, 122.73), "GBP/MWh", "DESNZ Green Book Data Table 9, central domestic LRVC", 2050, 2022, 1),
    (16, "gas_lrvc", (26.26, 26.26, 26.26), "GBP/MWh", "DESNZ Green Book Data Table 10, central domestic LRVC", 2050, 2022, 0),
    (19, "number_homes", (1_000_000, 1_000_000, 1_000_000), "homes", "Illustrative portfolio model boundary", 2050, None, 0),
    (22, "useful_heat_per_home", (10.0, 10.0, 10.0), "MWh/home/year", "Illustrative MVP assumption; not an official 2050 forecast", 2050, None, 0),
    (25, "electric_heat_share", (0.80, 0.50, 0.20), "ratio", "Illustrative scenario assumption informed by NESO FES 2025 pathway direction", 2050, None, 0),
    (28, "low_carbon_gas_heat_share", (0.20, 0.50, 0.80), "ratio", "Illustrative scenario assumption informed by NESO FES 2025 pathway direction", 2050, None, 0),
    (31, "low_carbon_gas_cost", (52.52, 52.52, 52.52), "GBP/MWh", "Illustrative MVP assumption: 2x DESNZ 2050 natural-gas LRVC; sensitivity parameter", 2050, 2022, 1),
    (34, "electricity_emissions_factor", (0.002, 0.002, 0.002), "tCO2e/MWh", "DESNZ Green Book energy/GHG appraisal: 2050 electricity factor", 2050, None, 0),
    (37, "low_carbon_gas_emissions_factor", (0.050, 0.050, 0.050), "tCO2e/MWh", "Illustrative lifecycle emissions assumption for low-carbon network gas; not an official forecast", 2050, None, 0),
    (40, "heat_pump_capex", (10_000.0, 10_000.0, 10_000.0), "GBP/home", "Illustrative 2050 MVP technology-cost assumption; sensitivity parameter", 2050, 2022, 1),
    (43, "low_carbon_gas_capex", (4_000.0, 4_000.0, 4_000.0), "GBP/home", "Illustrative 2050 MVP technology-cost assumption; sensitivity parameter", 2050, 2022, 1),
    (46, "heat_pump_lifetime", (15.0, 15.0, 15.0), "years", "Illustrative MVP technology-lifetime assumption", 2050, None, 0),
    (49, "low_carbon_gas_lifetime", (15.0, 15.0, 15.0), "years", "Illustrative MVP technology-lifetime assumption", 2050, None, 0),
    (52, "peak_heat_kw_per_home", (5.0, 5.0, 5.0), "kW/home", "Illustrative coincident peak-heat proxy for portfolio analysis", 2050, None, 0),
)


def _assumption_rows() -> list[tuple[object, ...]]:
    """Expand the compact validated assumption groups into database rows."""

    rows: list[tuple[object, ...]] = []
    for start_id, name, values, unit, source, reference_year, price_year, adjustable in ASSUMPTION_GROUPS:
        for offset, value in enumerate(values):
            rows.append(
                (
                    start_id + offset,
                    offset + 1,
                    name,
                    value,
                    unit,
                    source,
                    reference_year,
                    price_year,
                    adjustable,
                )
            )
    return rows


def build_scenario_database(db_path: str | Path = DB_PATH) -> Path:
    """Create or refresh the validated scenario inputs at ``db_path``.

    Existing ``scenario_results`` rows are preserved. The function only
    populates the scenario definitions and assumptions that the original
    offline script owned.
    """

    path = Path(db_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS scenarios (
                scenario_id INTEGER PRIMARY KEY,
                scenario_name TEXT NOT NULL,
                description TEXT,
                is_active INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scenario_assumptions (
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

            CREATE TABLE IF NOT EXISTS scenario_results (
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

            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_scenario_assumption
            ON scenario_assumptions (scenario_id, assumption_name);
            """
        )
        connection.executemany(
            """
            INSERT OR REPLACE INTO scenarios
                (scenario_id, scenario_name, description, is_active)
            VALUES (?, ?, ?, ?)
            """,
            SCENARIOS,
        )
        connection.executemany(
            """
            INSERT OR REPLACE INTO scenario_assumptions
                (assumption_id, scenario_id, assumption_name, value, unit,
                 source_note, reference_year, price_base_year, is_user_adjustable)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _assumption_rows(),
        )

    return path


def main() -> None:
    """Build the project database from the command line."""

    path = build_scenario_database()
    print(f"Scenario database created or refreshed at:\n{path}")


if __name__ == "__main__":
    main()
