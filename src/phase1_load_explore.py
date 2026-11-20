"""Phase 1: load raw 2024 CSVs into DuckDB and profile data quality.

Run from project root:
    python -m src.phase1_load_explore
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.db import DATA_PROCESSED, DATA_RAW, DB_PATH, get_connection

RAW_2024 = DATA_RAW / "2024"
STAGED_DIR = DATA_PROCESSED / "staged_parquet"


def read_city_csv(path: Path) -> pd.DataFrame:
    """Read one City ridership CSV with messy encodings / optional Model column.

    Why pandas first: DuckDB's CSV encoding options reject these files (mixed
    UTF-8/CP1252 and BOM). Staging a clean UTF-8 copy keeps DuckDB simple.
    """
    last_err: Exception | None = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, encoding=enc, low_memory=False)
        except UnicodeDecodeError as exc:
            last_err = exc
    raise RuntimeError(f"Could not decode {path.name}") from last_err


def parse_city_timestamp(series: pd.Series) -> pd.Series:
    """Parse 2024 City timestamps as explicit MM/DD/YYYY.

    Why not pd.to_datetime(dayfirst=False): pandas still mis-parses ambiguous
    dates like 01/02/2024 as 2 Jan in some paths. These files are month-first
    (evidence: many 01/13/2024 values), so we extract components ourselves.
    """
    parts = series.astype(str).str.extract(
        r"^\s*(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})"
    )
    return pd.to_datetime(
        {
            "year": parts["year"],
            "month": parts["month"],
            "day": parts["day"],
            "hour": parts["hour"],
            "minute": parts["minute"],
        },
        errors="coerce",
    )


def stage_clean_csvs() -> list[Path]:
    """Normalize monthly CSVs → UTF-8 staged copies with canonical columns."""
    STAGED_DIR.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []

    csvs = sorted(RAW_2024.glob("Bike share ridership 2024-*.csv"))
    if not csvs:
        raise FileNotFoundError(f"No CSVs under {RAW_2024}")

    for path in csvs:
        print(f"Staging {path.name}")
        df = read_city_csv(path)

        # Normalize awkward City header names
        rename = {
            "Trip Id": "trip_id",
            "Trip  Duration": "trip_duration_sec",
            "Start Station Id": "start_station_id",
            "Start Time": "start_time_raw",
            "Start Station Name": "start_station_name",
            "End Station Id": "end_station_id",
            "End Time": "end_time_raw",
            "End Station Name": "end_station_name",
            "Bike Id": "bike_id",
            "User Type": "user_type",
            "Model": "bike_model",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        if "bike_model" not in df.columns:
            df["bike_model"] = ""

        # Force stable dtypes across months so parquet schemas match.
        df["trip_id"] = pd.to_numeric(df["trip_id"], errors="coerce").astype("Int64")
        df["trip_duration_sec"] = pd.to_numeric(
            df["trip_duration_sec"], errors="coerce"
        ).astype("Int64")
        df["start_station_id"] = pd.to_numeric(
            df["start_station_id"], errors="coerce"
        ).astype("Int64")
        df["end_station_id"] = pd.to_numeric(
            df["end_station_id"], errors="coerce"
        ).astype("Int64")
        df["bike_id"] = pd.to_numeric(df["bike_id"], errors="coerce").astype("Int64")
        df["bike_model"] = df["bike_model"].fillna("").astype(str)
        df["user_type"] = df["user_type"].astype(str)
        df["start_station_name"] = df["start_station_name"].astype(str)
        df["end_station_name"] = df["end_station_name"].astype(str)

        df["start_time"] = parse_city_timestamp(df["start_time_raw"])
        df["end_time"] = parse_city_timestamp(df["end_time_raw"])
        df["source_file"] = path.name

        keep = [
            "trip_id",
            "trip_duration_sec",
            "start_station_id",
            "start_time",
            "start_station_name",
            "end_station_id",
            "end_time",
            "end_station_name",
            "bike_id",
            "user_type",
            "bike_model",
            "source_file",
        ]
        out = STAGED_DIR / (path.stem.replace(" ", "_") + ".parquet")
        df[keep].to_parquet(out, index=False)
        staged.append(out)

    return staged


def load_trips_raw(con) -> None:
    """Load staged parquet files into DuckDB table trips_raw."""
    staged = stage_clean_csvs()
    con.execute("DROP TABLE IF EXISTS trips_raw")

    glob_sql = (STAGED_DIR / "Bike_share_ridership_2024-*.parquet").as_posix().replace(
        "'", "''"
    )
    print(f"Loading {len(staged)} staged files into DuckDB")
    con.execute(
        f"""
        CREATE TABLE trips_raw AS
        SELECT
            trip_id::BIGINT AS trip_id,
            trip_duration_sec::BIGINT AS trip_duration_sec,
            start_station_id::INTEGER AS start_station_id,
            start_time::TIMESTAMP AS start_time,
            start_station_name::VARCHAR AS start_station_name,
            TRY_CAST(end_station_id AS INTEGER) AS end_station_id,
            TRY_CAST(end_time AS TIMESTAMP) AS end_time,
            end_station_name::VARCHAR AS end_station_name,
            TRY_CAST(bike_id AS INTEGER) AS bike_id,
            user_type::VARCHAR AS user_type,
            bike_model::VARCHAR AS bike_model,
            source_file::VARCHAR AS source_file
        FROM read_parquet('{glob_sql}', union_by_name = true)
        """
    )


def profile(con) -> None:
    print("\n=== row count / date range ===")
    print(
        con.execute(
            """
            SELECT
                COUNT(*) AS n_rows,
                COUNT(DISTINCT trip_id) AS n_distinct_trip_id,
                MIN(start_time) AS min_start,
                MAX(start_time) AS max_start
            FROM trips_raw
            """
        ).fetchdf()
    )

    print("\n=== nulls ===")
    print(
        con.execute(
            """
            SELECT
                SUM(trip_id IS NULL)::BIGINT AS trip_id_nulls,
                SUM(trip_duration_sec IS NULL)::BIGINT AS duration_nulls,
                SUM(start_station_id IS NULL)::BIGINT AS start_station_nulls,
                SUM(start_time IS NULL)::BIGINT AS start_time_nulls,
                SUM(end_station_id IS NULL)::BIGINT AS end_station_nulls,
                SUM(end_time IS NULL)::BIGINT AS end_time_nulls,
                SUM(bike_id IS NULL)::BIGINT AS bike_id_nulls,
                SUM(user_type IS NULL)::BIGINT AS user_type_nulls
            FROM trips_raw
            """
        ).fetchdf()
    )

    print("\n=== duplicate trip_id ===")
    print(
        con.execute(
            """
            SELECT COUNT(*) AS n_trip_ids_with_dupes
            FROM (
                SELECT trip_id
                FROM trips_raw
                GROUP BY trip_id
                HAVING COUNT(*) > 1
            )
            """
        ).fetchdf()
    )

    print("\n=== duration distribution (seconds) ===")
    print(
        con.execute(
            """
            SELECT
                MIN(trip_duration_sec) AS min_dur,
                quantile_cont(trip_duration_sec, 0.01) AS p01,
                quantile_cont(trip_duration_sec, 0.50) AS p50,
                quantile_cont(trip_duration_sec, 0.95) AS p95,
                quantile_cont(trip_duration_sec, 0.99) AS p99,
                MAX(trip_duration_sec) AS max_dur,
                SUM(trip_duration_sec <= 0)::BIGINT AS non_positive,
                SUM(trip_duration_sec < 60)::BIGINT AS under_60s,
                SUM(trip_duration_sec > 24 * 3600)::BIGINT AS over_24h
            FROM trips_raw
            """
        ).fetchdf()
    )

    print("\n=== user_type counts ===")
    print(
        con.execute(
            """
            SELECT user_type, COUNT(*) AS n
            FROM trips_raw
            GROUP BY 1
            ORDER BY n DESC
            """
        ).fetchdf()
    )

    print("\n=== rows per month ===")
    print(
        con.execute(
            """
            SELECT
                date_trunc('month', start_time) AS month,
                COUNT(*) AS n
            FROM trips_raw
            GROUP BY 1
            ORDER BY 1
            """
        ).fetchdf()
    )

    print("\n=== sample rows ===")
    print(con.execute("SELECT * FROM trips_raw LIMIT 5").fetchdf())


def main() -> None:
    if not RAW_2024.exists():
        raise FileNotFoundError(f"Missing raw folder: {RAW_2024}")

    csvs = list(RAW_2024.glob("Bike share ridership 2024-*.csv"))
    print(f"Found {len(csvs)} CSV files")

    con = get_connection()
    try:
        load_trips_raw(con)
        profile(con)
    finally:
        print(f"\nWrote trips_raw into {DB_PATH}")
        con.close()


if __name__ == "__main__":
    main()
