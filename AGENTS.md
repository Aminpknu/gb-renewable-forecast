# Repository instructions

These instructions apply to all future Codex work in this repository.

## Scientific rules

- Never use future information when constructing forecasting features.
- Never use random train/test splitting for model evaluation.
- Evaluation must be chronological.
- Forecast issue time and forecast valid time must be treated as different concepts.
- Historical weather inputs used for ML must represent information that could have been available at forecast issue time.
- Never silently use realised future weather as a substitute for an archived forecast.
- Establish a simple baseline before evaluating machine-learning models.
- Wind and solar must be modelled and evaluated separately.
- Document modelling assumptions.
- Investigate suspicious data rather than silently fixing or deleting it.
- Capacity-factor observations outside expected physical ranges must first be reported and investigated before clipping.

## Engineering rules

- Prefer reusable Python modules and scripts over notebook-only workflows.
- Raw downloaded data must never be manually modified.
- Add tests for important transformations.
- Use clear function names, docstrings and type hints where useful.
- Do not silently drop missing or invalid data.
- Keep timestamps and timezone handling explicit.
- Never store passwords, credentials, API keys or secrets in the repository.
- Run pytest after substantive code changes.
- Keep dependencies minimal.
- Do not proceed to later project stages unless explicitly requested.
