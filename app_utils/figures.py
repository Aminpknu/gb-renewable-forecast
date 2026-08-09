"""Plotly figure factories for consistent dashboard visuals."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

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
