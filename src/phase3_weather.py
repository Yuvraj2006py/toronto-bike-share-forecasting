"""Phase 3: download Open-Meteo historical hourly weather for Toronto.

Run from project root:
    python -m src.phase3_weather

POC note: this is *observed* weather. Operational forecasting would need
weather *forecasts* available at predict time — document that in features notes.
"""

from __future__ import annotations

import json
from datetime import date
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

from src.db import DATA_PROCESSED, get_connection

# Downtown Toronto (plan lock)
LAT = 43.65
LON = -79.38
TIMEZONE = "America/Toronto"

# Match POC ridership window (Jan–Sep 2024)
START_DATE = date(2024, 1, 1)
END_DATE = date(2024, 9, 30)

HOURLY_VARS = (
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
)

PARQUET_PATH = DATA_PROCESSED / "weather_2024.parquet"
API_URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_weather() -> pd.DataFrame:
    params = {
        "latitude": LAT,
        "longitude": LON,
        "start_date": START_DATE.isoformat(),
        "end_date": END_DATE.isoformat(),
        "hourly": ",".join(HOURLY_VARS),
        "timezone": TIMEZONE,
    }
    url = f"{API_URL}?{urlencode(params)}"
    print(f"GET {url}")
    with urlopen(url, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    hourly = payload["hourly"]
    df = pd.DataFrame(
        {
            "hour_ts": pd.to_datetime(hourly["time"]),
            "temp_c": hourly["temperature_2m"],
            "precip_mm": hourly["precipitation"],
            "wind_speed_kmh": hourly["wind_speed_10m"],
        }
    )
    if df["hour_ts"].isna().any():
        raise ValueError("Open-Meteo returned null timestamps")
    if df.duplicated(subset=["hour_ts"]).any():
        raise ValueError("Duplicate weather hours")
    return df


def persist(df: pd.DataFrame) -> None:
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PARQUET_PATH, index=False)

    con = get_connection()
    try:
        con.execute("DROP TABLE IF EXISTS weather_hourly")
        con.execute(
            """
            CREATE TABLE weather_hourly AS
            SELECT
                hour_ts::TIMESTAMP AS hour_ts,
                temp_c::DOUBLE AS temp_c,
                precip_mm::DOUBLE AS precip_mm,
                wind_speed_kmh::DOUBLE AS wind_speed_kmh
            FROM read_parquet(?)
            """,
            [str(PARQUET_PATH)],
        )
        n = con.execute("SELECT COUNT(*) FROM weather_hourly").fetchone()[0]
        print(f"weather_hourly rows: {n}")
        print(f"Wrote {PARQUET_PATH}")
    finally:
        con.close()


def main() -> None:
    df = fetch_weather()
    print(df.head(3).to_string(index=False))
    print(f"... {len(df)} hourly rows, {df['hour_ts'].min()} → {df['hour_ts'].max()}")
    persist(df)


if __name__ == "__main__":
    main()
