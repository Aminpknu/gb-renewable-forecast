# -*- coding: utf-8 -*-
"""
Created on Sun Aug  9 10:56:56 2026

@author: mz0013
"""

import sklearn
print("scikit-learn:", sklearn.__version__)

try:
    import xgboost
    print("xgboost:", xgboost.__version__)
except ImportError:
    print("XGBoost is not installed")
    
import xgboost
print("XGBoost:", xgboost.__version__)


#%% 1. Imports and paths

from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

ROOT = Path(__file__).resolve().parents[2]

DATA_FILE = (
    ROOT / "data" / "processed" / "ml_dataset.csv"
)




#%% 2. Load ML-ready dataset

df = pd.read_csv(DATA_FILE)

df["valid_time_utc"] = pd.to_datetime(
    df["valid_time_utc"],
    utc=True
)

df["settlement_date"] = pd.to_datetime(
    df["settlement_date"]
)

print("Dataset shape:", df.shape)

print("\nSplit counts:")
print(df["split"].value_counts())

print("\nSplit days:")
print(
    df.groupby("split")["settlement_date"]
    .nunique()
)

#%% 3. Feature definitions

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

#%% 4. Split data

train = df[df["split"] == "train"].copy()
validation = df[df["split"] == "validation"].copy()

# Keep test separate and DO NOT evaluate it yet.
test = df[df["split"] == "test"].copy()

print("Train:", train.shape)
print("Validation:", validation.shape)
print("Test:", test.shape)

#%% 5. Evaluation helper

def regression_metrics(y_true, y_pred):
    mae = mean_absolute_error(y_true, y_pred)

    rmse = np.sqrt(
        mean_squared_error(y_true, y_pred)
    )

    r2 = r2_score(y_true, y_pred)

    return {
        "MAE": mae,
        "RMSE": rmse,
        "R2": r2,
    }


#%% 6. Seasonal baseline keys

def add_baseline_key(data):
    data = data.copy()

    local_time = (
        data["valid_time_utc"]
        .dt.tz_convert("Europe/London")
    )

    data["baseline_month"] = local_time.dt.month
    data["baseline_day"] = local_time.dt.day

    data["baseline_hour"] = local_time.dt.hour
    data["baseline_minute"] = local_time.dt.minute

    return data


train_b = add_baseline_key(train)
validation_b = add_baseline_key(validation)


#%% 7. Seasonal climatology baseline

BASELINE_KEYS = [
    "baseline_month",
    "baseline_day",
    "baseline_hour",
    "baseline_minute",
]

wind_climatology = (
    train_b
    .groupby(BASELINE_KEYS)["wind_cf"]
    .mean()
    .rename("wind_baseline")
    .reset_index()
)

solar_climatology = (
    train_b
    .groupby(BASELINE_KEYS)["solar_cf"]
    .mean()
    .rename("solar_baseline")
    .reset_index()
)


#%% 8. Baseline validation predictions

validation_b = validation_b.merge(
    wind_climatology,
    on=BASELINE_KEYS,
    how="left",
)

validation_b = validation_b.merge(
    solar_climatology,
    on=BASELINE_KEYS,
    how="left",
)

print(
    validation_b[
        ["wind_baseline", "solar_baseline"]
    ].isna().sum()
)

#%% 9. Baseline metrics

wind_baseline_metrics = regression_metrics(
    validation_b["wind_cf"],
    validation_b["wind_baseline"],
)

solar_baseline_metrics = regression_metrics(
    validation_b["solar_cf"],
    validation_b["solar_baseline"],
)

print("Wind baseline:")
print(wind_baseline_metrics)

print("\nSolar baseline:")
print(solar_baseline_metrics)


#%% 10. Baseline MW metrics

wind_actual_mw = (
    validation_b["wind_cf"]
    * validation_b["embedded_wind_capacity_mw"]
)

wind_pred_mw = (
    validation_b["wind_baseline"]
    * validation_b["embedded_wind_capacity_mw"]
)

solar_actual_mw = (
    validation_b["solar_cf"]
    * validation_b["embedded_solar_capacity_mw"]
)

solar_pred_mw = (
    validation_b["solar_baseline"]
    * validation_b["embedded_solar_capacity_mw"]
)

print(
    "Wind baseline MAE MW:",
    mean_absolute_error(
        wind_actual_mw,
        wind_pred_mw
    )
)

print(
    "Solar baseline MAE MW:",
    mean_absolute_error(
        solar_actual_mw,
        solar_pred_mw
    )
)

#%% 11. Monthly half-hour climatology baseline

