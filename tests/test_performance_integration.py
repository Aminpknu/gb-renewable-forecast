"""Tests for the integrated forecasting validation area."""

from __future__ import annotations

import importlib

import pandas as pd

from app_utils.data_loading import available_historical_dates, load_historical_predictions


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
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        return " ".join(_text_content(child) for child in children)
    return _text_content(children)


def test_primary_navigation_has_exactly_four_validation_aware_items() -> None:
    app = importlib.import_module("app")

    assert app.NAVIGATION == [
        ("Day-ahead Forecast", "/"),
        ("Forecast Performance", "/performance"),
        ("2050 Heat Scenarios", "/scenarios"),
        ("Models, Data & Validation", "/methodology"),
    ]
    assert all(label != "Forecast vs Actual" for label, _path in app.NAVIGATION)


def test_performance_page_contains_both_views_and_locked_metrics() -> None:
    performance = importlib.import_module("pages.performance")
    rendered = performance.layout()
    text = _text_content(rendered)
    tabs = next(
        component
        for component in _walk_components(rendered)
        if getattr(component, "id", None) == "performance-view-tabs"
    )
    tab_labels = [tab.label for tab in tabs.children]

    assert "Day-ahead Forecast Performance" in text
    assert tab_labels == ["Overall performance", "Forecast vs actual"]
    assert "239.1 MW" in text
    assert "385.5 MW" in text
    assert "Locked aggregate metrics" in text
    assert "Wind mean bias" in text
    assert "Solar mean bias" in text


def test_history_payload_preserves_locked_daily_calculations_and_figures() -> None:
    performance = importlib.import_module("pages.performance")
    predictions = load_historical_predictions()
    selected_date = available_historical_dates(predictions)[-1]
    day = predictions.loc[
        predictions["settlement_date"] == pd.Timestamp(selected_date).date()
    ]
    wind_error = day["wind_pred_mw"] - day["embedded_wind_generation_mw"]
    solar_error = day["solar_pred_mw"] - day["embedded_solar_generation_mw"]

    wind_figure, solar_figure, *metrics = performance.history_day_payload(selected_date)

    assert metrics == [
        f"{wind_error.abs().mean():,.1f} MW",
        f"{wind_error.mean():+,.1f} MW",
        f"{solar_error.abs().mean():,.1f} MW",
        f"{solar_error.mean():+,.1f} MW",
    ]
    assert len(wind_figure.data) == 2
    assert len(solar_figure.data) == 2


def test_performance_query_selects_forecast_vs_actual_and_defaults_safely() -> None:
    performance = importlib.import_module("pages.performance")

    assert performance.performance_view_from_search(None) == "overall"
    assert performance.performance_view_from_search("") == "overall"
    assert performance.performance_view_from_search("?view=unknown") == "overall"
    assert (
        performance.performance_view_from_search("?view=forecast-vs-actual")
        == "forecast-vs-actual"
    )
    rendered = performance.layout(view="forecast-vs-actual")
    tabs = next(
        component
        for component in _walk_components(rendered)
        if getattr(component, "id", None) == "performance-view-tabs"
    )
    assert tabs.value == "forecast-vs-actual"


def test_history_route_is_redirect_only_and_preserves_payload_import() -> None:
    history = importlib.import_module("pages.history")
    rendered = history.layout()
    locations = [
        component
        for component in _walk_components(rendered)
        if getattr(component, "id", None) == "history-compatibility-redirect"
    ]

    assert history.FORECAST_VS_ACTUAL_URL == "/performance?view=forecast-vs-actual"
    assert len(locations) == 1
    assert locations[0].href == history.FORECAST_VS_ACTUAL_URL
    assert locations[0].refresh is True
    selected_date = available_historical_dates()[-1]
    assert history.history_day_payload(selected_date)[2:] == importlib.import_module(
        "pages.performance"
    ).history_day_payload(selected_date)[2:]


def test_existing_routes_remain_registered() -> None:
    importlib.import_module("app")
    import dash

    pages = {entry["path"]: entry for entry in dash.page_registry.values()}
    assert {"/", "/performance", "/history", "/scenarios", "/methodology"} == set(pages)
