# -*- coding: utf-8 -*-
"""
Created on Sun Aug  9 10:15:12 2026

@author: mz0013
"""

import sys
print(sys.executable)

#%% 1. Imports and paths

from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

TARGET_FILE = (
    ROOT / "data" / "interim" /
    "neso_embedded_wind_solar_targets.csv"
)

WEATHER_FILE = (
    ROOT / "data" / "interim" / "weather" /
    "ecmwf_ifs_hres_day_ahead_hourly.csv"
)

EXCLUSION_FILE = (
    ROOT / "data" / "raw" / "weather" /
    "excluded_target_dates.json"
)

OUTPUT_FILE = (
    ROOT / "data" / "processed" /
    "ml_dataset.csv"
)


#%% 2. Load datasets

targets = pd.read_csv(TARGET_FILE)
weather = pd.read_csv(WEATHER_FILE)

targets["valid_time_utc"] = pd.to_datetime(
    targets["valid_time_utc"],
    utc=True
)

targets["settlement_date"] = pd.to_datetime(
    targets["settlement_date"]
)

weather["valid_time_utc"] = pd.to_datetime(
    weather["valid_time_utc"],
    utc=True
)

weather["weather_run_init_utc"] = pd.to_datetime(
    weather["weather_run_init_utc"],
    utc=True
)

weather["target_date"] = pd.to_datetime(
    weather["target_date"]
)

print("Targets:", targets.shape)
print("Weather:", weather.shape)

print(
    "Weather target range:",
    weather["target_date"].min(),
    weather["target_date"].max()
)

#%% 3. Load documented exclusions
'''
with open(EXCLUSION_FILE, "r", encoding="utf-8") as f:
    exclusion_data = json.load(f)

print(exclusion_data)

print("Targets:", targets.shape)
print("Weather:", weather.shape)

print(
    "Weather target range:",
    weather["target_date"].min(),
    weather["target_date"].max()
)
'''
#%% 3. Load documented exclusions

with open(EXCLUSION_FILE, "r", encoding="utf-8") as f:
    exclusion_data = json.load(f)

print(type(exclusion_data))
print(exclusion_data)


#%% 4. Extract documented excluded target dates

excluded_dates = pd.to_datetime(
    [item["target_date"] for item in exclusion_data]
)

print("Excluded target dates:")
print(excluded_dates)

print("Number of exclusions:", len(excluded_dates))

assert len(excluded_dates) == 5



#%% 5. Restrict target data to modelling period and documented exclusions

targets = targets[
    (targets["settlement_date"] >= pd.Timestamp("2024-04-01")) &
    (targets["settlement_date"] <= pd.Timestamp("2025-08-31"))
].copy()

targets = targets[
    ~targets["settlement_date"].isin(excluded_dates)
].copy()

print("Target date range:")
print(targets["settlement_date"].min())
print(targets["settlement_date"].max())

print("Included target days:")
print(targets["settlement_date"].nunique())

print("Remaining excluded dates in targets:")
print(
    targets.loc[
        targets["settlement_date"].isin(excluded_dates),
        "settlement_date"
    ].unique()
)
print("Target rows after exclusions:", len(targets))


#%% 6. Convert wind direction to vector components

theta = np.deg2rad(
    weather["wind_direction_100m_deg"]
)

weather["wind_dir_sin"] = np.sin(theta)
weather["wind_dir_cos"] = np.cos(theta)

print(
    weather[
        [
            "wind_direction_100m_deg",
            "wind_dir_sin",
            "wind_dir_cos"
        ]
    ].head()
)

#%% 7. Interpolate hourly weather to NESO half-hour timestamps safely

WEATHER_VARS = [
    "temperature_2m_c",
    "pressure_msl_hpa",
    "wind_speed_100m_ms",
    "cloud_cover_pct",
    "shortwave_radiation_instant_wm2",
    "wind_dir_sin",
    "wind_dir_cos",
]

interpolated_groups = []

for (location, target_date), group in weather.groupby(
    ["location_name", "target_date"]
):

    # Get only the NESO half-hour timestamps belonging
    # to this same target day
    target_times = (
        targets.loc[
            targets["settlement_date"] == target_date,
            "valid_time_utc"
        ]
        .drop_duplicates()
        .sort_values()
    )

    # Excluded target dates will have no target timestamps
    if len(target_times) == 0:
        continue

    # Prepare the hourly weather time series
    group = (
        group
        .sort_values("valid_time_utc")
        .drop_duplicates("valid_time_utc")
        .set_index("valid_time_utc")
    )

    # Combine hourly weather timestamps with required
    # half-hour NESO timestamps
    combined_index = (
        group.index
        .union(pd.DatetimeIndex(target_times))
        .sort_values()
    )

    temp = (
        group[WEATHER_VARS]
        .reindex(combined_index)
        .interpolate(method="time")
    )

    # Keep only NESO half-hour timestamps
    temp = temp.reindex(
        pd.DatetimeIndex(target_times)
    )

    temp["location_name"] = location
    temp["target_date"] = target_date
    temp["valid_time_utc"] = temp.index

    interpolated_groups.append(
        temp.reset_index(drop=True)
    )

