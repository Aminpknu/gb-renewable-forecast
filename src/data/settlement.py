"""GB electricity settlement-period timestamp utilities."""

from __future__ import annotations

from datetime import date

import pandas as pd

LOCAL_TIMEZONE = "Europe/London"
UTC_TIMEZONE = "UTC"
SETTLEMENT_PERIOD_MINUTES = 30


def expected_period_count(settlement_date: date | str | pd.Timestamp) -> int:
    """Return the physical number of half-hours in a GB settlement day."""
    day = pd.Timestamp(settlement_date).normalize()
    local_start = day.tz_localize(LOCAL_TIMEZONE)
    local_end = (day + pd.Timedelta(days=1)).tz_localize(LOCAL_TIMEZONE)
    elapsed = local_end.tz_convert(UTC_TIMEZONE) - local_start.tz_convert(UTC_TIMEZONE)
    return int(elapsed / pd.Timedelta(minutes=SETTLEMENT_PERIOD_MINUTES))


def construct_settlement_timestamps(
    settlement_dates: pd.Series,
    settlement_periods: pd.Series,
) -> pd.DataFrame:
    """Construct local and UTC period-start timestamps from canonical market keys.

    Invalid dates, non-integral periods, and periods outside the physical GB
    settlement day are marked as impossible and receive missing timestamps.
    """
    dates = pd.to_datetime(settlement_dates, errors="coerce").dt.normalize()
    periods = pd.to_numeric(settlement_periods, errors="coerce")
    integral_periods = periods.notna() & periods.eq(periods.round())

    expected_counts = dates.map(
        lambda value: expected_period_count(value) if pd.notna(value) else pd.NA
    )
    possible = (
        dates.notna()
        & integral_periods
        & periods.ge(1)
        & periods.le(pd.to_numeric(expected_counts, errors="coerce"))
    )

    valid_time_utc = pd.Series(
        pd.NaT, index=settlement_dates.index, dtype="datetime64[ns, UTC]"
    )
    if possible.any():
        possible_dates = pd.DatetimeIndex(dates.loc[possible])
        midnight_utc = possible_dates.tz_localize(LOCAL_TIMEZONE).tz_convert(UTC_TIMEZONE)
        elapsed = pd.to_timedelta(
            (periods.loc[possible].astype("int64") - 1) * SETTLEMENT_PERIOD_MINUTES,
            unit="min",
        )
        valid_time_utc.loc[possible] = (midnight_utc + elapsed.to_numpy()).array

    valid_time_local = valid_time_utc.dt.tz_convert(LOCAL_TIMEZONE)
    return pd.DataFrame(
        {
            "valid_time_local": valid_time_local,
            "valid_time_utc": valid_time_utc,
            "impossible_timestamp": ~possible,
        },
        index=settlement_dates.index,
    )


def add_settlement_timestamps(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with validated local and UTC settlement timestamps."""
    result = frame.copy()
    timestamps = construct_settlement_timestamps(
        result["settlement_date"], result["settlement_period"]
    )
    for column in timestamps.columns:
        result[column] = timestamps[column]
    return result
