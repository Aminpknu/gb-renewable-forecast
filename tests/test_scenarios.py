"""Tests for the lightweight UK Heat and Energy Network scenario calculations."""

from __future__ import annotations

import pytest

from src.scenarios.calculations import calculate_scenario, capital_recovery_factor


def _assumptions(electric_share: float, gas_share: float) -> dict[str, float]:
    """Return one default SQLite scenario as ordinary Python input data."""

    return {
        "number_homes": 1_000_000,
        "useful_heat_per_home": 10,
        "electric_heat_share": electric_share,
        "low_carbon_gas_heat_share": gas_share,
        "heat_pump_cop": 2.8,
        "gas_heating_efficiency": 0.84,
        "electricity_lrvc": 122.73,
        "low_carbon_gas_cost": 52.52,
        "electricity_emissions_factor": 0.002,
        "low_carbon_gas_emissions_factor": 0.05,
        "carbon_value": 398,
        "heat_pump_capex": 10_000,
        "low_carbon_gas_capex": 4_000,
        "heat_pump_lifetime": 15,
        "low_carbon_gas_lifetime": 15,
        "discount_rate": 3.5,
        "peak_heat_kw_per_home": 5,
    }


@pytest.mark.parametrize(
    ("name", "electric_share", "gas_share", "expected"),
    [
        (
            "Electrification-led",
            0.8,
            0.2,
            {
                "financial_annual_cost_gbp": 1_239_765_372.325853,
                "social_annual_cost_gbp": 1_289_420_610.4210913,
                "annual_emissions_tco2e": 124_761.90476190476,
                "initial_investment_gbp": 8_800_000_000,
                "electricity_peak_mw": 1_428.5714285714287,
                "gas_network_utilisation_pct": 25.0,
            },
        ),
        (
            "Whole-system hybrid",
            0.5,
            0.5,
            {
                "financial_annual_cost_gbp": 1_139_555_247.4669936,
                "social_annual_cost_gbp": 1_259_429_056.990803,
                "annual_emissions_tco2e": 301_190.4761904762,
                "initial_investment_gbp": 7_000_000_000,
                "electricity_peak_mw": 892.857142857143,
                "gas_network_utilisation_pct": 62.5,
            },
        ),
        (
            "Low-carbon gas-led",
            0.2,
            0.8,
            {
                "financial_annual_cost_gbp": 1_039_345_122.608134,
                "social_annual_cost_gbp": 1_229_437_503.560515,
                "annual_emissions_tco2e": 477_619.04761904763,
                "initial_investment_gbp": 5_200_000_000,
                "electricity_peak_mw": 357.14285714285717,
                "gas_network_utilisation_pct": 100.0,
            },
        ),
    ],
)
def test_default_scenarios_reproduce_validated_outputs(
    name: str, electric_share: float, gas_share: float, expected: dict[str, float]
) -> None:
    """Each default scenario must preserve the prototype's validated outputs."""

    results = calculate_scenario(_assumptions(electric_share, gas_share), scenario_name=name)

    for metric, expected_value in expected.items():
        assert results[metric] == pytest.approx(expected_value, rel=1e-12)


def test_capital_recovery_factor_for_3_5_percent_and_15_years() -> None:
    assert capital_recovery_factor(0.035, 15) == pytest.approx(0.0868250694, rel=1e-9)


def test_heating_shares_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="heating shares do not sum to 1"):
        calculate_scenario(_assumptions(0.8, 0.3))


def test_electricity_demand_equals_electric_useful_heat_divided_by_cop() -> None:
    results = calculate_scenario(_assumptions(0.8, 0.2))
    assert results["electricity_demand_mwh"] == pytest.approx(
        results["electric_useful_heat_mwh"] / 2.8
    )


def test_gas_demand_equals_gas_useful_heat_divided_by_efficiency() -> None:
    results = calculate_scenario(_assumptions(0.8, 0.2))
    assert results["low_carbon_gas_demand_mwh"] == pytest.approx(
        results["gas_useful_heat_mwh"] / 0.84
    )


def test_social_annual_cost_equals_financial_cost_plus_carbon_cost() -> None:
    results = calculate_scenario(_assumptions(0.5, 0.5))
    assert results["social_annual_cost_gbp"] == pytest.approx(
        results["financial_annual_cost_gbp"] + results["carbon_cost_gbp"]
    )


def test_invalid_cop_raises_clear_error() -> None:
    assumptions = _assumptions(0.8, 0.2)
    assumptions["heat_pump_cop"] = 0
    with pytest.raises(ValueError, match="COP must be greater than zero"):
        calculate_scenario(assumptions)


def test_invalid_gas_efficiency_raises_clear_error() -> None:
    assumptions = _assumptions(0.8, 0.2)
    assumptions["gas_heating_efficiency"] = 0
    with pytest.raises(ValueError, match="gas heating efficiency must be greater than zero"):
        calculate_scenario(assumptions)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("number_homes", -1),
        ("electricity_lrvc", -1),
        ("heat_pump_capex", -1),
    ],
)
def test_negative_values_that_must_be_non_negative_are_rejected(field: str, value: float) -> None:
    assumptions = _assumptions(0.8, 0.2)
    assumptions[field] = value
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_scenario(assumptions)


@pytest.mark.parametrize("electric_share, gas_share", [(0.8, 0.2), (0.5, 0.5), (0.2, 0.8)])
def test_default_gas_utilisation_is_a_percentage(electric_share: float, gas_share: float) -> None:
    results = calculate_scenario(_assumptions(electric_share, gas_share))
    assert 0 <= results["gas_network_utilisation_pct"] <= 100
