"""Restart-safe, rate-limit-aware recovery for the Stage 3 weather cache."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from src.data.build_weather import (
    CACHE_DIRECTORY,
    PROJECT_ROOT,
    RAW_WEATHER_ROOT,
    _inventory_entry,
    _sha256,
    _stable_cache_metadata,
    _write_json,
    derive_required_run_dates,
    retrieve_and_validate_run,
)
from src.data.open_meteo import (
    OfficialArchiveUnavailableError,
    RateLimitError,
    WeatherResponseError,
    cache_path,
    create_retry_session,
    parse_multiple_location_response,
    select_following_local_day,
)
from src.data.weather_config import (
    WEATHER_MODEL,
    WEATHER_MODEL_API_IDENTIFIER,
    WeatherLocation,
    load_weather_locations,
)
from src.data.weather_validation import validate_single_run

INVENTORY_PATH = RAW_WEATHER_ROOT / "run_inventory.json"
RECOVERY_STATE_PATH = RAW_WEATHER_ROOT / "recovery_state.json"
REPAIR_LOG_PATH = RAW_WEATHER_ROOT / "cache_repairs.json"
QUARANTINE_DIRECTORY = RAW_WEATHER_ROOT / "quarantine"
EXCLUSIONS_PATH = RAW_WEATHER_ROOT / "excluded_target_dates.json"
PRIORITY_LAST_RUN = pd.Timestamp("2025-08-30T00:00:00Z")
MINIMUM_FREE_BYTES = 4_000_000_000
KNOWN_CORRUPT_RUN_DATES = {
    "2024-06-27",
    "2024-07-02",
    "2024-07-24",
    "2024-07-27",
    "2024-09-24",
}


def free_c_drive_bytes() -> int:
    """Return free bytes on the volume containing the project."""
    return shutil.disk_usage(PROJECT_ROOT.anchor).free


def _validation_summary(validation: dict[str, Any]) -> dict[str, Any]:
    """Reduce a full single-run report to stable inventory fields."""
    return {
        "passed": validation["passed"],
        "expected_rows_per_location": validation["expected_rows_per_location"],
        "duplicate_count": validation["duplicate_count"],
        "missing_value_count": sum(validation["missing_values"].values()),
        "physical_suspicion_count": sum(
            validation["physical_suspicion_counts"].values()
        ),
        "leakage_violation_count": sum(
            validation["leakage_violation_counts"].values()
        ),
        "incomplete_location_count": len(validation["incomplete_locations"]),
    }


def inspect_cached_run(
    run_init: pd.Timestamp,
    locations: tuple[WeatherLocation, ...],
) -> dict[str, Any]:
    """Validate one cache file without modifying it or making a network call."""
    path = cache_path(CACHE_DIRECTORY, run_init)
    if not path.is_file():
        return _inventory_entry(run_init, "missing", error="Raw cache absent.")
    try:
        payload = json.loads(path.read_bytes())
        parsed = parse_multiple_location_response(payload, locations, run_init)
        selected = select_following_local_day(parsed, run_init)
        validation = validate_single_run(selected, run_init, locations)
        if not validation["passed"]:
            raise WeatherResponseError(
                "Cached forecast failed validation: "
                + json.dumps(_validation_summary(validation), sort_keys=True)
            )
        file_size, file_hash = _stable_cache_metadata(path)
        return _inventory_entry(
            run_init,
            "success",
            cache_file=str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            cache_reused=True,
            file_size_bytes=file_size,
            sha256=file_hash,
            validation=_validation_summary(validation),
        )
    except (json.JSONDecodeError, UnicodeDecodeError, WeatherResponseError, ValueError, OSError) as error:
        return _inventory_entry(
            run_init,
            "failed",
            cache_file=str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            file_size_bytes=path.stat().st_size if path.exists() else None,
            sha256=_sha256(path) if path.exists() else None,
            error_type=type(error).__name__,
            error=str(error),
        )


def scan_cache_authority(
    run_dates: pd.DatetimeIndex,
    locations: tuple[WeatherLocation, ...],
) -> list[dict[str, Any]]:
    """Build a complete inventory directly from immutable raw run files."""
    inventory = [inspect_cached_run(run_init, locations) for run_init in run_dates]
    exclusions = {
        item["required_weather_run_init_utc"]: item for item in load_exclusions()
    }
    for entry in inventory:
        exclusion = exclusions.get(entry["run_init_utc"])
        if entry["status"] in {"missing", "failed"} and exclusion:
            entry.update(
                status="official_archive_unavailable",
                error_type="OfficialArchiveUnavailableError",
                error=exclusion["api_error"],
                exclusion=exclusion,
            )
    if REPAIR_LOG_PATH.is_file():
        repairs = {
            item["run_date"]: item
            for item in _load_repair_log()
            if item.get("replacement_status") == "validated"
        }
        for entry in inventory:
            run_date = pd.Timestamp(entry["run_init_utc"]).date().isoformat()
            if entry["status"] == "success" and run_date in repairs:
                repair = repairs[run_date]
                entry["cache_repair"] = {
                    "quarantined_sha256": repair["sha256"],
                    "quarantine_file": repair["quarantine_file"],
                    "replacement_validated_at_utc": repair[
                        "replacement_validated_at_utc"
                    ],
                }
    inventory.sort(key=lambda item: item["run_init_utc"])
    return inventory


def _load_repair_log() -> list[dict[str, Any]]:
    if not REPAIR_LOG_PATH.is_file():
        return []
    return json.loads(REPAIR_LOG_PATH.read_text(encoding="utf-8"))


def load_exclusions() -> list[dict[str, Any]]:
    """Load explicitly accepted official-archive exclusions."""
    if not EXCLUSIONS_PATH.is_file():
        return []
    return json.loads(EXCLUSIONS_PATH.read_text(encoding="utf-8"))


def record_official_archive_exclusion(
    run_init: pd.Timestamp,
    error: OfficialArchiveUnavailableError,
) -> dict[str, Any]:
    """Atomically record a model-run exclusion without creating synthetic data."""
    exclusions = load_exclusions()
    run_key = run_init.isoformat()
    existing = next(
        (
            item
            for item in exclusions
            if item["required_weather_run_init_utc"] == run_key
        ),
        None,
    )
    if existing:
        return existing
    target_date = (run_init + pd.Timedelta(days=1)).date().isoformat()
    exclusion = {
        "target_date": target_date,
        "required_weather_run_init_utc": run_key,
        "weather_model": WEATHER_MODEL,
        "weather_model_api_identifier": WEATHER_MODEL_API_IDENTIFIER,
        "api_error": "modelRunUnavailable",
        "reason": (
            "The required official ECMWF IFS HRES 00 UTC archived run was "
            "unavailable from the Open-Meteo Single Runs API."
        ),
        "api_response": str(error),
        "exclusion_decision": (
            "Exclude the target date; do not substitute another model, run cycle, "
            "realised weather, interpolation, or synthetic data."
        ),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    exclusions.append(exclusion)
    exclusions.sort(key=lambda item: item["target_date"])
    _write_json(EXCLUSIONS_PATH, exclusions)
    return exclusion


def quarantine_known_corrupt_entries(
    inventory: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Quarantine only the five approved corrupt cache entries, preserving bytes."""
    failed = [entry for entry in inventory if entry["status"] == "failed"]
    failed_dates = {pd.Timestamp(entry["run_init_utc"]).date().isoformat() for entry in failed}
    unexpected = failed_dates - KNOWN_CORRUPT_RUN_DATES
    if unexpected:
        raise RuntimeError(
            "Unexpected invalid cache files require investigation before mutation: "
            + ", ".join(sorted(unexpected))
        )

    repair_log = _load_repair_log()
    already_quarantined = {item["run_date"] for item in repair_log}
    QUARANTINE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for entry in failed:
        run_date = pd.Timestamp(entry["run_init_utc"]).date().isoformat()
        if run_date not in KNOWN_CORRUPT_RUN_DATES or run_date in already_quarantined:
            continue
        source = PROJECT_ROOT / entry["cache_file"]
        digest = entry["sha256"]
        destination = QUARANTINE_DIRECTORY / (
            f"{source.stem}.corrupt-{digest[:12]}{source.suffix}"
        )
        if destination.exists():
            raise FileExistsError(f"Quarantine destination already exists: {destination}")
        source.replace(destination)
        repair_log.append(
            {
                "run_date": run_date,
                "quarantined_at_utc": datetime.now(timezone.utc).isoformat(),
                "original_cache_file": entry["cache_file"],
                "quarantine_file": str(destination.relative_to(PROJECT_ROOT)).replace(
                    "\\", "/"
                ),
                "file_size_bytes": entry["file_size_bytes"],
                "sha256": digest,
                "reason": entry["error"],
                "replacement_status": "pending",
            }
        )
        _write_json(REPAIR_LOG_PATH, repair_log)
        print(f"Quarantined approved corrupt cache for {run_date}.", flush=True)
    return repair_log


