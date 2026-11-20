"""Phase 6 app data helpers shared by the prep script, the API and the Streamlit lab.

Pure functions only (no file or network I/O) so they can be unit tested.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

TORONTO = ZoneInfo("America/Toronto")

# Generous Toronto bounding box; anything outside is a bad or placeholder coordinate.
TORONTO_BBOX = {"lat_min": 43.40, "lat_max": 44.00, "lon_min": -79.80, "lon_max": -79.00}

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Columns that are identical for every station in a given hour (weather + calendar).
HOUR_CONTEXT_COLUMNS = [
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "is_holiday",
    "temp_c",
    "precip_mm",
    "wind_speed_kmh",
]


def to_toronto_local(now: datetime) -> datetime:
    """Naive Toronto wall-clock time. Naive input is assumed to already be Toronto local."""
    if now.tzinfo is None:
        return now
    return now.astimezone(TORONTO).replace(tzinfo=None)


def resolve_demo_hour(now: datetime, available_hours: pd.DatetimeIndex) -> pd.Timestamp:
    """Map a real clock time onto the latest demo hour with the same weekday and hour.

    The POC only has 2024 data, so "now" is shown as the most recent holdout hour that
    shares its day-of-week and hour-of-day. Falls back to the latest available hour.
    """
    hours = pd.DatetimeIndex(available_hours)
    if len(hours) == 0:
        raise ValueError("no available demo hours")
    local = to_toronto_local(now)
    mask = (hours.dayofweek == local.weekday()) & (hours.hour == local.hour)
    matches = hours[mask]
    return pd.Timestamp(matches.max() if len(matches) else hours.max())


def _valid_coord(lat: Any, lon: Any) -> bool:
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    if math.isnan(lat_f) or math.isnan(lon_f):
        return False
    return (
        TORONTO_BBOX["lat_min"] <= lat_f <= TORONTO_BBOX["lat_max"]
        and TORONTO_BBOX["lon_min"] <= lon_f <= TORONTO_BBOX["lon_max"]
    )


def parse_gbfs_stations(payload: dict) -> pd.DataFrame:
    """GBFS station_information JSON -> one row per station with a usable Toronto location."""
    rows = []
    for st in payload.get("data", {}).get("stations", []):
        sid = str(st.get("station_id", ""))
        if not sid.isdigit() or not _valid_coord(st.get("lat"), st.get("lon")):
            continue
        rows.append(
            {
                "station_id": int(sid),
                "name": str(st.get("name", "")).strip(),
                "lat": float(st["lat"]),
                "lon": float(st["lon"]),
                "capacity": st.get("capacity"),
            }
        )
    frame = pd.DataFrame(rows, columns=["station_id", "name", "lat", "lon", "capacity"])
    frame["station_id"] = frame["station_id"].astype("int64")
    return frame.drop_duplicates("station_id").reset_index(drop=True)


def build_hour_context(row: pd.Series) -> dict[str, Any]:
    """Time, calendar and weather for one hour; the same object the map strip and panel show."""
    ts = pd.Timestamp(row["hour_ts"])
    return {
        "hour_ts": ts.isoformat(),
        "weekday": WEEKDAYS[ts.weekday()],
        "hour_of_day": int(row["hour_of_day"]),
        "is_weekend": bool(int(row["is_weekend"])),
        "is_holiday": bool(int(row["is_holiday"])),
        "temp_c": _maybe_float(row.get("temp_c")),
        "precip_mm": _maybe_float(row.get("precip_mm")),
        "wind_speed_kmh": _maybe_float(row.get("wind_speed_kmh")),
        "horizon": "1h",
    }


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else round(f, 2)
