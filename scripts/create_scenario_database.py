# -*- coding: utf-8 -*-
"""
Created on Fri Aug 14 08:47:03 2026

@author: mz0013
"""

from pathlib import Path
import sqlite3


# Find the root folder of your GB forecasting project
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Define where the database will live
DB_DIR = PROJECT_ROOT / "data" / "scenarios"

# Create the folders if they do not already exist
DB_DIR.mkdir(parents=True, exist_ok=True)

# Full path of the SQLite database
DB_PATH = DB_DIR / "scenario_explorer.sqlite"

# Connect to SQLite.
# If the database does not exist, SQLite creates it automatically.
conn = sqlite3.connect(DB_PATH)

print(f"Database created at:\n{DB_PATH}")

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id INTEGER PRIMARY KEY,
    scenario_name TEXT NOT NULL,
    description TEXT,
    is_active INTEGER NOT NULL
)
""")

cursor.execute("""
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
)
""")

print("Table 'scenario_results' created successfully.")

discount_rates = [
    (1, 1, "discount_rate", 3.5, "%", "HM Treasury Green Book 2026", None, None, 1),
    (2, 2, "discount_rate", 3.5, "%", "HM Treasury Green Book 2026", None, None, 1),
    (3, 3, "discount_rate", 3.5, "%", "HM Treasury Green Book 2026", None, None, 1)
]

cursor.executemany("""
INSERT OR REPLACE INTO scenario_assumptions
(assumption_id, scenario_id, assumption_name, value, unit, source_note,
 reference_year, price_base_year, is_user_adjustable)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", discount_rates)

carbon_values = [
    (4, 1, "carbon_value", 398.0, "GBP/tCO2e", "DESNZ Green Book carbon appraisal value", 2050, 2022, 1),
    (5, 2, "carbon_value", 398.0, "GBP/tCO2e", "DESNZ Green Book carbon appraisal value", 2050, 2022, 1),
    (6, 3, "carbon_value", 398.0, "GBP/tCO2e", "DESNZ Green Book carbon appraisal value", 2050, 2022, 1)
]

heat_pump_cop = [
    (7, 1, "heat_pump_cop", 2.8, "ratio", "DESNZ Warm Homes Plan Technical Annex 2026 - CODE assumption", None, None, 0),
    (8, 2, "heat_pump_cop", 2.8, "ratio", "DESNZ Warm Homes Plan Technical Annex 2026 - CODE assumption", None, None, 0),
    (9, 3, "heat_pump_cop", 2.8, "ratio", "DESNZ Warm Homes Plan Technical Annex 2026 - CODE assumption", None, None, 0)
]


boiler_efficiency = [
    (10, 1, "gas_heating_efficiency", 0.84, "ratio", "DESNZ Warm Homes Plan Technical Annex 2026 - gas boiler efficiency", None, None, 0),
    (11, 2, "gas_heating_efficiency", 0.84, "ratio", "DESNZ Warm Homes Plan Technical Annex 2026 - gas boiler efficiency", None, None, 0),
    (12, 3, "gas_heating_efficiency", 0.84, "ratio", "DESNZ Warm Homes Plan Technical Annex 2026 - gas boiler efficiency", None, None, 0)
]

energy_lrvc = [
    (13, 1, "electricity_lrvc", 122.73, "GBP/MWh", "DESNZ Green Book Data Table 9, central domestic LRVC", 2050, 2022, 1),
    (14, 2, "electricity_lrvc", 122.73, "GBP/MWh", "DESNZ Green Book Data Table 9, central domestic LRVC", 2050, 2022, 1),
    (15, 3, "electricity_lrvc", 122.73, "GBP/MWh", "DESNZ Green Book Data Table 9, central domestic LRVC", 2050, 2022, 1),
    (16, 1, "gas_lrvc", 26.26, "GBP/MWh", "DESNZ Green Book Data Table 10, central domestic LRVC", 2050, 2022, 0),
    (17, 2, "gas_lrvc", 26.26, "GBP/MWh", "DESNZ Green Book Data Table 10, central domestic LRVC", 2050, 2022, 0),
    (18, 3, "gas_lrvc", 26.26, "GBP/MWh", "DESNZ Green Book Data Table 10, central domestic LRVC", 2050, 2022, 0)
]


