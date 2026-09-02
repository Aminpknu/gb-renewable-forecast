# Production model packaging

## V2 release candidate

V2 promotes compact spatial XGBoost models for both wind and solar after chronological development tuning and locked Apr–Jun 2026 confirmation.

| Model | Serialized size | Locked MAE | Locked R² |
|---|---:|---:|---:|
| Wind spatial XGBoost | 0.50 MB | 239.1 MW | 0.912 |
| Solar spatial XGBoost | 1.35 MB | 385.5 MW | 0.974 |

Both estimators were refitted on all 815 usable target days from 1 Apr 2024 to 30 Jun 2026, serialized with joblib, reloaded, and checked for prediction equivalence on a smoke sample. Their SHA-256 hashes are stored in `models/model_metadata.json`.

The spatial ExtraTrees solar challenger achieved slightly better development accuracy, but its serialized size was about 521 MB. It was declared benchmark-only before locked-test access and was not eligible for production selection.

## V1 packaging history

V1 used a compressed ExtraTrees solar artefact of 99,540,687 bytes (94.93 MiB), reduced from an original 337,998,881-byte estimator using lossless lzma level-3 joblib compression. That V1 artefact is removed from the V2 branch because the promoted compact solar XGBoost model supersedes it.

The Dash web process still does not load estimators during ordinary page navigation; model loading remains isolated in `python -m src.forecast_tomorrow`.