CLIM_KEYS = [
    "baseline_month",
    "baseline_hour",
    "baseline_minute",
]

wind_monthly_clim = (
    train_b
    .groupby(CLIM_KEYS)["wind_cf"]
    .mean()
    .rename("wind_monthly_baseline")
    .reset_index()
)

solar_monthly_clim = (
    train_b
    .groupby(CLIM_KEYS)["solar_cf"]
    .mean()
    .rename("solar_monthly_baseline")
    .reset_index()
)

validation_b = validation_b.merge(
    wind_monthly_clim,
    on=CLIM_KEYS,
    how="left",
)

validation_b = validation_b.merge(
    solar_monthly_clim,
    on=CLIM_KEYS,
    how="left",
)

print(
    validation_b[
        [
            "wind_monthly_baseline",
            "solar_monthly_baseline"
        ]
    ].isna().sum()
)

#%% 12. Monthly climatology validation metrics

wind_monthly_metrics = regression_metrics(
    validation_b["wind_cf"],
    validation_b["wind_monthly_baseline"],
)

solar_monthly_metrics = regression_metrics(
    validation_b["solar_cf"],
    validation_b["solar_monthly_baseline"],
)

print("Wind monthly climatology:")
print(wind_monthly_metrics)

print("\nSolar monthly climatology:")
print(solar_monthly_metrics)

#%% 13. Monthly climatology MW metrics

wind_monthly_pred_mw = (
    validation_b["wind_monthly_baseline"]
    * validation_b["embedded_wind_capacity_mw"]
)

solar_monthly_pred_mw = (
    validation_b["solar_monthly_baseline"]
    * validation_b["embedded_solar_capacity_mw"]
)

print(
    "Wind monthly baseline MAE MW:",
    mean_absolute_error(
        wind_actual_mw,
        wind_monthly_pred_mw
    )
)

print(
    "Solar monthly baseline MAE MW:",
    mean_absolute_error(
        solar_actual_mw,
        solar_monthly_pred_mw
    )
)

#%% 14. Ridge imports

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge


#%% 15. Wind Ridge model

X_train_wind = train[WIND_FEATURES]
y_train_wind = train["wind_cf"]

X_val_wind = validation[WIND_FEATURES]
y_val_wind = validation["wind_cf"]

wind_ridge = Pipeline([
    ("scaler", StandardScaler()),
    ("model", Ridge(alpha=1.0))
])

wind_ridge.fit(
    X_train_wind,
    y_train_wind
)

wind_ridge_pred = wind_ridge.predict(
    X_val_wind
)

wind_ridge_pred = np.clip(
    wind_ridge_pred,
    0,
    1
)

wind_ridge_metrics = regression_metrics(
    y_val_wind,
    wind_ridge_pred
)

print("Wind Ridge:")
print(wind_ridge_metrics)


#%% 16. Solar Ridge model

X_train_solar = train[SOLAR_FEATURES]
y_train_solar = train["solar_cf"]

X_val_solar = validation[SOLAR_FEATURES]
y_val_solar = validation["solar_cf"]

solar_ridge = Pipeline([
    ("scaler", StandardScaler()),
    ("model", Ridge(alpha=1.0))
])

solar_ridge.fit(
    X_train_solar,
    y_train_solar
)

solar_ridge_pred = solar_ridge.predict(
    X_val_solar
)

solar_ridge_pred = np.clip(
    solar_ridge_pred,
    0,
    1
)

solar_ridge_metrics = regression_metrics(
    y_val_solar,
    solar_ridge_pred
)

print("Solar Ridge:")
print(solar_ridge_metrics)


#%% 17. Ridge MW MAE

wind_ridge_pred_mw = (
    wind_ridge_pred
    * validation["embedded_wind_capacity_mw"]
)

solar_ridge_pred_mw = (
    solar_ridge_pred
    * validation["embedded_solar_capacity_mw"]
)

wind_ridge_actual_mw = (
    validation["wind_cf"]
    * validation["embedded_wind_capacity_mw"]
)

solar_ridge_actual_mw = (
    validation["solar_cf"]
    * validation["embedded_solar_capacity_mw"]
)

print(
    "Wind Ridge MAE MW:",
    mean_absolute_error(
        wind_ridge_actual_mw,
        wind_ridge_pred_mw
    )
)

print(
    "Solar Ridge MAE MW:",
    mean_absolute_error(
        solar_ridge_actual_mw,
        solar_ridge_pred_mw
    )
)


#%% ExtraTrees models: wind + solar + metrics + skill + importance