weather_30m = pd.concat(
    interpolated_groups,
    ignore_index=True
)

print("Interpolated weather shape:", weather_30m.shape)

print("\nMissing values:")
print(weather_30m[WEATHER_VARS].isna().sum())


#%% 8. Validate interpolated location coverage

location_counts = (
    weather_30m
    .groupby("valid_time_utc")["location_name"]
    .nunique()
)

print("Location-count distribution:")
print(location_counts.value_counts().sort_index())

print("\nMinimum locations per timestamp:")
print(location_counts.min())

print("\nMaximum locations per timestamp:")
print(location_counts.max())

print("\nDuplicate location-time rows:")
print(
    weather_30m.duplicated(
        subset=["location_name", "valid_time_utc"]
    ).sum()
)

assert len(weather_30m) == len(targets) * 10

assert location_counts.min() == 10
assert location_counts.max() == 10

assert (
    weather_30m[WEATHER_VARS]
    .isna()
    .sum()
    .sum()
    == 0
)

assert (
    weather_30m.duplicated(
        subset=["location_name", "valid_time_utc"]
    ).sum()
    == 0
)

sample_time = weather_30m[
    weather_30m["shortwave_radiation_instant_wm2"] > 0
]["valid_time_utc"].iloc[1000]

print(
    weather_30m.loc[
        weather_30m["valid_time_utc"] == sample_time,
        [
            "location_name",
            "wind_speed_100m_ms",
            "cloud_cover_pct",
            "shortwave_radiation_instant_wm2",
        ]
    ]
)



#%% 9. Aggregate the 10 locations into GB-level weather features

gb_weather = (
    weather_30m
    .groupby("valid_time_utc")
    .agg(
        # Wind
        wind_speed_mean=(
            "wind_speed_100m_ms", "mean"
        ),
        wind_speed_max=(
            "wind_speed_100m_ms", "max"
        ),
        wind_speed_std=(
            "wind_speed_100m_ms", "std"
        ),

        # Temperature
        temperature_mean=(
            "temperature_2m_c", "mean"
        ),
        temperature_std=(
            "temperature_2m_c", "std"
        ),

        # Pressure
        pressure_mean=(
            "pressure_msl_hpa", "mean"
        ),

        # Cloud
        cloud_mean=(
            "cloud_cover_pct", "mean"
        ),
        cloud_std=(
            "cloud_cover_pct", "std"
        ),

        # Solar radiation
        radiation_mean=(
            "shortwave_radiation_instant_wm2", "mean"
        ),
        radiation_max=(
            "shortwave_radiation_instant_wm2", "max"
        ),
        radiation_std=(
            "shortwave_radiation_instant_wm2", "std"
        ),

        # Wind direction vector components
        wind_dir_sin_mean=(
            "wind_dir_sin", "mean"
        ),
        wind_dir_cos_mean=(
            "wind_dir_cos", "mean"
        ),
    )
    .reset_index()
)

print("GB weather shape:", gb_weather.shape)

print("\nMissing values:")
print(gb_weather.isna().sum())

print("\nFirst rows:")
print(gb_weather.head())

#%% 10. GB weather sanity checks

print("\nWind speed:")
print(
    gb_weather[
        [
            "wind_speed_mean",
            "wind_speed_max",
            "wind_speed_std"
        ]
    ].describe()
)

print("\nRadiation:")
print(
    gb_weather[
        [
            "radiation_mean",
            "radiation_max",
            "radiation_std"
        ]
    ].describe()
)

print("\nCloud:")
print(
    gb_weather[
        [
            "cloud_mean",
            "cloud_std"
        ]
    ].describe()
)

assert (gb_weather["wind_speed_mean"] >= 0).all()

assert (
    gb_weather["wind_speed_max"]
    >= gb_weather["wind_speed_mean"]
).all()

assert (gb_weather["radiation_mean"] >= 0).all()

assert (
    gb_weather["cloud_mean"]
    .between(0, 100)
    .all()
)

#%% 11. Merge GB weather features with NESO targets

df = targets.merge(
    gb_weather,
    on="valid_time_utc",
    how="left",
    validate="one_to_one"
)

print("Merged shape:", df.shape)

print("\nMissing weather after merge:")
print(
    df[
        [
            "wind_speed_mean",
            "radiation_mean",
            "cloud_mean",
            "temperature_mean"
        ]
    ].isna().sum()
)

print("\nDuplicate timestamps:")
print(
    df["valid_time_utc"]
    .duplicated()
    .sum()
)

assert len(df) == len(targets)

assert (
    df["valid_time_utc"]
    .duplicated()
    .sum()
    == 0
)

