"""Reusable, database-independent scenario calculations.

The assumptions use the units stored in the existing SQLite prototype.  In
particular, ``discount_rate`` is a percentage (for example, ``3.5``) and the
energy quantities are annual MWh.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite


REFERENCE_GAS_SHARE = 0.80

_REQUIRED_ASSUMPTIONS = (
    "number_homes",
    "useful_heat_per_home",
    "electric_heat_share",
    "low_carbon_gas_heat_share",
    "heat_pump_cop",
    "gas_heating_efficiency",
    "electricity_lrvc",
    "low_carbon_gas_cost",
    "electricity_emissions_factor",
    "low_carbon_gas_emissions_factor",
    "carbon_value",
    "heat_pump_capex",
    "low_carbon_gas_capex",
    "heat_pump_lifetime",
    "low_carbon_gas_lifetime",
    "discount_rate",
    "peak_heat_kw_per_home",
)

_NON_NEGATIVE_ASSUMPTIONS = (
    "number_homes",
    "useful_heat_per_home",
    "electric_heat_share",
    "low_carbon_gas_heat_share",
    "electricity_lrvc",
    "low_carbon_gas_cost",
    "electricity_emissions_factor",
    "low_carbon_gas_emissions_factor",
    "carbon_value",
    "heat_pump_capex",
    "low_carbon_gas_capex",
    "peak_heat_kw_per_home",
)


def capital_recovery_factor(discount_rate: float, lifetime_years: float) -> float:
    """Return the capital recovery factor for a decimal discount rate.

    The scenario assumption ``discount_rate`` is converted from percent to a
    decimal before calling this function.
    """

    if not isfinite(discount_rate) or discount_rate <= 0:
        raise ValueError("Discount rate must be a positive finite decimal.")
    if not isfinite(lifetime_years) or lifetime_years <= 0:
        raise ValueError("Asset lifetime must be a positive finite number of years.")

    growth_factor = (1 + discount_rate) ** lifetime_years
    return discount_rate * growth_factor / (growth_factor - 1)


def _validated_values(assumptions: Mapping[str, float], scenario_name: str) -> dict[str, float]:
    """Validate and normalise the small, fixed scenario input contract."""

    missing = [key for key in _REQUIRED_ASSUMPTIONS if key not in assumptions]
    if missing:
        raise ValueError(f"{scenario_name}: missing required assumptions: {', '.join(missing)}.")

    values = {key: float(assumptions[key]) for key in _REQUIRED_ASSUMPTIONS}
    non_finite = [key for key, value in values.items() if not isfinite(value)]
    if non_finite:
        raise ValueError(f"{scenario_name}: assumptions must be finite: {', '.join(non_finite)}.")

    negative = [key for key in _NON_NEGATIVE_ASSUMPTIONS if values[key] < 0]
    if negative:
        raise ValueError(f"{scenario_name}: values cannot be negative: {', '.join(negative)}.")

    if values["heat_pump_cop"] <= 0:
        raise ValueError(f"{scenario_name}: heat pump COP must be greater than zero.")
    if values["gas_heating_efficiency"] <= 0:
        raise ValueError(f"{scenario_name}: gas heating efficiency must be greater than zero.")
    if values["heat_pump_lifetime"] <= 0 or values["low_carbon_gas_lifetime"] <= 0:
        raise ValueError(f"{scenario_name}: technology lifetimes must be greater than zero.")
    if values["discount_rate"] <= 0:
        raise ValueError(f"{scenario_name}: discount rate must be greater than zero.")

    heat_share_total = values["electric_heat_share"] + values["low_carbon_gas_heat_share"]
    if abs(heat_share_total - 1.0) > 1e-9:
        raise ValueError(f"{scenario_name}: heating shares do not sum to 1.")

    return values


def calculate_scenario(
    assumptions: Mapping[str, float], *, scenario_name: str = "Scenario"
) -> dict[str, float]:
    """Calculate annual transition metrics from one scenario's assumptions.

    This function deliberately contains no SQL or file-system logic.  It
    preserves the equations from the validated SQLite prototype, including
    the strategic gas-network utilisation proxy using ``REFERENCE_GAS_SHARE``.
    """

    values = _validated_values(assumptions, scenario_name)

    homes = values["number_homes"]
    useful_heat_per_home = values["useful_heat_per_home"]
    electric_share = values["electric_heat_share"]
    gas_share = values["low_carbon_gas_heat_share"]
    cop = values["heat_pump_cop"]
    gas_efficiency = values["gas_heating_efficiency"]

    total_useful_heat = homes * useful_heat_per_home
    electric_useful_heat = total_useful_heat * electric_share
    gas_useful_heat = total_useful_heat * gas_share

    electricity_demand = electric_useful_heat / cop
    gas_demand = gas_useful_heat / gas_efficiency

    electricity_energy_cost = electricity_demand * values["electricity_lrvc"]
    gas_energy_cost = gas_demand * values["low_carbon_gas_cost"]
    annual_energy_cost = electricity_energy_cost + gas_energy_cost

    heat_pump_homes = homes * electric_share
    gas_heated_homes = homes * gas_share
    heat_pump_investment = heat_pump_homes * values["heat_pump_capex"]
    gas_investment = gas_heated_homes * values["low_carbon_gas_capex"]
    initial_investment = heat_pump_investment + gas_investment

    discount_rate = values["discount_rate"] / 100
    heat_pump_crf = capital_recovery_factor(discount_rate, values["heat_pump_lifetime"])
    gas_crf = capital_recovery_factor(discount_rate, values["low_carbon_gas_lifetime"])
    annualised_heat_pump_capex = heat_pump_investment * heat_pump_crf
    annualised_gas_capex = gas_investment * gas_crf
    annualised_capex = annualised_heat_pump_capex + annualised_gas_capex

    electricity_emissions = electricity_demand * values["electricity_emissions_factor"]
    gas_emissions = gas_demand * values["low_carbon_gas_emissions_factor"]
    annual_emissions = electricity_emissions + gas_emissions
    carbon_cost = annual_emissions * values["carbon_value"]

    financial_annual_cost = annual_energy_cost + annualised_capex
    social_annual_cost = financial_annual_cost + carbon_cost

    electricity_peak_mw = heat_pump_homes * values["peak_heat_kw_per_home"] / cop / 1000
    reference_gas_throughput = total_useful_heat * REFERENCE_GAS_SHARE / gas_efficiency
    gas_utilisation_pct = gas_demand / reference_gas_throughput * 100

    return {
        "total_useful_heat_mwh": total_useful_heat,
        "electric_useful_heat_mwh": electric_useful_heat,
        "gas_useful_heat_mwh": gas_useful_heat,
        "electricity_demand_mwh": electricity_demand,
        "low_carbon_gas_demand_mwh": gas_demand,
        "electricity_energy_cost_gbp": electricity_energy_cost,
        "low_carbon_gas_energy_cost_gbp": gas_energy_cost,
        "annual_energy_cost_gbp": annual_energy_cost,
        "heat_pump_homes": heat_pump_homes,
        "low_carbon_gas_homes": gas_heated_homes,
        "heat_pump_investment_gbp": heat_pump_investment,
        "low_carbon_gas_investment_gbp": gas_investment,
        "initial_investment_gbp": initial_investment,
        "heat_pump_capital_recovery_factor": heat_pump_crf,
        "low_carbon_gas_capital_recovery_factor": gas_crf,
        "annualised_heat_pump_capex_gbp": annualised_heat_pump_capex,
        "annualised_low_carbon_gas_capex_gbp": annualised_gas_capex,
        "annualised_capex_gbp": annualised_capex,
        "electricity_emissions_tco2e": electricity_emissions,
        "low_carbon_gas_emissions_tco2e": gas_emissions,
        "annual_emissions_tco2e": annual_emissions,
        "carbon_cost_gbp": carbon_cost,
        "financial_annual_cost_gbp": financial_annual_cost,
        "social_annual_cost_gbp": social_annual_cost,
        "electricity_peak_mw": electricity_peak_mw,
        "reference_gas_throughput_mwh": reference_gas_throughput,
        "gas_network_utilisation_pct": gas_utilisation_pct,
    }