from sklearn.ensemble import ExtraTreesRegressor

# -------------------------
# WIND
# -------------------------

wind_extra = ExtraTreesRegressor(
    n_estimators=400,
    max_depth=None,
    min_samples_leaf=2,
    max_features=0.8,
    random_state=42,
    n_jobs=-1,
)

wind_extra.fit(
    X_train_wind,
    y_train_wind
)

wind_extra_pred = wind_extra.predict(
    X_val_wind
)

wind_extra_pred = np.clip(
    wind_extra_pred,
    0,
    1
)

wind_extra_metrics = regression_metrics(
    y_val_wind,
    wind_extra_pred
)

wind_extra_pred_mw = (
    wind_extra_pred
    * validation["embedded_wind_capacity_mw"]
)

wind_extra_mae_mw = mean_absolute_error(
    wind_ridge_actual_mw,
    wind_extra_pred_mw
)

wind_extra_skill = (
    1
    - wind_extra_metrics["MAE"]
    / wind_monthly_metrics["MAE"]
)


# -------------------------
# SOLAR
# -------------------------

solar_extra = ExtraTreesRegressor(
    n_estimators=400,
    max_depth=None,
    min_samples_leaf=2,
    max_features=0.8,
    random_state=42,
    n_jobs=-1,
)

solar_extra.fit(
    X_train_solar,
    y_train_solar
)

solar_extra_pred = solar_extra.predict(
    X_val_solar
)

solar_extra_pred = np.clip(
    solar_extra_pred,
    0,
    1
)

solar_extra_metrics = regression_metrics(
    y_val_solar,
    solar_extra_pred
)

solar_extra_pred_mw = (
    solar_extra_pred
    * validation["embedded_solar_capacity_mw"]
)

solar_extra_mae_mw = mean_absolute_error(
    solar_ridge_actual_mw,
    solar_extra_pred_mw
)

solar_extra_skill = (
    1
    - solar_extra_metrics["MAE"]
    / solar_monthly_metrics["MAE"]
)


# -------------------------
# FEATURE IMPORTANCE
# -------------------------

wind_extra_importance = (
    pd.Series(
        wind_extra.feature_importances_,
        index=WIND_FEATURES
    )
    .sort_values(ascending=False)
)

solar_extra_importance = (
    pd.Series(
        solar_extra.feature_importances_,
        index=SOLAR_FEATURES
    )
    .sort_values(ascending=False)
)


# -------------------------
# RESULTS
# -------------------------

print("\n====================")
print("EXTRATREES RESULTS")
print("====================")

print("\nWIND:")
print(wind_extra_metrics)
print(
    "MAE MW:",
    wind_extra_mae_mw
)
print(
    "Skill vs monthly climatology:",
    f"{wind_extra_skill:.2%}"
)

print("\nTop wind features:")
print(
    wind_extra_importance.head(5)
)

print("\nSOLAR:")
print(solar_extra_metrics)
print(
    "MAE MW:",
    solar_extra_mae_mw
)
print(
    "Skill vs monthly climatology:",
    f"{solar_extra_skill:.2%}"
)

print("\nTop solar features:")
print(
    solar_extra_importance.head(5)
)


#%% XGBoost models: wind + solar + metrics + skill + importance

from xgboost import XGBRegressor


# -------------------------
# WIND
# -------------------------

wind_xgb = XGBRegressor(
    n_estimators=700,
    max_depth=5,
    learning_rate=0.03,
    subsample=0.85,
    colsample_bytree=0.85,
    min_child_weight=3,
    reg_alpha=0.0,
    reg_lambda=1.0,
    objective="reg:squarederror",
    random_state=42,
    n_jobs=-1,
)

wind_xgb.fit(
    X_train_wind,
    y_train_wind
)

wind_xgb_pred = wind_xgb.predict(
    X_val_wind
)

wind_xgb_pred = np.clip(
    wind_xgb_pred,
    0,
    1
)

wind_xgb_metrics = regression_metrics(
    y_val_wind,
    wind_xgb_pred
)

wind_xgb_pred_mw = (
    wind_xgb_pred
    * validation["embedded_wind_capacity_mw"]
)

wind_xgb_mae_mw = mean_absolute_error(
    wind_ridge_actual_mw,
    wind_xgb_pred_mw
)

wind_xgb_skill = (
    1
    - wind_xgb_metrics["MAE"]
    / wind_monthly_metrics["MAE"]
)


# -------------------------
# SOLAR
# -------------------------

