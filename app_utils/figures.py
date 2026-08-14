"""Plotly figure factories for consistent dashboard visuals."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app_utils.theme import COLORS, base_layout


def _finish(figure: go.Figure, *, title: str, y_title: str, height: int = 430) -> go.Figure:
    layout = base_layout(height=height)
    figure.update_layout(title={"text": title, "x": 0.0, "xanchor": "left"}, **layout)
    figure.update_xaxes(title_text="Local target time")
    figure.update_yaxes(title_text=y_title, tickformat=",")
    return figure


def forecast_figure(frame: pd.DataFrame) -> go.Figure:
    """Build the live wind/solar forecast chart."""

    figure = go.Figure()
    common = (
        "<b>%{x|%d %b %H:%M}</b><br>"
        "Settlement period: %{customdata[0]:.0f}<br>"
        "Generation: %{y:,.1f} MW<br>"
        "Capacity factor: %{customdata[1]:.3f}<extra></extra>"
    )
    figure.add_trace(
        go.Scatter(
            x=frame["valid_time_local"],
            y=frame["wind_forecast_mw"],
            customdata=frame[["settlement_period", "wind_pred_cf"]],
            name="Embedded wind forecast",
            mode="lines",
            line={"color": COLORS["wind"], "width": 3},
            hovertemplate=common,
        )
    )
    figure.add_trace(
        go.Scatter(
            x=frame["valid_time_local"],
            y=frame["solar_forecast_mw"],
            customdata=frame[["settlement_period", "solar_pred_cf"]],
            name="Embedded solar forecast",
            mode="lines",
            line={"color": COLORS["solar"], "width": 3},
            hovertemplate=common,
        )
    )
    return _finish(
        figure,
        title="Next-day embedded generation forecast",
        y_title="Forecast generation (MW)",
        height=470,
    )


def model_vs_baseline_figure(metrics: pd.DataFrame) -> go.Figure:
    """Compare locked model MAE against monthly climatology."""

    technologies = metrics["Technology"].tolist()
    figure = go.Figure()
    figure.add_bar(
        x=technologies,
        y=metrics["Baseline_MAE_MW"],
        name="Monthly climatology",
        marker_color=COLORS["baseline"],
        text=metrics["Baseline_MAE_MW"].map(lambda value: f"{value:,.1f}"),
        textposition="outside",
        hovertemplate="%{x}<br>Monthly climatology MAE: %{y:,.1f} MW<extra></extra>",
    )
    figure.add_bar(
        x=technologies,
        y=metrics["MAE_MW"],
        name="Selected model",
        marker_color=[COLORS["wind"], COLORS["solar"]],
        text=metrics["MAE_MW"].map(lambda value: f"{value:,.1f}"),
        textposition="outside",
        hovertemplate="%{x}<br>Selected-model MAE: %{y:,.1f} MW<extra></extra>",
    )
    figure.update_layout(barmode="group")
    return _finish(
        figure,
        title="Locked test MAE: selected models vs baseline",
        y_title="Mean absolute error (MW)",
        height=410,
    )


def daily_error_figure(daily: pd.DataFrame) -> go.Figure:
    """Plot daily wind and solar MAE during the locked test period."""

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=daily["settlement_date"],
            y=daily["wind_mae_mw"],
            name="Wind daily MAE",
            mode="lines",
            line={"color": COLORS["wind"], "width": 2},
            hovertemplate="%{x|%d %b %Y}<br>Wind MAE: %{y:,.1f} MW<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=daily["settlement_date"],
            y=daily["solar_mae_mw"],
            name="Solar daily MAE",
            mode="lines",
            line={"color": COLORS["solar"], "width": 2},
            hovertemplate="%{x|%d %b %Y}<br>Solar MAE: %{y:,.1f} MW<extra></extra>",
        )
    )
    return _finish(
        figure,
        title="Daily error across the untouched test period",
        y_title="Daily MAE (MW)",
        height=430,
    )


def historical_generation_figure(
    day: pd.DataFrame, *, technology: str
) -> go.Figure:
    """Plot actual and forecast generation for one historical test day."""

    if technology == "wind":
        actual_column = "embedded_wind_generation_mw"
        forecast_column = "wind_pred_mw"
        accent = COLORS["wind"]
        label = "Wind"
    elif technology == "solar":
        actual_column = "embedded_solar_generation_mw"
        forecast_column = "solar_pred_mw"
        accent = COLORS["solar"]
        label = "Solar"
    else:
        raise ValueError(f"Unknown technology: {technology}")

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=day["valid_time_local"],
            y=day[actual_column],
            name="Actual embedded generation",
            mode="lines",
            line={"color": COLORS["actual"], "width": 3},
            hovertemplate="%{x|%H:%M}<br>Actual: %{y:,.1f} MW<extra></extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=day["valid_time_local"],
            y=day[forecast_column],
            name="Model forecast",
            mode="lines",
            line={"color": accent, "width": 2.5, "dash": "dash"},
            hovertemplate="%{x|%H:%M}<br>Forecast: %{y:,.1f} MW<extra></extra>",
        )
    )
    return _finish(
        figure,
        title=f"{label}: forecast versus actual",
        y_title="Embedded generation (MW)",
        height=400,
    )


def scenario_cost_investment_figure(comparison: pd.DataFrame) -> go.Figure:
    """Compare recurring annual costs and upfront investment by scenario."""

    figure = go.Figure()
    series = (
        (
            "Financial annual cost",
            "financial_annual_cost_gbp",
            COLORS["wind"],
            "Financial annual cost: £%{y:.2f}bn/year",
        ),
        (
            "Social annual cost",
            "social_annual_cost_gbp",
            COLORS["solar"],
            "Social annual cost: £%{y:.2f}bn/year",
        ),
        (
            "Initial investment",
            "initial_investment_gbp",
            COLORS["actual"],
            "Initial investment: £%{y:.2f}bn upfront",
        ),
    )
    for label, column, color, hover in series:
        values = comparison[column] / 1e9
        figure.add_bar(
            x=comparison["scenario_name"],
            y=values,
            name=label,
            marker_color=color,
            customdata=comparison["scenario_name"],
            hovertemplate="<b>%{customdata}</b><br>" + hover + "<extra></extra>",
        )

    layout = base_layout(height=440)
    figure.update_layout(
        title={"text": "Default scenario costs and investment", "x": 0, "xanchor": "left"},
        barmode="group",
        **layout,
    )
    figure.update_xaxes(title_text="Scenario")
    figure.update_yaxes(title_text="Value (£bn)", tickformat=".1f")
    return figure


def scenario_trade_offs_figure(comparison: pd.DataFrame) -> go.Figure:
    """Show emissions and network proxies on three independent scales."""

    figure = make_subplots(
        rows=1,
        cols=3,
        shared_yaxes=True,
        horizontal_spacing=0.08,
        subplot_titles=(
            "Annual emissions",
            "Electricity peak proxy",
            "Gas-network utilisation proxy",
        ),
    )
    panels = (
        ("annual_emissions_tco2e", 1e6, "MtCO2e/year", COLORS["negative"], ".3f"),
        ("electricity_peak_mw", 1, "MW", COLORS["wind"], ",.0f"),
        ("gas_network_utilisation_pct", 1, "%", COLORS["solar"], ".1f"),
    )
    for column_index, (column, divisor, unit, color, number_format) in enumerate(panels, 1):
        figure.add_trace(
            go.Bar(
                x=comparison[column] / divisor,
                y=comparison["scenario_name"],
                orientation="h",
                marker_color=color,
                showlegend=False,
                customdata=comparison["scenario_name"],
                hovertemplate=(
                    "<b>%{customdata}</b><br>%{x:" + number_format + "} " + unit + "<extra></extra>"
                ),
            ),
            row=1,
            col=column_index,
        )
        figure.update_xaxes(title_text=unit, row=1, col=column_index)

    layout = base_layout(height=430)
    layout["showlegend"] = False
    figure.update_layout(
        title={"text": "Default scenario system trade-offs", "x": 0, "xanchor": "left"},
        **layout,
    )
    figure.update_yaxes(autorange="reversed", row=1, col=1)
    return figure


def scenario_sensitivity_figure(sensitivity: pd.DataFrame, scenario_name: str) -> go.Figure:
    """Build a one-at-a-time ±20% social-cost sensitivity chart."""

    figure = go.Figure()
    figure.add_bar(
        y=sensitivity["label"],
        x=sensitivity["low_change_gbp_m"],
        orientation="h",
        name="Parameter −20%",
        marker_color=COLORS["positive"],
        customdata=sensitivity[["low_parameter_value", "base_parameter_value"]],
        hovertemplate=(
            "<b>%{y}</b><br>Parameter: %{customdata[1]:,.2f} → %{customdata[0]:,.2f}"
            "<br>Social-cost change: £%{x:+,.1f}m/year<extra></extra>"
        ),
    )
    figure.add_bar(
        y=sensitivity["label"],
        x=sensitivity["high_change_gbp_m"],
        orientation="h",
        name="Parameter +20%",
        marker_color=COLORS["negative"],
        customdata=sensitivity[["high_parameter_value", "base_parameter_value"]],
        hovertemplate=(
            "<b>%{y}</b><br>Parameter: %{customdata[1]:,.2f} → %{customdata[0]:,.2f}"
            "<br>Social-cost change: £%{x:+,.1f}m/year<extra></extra>"
        ),
    )
    layout = base_layout(height=420)
    figure.update_layout(
        title={
            "text": f"{scenario_name}: ±20% one-at-a-time sensitivity",
            "x": 0,
            "xanchor": "left",
        },
        barmode="overlay",
        **layout,
    )
    figure.update_xaxes(
        title_text="Change from base social annual cost (£m/year)",
        zeroline=True,
        zerolinecolor=COLORS["actual"],
    )
    figure.update_yaxes(title_text="Assumption", autorange="reversed")
    return figure
