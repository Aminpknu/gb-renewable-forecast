"""Display formatting helpers shared by dashboard pages."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd


def format_power_mw(value: float) -> str:
    """Format a power value intelligently as MW or GW."""

    value = float(value)
    if abs(value) >= 1_000:
        return f"{value / 1_000:.2f} GW"
    return f"{value:,.0f} MW"


def format_energy_mwh(value: float) -> str:
    """Format an energy value intelligently as MWh or GWh."""

    value = float(value)
    if abs(value) >= 1_000:
        return f"{value / 1_000:,.1f} GWh"
    return f"{value:,.0f} MWh"


def format_local_time(value: Any) -> str:
    """Format a timestamp as a concise local clock time."""

    return pd.Timestamp(value).strftime("%H:%M")


def format_date(value: Any) -> str:
    """Format an ISO-like date for public display."""

    if isinstance(value, date):
        parsed = pd.Timestamp(value)
    else:
        parsed = pd.Timestamp(str(value))
    return parsed.strftime("%d %b %Y")