solar_xgb = XGBRegressor(
    n_estimators=700,
    max_depth=5,
    learning_rate=0.03,
    subsample=0.85,
    colsample_bytree=0.85,
    min_child_weight=3,
    reg_alpha=0.0,
    reg_lambda=1.0,
    objective="reg:squarederror",
    random_state=42,
    n_jobs=-1,
)

solar_xgb.fit(
    X_train_solar,
    y_train_solar
)

solar_xgb_pred = solar_xgb.predict(
    X_val_solar
)

solar_xgb_pred = np.clip(
    solar_xgb_pred,
    0,
    1
)

solar_xgb_metrics = regression_metrics(
    y_val_solar,
    solar_xgb_pred
)

solar_xgb_pred_mw = (
    solar_xgb_pred
    * validation["embedded_solar_capacity_mw"]
)

solar_xgb_mae_mw = mean_absolute_error(
    solar_ridge_actual_mw,
    solar_xgb_pred_mw
)

solar_xgb_skill = (
    1
    - solar_xgb_metrics["MAE"]
    / solar_monthly_metrics["MAE"]
)


# -------------------------
# FEATURE IMPORTANCE
# -------------------------

wind_xgb_importance = (
    pd.Series(
        wind_xgb.feature_importances_,
        index=WIND_FEATURES
    )
    .sort_values(ascending=False)
)

solar_xgb_importance = (
    pd.Series(
        solar_xgb.feature_importances_,
        index=SOLAR_FEATURES
    )
    .sort_values(ascending=False)
)


# -------------------------
# RESULTS
# -------------------------

print("\n====================")
print("XGBOOST RESULTS")
print("====================")

print("\nWIND:")
print(wind_xgb_metrics)
print(
    "MAE MW:",
    wind_xgb_mae_mw
)
print(
    "Skill vs monthly climatology:",
    f"{wind_xgb_skill:.2%}"
)

print("\nTop wind features:")
print(
    wind_xgb_importance.head(5)
)

print("\nSOLAR:")
print(solar_xgb_metrics)
print(
    "MAE MW:",
    solar_xgb_mae_mw
)
print(
    "Skill vs monthly climatology:",
    f"{solar_xgb_skill:.2%}"
)

print("\nTop solar features:")
print(
    solar_xgb_importance.head(5)
)


#%% Final Stage 5 validation comparison

# ----------------------------------
# RIDGE skill vs climatology
# ----------------------------------

wind_ridge_skill = (
    1
    - wind_ridge_metrics["MAE"]
    / wind_monthly_metrics["MAE"]
)

solar_ridge_skill = (
    1
    - solar_ridge_metrics["MAE"]
    / solar_monthly_metrics["MAE"]
)


# ----------------------------------
# BUILD WIND COMPARISON TABLE
# ----------------------------------

wind_results = pd.DataFrame([
    {
        "Model": "Monthly climatology",
        "MAE_CF": wind_monthly_metrics["MAE"],
        "RMSE_CF": wind_monthly_metrics["RMSE"],
        "R2": wind_monthly_metrics["R2"],
        "MAE_MW": 929.1287968084652,
        "Skill_vs_baseline_pct": 0.0,
    },
    {
        "Model": "Ridge",
        "MAE_CF": wind_ridge_metrics["MAE"],
        "RMSE_CF": wind_ridge_metrics["RMSE"],
        "R2": wind_ridge_metrics["R2"],
        "MAE_MW": 287.50916140515096,
        "Skill_vs_baseline_pct": wind_ridge_skill * 100,
    },
    {
        "Model": "ExtraTrees",
        "MAE_CF": wind_extra_metrics["MAE"],
        "RMSE_CF": wind_extra_metrics["RMSE"],
        "R2": wind_extra_metrics["R2"],
        "MAE_MW": wind_extra_mae_mw,
        "Skill_vs_baseline_pct": wind_extra_skill * 100,
    },
    {
        "Model": "XGBoost",
        "MAE_CF": wind_xgb_metrics["MAE"],
        "RMSE_CF": wind_xgb_metrics["RMSE"],
        "R2": wind_xgb_metrics["R2"],
        "MAE_MW": wind_xgb_mae_mw,
        "Skill_vs_baseline_pct": wind_xgb_skill * 100,
    },
])

wind_results = (
    wind_results
    .sort_values("MAE_CF")
    .reset_index(drop=True)
)


# ----------------------------------
# BUILD SOLAR COMPARISON TABLE
# ----------------------------------

