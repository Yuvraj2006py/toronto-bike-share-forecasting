"""Phase 2: build hourly_departures (station × hour, zero-filled).

Run from project root:
    python -m src.phase2_hourly
"""

from __future__ import annotations

from src.db import DB_PATH, DATA_PROCESSED, PROJECT_ROOT, get_connection

SQL_PATH = PROJECT_ROOT / "sql" / "02_hourly_departures.sql"
PARQUET_PATH = DATA_PROCESSED / "hourly_departures.parquet"


def run_sql(con) -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    con.execute(sql)


def export_parquet(con) -> None:
    out = PARQUET_PATH.as_posix().replace("'", "''")
    con.execute(f"COPY hourly_departures TO '{out}' (FORMAT PARQUET)")


def sanity_checks(con) -> None:
    """Verify grain, first-appearance spines, and sum(departures) == trip count."""
    n_trips = con.execute(
        "SELECT COUNT(*) FROM trips_clean WHERE start_station_id IS NOT NULL"
    ).fetchone()[0]
    summary = con.execute(
        """
        SELECT
            COUNT(*) AS n_rows,
            COUNT(DISTINCT start_station_id) AS n_stations,
            COUNT(DISTINCT hour_ts) AS n_hours,
            SUM(departures)::BIGINT AS sum_departures,
            MIN(hour_ts) AS min_hour,
            MAX(hour_ts) AS max_hour,
            SUM((departures = 0)::INT)::BIGINT AS n_zero_hours
        FROM hourly_departures
        """
    ).fetchdf()
    dupes = con.execute(
        """
        SELECT COUNT(*) AS n_duplicate_keys
        FROM (
            SELECT start_station_id, hour_ts
            FROM hourly_departures
            GROUP BY 1, 2
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    # Option B: expected rows = sum over stations of hours from first → global max
    expected_rows = con.execute(
        """
        WITH trip_hours AS (
            SELECT
                start_station_id,
                date_trunc('hour', start_time) AS hour_ts
            FROM trips_clean
            WHERE start_station_id IS NOT NULL
        ),
        bounds AS (
            SELECT
                start_station_id,
                MIN(hour_ts) AS first_hour,
                (SELECT MAX(hour_ts) FROM trip_hours) AS max_hour
            FROM trip_hours
            GROUP BY start_station_id
        )
        SELECT SUM(
            date_diff('hour', first_hour, max_hour) + 1
        )::BIGINT
        FROM bounds
        """
    ).fetchone()[0]

    # No station should have a row before its first real trip hour
    pre_open = con.execute(
        """
        WITH first_seen AS (
            SELECT
                start_station_id,
                MIN(date_trunc('hour', start_time)) AS first_hour
            FROM trips_clean
            WHERE start_station_id IS NOT NULL
            GROUP BY 1
        )
        SELECT COUNT(*)
        FROM hourly_departures h
        JOIN first_seen f USING (start_station_id)
        WHERE h.hour_ts < f.first_hour
        """
    ).fetchone()[0]

    sum_dep = int(summary.loc[0, "sum_departures"])
    print(summary.to_string(index=False))
    print(f"\nexpected rows (per-station first→max): {expected_rows:,}")
    print(f"actual rows:                          {int(summary.loc[0, 'n_rows']):,}")
    print(f"trips_clean (non-null start):         {n_trips:,}")
    print(f"sum(departures):                      {sum_dep:,}")
    print(f"difference:                           {n_trips - sum_dep:,}")
    print(f"duplicate (station, hour) keys:       {dupes}")
    print(f"rows before first appearance:         {pre_open}")

    if dupes != 0:
        raise AssertionError("hourly_departures has duplicate (station, hour) keys")
    if int(summary.loc[0, "n_rows"]) != int(expected_rows):
        raise AssertionError(
            f"row count {int(summary.loc[0, 'n_rows'])} != expected {expected_rows}"
        )
    if pre_open != 0:
        raise AssertionError(f"{pre_open} rows exist before station first appearance")
    if sum_dep != n_trips:
        raise AssertionError(
            f"sum(departures)={sum_dep} != trips_clean count={n_trips}"
        )


def main() -> None:
    if not SQL_PATH.exists():
        raise FileNotFoundError(SQL_PATH)

    con = get_connection()
    try:
        print(f"Running {SQL_PATH.relative_to(PROJECT_ROOT)} ...")
        run_sql(con)
        export_parquet(con)
        print("\nSanity checks:")
        sanity_checks(con)
        print(f"\nhourly_departures ready in {DB_PATH}")
        print(f"Also wrote {PARQUET_PATH}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
