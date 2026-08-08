"""Build the Stage 2 NESO embedded wind and solar target dataset."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.data.neso import NESO_DATASET_PAGE, NESO_RESOURCES, detect_latest_complete_month, load_neso_sources
from src.data.settlement import add_settlement_timestamps
from src.data.validation import build_quality_summary
from src.features.targets import add_capacity_factors

RAW_DIRECTORY = PROJECT_ROOT / "data" / "raw" / "neso"
INTERIM_DIRECTORY = PROJECT_ROOT / "data" / "interim"
METRICS_DIRECTORY = PROJECT_ROOT / "outputs" / "metrics"
FIGURES_DIRECTORY = PROJECT_ROOT / "outputs" / "figures"
START_DATE = pd.Timestamp("2024-04-01")

OUTPUT_COLUMNS = [
    "settlement_date",
    "settlement_period",
    "valid_time_local",
    "valid_time_utc",
    "embedded_wind_generation_mw",
    "embedded_wind_capacity_mw",
    "embedded_solar_generation_mw",
    "embedded_solar_capacity_mw",
    "wind_cf",
    "solar_cf",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_source_manifest() -> Path:
    """Record official provenance and byte-level identity of local raw files."""
    sources = []
    for year, resource in sorted(NESO_RESOURCES.items()):
        path = RAW_DIRECTORY / resource["filename"]
        if not path.is_file():
            raise FileNotFoundError(f"Missing raw NESO source: {path}")
        retrieved_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        sources.append(
            {
                "year": year,
                "official_source_url": resource["url"],
                "retrieval_timestamp_utc": retrieved_at.isoformat(),
                "local_filename": path.name,
                "file_size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    manifest = {
        "dataset": "NESO Historic Demand Data",
        "official_dataset_page": NESO_DATASET_PAGE,
        "sources": sources,
    }
    output = RAW_DIRECTORY / "source_manifest.json"
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return output


def _write_readable_summary(summary: dict[str, Any], latest_month: str) -> Path:
    checks = summary["quality_checks"]
    lines = [
        "# NESO target-data quality summary",
        "",
        f"- Date range: {summary['date_range']['first']} to {summary['date_range']['last']}",
        f"- Latest complete month: {latest_month}",
        f"- Total rows: {summary['total_rows']:,}",
        f"- Abnormal settlement days: {checks['abnormal_settlement_day_count']}",
        f"- Duplicate records: {checks['duplicate_record_count']}",
        f"- Missing settlement periods: {checks['missing_period_count']}",
        f"- Impossible timestamps: {checks['impossible_timestamp_count']}",
        f"- Non-monotonic UTC timestamps: {checks['non_monotonic_utc_timestamp_count']}",
        f"- Unexpected UTC discontinuities: {checks['unexpected_utc_discontinuity_count']}",
        f"- Duplicate UTC timestamps: {checks['duplicate_utc_timestamp_count']}",
        "",
        "## Capacity-factor range checks",
        "",
        f"- Wind CF < 0: {checks['wind_cf_below_zero_count']}",
        f"- Wind CF > 1: {checks['wind_cf_above_one_count']}",
        f"- Solar CF < 0: {checks['solar_cf_below_zero_count']}",
        f"- Solar CF > 1: {checks['solar_cf_above_one_count']}",
        "",
        "Observed capacity factors were not clipped. Any out-of-range values remain traceable to NESO source observations.",
        "",
        "## Period-count distribution",
        "",
    ]
    lines.extend(
        f"- {periods} periods: {days} days"
        for periods, days in summary["period_count_distribution"].items()
    )
    lines.extend(["", "## Missing values", ""])
    lines.extend(
        f"- `{column}`: {count}"
        for column, count in checks["missing_values"].items()
    )
    lines.extend(["", "## Capacity-factor extrema", ""])
    for name, record in summary["capacity_factor_extremes"].items():
        lines.append(f"- `{name}`: {record}")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Embedded generation is NESO's estimated output from generation connected to distribution networks and is paired here with NESO's embedded capacity series. A capacity factor above one can therefore reflect estimation, timing, or capacity-definition mismatch as well as source-data quality; it is reported rather than altered.",
        ]
    )
    output = METRICS_DIRECTORY / "neso_target_quality_summary.md"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def _save_figures(frame: pd.DataFrame) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    daily = frame.set_index("valid_time_utc").resample("D").mean(numeric_only=True)

    for technology, colour in (("wind", "#1f77b4"), ("solar", "#e69f00")):
        figure, axis = plt.subplots(figsize=(11, 4.5))
        axis.plot(
            daily.index,
            daily[f"embedded_{technology}_generation_mw"],
            color=colour,
            linewidth=1.0,
        )
        axis.set_title(f"GB Estimated Embedded {technology.title()} Generation")
        axis.set_xlabel("Valid date (UTC)")
        axis.set_ylabel("Daily mean generation (MW)")
        figure.tight_layout()
        figure.savefig(
            FIGURES_DIRECTORY / f"embedded_{technology}_generation_over_time.png",
            dpi=150,
        )
        plt.close(figure)

    monthly = (
        frame.assign(month=frame["settlement_date"].dt.to_period("M").dt.to_timestamp())
        .groupby("month")[["wind_cf", "solar_cf"]]
        .mean()
    )
    figure, axis = plt.subplots(figsize=(11, 4.5))
    axis.plot(monthly.index, monthly["wind_cf"], marker="o", label="Wind", color="#1f77b4")
    axis.plot(monthly.index, monthly["solar_cf"], marker="o", label="Solar", color="#e69f00")
    axis.set_title("Monthly Mean Embedded Wind and Solar Capacity Factors")
    axis.set_xlabel("Settlement month")
    axis.set_ylabel("Mean capacity factor")
    axis.legend()
    figure.tight_layout()
    figure.savefig(FIGURES_DIRECTORY / "monthly_mean_capacity_factors.png", dpi=150)
    plt.close(figure)


def build_stage_2_targets() -> tuple[pd.DataFrame, dict[str, Any], pd.Period]:
    """Build, validate, report, and save the historical target dataset."""
    for directory in (INTERIM_DIRECTORY, METRICS_DIRECTORY, FIGURES_DIRECTORY):
        directory.mkdir(parents=True, exist_ok=True)
    write_source_manifest()

    paths = [RAW_DIRECTORY / NESO_RESOURCES[year]["filename"] for year in sorted(NESO_RESOURCES)]
    targets = load_neso_sources(paths)
    latest_complete_month = detect_latest_complete_month(targets)
    end_date = latest_complete_month.end_time.normalize()
    targets = targets.loc[targets["settlement_date"].between(START_DATE, end_date)].copy()
    targets = add_settlement_timestamps(targets)
    targets = add_capacity_factors(targets)
    targets = targets.sort_values(["settlement_date", "settlement_period"], kind="stable").reset_index(drop=True)

    summary = build_quality_summary(targets)
    summary["latest_complete_month"] = str(latest_complete_month)
    output_path = INTERIM_DIRECTORY / "neso_embedded_wind_solar_targets.csv"
    output_frame = targets.loc[:, OUTPUT_COLUMNS].copy()
    output_frame["settlement_date"] = output_frame["settlement_date"].dt.strftime(
        "%Y-%m-%d"
    )
    output_frame.to_csv(
        output_path, index=False, date_format="%Y-%m-%dT%H:%M:%S%z"
    )

    metrics_path = METRICS_DIRECTORY / "neso_target_quality_summary.json"
    metrics_path.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    _write_readable_summary(summary, str(latest_complete_month))
    _save_figures(targets)
    return targets, summary, latest_complete_month


if __name__ == "__main__":
    data, quality, complete_month = build_stage_2_targets()
    print(f"Latest complete month: {complete_month}")
    print(f"Rows: {len(data)}")
    print("First five cleaned rows:")
    print(data.loc[:, OUTPUT_COLUMNS].head().to_string(index=False))
    print("Last five cleaned rows:")
    print(data.loc[:, OUTPUT_COLUMNS].tail().to_string(index=False))
