"""Tests for the Models, Data & Validation guide."""

from __future__ import annotations

import importlib

import pytest

from app_utils.data_loading import load_final_test_metrics, load_model_metadata


def _walk_components(component):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk_components(child)
    elif children is not None:
        yield from _walk_components(children)


def _text_content(component) -> str:
    if component is None:
        return ""
    if isinstance(component, (str, int, float)):
        return str(component)
    return " ".join(_text_content(child) for child in _walk_children(component))


def _walk_children(component):
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        return children
    if children is None:
        return []
    return [children]


@pytest.fixture
def guide_page():
    importlib.import_module("app")
    return importlib.import_module("pages.methodology")


def test_navigation_labels_change_without_breaking_routes(guide_page) -> None:
    import app
    import dash

    assert app.NAVIGATION == [
        ("Day-ahead Forecast", "/"),
        ("Forecast Performance", "/performance"),
        ("2050 Heat Scenarios", "/scenarios"),
        ("Models, Data & Validation", "/methodology"),
    ]

    pages = {entry["path"]: entry for entry in dash.page_registry.values()}
    assert pages["/"]["name"] == "Day-ahead Forecast"
    assert pages["/performance"]["name"] == "Forecast Performance"
    assert pages["/scenarios"]["name"] == "2050 Heat Scenarios"
    assert pages["/methodology"]["name"] == "Models, Data & Validation"


def test_guide_contains_required_sections_equations_and_links(guide_page) -> None:
    rendered = guide_page.layout()
    text = _text_content(rendered)
    links = {
        getattr(component, "href", None)
        for component in _walk_components(rendered)
        if getattr(component, "href", None)
    }

    for expected in (
        "How to read this guide",
        "Part A",
        "Day-ahead renewable forecasting",
        "How does the model turn weather into a generation forecast?",
        "What did the model predict, and what actually happened?",
        "How do we avoid data leakage?",
        "Part B",
        "2050 energy-transition scenario analysis",
        "What are the three scenarios?",
        "Emissions and costs",
        "Which inputs come from published sources, and which are modelling choices?",
        "What are the scenario limitations?",
        "Part C",
        "How the models are kept transparent and reproducible",
        "Q_{total}",
        "MAE=",
        "100% gas-network utilisation",
    ):
        assert expected in text

    assert {"/performance", "/performance?view=forecast-vs-actual", "/scenarios"}.issubset(links)
    assert "/history" not in links
    assert {"#forecasting", "#scenario-analysis", "#reproducibility"}.issubset(links)


def test_guide_parts_and_reader_order_are_explicit(guide_page) -> None:
    rendered = guide_page.layout()
    top_level_ids = [
        getattr(component, "id", None)
        for component in _walk_children(rendered)
        if getattr(component, "id", None)
    ]
    assert top_level_ids == [
        "model-scope",
        "forecasting",
        "scenario-analysis",
        "reproducibility",
    ]

    text = _text_content(rendered)
    assert text.index("How the forecast is produced") < text.index("How accurate is it?")
    assert text.index("How accurate is it?") < text.index("How do we avoid data leakage?")
    assert text.index("What are the three scenarios?") < text.index("How are the outputs calculated?")
    assert text.index("Which inputs come from published sources") < text.index("How does the sensitivity analysis work?")


def test_guide_metrics_use_locked_files_and_model_metadata(guide_page) -> None:
    data = guide_page.guide_data()
    metrics = load_final_test_metrics().set_index("Technology")
    metadata = load_model_metadata()

    assert data["metrics"]["wind"]["model"] == metadata["wind_model"]["algorithm"]
    assert data["metrics"]["solar"]["model"] == metadata["solar_model"]["algorithm"]
    assert data["metrics"]["wind"]["mae_mw"] == pytest.approx(
        metrics.loc["Wind", "MAE_MW"]
    )
    assert data["metrics"]["solar"]["r2"] == pytest.approx(
        metrics.loc["Solar", "R2"]
    )


def test_three_scenario_definitions_and_shares_are_loaded_from_sqlite(guide_page) -> None:
    scenarios = guide_page.guide_data()["scenarios"]

    assert [scenario["scenario_name"] for scenario in scenarios] == [
        "Electrification-led",
        "Whole-system hybrid",
        "Low-carbon gas-led",
    ]
    assert [scenario["electric_share"] for scenario in scenarios] == pytest.approx(
        [0.8, 0.5, 0.2]
    )
    assert [scenario["gas_share"] for scenario in scenarios] == pytest.approx(
        [0.2, 0.5, 0.8]
    )


def test_provenance_distinguishes_sources_and_preserves_six_controls(guide_page) -> None:
    from pages.scenarios import ADJUSTABLE_FIELDS

    assumptions = guide_page.guide_data()["assumptions"]
    by_name = {record["assumption_name"]: record for record in assumptions}

    assert len(ADJUSTABLE_FIELDS) == 6
    assert sum(bool(record["is_user_adjustable"]) for record in assumptions) == 6
    assert by_name["discount_rate"]["evidence_type"] == "Source-informed"
    assert by_name["heat_pump_cop"]["evidence_type"] == "Source-informed"
    assert by_name["number_homes"]["evidence_type"] == "Illustrative"
    assert by_name["low_carbon_gas_emissions_factor"]["evidence_type"] == "Illustrative"
    assert all(record["source_note"] for record in assumptions)
