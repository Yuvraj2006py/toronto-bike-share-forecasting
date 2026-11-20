"""Phase 3: build features_2024 (calendar, lags, rolling, weather).

Prereqs:
    python -m src.phase2_hourly
    python -m src.phase3_weather

Run from project root:
    python -m src.phase3_features
"""

from __future__ import annotations

from pathlib import Path

import holidays
import pandas as pd

from src.db import DB_PATH, DATA_PROCESSED, PROJECT_ROOT, get_connection

SQL_PATH = PROJECT_ROOT / "sql" / "03_features.sql"
PARQUET_PATH = DATA_PROCESSED / "features_2024.parquet"
NOTES_PATH = PROJECT_ROOT / "sql" / "03_feature_safety_notes.md"

FEATURE_SAFETY_NOTES = """# Phase 3 feature safety notes

Each feature: one-line **safe at predict time?** answer.

| Feature | Safe at predict time? |
|---------|------------------------|
| `departures` | **Target only** — never use as a feature for the same row. |
| `hour_of_day` | Yes — known from the forecast timestamp. |
| `day_of_week` | Yes — known from the forecast timestamp. |
| `month` | Yes — known from the forecast timestamp. |
| `is_weekend` | Yes — known from the forecast timestamp. |
| `is_holiday` | Yes — Ontario holiday calendar is known in advance. |
| `lag_1h` | Yes — uses departures at t−1 only (needs that hour observed / forecasted recursively). |
| `lag_24h` | Yes — uses departures at t−24 only. |
| `lag_168h` | Yes — uses departures at t−168 only (same signal as weekly naive baseline). |
| `roll_mean_24h` | Yes — AVG over t−24…t−1 only (current hour excluded). |
| `roll_std_24h` | Yes — STDDEV over t−24…t−1 only. |
| `roll_mean_168h` | Yes — AVG over t−168…t−1 only. |
| `roll_std_168h` | Yes — STDDEV over t−168…t−1 only. |
| `temp_c` | **POC yes / ops no as-is** — historical observed weather. Production needs a weather *forecast* available before the hour. |
| `precip_mm` | **POC yes / ops no as-is** — same as temp. |
| `wind_speed_kmh` | **POC yes / ops no as-is** — same as temp. |

## Leakage controls baked into SQL

- Window frames use `ROWS BETWEEN N PRECEDING AND 1 PRECEDING` (never include current `departures`).
- Lags use `LAG` only (past offsets).
- No global train/test aggregates in this table.
- Station spines start at first appearance (Phase 2 Option B), so early lags are NULL (cold start), not fabricated zeros from pre-open periods.

## Locked model feature sets (accepted)

**Poisson GLM (small / interpretable):**
`hour_of_day`, `day_of_week`, `is_weekend`, `is_holiday`, `lag_168h`, `temp_c`, `precip_mm`,
plus `start_station_id` (one-hot) — added in Phase 4 after it fixed the model's missing station level.

**Gradient boosting (fuller):**
all non-target columns (calendar + all lags + all rolling + weather).
"""


def load_ontario_holidays(con) -> None:
    """Materialize Ontario statutory holidays for 2024 as a DuckDB table."""
    on_holidays = holidays.Canada(prov="ON", years=[2024])
    rows = [{"holiday_date": d, "holiday_name": name} for d, name in sorted(on_holidays.items())]
    df = pd.DataFrame(rows)
    df["holiday_date"] = pd.to_datetime(df["holiday_date"]).dt.date
    con.execute("DROP TABLE IF EXISTS ontario_holidays")
    con.register("_holidays_df", df)
    con.execute(
        """
        CREATE TABLE ontario_holidays AS
        SELECT holiday_date::DATE AS holiday_date, holiday_name::VARCHAR AS holiday_name
        FROM _holidays_df
        """
    )
    con.unregister("_holidays_df")
    print(f"ontario_holidays: {len(df)} days")
    print(df.to_string(index=False))


def run_feature_sql(con) -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    con.execute(sql)


def export_parquet(con) -> None:
    out = PARQUET_PATH.as_posix().replace("'", "''")
    con.execute(f"COPY features_2024 TO '{out}' (FORMAT PARQUET)")


def write_notes() -> None:
    NOTES_PATH.write_text(FEATURE_SAFETY_NOTES, encoding="utf-8")
    print(f"Wrote {NOTES_PATH}")