assert (
    df[
        [
            "wind_speed_mean",
            "radiation_mean",
            "cloud_mean",
            "temperature_mean"
        ]
    ]
    .isna()
    .sum()
    .sum()
    == 0
)


#%% 12. Calendar features

local_time = df["valid_time_utc"].dt.tz_convert("Europe/London")

hour_decimal = (
    local_time.dt.hour
    + local_time.dt.minute / 60
)

day_of_year = local_time.dt.dayofyear

df["hour_sin"] = np.sin(
    2 * np.pi * hour_decimal / 24
)

df["hour_cos"] = np.cos(
    2 * np.pi * hour_decimal / 24
)

df["doy_sin"] = np.sin(
    2 * np.pi * day_of_year / 365.25
)

df["doy_cos"] = np.cos(
    2 * np.pi * day_of_year / 365.25
)

df["month"] = local_time.dt.month


#%% 13. Define model feature sets

WIND_FEATURES = [
    "wind_speed_mean",
    "wind_speed_max",
    "wind_speed_std",
    "temperature_mean",
    "temperature_std",
    "pressure_mean",
    "wind_dir_sin_mean",
    "wind_dir_cos_mean",
    "hour_sin",
    "hour_cos",
    "doy_sin",
    "doy_cos",
]

SOLAR_FEATURES = [
    "radiation_mean",
    "radiation_max",
    "radiation_std",
    "cloud_mean",
    "cloud_std",
    "temperature_mean",
    "hour_sin",
    "hour_cos",
    "doy_sin",
    "doy_cos",
]

print("Wind features:", len(WIND_FEATURES))
print("Solar features:", len(SOLAR_FEATURES))


#%% 14. Chronological train / validation / test split

date = df["settlement_date"]

df["split"] = np.select(
    [
        (
            (date >= pd.Timestamp("2024-04-01")) &
            (date <= pd.Timestamp("2025-03-31"))
        ),
        (
            (date >= pd.Timestamp("2025-04-01")) &
            (date <= pd.Timestamp("2025-05-31"))
        ),
        (
            (date >= pd.Timestamp("2025-06-01")) &
            (date <= pd.Timestamp("2025-08-31"))
        ),
    ],
    [
        "train",
        "validation",
        "test",
    ],
    default="exclude"
)

print("Row counts:")
print(df["split"].value_counts())

print("\nUnique days:")
print(
    df.groupby("split")["settlement_date"]
    .nunique()
)


#%% 15. Final Stage 4 audit

all_features = sorted(
    set(WIND_FEATURES + SOLAR_FEATURES)
)

print("Total rows:", len(df))
print("Unique target days:", df["settlement_date"].nunique())

print("\nDuplicate UTC timestamps:")
print(df["valid_time_utc"].duplicated().sum())

print("\nMissing targets:")
print(
    df[
        ["wind_cf", "solar_cf"]
    ].isna().sum()
)

print("\nMissing model features:")
print(
    df[all_features].isna().sum()
)

print("\nSplit row counts:")
print(df["split"].value_counts())

print("\nSplit day counts:")
print(
    df.groupby("split")["settlement_date"]
    .nunique()
)

print("\nWind CF summary:")
print(df["wind_cf"].describe())

print("\nSolar CF summary:")
print(df["solar_cf"].describe())

#%% 16. Hard validation checks

assert len(df) == 24624

assert df["settlement_date"].nunique() == 513

assert df["valid_time_utc"].duplicated().sum() == 0

assert (
    df[["wind_cf", "solar_cf"]]
    .isna()
    .sum()
    .sum()
    == 0
)

assert (
    df[all_features]
    .isna()
    .sum()
    .sum()
    == 0
)

assert not df["settlement_date"].isin(excluded_dates).any()

assert set(df["split"].unique()) == {
    "train",
    "validation",
    "test"
}


# Verify chronological ordering between splits

train_max = df.loc[
    df["split"] == "train",
    "valid_time_utc"
].max()

validation_min = df.loc[
    df["split"] == "validation",
    "valid_time_utc"
].min()

validation_max = df.loc[
    df["split"] == "validation",
    "valid_time_utc"
].max()

test_min = df.loc[
    df["split"] == "test",
    "valid_time_utc"
].min()

print("Train max:", train_max)
print("Validation min:", validation_min)
print("Validation max:", validation_max)
print("Test min:", test_min)

assert train_max < validation_min
assert validation_max < test_min


#%% 17. Save Stage 4 ML-ready dataset

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

df.to_csv(
    OUTPUT_FILE,
    index=False
)

print("Saved:", OUTPUT_FILE)
print("Final shape:", df.shape)


print(df.shape)

print(
    df.groupby("split")["settlement_date"]
    .nunique()
)

print(df["split"].value_counts())

print(
    df[all_features]
    .isna()
    .sum()
)

print(df["wind_cf"].describe())
print(df["solar_cf"].describe())