cursor.executemany("""
INSERT OR REPLACE INTO scenario_assumptions
(assumption_id, scenario_id, assumption_name, value, unit, source_note, reference_year, price_base_year, is_user_adjustable)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", energy_lrvc)


model_boundary = [
    (19, 1, "number_homes", 1_000_000, "homes", "Illustrative portfolio model boundary", 2050, None, 0),
    (20, 2, "number_homes", 1_000_000, "homes", "Illustrative portfolio model boundary", 2050, None, 0),
    (21, 3, "number_homes", 1_000_000, "homes", "Illustrative portfolio model boundary", 2050, None, 0),

    (22, 1, "useful_heat_per_home", 10.0, "MWh/home/year", "Illustrative MVP assumption; not an official 2050 forecast", 2050, None, 0),
    (23, 2, "useful_heat_per_home", 10.0, "MWh/home/year", "Illustrative MVP assumption; not an official 2050 forecast", 2050, None, 0),
    (24, 3, "useful_heat_per_home", 10.0, "MWh/home/year", "Illustrative MVP assumption; not an official 2050 forecast", 2050, None, 0)
]

cursor.executemany("""
INSERT OR REPLACE INTO scenario_assumptions
(assumption_id, scenario_id, assumption_name, value, unit, source_note, reference_year, price_base_year, is_user_adjustable)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", model_boundary)

heat_shares = [
    (25, 1, "electric_heat_share", 0.80, "ratio", "Illustrative scenario assumption informed by NESO FES 2025 pathway direction", 2050, None, 0),
    (26, 2, "electric_heat_share", 0.50, "ratio", "Illustrative scenario assumption informed by NESO FES 2025 pathway direction", 2050, None, 0),
    (27, 3, "electric_heat_share", 0.20, "ratio", "Illustrative scenario assumption informed by NESO FES 2025 pathway direction", 2050, None, 0),
    (28, 1, "low_carbon_gas_heat_share", 0.20, "ratio", "Illustrative scenario assumption informed by NESO FES 2025 pathway direction", 2050, None, 0),
    (29, 2, "low_carbon_gas_heat_share", 0.50, "ratio", "Illustrative scenario assumption informed by NESO FES 2025 pathway direction", 2050, None, 0),
    (30, 3, "low_carbon_gas_heat_share", 0.80, "ratio", "Illustrative scenario assumption informed by NESO FES 2025 pathway direction", 2050, None, 0)
]

cursor.executemany("""
INSERT OR REPLACE INTO scenario_assumptions
(assumption_id, scenario_id, assumption_name, value, unit, source_note, reference_year, price_base_year, is_user_adjustable)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", heat_shares)

remaining_assumptions = [

    # ---- Low-carbon gas cost ----
    # Illustrative MVP assumption: 2 × natural-gas LRVC (2 × 26.26 = 52.52 GBP/MWh)
    (31, 1, "low_carbon_gas_cost", 52.52, "GBP/MWh", "Illustrative MVP assumption: 2x DESNZ 2050 natural-gas LRVC; sensitivity parameter", 2050, 2022, 1),
    (32, 2, "low_carbon_gas_cost", 52.52, "GBP/MWh", "Illustrative MVP assumption: 2x DESNZ 2050 natural-gas LRVC; sensitivity parameter", 2050, 2022, 1),
    (33, 3, "low_carbon_gas_cost", 52.52, "GBP/MWh", "Illustrative MVP assumption: 2x DESNZ 2050 natural-gas LRVC; sensitivity parameter", 2050, 2022, 1),

    # ---- Electricity emissions factor ----
    (34, 1, "electricity_emissions_factor", 0.002, "tCO2e/MWh", "DESNZ Green Book energy/GHG appraisal: 2050 electricity factor", 2050, None, 0),
    (35, 2, "electricity_emissions_factor", 0.002, "tCO2e/MWh", "DESNZ Green Book energy/GHG appraisal: 2050 electricity factor", 2050, None, 0),
    (36, 3, "electricity_emissions_factor", 0.002, "tCO2e/MWh", "DESNZ Green Book energy/GHG appraisal: 2050 electricity factor", 2050, None, 0),

    # ---- Low-carbon gas emissions ----
    (37, 1, "low_carbon_gas_emissions_factor", 0.050, "tCO2e/MWh", "Illustrative lifecycle emissions assumption for low-carbon network gas; not an official forecast", 2050, None, 0),
    (38, 2, "low_carbon_gas_emissions_factor", 0.050, "tCO2e/MWh", "Illustrative lifecycle emissions assumption for low-carbon network gas; not an official forecast", 2050, None, 0),
    (39, 3, "low_carbon_gas_emissions_factor", 0.050, "tCO2e/MWh", "Illustrative lifecycle emissions assumption for low-carbon network gas; not an official forecast", 2050, None, 0),

    # ---- Heat-pump CAPEX ----
    (40, 1, "heat_pump_capex", 10000.0, "GBP/home", "Illustrative 2050 MVP technology-cost assumption; sensitivity parameter", 2050, 2022, 1),
    (41, 2, "heat_pump_capex", 10000.0, "GBP/home", "Illustrative 2050 MVP technology-cost assumption; sensitivity parameter", 2050, 2022, 1),
    (42, 3, "heat_pump_capex", 10000.0, "GBP/home", "Illustrative 2050 MVP technology-cost assumption; sensitivity parameter", 2050, 2022, 1),

    # ---- Low-carbon-gas heating-system CAPEX ----
    (43, 1, "low_carbon_gas_capex", 4000.0, "GBP/home", "Illustrative 2050 MVP technology-cost assumption; sensitivity parameter", 2050, 2022, 1),
    (44, 2, "low_carbon_gas_capex", 4000.0, "GBP/home", "Illustrative 2050 MVP technology-cost assumption; sensitivity parameter", 2050, 2022, 1),
    (45, 3, "low_carbon_gas_capex", 4000.0, "GBP/home", "Illustrative 2050 MVP technology-cost assumption; sensitivity parameter", 2050, 2022, 1),

    # ---- Technology lifetimes ----
    (46, 1, "heat_pump_lifetime", 15.0, "years", "Illustrative MVP technology-lifetime assumption", 2050, None, 0),
    (47, 2, "heat_pump_lifetime", 15.0, "years", "Illustrative MVP technology-lifetime assumption", 2050, None, 0),
    (48, 3, "heat_pump_lifetime", 15.0, "years", "Illustrative MVP technology-lifetime assumption", 2050, None, 0),

    (49, 1, "low_carbon_gas_lifetime", 15.0, "years", "Illustrative MVP technology-lifetime assumption", 2050, None, 0),
    (50, 2, "low_carbon_gas_lifetime", 15.0, "years", "Illustrative MVP technology-lifetime assumption", 2050, None, 0),
    (51, 3, "low_carbon_gas_lifetime", 15.0, "years", "Illustrative MVP technology-lifetime assumption", 2050, None, 0),

    # ---- Peak heat-demand proxy ----
    (52, 1, "peak_heat_kw_per_home", 5.0, "kW/home", "Illustrative coincident peak-heat proxy for portfolio analysis", 2050, None, 0),
    (53, 2, "peak_heat_kw_per_home", 5.0, "kW/home", "Illustrative coincident peak-heat proxy for portfolio analysis", 2050, None, 0),
    (54, 3, "peak_heat_kw_per_home", 5.0, "kW/home", "Illustrative coincident peak-heat proxy for portfolio analysis", 2050, None, 0)
]

cursor.executemany("""
INSERT OR REPLACE INTO scenario_assumptions
(assumption_id, scenario_id, assumption_name, value, unit, source_note, reference_year, price_base_year, is_user_adjustable)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", remaining_assumptions)

conn.commit()


cursor.executemany("""
INSERT OR REPLACE INTO scenario_assumptions
(assumption_id, scenario_id, assumption_name, value, unit, source_note,
 reference_year, price_base_year, is_user_adjustable)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", boiler_efficiency)

conn.commit()

cursor.executemany("""
INSERT OR REPLACE INTO scenario_assumptions
(assumption_id, scenario_id, assumption_name, value, unit, source_note,
 reference_year, price_base_year, is_user_adjustable)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", heat_pump_cop)

conn.commit()

cursor.executemany("""
INSERT OR REPLACE INTO scenario_assumptions
(assumption_id, scenario_id, assumption_name, value, unit, source_note,
 reference_year, price_base_year, is_user_adjustable)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", carbon_values)


cursor.execute("SELECT scenario_id, assumption_name, value, unit, is_user_adjustable FROM scenario_assumptions WHERE assumption_name = 'heat_pump_cop'")
print("\nHeat-pump COP:", cursor.fetchall())


cursor.execute("SELECT scenario_id, assumption_name, value, unit, reference_year, price_base_year FROM scenario_assumptions WHERE assumption_name = 'carbon_value'")
print("\nCarbon values:", cursor.fetchall())
conn.commit()

cursor.execute("SELECT scenario_id, assumption_name, value, unit FROM scenario_assumptions WHERE assumption_name = 'gas_heating_efficiency'")
print("\nGas-heating efficiency:", cursor.fetchall())


cursor.execute("SELECT scenario_id, assumption_name, value, unit, reference_year, price_base_year FROM scenario_assumptions WHERE assumption_name IN ('electricity_lrvc', 'gas_lrvc')")
print("\nEnergy LRVCs:", cursor.fetchall())

cursor.execute("SELECT scenario_id, assumption_name, value, unit FROM scenario_assumptions WHERE assumption_name IN ('number_homes', 'useful_heat_per_home')")
print("\nModel boundary:", cursor.fetchall())

cursor.execute("SELECT scenario_id, assumption_name, value FROM scenario_assumptions WHERE assumption_name IN ('electric_heat_share', 'low_carbon_gas_heat_share')")
print("\nHeat shares:", cursor.fetchall())


cursor.execute("""
SELECT scenario_id, assumption_name, value, unit
FROM scenario_assumptions
ORDER BY scenario_id, assumption_name
""")

print("\nAll model assumptions:")
for row in cursor.fetchall(): print(row)


print("Table 'scenarios' created successfully.")

scenarios = [
    (
        1,
        "High Electrification",
        "A pathway with strong electrification of heat and reduced gas-network use.",
        1
    ),
    (
        2,
        "Hybrid Energy System",
        "A pathway combining electrification with continued use of low-carbon gases.",
        1
    ),
    (
        3,
        "Low-Carbon Gas / Biomethane",
        "A pathway with greater continued use of the gas network supported by biomethane and other low-carbon gases.",
        1
    )
]

cursor.execute("PRAGMA foreign_keys = ON")

cursor.execute("""
CREATE TABLE IF NOT EXISTS scenario_assumptions (
    assumption_id INTEGER PRIMARY KEY,
    scenario_id INTEGER NOT NULL,
    assumption_name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT,
    source_note TEXT,
    FOREIGN KEY (scenario_id) REFERENCES scenarios(scenario_id)
)
""")

print("Table 'scenario_assumptions' created successfully.")

columns = [col[1] for col in cursor.execute("PRAGMA table_info(scenario_assumptions)").fetchall()]

if "reference_year" not in columns:
    cursor.execute("ALTER TABLE scenario_assumptions ADD COLUMN reference_year INTEGER")
    print("Added 'reference_year' column.")
else:
    print("'reference_year' column already exists.")


columns = [row[1] for row in cursor.execute("PRAGMA table_info(scenario_assumptions)").fetchall()]

if "price_base_year" not in columns:
    cursor.execute("ALTER TABLE scenario_assumptions ADD COLUMN price_base_year INTEGER")
    print("Added 'price_base_year' column.")
else:
    print("'price_base_year' column already exists.")

if "is_user_adjustable" not in columns:
    cursor.execute("ALTER TABLE scenario_assumptions ADD COLUMN is_user_adjustable INTEGER")
    print("Added 'is_user_adjustable' column.")
else:
    print("'is_user_adjustable' column already exists.")

conn.commit()


cursor.executemany("""
INSERT OR REPLACE INTO scenarios
    (scenario_id, scenario_name, description, is_active)
VALUES (?, ?, ?, ?)
""", scenarios)

print("Three scenarios inserted successfully.")

scenario_names = [
    ("Electrification-led", 1),
    ("Whole-system hybrid", 2),
    ("Low-carbon gas-led", 3)
]

cursor.executemany("UPDATE scenarios SET scenario_name = ? WHERE scenario_id = ?", scenario_names)
conn.commit()

print("Scenario names updated.")

cursor.execute("SELECT scenario_id, scenario_name FROM scenarios")
print("\nUpdated scenarios:", cursor.fetchall())


cursor.execute("""
SELECT *
FROM scenarios
""")

cursor.execute("""
SELECT scenario_id, assumption_name, value, unit,
       reference_year, price_base_year, is_user_adjustable
FROM scenario_assumptions
""")

print("\nAll assumptions:", cursor.fetchall())

cursor.execute("SELECT scenario_id, scenario_name FROM scenarios WHERE scenario_id = 2")
row = cursor.fetchone()
print("\nFiltered scenario:", row)

cursor.execute("""
SELECT s.scenario_name, a.assumption_name, a.value, a.unit
FROM scenarios s
JOIN scenario_assumptions a ON s.scenario_id = a.scenario_id
""")

print("\nJoined data:", cursor.fetchall())

cursor.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_scenario_assumption
ON scenario_assumptions (scenario_id, assumption_name)
""")

print("Unique scenario-assumption rule confirmed.")

rows = cursor.fetchall()

for row in rows:
    print(row)


columns = cursor.execute("PRAGMA table_info(scenario_assumptions)").fetchall()

print("\nscenario_assumptions structure:")
for column in columns:
    print(column)


column_names = [row[1] for row in cursor.execute("PRAGMA table_info(scenario_assumptions)").fetchall()]
print("\nColumn names:", column_names)

conn.close()