def _mark_repair_complete(repair_log: list[dict[str, Any]], run_init: pd.Timestamp) -> None:
    run_date = run_init.date().isoformat()
    changed = False
    for item in repair_log:
        if item["run_date"] == run_date and item["replacement_status"] != "validated":
            item["replacement_status"] = "validated"
            item["replacement_validated_at_utc"] = datetime.now(timezone.utc).isoformat()
            changed = True
    if changed:
        _write_json(REPAIR_LOG_PATH, repair_log)


def _checkpoint(
    inventory_by_run: dict[str, dict[str, Any]],
    phase: str,
    stop_reason: str | None,
    started_at_utc: str,
) -> None:
    inventory = sorted(inventory_by_run.values(), key=lambda item: item["run_init_utc"])
    _write_json(INVENTORY_PATH, inventory)
    state = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "started_at_utc": started_at_utc,
        "phase": phase,
        "stop_reason": stop_reason,
        "successful_run_count": sum(item["status"] == "success" for item in inventory),
        "failed_run_count": sum(item["status"] == "failed" for item in inventory),
        "missing_run_count": sum(item["status"] == "missing" for item in inventory),
        "official_archive_unavailable_count": sum(
            item["status"] == "official_archive_unavailable" for item in inventory
        ),
        "free_c_drive_bytes": free_c_drive_bytes(),
    }
    _write_json(RECOVERY_STATE_PATH, state)


