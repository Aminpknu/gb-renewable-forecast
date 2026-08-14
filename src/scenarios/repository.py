"""Small read-only SQLite access helpers for the Scenario Explorer."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def _connect_read_only(db_path: str | Path) -> sqlite3.Connection:
    """Open an existing SQLite database in read-only mode."""

    path = Path(db_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Scenario database does not exist: {path}")

    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def _scenario_exists(connection: sqlite3.Connection, scenario_id: int) -> bool:
    """Return whether a scenario ID exists, regardless of active status."""

    row = connection.execute(
        "SELECT scenario_id FROM scenarios WHERE scenario_id = ?",
        (scenario_id,),
    ).fetchone()
    return row is not None


def load_active_scenarios(db_path: str | Path) -> list[dict[str, object]]:
    """Load active scenario IDs, names, and descriptions in display order."""

    with _connect_read_only(db_path) as connection:
        rows = connection.execute(
            """
            SELECT scenario_id, scenario_name, description
            FROM scenarios
            WHERE is_active = 1
            ORDER BY scenario_id
            """
        ).fetchall()

    return [
        {
            "scenario_id": row[0],
            "scenario_name": row[1],
            "description": row[2],
        }
        for row in rows
    ]


def load_scenario_assumptions(db_path: str | Path, scenario_id: int) -> dict[str, object]:
    """Load one scenario's values plus source metadata.

    ``values`` is suitable for :func:`src.scenarios.calculate_scenario`;
    ``records`` retains the database metadata for future display.
    """

    with _connect_read_only(db_path) as connection:
        if not _scenario_exists(connection, scenario_id):
            raise ValueError(f"Scenario ID {scenario_id} does not exist.")

        rows = connection.execute(
            """
            SELECT
                assumption_name,
                value,
                unit,
                source_note,
                reference_year,
                price_base_year,
                is_user_adjustable
            FROM scenario_assumptions
            WHERE scenario_id = ?
            ORDER BY assumption_id
            """,
            (scenario_id,),
        ).fetchall()

    records = [
        {
            "assumption_name": row[0],
            "value": row[1],
            "unit": row[2],
            "source_note": row[3],
            "reference_year": row[4],
            "price_base_year": row[5],
            "is_user_adjustable": bool(row[6]),
        }
        for row in rows
    ]
    return {
        "values": {record["assumption_name"]: record["value"] for record in records},
        "records": records,
    }


def load_adjustable_assumptions(db_path: str | Path, scenario_id: int) -> list[dict[str, object]]:
    """Load only the database-marked user-adjustable assumptions for a scenario."""

    with _connect_read_only(db_path) as connection:
        if not _scenario_exists(connection, scenario_id):
            raise ValueError(f"Scenario ID {scenario_id} does not exist.")

        rows = connection.execute(
            """
            SELECT
                assumption_name,
                value,
                unit,
                source_note,
                reference_year,
                price_base_year
            FROM scenario_assumptions
            WHERE scenario_id = ? AND is_user_adjustable = 1
            ORDER BY assumption_id
            """,
            (scenario_id,),
        ).fetchall()

    return [
        {
            "assumption_name": row[0],
            "value": row[1],
            "unit": row[2],
            "source_note": row[3],
            "reference_year": row[4],
            "price_base_year": row[5],
        }
        for row in rows
    ]


def load_scenario_results(
    db_path: str | Path, run_label: str = "default_2050"
) -> list[dict[str, object]]:
    """Load persisted results and their scenario names for one run label."""

    with _connect_read_only(db_path) as connection:
        rows = connection.execute(
            """
            SELECT
                r.scenario_id,
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
            (run_label,),
        ).fetchall()

    return [
        {
            "scenario_id": row[0],
            "scenario_name": row[1],
            "financial_cost_gbp_year": row[2],
            "social_cost_gbp_year": row[3],
            "annual_emissions_tco2e": row[4],
            "initial_investment_gbp": row[5],
            "electricity_peak_mw": row[6],
            "gas_throughput_mwh": row[7],
            "gas_utilisation_pct": row[8],
        }
        for row in rows
    ]