solar_results = pd.DataFrame([
    {
        "Model": "Monthly climatology",
        "MAE_CF": solar_monthly_metrics["MAE"],
        "RMSE_CF": solar_monthly_metrics["RMSE"],
        "R2": solar_monthly_metrics["R2"],
        "MAE_MW": 1018.6556377392011,
        "Skill_vs_baseline_pct": 0.0,
    },
    {
        "Model": "Ridge",
        "MAE_CF": solar_ridge_metrics["MAE"],
        "RMSE_CF": solar_ridge_metrics["RMSE"],
        "R2": solar_ridge_metrics["R2"],
        "MAE_MW": 530.1950054775707,
        "Skill_vs_baseline_pct": solar_ridge_skill * 100,
    },
    {
        "Model": "ExtraTrees",
        "MAE_CF": solar_extra_metrics["MAE"],
        "RMSE_CF": solar_extra_metrics["RMSE"],
        "R2": solar_extra_metrics["R2"],
        "MAE_MW": solar_extra_mae_mw,
        "Skill_vs_baseline_pct": solar_extra_skill * 100,
    },
    {
        "Model": "XGBoost",
        "MAE_CF": solar_xgb_metrics["MAE"],
        "RMSE_CF": solar_xgb_metrics["RMSE"],
        "R2": solar_xgb_metrics["R2"],
        "MAE_MW": solar_xgb_mae_mw,
        "Skill_vs_baseline_pct": solar_xgb_skill * 100,
    },
])

solar_results = (
    solar_results
    .sort_values("MAE_CF")
    .reset_index(drop=True)
)


# ----------------------------------
# IDENTIFY VALIDATION WINNERS
# ----------------------------------

best_wind_model = wind_results.iloc[0]["Model"]
best_solar_model = solar_results.iloc[0]["Model"]


# ----------------------------------
# PRINT RESULTS
# ----------------------------------

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 150)

print("\n====================================")
print("WIND VALIDATION MODEL COMPARISON")
print("====================================")
print(wind_results.round(4).to_string(index=False))

print("\n====================================")
print("SOLAR VALIDATION MODEL COMPARISON")
print("====================================")
print(solar_results.round(4).to_string(index=False))

print("\n====================================")
print("VALIDATION WINNERS")
print("====================================")
print("Best wind model :", best_wind_model)
print("Best solar model:", best_solar_model)

print("\nIMPORTANT:")
print("The TEST dataset has not been used for model selection.")



#%% STAGE 6 — Final untouched test evaluation

# ============================================================
# 1. Combine TRAIN + VALIDATION
# ============================================================

development = pd.concat(
    [train, validation],
    ignore_index=True
).sort_values("valid_time_utc").reset_index(drop=True)

print("Development rows:", len(development))
print("Test rows:", len(test))

print(
    "Development period:",
    development["settlement_date"].min(),
    "to",
    development["settlement_date"].max()
)

print(
    "Test period:",
    test["settlement_date"].min(),
    "to",
    test["settlement_date"].max()
)


# ============================================================
# 2. FINAL WIND MODEL — XGBOOST
# ============================================================

X_dev_wind = development[WIND_FEATURES]
y_dev_wind = development["wind_cf"]

X_test_wind = test[WIND_FEATURES]
y_test_wind = test["wind_cf"]

final_wind_model = XGBRegressor(
    n_estimators=700,
    max_depth=5,
    learning_rate=0.03,
    subsample=0.85,
    colsample_bytree=0.85,
    min_child_weight=3,
    reg_alpha=0.0,
    reg_lambda=1.0,
    objective="reg:squarederror",
    random_state=42,
    n_jobs=-1,
)

final_wind_model.fit(
    X_dev_wind,
    y_dev_wind
)

wind_test_pred = final_wind_model.predict(
    X_test_wind
)

wind_test_pred = np.clip(
    wind_test_pred,
    0,
    1
)

wind_test_metrics = regression_metrics(
    y_test_wind,
    wind_test_pred
)


# ============================================================
# 3. FINAL SOLAR MODEL — EXTRATREES
# ============================================================

X_dev_solar = development[SOLAR_FEATURES]
y_dev_solar = development["solar_cf"]

X_test_solar = test[SOLAR_FEATURES]
y_test_solar = test["solar_cf"]

final_solar_model = ExtraTreesRegressor(
    n_estimators=400,
    max_depth=None,
    min_samples_leaf=2,
    max_features=0.8,
    random_state=42,
    n_jobs=-1,
)

final_solar_model.fit(
    X_dev_solar,
    y_dev_solar
)

solar_test_pred = final_solar_model.predict(
    X_test_solar
)

