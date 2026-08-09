"""Configuration for archived ECMWF IFS HRES weather forecasts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCATION_CONFIG = PROJECT_ROOT / "config" / "weather_locations.json"

OPEN_METEO_SINGLE_RUNS_ENDPOINT = "https://single-runs-api.open-meteo.com/v1/forecast"
WEATHER_SOURCE = "Open-Meteo Single Runs API"
WEATHER_MODEL = "ECMWF IFS HRES 9 km"
WEATHER_MODEL_API_IDENTIFIER = "ecmwf_ifs"
LOCAL_TIMEZONE = "Europe/London"
RUN_HOUR_UTC = 0
NOMINAL_ISSUE_HOUR_LOCAL = 9
FORECAST_HOURS = 49

HOURLY_VARIABLES = (
    "temperature_2m",
    "pressure_msl",
    "wind_speed_100m",
    "wind_direction_100m",
    "cloud_cover",
    "shortwave_radiation",
    "shortwave_radiation_instant",
)

VARIABLE_COLUMN_MAP = {
    "temperature_2m": "temperature_2m_c",
    "pressure_msl": "pressure_msl_hpa",
    "wind_speed_100m": "wind_speed_100m_ms",
    "wind_direction_100m": "wind_direction_100m_deg",
    "cloud_cover": "cloud_cover_pct",
    "shortwave_radiation": "shortwave_radiation_wm2",
    "shortwave_radiation_instant": "shortwave_radiation_instant_wm2",
}

EXPECTED_API_UNITS = {
    "temperature_2m": "°C",
    "pressure_msl": "hPa",
    "wind_speed_100m": "m/s",
    "wind_direction_100m": "°",
    "cloud_cover": "%",
    "shortwave_radiation": "W/m²",
    "shortwave_radiation_instant": "W/m²",
}


@dataclass(frozen=True)
class WeatherLocation:
    """A fixed representative weather sampling location."""

    name: str
    latitude: float
    longitude: float


def load_weather_locations(path: Path = DEFAULT_LOCATION_CONFIG) -> tuple[WeatherLocation, ...]:
    """Load and validate the representative GB location configuration."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    locations = tuple(WeatherLocation(**item) for item in payload["locations"])
    if len(locations) != 10:
        raise ValueError(f"Expected 10 weather locations, found {len(locations)}.")
    names = [location.name for location in locations]
    coordinates = [(location.latitude, location.longitude) for location in locations]
    if len(set(names)) != len(names):
        raise ValueError("Weather location names must be unique.")
    if len(set(coordinates)) != len(coordinates):
        raise ValueError("Weather location coordinates must be unique.")
    return locations