def sanity_checks(con) -> None:
    n_hourly = con.execute("SELECT COUNT(*) FROM hourly_departures").fetchone()[0]
    summary = con.execute(
        """
        SELECT
            COUNT(*) AS n_rows,
            COUNT(DISTINCT start_station_id) AS n_stations,
            SUM(departures)::BIGINT AS sum_departures,
            SUM((temp_c IS NULL)::INT)::BIGINT AS null_temp,
            SUM((lag_1h IS NULL)::INT)::BIGINT AS null_lag_1h,
            SUM((lag_168h IS NULL)::INT)::BIGINT AS null_lag_168h,
            SUM((roll_mean_24h IS NULL)::INT)::BIGINT AS null_roll_24h
        FROM features_2024
        """
    ).fetchdf()
    dupes = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT start_station_id, hour_ts
            FROM features_2024
            GROUP BY 1, 2
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    # Leakage spot-check on a mature row (full 24h history):
    # roll_mean_24h == mean(t-24..t-1) and != mean that includes current hour.
    leak_probe = con.execute(
        """
        WITH sample AS (
            SELECT start_station_id, hour_ts, departures, roll_mean_24h, lag_1h
            FROM features_2024
            WHERE lag_24h IS NOT NULL
            ORDER BY start_station_id, hour_ts
            LIMIT 1 OFFSET 1000
        ),
        hist AS (
            SELECT
                AVG(CASE WHEN f.hour_ts < s.hour_ts
                          AND f.hour_ts >= s.hour_ts - INTERVAL 24 HOUR
                         THEN f.departures END) AS manual_past_mean,
                AVG(CASE WHEN f.hour_ts <= s.hour_ts
                          AND f.hour_ts > s.hour_ts - INTERVAL 24 HOUR
                         THEN f.departures END) AS leaky_include_current
            FROM features_2024 f
            CROSS JOIN sample s
            WHERE f.start_station_id = s.start_station_id
        )
        SELECT
            s.start_station_id,
            s.hour_ts,
            s.roll_mean_24h,
            h.manual_past_mean AS manual_mean,
            abs(s.roll_mean_24h - h.manual_past_mean) AS abs_diff,
            abs(s.roll_mean_24h - h.leaky_include_current) AS abs_diff_vs_leaky,
            s.lag_1h,
            (
              SELECT departures FROM features_2024 f2
              WHERE f2.start_station_id = s.start_station_id
                AND f2.hour_ts = s.hour_ts - INTERVAL 1 HOUR
            ) AS true_lag_1h
        FROM sample s, hist h
        """
    ).fetchdf()

    # Weather coverage: every feature hour should match a weather hour
    weather_miss = con.execute(
        """
        SELECT COUNT(*) FROM features_2024 WHERE temp_c IS NULL
        """
    ).fetchone()[0]

    # Holiday sanity: Canada Day / Labour Day present as is_holiday=1
    holiday_hours = con.execute(
        """
        SELECT CAST(hour_ts AS DATE) AS d, COUNT(*) AS n, SUM(is_holiday) AS hol_rows
        FROM features_2024
        WHERE CAST(hour_ts AS DATE) IN (DATE '2024-07-01', DATE '2024-09-02')
        GROUP BY 1
        ORDER BY 1
        """
    ).fetchdf()

    print(summary.to_string(index=False))
    print(f"\nhourly_departures rows: {n_hourly:,}")
    print(f"duplicate keys: {dupes}")
    print(f"weather null temp rows: {weather_miss}")
    print("\nLeakage probe (roll_mean_24h vs manual past mean; lag_1h vs true):")
    print(leak_probe.to_string(index=False))
    print("\nHoliday spot-check (Canada Day / Labour Day):")
    print(holiday_hours.to_string(index=False))

    if int(summary.loc[0, "n_rows"]) != n_hourly:
        raise AssertionError("features_2024 row count != hourly_departures")
    if dupes != 0:
        raise AssertionError("duplicate (station, hour) in features_2024")
    if weather_miss != 0:
        raise AssertionError(f"{weather_miss} feature rows missing weather")

    abs_diff = float(leak_probe.loc[0, "abs_diff"])
    abs_diff_leaky = float(leak_probe.loc[0, "abs_diff_vs_leaky"])
    if abs_diff > 1e-6:
        raise AssertionError(f"roll_mean_24h mismatch vs past-only mean: {abs_diff}")
    # When current hour differs from the past window, a leaky frame would move the mean
    if abs_diff_leaky < 1e-9:
        raise AssertionError(
            "roll_mean_24h equals include-current mean; cannot confirm current hour excluded"
        )
    if leak_probe.loc[0, "lag_1h"] != leak_probe.loc[0, "true_lag_1h"]:
        raise AssertionError("lag_1h does not match prior hour departures")

    if holiday_hours.empty or int(holiday_hours["hol_rows"].min()) <= 0:
        raise AssertionError("expected is_holiday=1 on known Ontario holidays")


def main() -> None:
    if not SQL_PATH.exists():
        raise FileNotFoundError(SQL_PATH)

    con = get_connection()
    try:
        # Fail fast if prereqs missing
        tables = {
            r[0]
            for r in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
        for required in ("hourly_departures", "weather_hourly"):
            if required not in tables:
                raise RuntimeError(
                    f"Missing {required}. Run phase2_hourly and phase3_weather first."
                )

        print("Loading Ontario holidays ...")
        load_ontario_holidays(con)

        print(f"Running {SQL_PATH.relative_to(PROJECT_ROOT)} ...")
        run_feature_sql(con)
        export_parquet(con)
        write_notes()

        print("\nSanity checks:")
        sanity_checks(con)
        print(f"\nfeatures_2024 ready in {DB_PATH}")
        print(f"Also wrote {PARQUET_PATH}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