solar_test_pred = np.clip(
    solar_test_pred,
    0,
    1
)

solar_test_metrics = regression_metrics(
    y_test_solar,
    solar_test_pred
)


# ============================================================
# 4. TEST MW ERRORS
# ============================================================

wind_test_actual_mw = (
    test["wind_cf"]
    * test["embedded_wind_capacity_mw"]
)

wind_test_pred_mw = (
    wind_test_pred
    * test["embedded_wind_capacity_mw"]
)

solar_test_actual_mw = (
    test["solar_cf"]
    * test["embedded_solar_capacity_mw"]
)

solar_test_pred_mw = (
    solar_test_pred
    * test["embedded_solar_capacity_mw"]
)

wind_test_mae_mw = mean_absolute_error(
    wind_test_actual_mw,
    wind_test_pred_mw
)

solar_test_mae_mw = mean_absolute_error(
    solar_test_actual_mw,
    solar_test_pred_mw
)


# ============================================================
# 5. FINAL MONTHLY CLIMATOLOGY BASELINE
# Built using TRAIN + VALIDATION only
# ============================================================

def add_climatology_keys(data):
    data = data.copy()

    local_time = (
        data["valid_time_utc"]
        .dt.tz_convert("Europe/London")
    )

    data["baseline_month"] = local_time.dt.month
    data["baseline_hour"] = local_time.dt.hour
    data["baseline_minute"] = local_time.dt.minute

    return data


development_b = add_climatology_keys(
    development
)

test_b = add_climatology_keys(
    test
)

CLIM_KEYS = [
    "baseline_month",
    "baseline_hour",
    "baseline_minute",
]

wind_final_clim = (
    development_b
    .groupby(CLIM_KEYS)["wind_cf"]
    .mean()
    .rename("wind_baseline")
    .reset_index()
)

solar_final_clim = (
    development_b
    .groupby(CLIM_KEYS)["solar_cf"]
    .mean()
    .rename("solar_baseline")
    .reset_index()
)

test_b = test_b.merge(
    wind_final_clim,
    on=CLIM_KEYS,
    how="left"
)

test_b = test_b.merge(
    solar_final_clim,
    on=CLIM_KEYS,
    how="left"
)

assert test_b["wind_baseline"].isna().sum() == 0
assert test_b["solar_baseline"].isna().sum() == 0


# ============================================================
# 6. BASELINE TEST METRICS
# ============================================================

wind_test_baseline_metrics = regression_metrics(
    test_b["wind_cf"],
    test_b["wind_baseline"]
)

solar_test_baseline_metrics = regression_metrics(
    test_b["solar_cf"],
    test_b["solar_baseline"]
)

wind_baseline_test_mw = (
    test_b["wind_baseline"]
    * test_b["embedded_wind_capacity_mw"]
)

solar_baseline_test_mw = (
    test_b["solar_baseline"]
    * test_b["embedded_solar_capacity_mw"]
)

wind_baseline_test_mae_mw = mean_absolute_error(
    wind_test_actual_mw,
    wind_baseline_test_mw
)

solar_baseline_test_mae_mw = mean_absolute_error(
    solar_test_actual_mw,
    solar_baseline_test_mw
)


# ============================================================
# 7. FINAL TEST SKILL
# ============================================================

wind_test_skill = (
    1
    - wind_test_metrics["MAE"]
    / wind_test_baseline_metrics["MAE"]
)

solar_test_skill = (
    1
    - solar_test_metrics["MAE"]
    / solar_test_baseline_metrics["MAE"]
)


# ============================================================
# 8. FINAL TEST RESULTS TABLE
# ============================================================

test_results = pd.DataFrame([
    {
        "Technology": "Wind",
        "Model": "XGBoost",
        "MAE_CF": wind_test_metrics["MAE"],
        "RMSE_CF": wind_test_metrics["RMSE"],
        "R2": wind_test_metrics["R2"],
        "MAE_MW": wind_test_mae_mw,
        "Baseline_MAE_CF": wind_test_baseline_metrics["MAE"],
        "Baseline_MAE_MW": wind_baseline_test_mae_mw,
        "Skill_vs_baseline_pct": wind_test_skill * 100,
    },
    {
        "Technology": "Solar",
        "Model": "ExtraTrees",
        "MAE_CF": solar_test_metrics["MAE"],
        "RMSE_CF": solar_test_metrics["RMSE"],
        "R2": solar_test_metrics["R2"],
        "MAE_MW": solar_test_mae_mw,
        "Baseline_MAE_CF": solar_test_baseline_metrics["MAE"],
        "Baseline_MAE_MW": solar_baseline_test_mae_mw,
        "Skill_vs_baseline_pct": solar_test_skill * 100,
    },
])