def _pending_dates(
    run_dates: pd.DatetimeIndex,
    inventory_by_run: dict[str, dict[str, Any]],
    priority: bool,
) -> list[pd.Timestamp]:
    return [
        run_init
        for run_init in run_dates
        if (run_init <= PRIORITY_LAST_RUN) == priority
        and inventory_by_run[run_init.isoformat()]["status"]
        not in {"success", "official_archive_unavailable"}
    ]


def recover_weather_cache(
    max_runtime_minutes: float = 50.0,
    success_delay_seconds: float = 2.0,
    priority_only: bool = False,
) -> dict[str, Any]:
    """Recover priority coverage serially, then continue only after clean API service."""
    started = time.monotonic()
    started_at_utc = datetime.now(timezone.utc).isoformat()
    locations = load_weather_locations()
    run_dates = derive_required_run_dates()
    inventory = scan_cache_authority(run_dates, locations)
    _write_json(INVENTORY_PATH, inventory)
    repair_log = quarantine_known_corrupt_entries(inventory)
    if any(entry["status"] == "failed" for entry in inventory):
        inventory = scan_cache_authority(run_dates, locations)
    inventory_by_run = {entry["run_init_utc"]: entry for entry in inventory}
    _checkpoint(inventory_by_run, "priority", None, started_at_utc)

    downloaded = 0
    recent_rate_limit_retries: list[int] = []
    stop_reason: str | None = None
    phase = "priority"

    with create_retry_session() as session:
        for priority in (True, False):
            if not priority and priority_only:
                stop_reason = "Priority-only retrieval completed as requested."
                break
            phase = "priority" if priority else "full-range"
            pending = _pending_dates(run_dates, inventory_by_run, priority)
            if not priority:
                priority_incomplete = _pending_dates(run_dates, inventory_by_run, True)
                api_normal = len(recent_rate_limit_retries) >= 10 and not any(
                    recent_rate_limit_retries[-25:]
                )
                if priority_incomplete:
                    stop_reason = "Priority coverage remains incomplete."
                    break
                if not api_normal:
                    stop_reason = (
                        "Priority complete, but API normality gate was not met: at least "
                        "10 recent downloads with no HTTP 429 retries are required."
                    )
                    break
            print(f"{phase}: {len(pending)} unresolved runs.", flush=True)
            for position, run_init in enumerate(pending, start=1):
                if free_c_drive_bytes() < MINIMUM_FREE_BYTES:
                    stop_reason = "Free C: space fell below the 4.0 GB safety floor."
                    break
                if time.monotonic() - started >= max_runtime_minutes * 60:
                    stop_reason = f"Graceful runtime checkpoint at {max_runtime_minutes:.1f} minutes."
                    break
                try:
                    _, entry = retrieve_and_validate_run(run_init, locations, session)
                    cached = entry.get("cache_reused", False)
                    if cached:
                        raise RuntimeError(
                            "A pending run unexpectedly resolved to an existing cache file."
                        )
                    # fetch_run stores this only internally; zero is the normal case.
                    rate_limit_retries = int(entry.get("rate_limit_retries", 0))
                    inventory_by_run[run_init.isoformat()] = entry
                    _mark_repair_complete(repair_log, run_init)
                    downloaded += 1
                    recent_rate_limit_retries.append(rate_limit_retries)
                    recent_rate_limit_retries = recent_rate_limit_retries[-25:]
                    _checkpoint(inventory_by_run, phase, None, started_at_utc)
                    print(
                        f"Validated {run_init.date()} ({position}/{len(pending)} {phase}); "
                        f"total success={sum(item['status'] == 'success' for item in inventory_by_run.values())}.",
                        flush=True,
                    )
                    time.sleep(success_delay_seconds)
                except RateLimitError as error:
                    inventory_by_run[run_init.isoformat()] = _inventory_entry(
                        run_init,
                        "missing",
                        error_type=type(error).__name__,
                        error=str(error),
                        last_attempt_utc=datetime.now(timezone.utc).isoformat(),
                    )
                    stop_reason = f"Sustained HTTP 429 at run {run_init.date()}: {error}"
                    _checkpoint(inventory_by_run, phase, stop_reason, started_at_utc)
                    break
                except OfficialArchiveUnavailableError as error:
                    exclusion = record_official_archive_exclusion(run_init, error)
                    inventory_by_run[run_init.isoformat()] = _inventory_entry(
                        run_init,
                        "official_archive_unavailable",
                        error_type=type(error).__name__,
                        error="modelRunUnavailable",
                        exclusion=exclusion,
                    )
                    _checkpoint(inventory_by_run, phase, None, started_at_utc)
                    print(
                        f"EXCLUDED official unavailable run {run_init.date()} "
                        f"for target {exclusion['target_date']}.",
                        flush=True,
                    )
                    continue
                except (requests.RequestException, WeatherResponseError, ValueError, OSError) as error:
                    # A non-rate-limit failure is recorded and the conservative pass stops.
                    inventory_by_run[run_init.isoformat()] = inspect_cached_run(
                        run_init, locations
                    )
                    inventory_by_run[run_init.isoformat()].update(
                        error_type=type(error).__name__,
                        error=str(error),
                        last_attempt_utc=datetime.now(timezone.utc).isoformat(),
                    )
                    stop_reason = f"Retrieval failure at run {run_init.date()}: {error}"
                    _checkpoint(inventory_by_run, phase, stop_reason, started_at_utc)
                    break
            if stop_reason:
                break

    final_inventory = scan_cache_authority(run_dates, locations)
    final_by_run = {entry["run_init_utc"]: entry for entry in final_inventory}
    _checkpoint(final_by_run, phase, stop_reason, started_at_utc)
    priority_missing = _pending_dates(run_dates, final_by_run, True)
    full_missing = [
        run_init
        for run_init in run_dates
        if final_by_run[run_init.isoformat()]["status"]
        not in {"success", "official_archive_unavailable"}
    ]
    return {
        "downloaded_this_pass": downloaded,
        "stop_reason": stop_reason,
        "priority_complete": not priority_missing,
        "full_range_complete": not full_missing,
        "successful_run_count": sum(
            entry["status"] == "success" for entry in final_inventory
        ),
        "failed_run_count": sum(entry["status"] == "failed" for entry in final_inventory),
        "missing_run_count": sum(entry["status"] == "missing" for entry in final_inventory),
        "official_archive_unavailable_count": sum(
            entry["status"] == "official_archive_unavailable"
            for entry in final_inventory
        ),
        "free_c_drive_bytes": free_c_drive_bytes(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-runtime-minutes", type=float, default=50.0)
    parser.add_argument("--success-delay-seconds", type=float, default=2.0)
    parser.add_argument("--priority-only", action="store_true")
    arguments = parser.parse_args()
    result = recover_weather_cache(
        max_runtime_minutes=arguments.max_runtime_minutes,
        success_delay_seconds=arguments.success_delay_seconds,
        priority_only=arguments.priority_only,
    )
    print(json.dumps(result, indent=2), flush=True)
