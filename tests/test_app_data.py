"""Phase 6 app data helpers: demo-hour mapping, GBFS parsing, hour context."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src.app_data import (
    build_hour_context,
    parse_gbfs_stations,
    resolve_demo_hour,
)

TORONTO = ZoneInfo("America/Toronto")


def _sept_hours() -> pd.DatetimeIndex:
    return pd.date_range("2024-09-01 00:00", "2024-09-30 23:00", freq="h")


def test_resolve_demo_hour_matches_weekday_and_hour_latest_date():
    # Thursday 2026-11-19 21:30 Toronto -> latest Thursday 21:00 in Sept 2024 = 2024-09-26
    now = datetime(2026, 11, 19, 21, 30, tzinfo=TORONTO)
    assert resolve_demo_hour(now, _sept_hours()) == pd.Timestamp("2024-09-26 21:00")


def test_resolve_demo_hour_monday_8am():
    now = datetime(2026, 11, 16, 8, 5, tzinfo=TORONTO)
    assert resolve_demo_hour(now, _sept_hours()) == pd.Timestamp("2024-09-30 08:00")


def test_resolve_demo_hour_converts_utc_input_across_dst_end():
    # 2026-11-01: clocks fall back at 02:00 EDT -> 01:00 EST.
    # 05:30 UTC is 01:30 EDT and 06:30 UTC is 01:30 EST: both Sunday 01:00 local.
    utc = ZoneInfo("UTC")
    hours = _sept_hours()
    first = resolve_demo_hour(datetime(2026, 11, 1, 5, 30, tzinfo=utc), hours)
    second = resolve_demo_hour(datetime(2026, 11, 1, 6, 30, tzinfo=utc), hours)
    assert first == second == pd.Timestamp("2024-09-29 01:00")


def test_resolve_demo_hour_naive_input_treated_as_toronto_local():
    now = datetime(2026, 11, 16, 8, 5)  # Monday, no tz
    assert resolve_demo_hour(now, _sept_hours()) == pd.Timestamp("2024-09-30 08:00")


def test_resolve_demo_hour_falls_back_to_latest_when_no_match():
    # Only Mondays available; a Tuesday request falls back to the latest hour overall.
    hours = pd.DatetimeIndex(["2024-09-02 08:00", "2024-09-09 08:00"])
    now = datetime(2026, 11, 17, 8, 0, tzinfo=TORONTO)
    assert resolve_demo_hour(now, hours) == pd.Timestamp("2024-09-09 08:00")


def test_resolve_demo_hour_empty_raises():
    with pytest.raises(ValueError):
        resolve_demo_hour(datetime(2026, 1, 1, tzinfo=TORONTO), pd.DatetimeIndex([]))


def test_parse_gbfs_stations_drops_invalid_coordinates():
    payload = {
        "data": {
            "stations": [
                {"station_id": "7006", "name": "Bay St / College St (East Side)",
                 "lat": 43.6608, "lon": -79.3856, "capacity": 31},
                {"station_id": "9999", "name": "Ghost", "lat": 0.0, "lon": 0.0},
                {"station_id": "9998", "name": "No coords"},
                {"station_id": "9997", "name": "Far away", "lat": 40.7, "lon": -74.0},
                {"station_id": "not-a-number", "name": "Bad id", "lat": 43.65, "lon": -79.38},
            ]
        }
    }
    out = parse_gbfs_stations(payload)
    assert list(out.columns) == ["station_id", "name", "lat", "lon", "capacity"]
    assert out["station_id"].tolist() == [7006]
    assert out["station_id"].dtype.kind == "i"


def test_build_hour_context_fields_and_labels():
    row = pd.Series(
        {
            "hour_ts": pd.Timestamp("2024-09-23 08:00"),
            "hour_of_day": 8,
            "day_of_week": 0,
            "is_weekend": 0,
            "is_holiday": 0,
            "temp_c": 18.9,
            "precip_mm": 1.5,
            "wind_speed_kmh": 12.3,
        }
    )
    ctx = build_hour_context(row)
    assert ctx["hour_ts"] == "2024-09-23T08:00:00"
    assert ctx["weekday"] == "Monday"
    assert ctx["is_weekend"] is False
    assert ctx["is_holiday"] is False
    assert ctx["temp_c"] == pytest.approx(18.9)
    assert ctx["precip_mm"] == pytest.approx(1.5)
    assert ctx["horizon"] == "1h"


def test_build_hour_context_weekday_ignores_feature_dow_convention():
    # features_2024 stores DuckDB dayofweek (Sunday=0, Monday=1); the label must still be Monday.
    row = pd.Series(
        {
            "hour_ts": pd.Timestamp("2024-09-23 08:00"),
            "hour_of_day": 8,
            "day_of_week": 1,
            "is_weekend": 0,
            "is_holiday": 0,
            "temp_c": 18.9,
            "precip_mm": 1.5,
            "wind_speed_kmh": 12.3,
        }
    )
    ctx = build_hour_context(row)
    assert ctx["weekday"] == "Monday"
    assert ctx["is_weekend"] is False
    assert ctx["is_holiday"] is False
    assert ctx["temp_c"] == pytest.approx(18.9)
    assert ctx["precip_mm"] == pytest.approx(1.5)
    assert ctx["horizon"] == "1h"