print("\n==============================================")
print("FINAL UNTOUCHED TEST RESULTS")
print("==============================================")

print(
    test_results
    .round(4)
    .to_string(index=False)
)


# ============================================================
# 9. SAVE HALF-HOURLY TEST PREDICTIONS
# ============================================================

test_predictions = test[
    [
        "settlement_date",
        "settlement_period",
        "valid_time_utc",
        "embedded_wind_generation_mw",
        "embedded_wind_capacity_mw",
        "embedded_solar_generation_mw",
        "embedded_solar_capacity_mw",
        "wind_cf",
        "solar_cf",
    ]
].copy()

test_predictions["wind_pred_cf"] = wind_test_pred
test_predictions["wind_pred_mw"] = wind_test_pred_mw

test_predictions["solar_pred_cf"] = solar_test_pred
test_predictions["solar_pred_mw"] = solar_test_pred_mw

test_predictions["wind_error_mw"] = (
    test_predictions["wind_pred_mw"]
    - test_predictions["embedded_wind_generation_mw"]
)

test_predictions["solar_error_mw"] = (
    test_predictions["solar_pred_mw"]
    - test_predictions["embedded_solar_generation_mw"]
)

RESULTS_DIR = (
    ROOT / "outputs" / "metrics"
)

RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True
)

test_results.to_csv(
    RESULTS_DIR / "final_test_metrics.csv",
    index=False
)

test_predictions.to_csv(
    RESULTS_DIR / "final_test_predictions.csv",
    index=False
)

print("\nSaved final test results and predictions.")



#%% STAGE 6B — Final test error analysis and portfolio figures

import matplotlib.pyplot as plt


# ============================================================
# 1. DAILY PERFORMANCE
# ============================================================

daily_results = (
    test_predictions
    .groupby("settlement_date")
    .agg(
        wind_mae_mw=(
            "wind_error_mw",
            lambda x: np.mean(np.abs(x))
        ),
        solar_mae_mw=(
            "solar_error_mw",
            lambda x: np.mean(np.abs(x))
        ),
        wind_bias_mw=(
            "wind_error_mw",
            "mean"
        ),
        solar_bias_mw=(
            "solar_error_mw",
            "mean"
        ),
    )
    .reset_index()
)

print("\n==============================")
print("DAILY ERROR SUMMARY")
print("==============================")

print(daily_results.describe())


# ============================================================
# 2. WORST FORECAST DAYS
# ============================================================

worst_wind_days = (
    daily_results
    .sort_values(
        "wind_mae_mw",
        ascending=False
    )
    .head(10)
)

worst_solar_days = (
    daily_results
    .sort_values(
        "solar_mae_mw",
        ascending=False
    )
    .head(10)
)

print("\nWorst 10 wind forecast days:")
print(
    worst_wind_days[
        ["settlement_date", "wind_mae_mw"]
    ].to_string(index=False)
)

print("\nWorst 10 solar forecast days:")
print(
    worst_solar_days[
        ["settlement_date", "solar_mae_mw"]
    ].to_string(index=False)
)


# ============================================================
# 3. OVERALL BIAS
# ============================================================

wind_bias = np.mean(
    test_predictions["wind_error_mw"]
)

solar_bias = np.mean(
    test_predictions["solar_error_mw"]
)

print("\nOverall wind bias MW:", wind_bias)
print("Overall solar bias MW:", solar_bias)


# ============================================================
# 4. ACTUAL VS FORECAST — FULL TEST PERIOD
# ============================================================

FIGURE_DIR = (
    ROOT / "outputs" / "figures"
)

FIGURE_DIR.mkdir(
    parents=True,
    exist_ok=True
)


plt.figure(figsize=(12, 5))

plt.plot(
    test_predictions["valid_time_utc"],
    test_predictions["embedded_wind_generation_mw"],
    label="Actual",
    linewidth=1
)

plt.plot(
    test_predictions["valid_time_utc"],
    test_predictions["wind_pred_mw"],
    label="Forecast",
    linewidth=1
)

plt.xlabel("Time")
plt.ylabel("Wind generation (MW)")
plt.title(
    "GB Embedded Wind Generation: "
    "Day-Ahead Forecast vs Actual"
)
plt.legend()
plt.tight_layout()

plt.savefig(
    FIGURE_DIR / "wind_test_forecast_vs_actual.png",
    dpi=200
)

plt.show()


