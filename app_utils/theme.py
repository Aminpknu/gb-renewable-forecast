"""Central Plotly theme values for the dashboard."""

COLORS = {
    "ink": "#152238",
    "muted": "#617087",
    "grid": "#DCE4EC",
    "surface": "#FFFFFF",
    "wind": "#176B87",
    "solar": "#D48A16",
    "actual": "#27364A",
    "baseline": "#94A3B8",
    "positive": "#277A55",
    "negative": "#B04747",
}

FONT_FAMILY = "Inter, Aptos, Segoe UI, sans-serif"


def base_layout(*, height: int = 430) -> dict:
    """Return consistent responsive Plotly layout settings."""

    return {
        "height": height,
        "margin": {"l": 56, "r": 24, "t": 70, "b": 52},
        "paper_bgcolor": COLORS["surface"],
        "plot_bgcolor": COLORS["surface"],
        "font": {"family": FONT_FAMILY, "color": COLORS["ink"], "size": 13},
        "hovermode": "x unified",
        "legend": {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        "xaxis": {"showgrid": False, "linecolor": COLORS["grid"]},
        "yaxis": {
            "gridcolor": COLORS["grid"],
            "zerolinecolor": COLORS["grid"],
            "rangemode": "tozero",
        },
    }
