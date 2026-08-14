"""Populate and validate default SQLite scenario results.

The mathematical calculations live in :mod:`src.scenarios.calculations` so
they can be tested and reused independently of SQLite.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.scenarios.calculations import calculate_scenario


DB_PATH = PROJECT_ROOT / "data" / "scenarios" / "scenario_explorer.sqlite"
RUN_LABEL = "default_2050"


def _print_results(scenario_name: str, results: dict[str, float]) -> None:
    """Print the concise validation output used by the original prototype."""

    print(f"\n--- {scenario_name} ---")
    print(f"Total useful heat: {results['total_useful_heat_mwh']:,.0f} MWh/year")
    print(f"Electricity demand: {results['electricity_demand_mwh']:,.0f} MWh/year")
    print(f"Low-carbon gas demand: {results['low_carbon_gas_demand_mwh']:,.0f} MWh/year")
    print(f"Annual energy cost: £{results['annual_energy_cost_gbp'] / 1e9:,.3f} bn/year")
    print(f"Initial technology investment: £{results['initial_investment_gbp'] / 1e9:,.2f} bn")
    print(f"Annualised CAPEX: £{results['annualised_capex_gbp'] / 1e9:,.3f} bn/year")
    print(f"Annual emissions: {results['annual_emissions_tco2e'] / 1e6:,.3f} MtCO2e/year")
    print(f"Carbon impact: £{results['carbon_cost_gbp'] / 1e9:,.3f} bn/year")
    print(f"Financial annual cost: £{results['financial_annual_cost_gbp'] / 1e9:,.3f} bn/year")
    print(f"Social annual cost: £{results['social_annual_cost_gbp'] / 1e9:,.3f} bn/year")
    print(f"Electricity peak proxy: {results['electricity_peak_mw']:,.1f} MW")
    print(f"Gas-network utilisation proxy: {results['gas_network_utilisation_pct']:,.1f}%")


def validate_saved_results(rows: list[tuple]) -> None:
    """Retain the original prototype's basic cross-scenario sanity checks."""

    if len(rows) != 3:
        raise AssertionError("Expected exactly three active scenario results.")

    for row in rows:
        name, financial, social, emissions, investment, peak, gas_throughput, utilisation = row
        if financial < 0 or social < 0 or emissions < 0 or investment < 0:
            raise AssertionError(f"{name}: negative result found.")
        if social < financial:
            raise AssertionError(f"{name}: social cost is below financial cost.")
        if not 0 <= utilisation <= 100:
            raise AssertionError(f"{name}: gas utilisation is outside 0-100%.")

    _, _, _, emissions_elec, _, peak_elec, gas_elec, _ = rows[0]
    _, _, _, emissions_hybrid, _, peak_hybrid, gas_hybrid, _ = rows[1]
    _, _, _, emissions_gas, _, peak_gas, gas_gas, _ = rows[2]

    if not peak_elec > peak_hybrid > peak_gas:
        raise AssertionError("Electricity peak ordering does not match scenario shares.")
    if not gas_elec < gas_hybrid < gas_gas:
        raise AssertionError("Gas throughput ordering does not match scenario shares.")
    if not emissions_elec < emissions_hybrid < emissions_gas:
        raise AssertionError("Emissions ordering does not match scenario shares.")


def main() -> None:
    """Read active SQLite assumptions, calculate, persist, and validate results."""

    calculated_at = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(DB_PATH) as connection:
        cursor = connection.cursor()
        scenarios = cursor.execute(
            """
            SELECT scenario_id, scenario_name
            FROM scenarios
            WHERE is_active = 1
            ORDER BY scenario_id
            """
        ).fetchall()

        result_rows = []
        for scenario_id, scenario_name in scenarios:
            assumptions = dict(
                cursor.execute(
                    """
                    SELECT assumption_name, value
                    FROM scenario_assumptions
                    WHERE scenario_id = ?
                    """,
                    (scenario_id,),
                ).fetchall()
            )
            results = calculate_scenario(assumptions, scenario_name=scenario_name)
            _print_results(scenario_name, results)
            result_rows.append(
                (
                    scenario_id,
                    RUN_LABEL,
                    results["financial_annual_cost_gbp"],
                    results["social_annual_cost_gbp"],
                    results["annual_emissions_tco2e"],
                    results["initial_investment_gbp"],
                    results["electricity_peak_mw"],
                    results["low_carbon_gas_demand_mwh"],
                    results["gas_network_utilisation_pct"],
                    calculated_at,
                )
            )

        cursor.execute("DELETE FROM scenario_results WHERE run_label = ?", (RUN_LABEL,))
        cursor.executemany(
            """
            INSERT INTO scenario_results (
                scenario_id,
                run_label,
                financial_cost_gbp_year,
                social_cost_gbp_year,
                annual_emissions_tco2e,
                initial_investment_gbp,
                electricity_peak_mw,
                gas_throughput_mwh,
                gas_utilisation_pct,
                calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            result_rows,
        )
        connection.commit()

        saved_rows = cursor.execute(
            """
            SELECT
                s.scenario_name,
                r.financial_cost_gbp_year,
                r.social_cost_gbp_year,
                r.annual_emissions_tco2e,
                r.initial_investment_gbp,
                r.electricity_peak_mw,
                r.gas_throughput_mwh,
                r.gas_utilisation_pct
            FROM scenario_results AS r
            JOIN scenarios AS s ON s.scenario_id = r.scenario_id
            WHERE r.run_label = ?
            ORDER BY r.scenario_id
            """,
            (RUN_LABEL,),
        ).fetchall()

    print("\n--- Saved results (SQLite join) ---")
    for row in saved_rows:
        name, financial, social, emissions, investment, peak, gas_throughput, utilisation = row
        print(
            f"{name}: financial £{financial / 1e9:.3f}bn, social £{social / 1e9:.3f}bn, "
            f"emissions {emissions / 1e6:.3f}MtCO2e, investment £{investment / 1e9:.2f}bn, "
            f"peak {peak:.1f}MW, gas {gas_throughput:,.0f}MWh, utilisation {utilisation:.1f}%"
        )

    validate_saved_results(saved_rows)
    print("\nBasic model validation checks passed.")


if __name__ == "__main__":
    main()