# ============================================================
# 5. SOLAR ACTUAL VS FORECAST — FULL TEST PERIOD
# ============================================================

plt.figure(figsize=(12, 5))

plt.plot(
    test_predictions["valid_time_utc"],
    test_predictions["embedded_solar_generation_mw"],
    label="Actual",
    linewidth=1
)

plt.plot(
    test_predictions["valid_time_utc"],
    test_predictions["solar_pred_mw"],
    label="Forecast",
    linewidth=1
)

plt.xlabel("Time")
plt.ylabel("Solar generation (MW)")
plt.title(
    "GB Embedded Solar Generation: "
    "Day-Ahead Forecast vs Actual"
)
plt.legend()
plt.tight_layout()

plt.savefig(
    FIGURE_DIR / "solar_test_forecast_vs_actual.png",
    dpi=200
)

plt.show()


# ============================================================
# 6. EXAMPLE 7-DAY WINDOW
# ============================================================

example_start = pd.Timestamp(
    "2025-07-01",
    tz="UTC"
)

example_end = pd.Timestamp(
    "2025-07-08",
    tz="UTC"
)

example = test_predictions[
    (
        test_predictions["valid_time_utc"]
        >= example_start
    )
    &
    (
        test_predictions["valid_time_utc"]
        < example_end
    )
].copy()


plt.figure(figsize=(12, 5))

plt.plot(
    example["valid_time_utc"],
    example["embedded_wind_generation_mw"],
    label="Actual",
    linewidth=1.5
)

plt.plot(
    example["valid_time_utc"],
    example["wind_pred_mw"],
    label="Forecast",
    linewidth=1.5
)

plt.xlabel("Time")
plt.ylabel("Wind generation (MW)")
plt.title(
    "Example Week: Wind Forecast vs Actual"
)
plt.legend()
plt.tight_layout()

plt.savefig(
    FIGURE_DIR / "wind_example_week.png",
    dpi=200
)

plt.show()


plt.figure(figsize=(12, 5))

plt.plot(
    example["valid_time_utc"],
    example["embedded_solar_generation_mw"],
    label="Actual",
    linewidth=1.5
)

plt.plot(
    example["valid_time_utc"],
    example["solar_pred_mw"],
    label="Forecast",
    linewidth=1.5
)

plt.xlabel("Time")
plt.ylabel("Solar generation (MW)")
plt.title(
    "Example Week: Solar Forecast vs Actual"
)
plt.legend()
plt.tight_layout()

plt.savefig(
    FIGURE_DIR / "solar_example_week.png",
    dpi=200
)

plt.show()


# ============================================================
# 7. DAILY MAE THROUGH TEST PERIOD
# ============================================================

plt.figure(figsize=(12, 5))

plt.plot(
    daily_results["settlement_date"],
    daily_results["wind_mae_mw"],
    label="Wind"
)

plt.plot(
    daily_results["settlement_date"],
    daily_results["solar_mae_mw"],
    label="Solar"
)

plt.xlabel("Date")
plt.ylabel("Daily MAE (MW)")
plt.title(
    "Daily Day-Ahead Forecast Error"
)
plt.legend()
plt.tight_layout()

plt.savefig(
    FIGURE_DIR / "daily_test_mae.png",
    dpi=200
)

plt.show()


# ============================================================
# 8. MODEL COMPARISON BAR CHART
# ============================================================

comparison = pd.DataFrame({
    "Technology": [
        "Wind",
        "Solar"
    ],
    "Monthly climatology": [
        wind_baseline_test_mae_mw,
        solar_baseline_test_mae_mw
    ],
    "ML forecast": [
        wind_test_mae_mw,
        solar_test_mae_mw
    ]
})

comparison_plot = (
    comparison
    .set_index("Technology")
)

comparison_plot.plot(
    kind="bar",
    figsize=(8, 5)
)

plt.ylabel("MAE (MW)")
plt.xlabel("")
plt.title(
    "Final Test Error: "
    "ML Forecast vs Climatology"
)
plt.xticks(rotation=0)
plt.tight_layout()

plt.savefig(
    FIGURE_DIR / "model_vs_baseline_mae.png",
    dpi=200
)

plt.show()


# ============================================================
# 9. SAVE DAILY RESULTS
# ============================================================

daily_results.to_csv(
    RESULTS_DIR / "daily_test_metrics.csv",
    index=False
)

print("\nSaved:")
print(
    RESULTS_DIR / "daily_test_metrics.csv"
)

print("\nFigures saved to:")
print(FIGURE_DIR)
