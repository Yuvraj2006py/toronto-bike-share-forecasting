"""Phase 1: build trips_clean from trips_raw using approved cleaning rules.

Run from project root:
    python -m src.phase1_clean
"""

from __future__ import annotations

from src.db import DB_PATH, DATA_PROCESSED, get_connection


CLEANING_RULES = """
Approved cleaning rules (Phase 1):
1. Drop trip_duration_sec < 60   (includes <=0 dock noise / false starts)
2. Drop trip_duration_sec > 86400 (24h+ abandoned / system junk)
3. Keep null end_station_id       (still a valid departure for demand)
4. Keep all user_type values
"""


def build_trips_clean(con) -> None:
    con.execute("DROP TABLE IF EXISTS trips_clean")
    con.execute(
        """
        CREATE TABLE trips_clean AS
        SELECT *
        FROM trips_raw
        WHERE trip_duration_sec >= 60
          AND trip_duration_sec <= 24 * 3600
        """
    )

    # Persist a portable copy for later phases / Streamlit
    out = (DATA_PROCESSED / "trips_clean.parquet").as_posix().replace("'", "''")
    con.execute(f"COPY trips_clean TO '{out}' (FORMAT PARQUET)")


def summarize(con) -> None:
    print(CLEANING_RULES)
    print(
        con.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM trips_raw) AS n_raw,
                (SELECT COUNT(*) FROM trips_clean) AS n_clean,
                (SELECT COUNT(*) FROM trips_raw)
                  - (SELECT COUNT(*) FROM trips_clean) AS n_dropped,
                (SELECT MIN(start_time) FROM trips_clean) AS min_start,
                (SELECT MAX(start_time) FROM trips_clean) AS max_start,
                (SELECT COUNT(DISTINCT start_station_id) FROM trips_clean) AS n_stations
            """
        ).fetchdf()
    )
    print("\nDropped by reason (approx, overlapping rows counted once in total):")
    print(
        con.execute(
            """
            SELECT
                SUM(trip_duration_sec < 60)::BIGINT AS dropped_under_60s,
                SUM(trip_duration_sec > 24 * 3600)::BIGINT AS dropped_over_24h
            FROM trips_raw
            """
        ).fetchdf()
    )


def main() -> None:
    con = get_connection()
    try:
        build_trips_clean(con)
        summarize(con)
        print(f"\ntrips_clean ready in {DB_PATH}")
        print(f"Also wrote {DATA_PROCESSED / 'trips_clean.parquet'}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
