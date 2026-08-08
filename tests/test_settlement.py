"""Tests for GB settlement-period timestamp construction."""

import pandas as pd

from src.data.settlement import construct_settlement_timestamps, expected_period_count


def _timestamps_for_day(day: str) -> pd.DataFrame:
    periods = pd.Series(range(1, expected_period_count(day) + 1))
    dates = pd.Series([day] * len(periods))
    return construct_settlement_timestamps(dates, periods)


def test_settlement_timestamp_construction() -> None:
    timestamps = construct_settlement_timestamps(
        pd.Series(["2024-01-15", "2024-01-15"]), pd.Series([1, 48])
    )
    assert timestamps.loc[0, "valid_time_local"].isoformat() == "2024-01-15T00:00:00+00:00"
    assert timestamps.loc[1, "valid_time_utc"].isoformat() == "2024-01-15T23:30:00+00:00"
    assert not timestamps["impossible_timestamp"].any()


def test_normal_settlement_day_has_48_periods() -> None:
    timestamps = _timestamps_for_day("2024-02-01")
    assert expected_period_count("2024-02-01") == 48
    assert timestamps["valid_time_utc"].nunique() == 48
    assert timestamps["valid_time_utc"].diff().dropna().eq(pd.Timedelta(minutes=30)).all()


def test_spring_dst_transition_has_46_periods() -> None:
    timestamps = _timestamps_for_day("2024-03-31")
    local_times = timestamps["valid_time_local"]
    assert expected_period_count("2024-03-31") == 46
    assert len(timestamps) == 46
    assert not local_times.dt.hour.eq(1).any()
    assert timestamps["valid_time_utc"].diff().dropna().eq(pd.Timedelta(minutes=30)).all()


def test_autumn_dst_transition_has_50_periods() -> None:
    timestamps = _timestamps_for_day("2024-10-27")
    local_wall_times = timestamps["valid_time_local"].dt.strftime("%H:%M")
    assert expected_period_count("2024-10-27") == 50
    assert len(timestamps) == 50
    assert local_wall_times.eq("01:00").sum() == 2
    assert local_wall_times.eq("01:30").sum() == 2
    assert timestamps["valid_time_utc"].nunique() == 50
    assert timestamps["valid_time_utc"].diff().dropna().eq(pd.Timedelta(minutes=30)).all()
