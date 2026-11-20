"""Phase 6 data prep: station locations + September app table (preds, weather, calendar, lags).

Writes (all under data/processed/, gitignored):
    stations_geo.parquet          GBFS station locations, valid Toronto coords only
    app_hourly_preds_2024_09.parquet
                                  one row per scored September station-hour with every model's
                                  prediction and the exact feature values the models saw
    app_meta.json                 row counts, dropped stations, MAE spot-check vs Phase 4

Run from project root (after Phase 4 final models exist):
    python -m src.phase6_prep
"""

from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
import requests

from src.app_data import parse_gbfs_stations
from src.db import DATA_PROCESSED, PROJECT_ROOT, get_connection
from src.modeling import (
    GBM_FEATURES,
    POISSON_FEATURES,
    TARGET,
    load_features,
    regression_metrics,
)

GBFS_STATION_INFO = "https://tor.publicbikesystem.net/ube/gbfs/v1/en/station_information"
MODELS_DIR = PROJECT_ROOT / "models"

STATIONS_PATH = DATA_PROCESSED / "stations_geo.parquet"
APP_PREDS_PATH = DATA_PROCESSED / "app_hourly_preds_2024_09.parquet"
APP_META_PATH = DATA_PROCESSED / "app_meta.json"

APP_COLUMNS = [
    "station_id",
    "hour_ts",
    "actual",
    "weekly_naive",
    "gbm_pred",
    "poisson_pred",
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "is_holiday",
    "temp_c",
    "precip_mm",
    "wind_speed_kmh",
    "lag_1h",
    "lag_24h",
    "lag_168h",
    "roll_mean_24h",
]

# Must agree with reports/phase4/test_results.csv to this tolerance, else the app shows
# different numbers than the write-up.
MAE_TOLERANCE = 1e-3


def fetch_stations() -> pd.DataFrame:
    resp = requests.get(GBFS_STATION_INFO, timeout=30)
    resp.raise_for_status()
    return parse_gbfs_stations(resp.json())


def ridership_station_names() -> pd.DataFrame:
    """Most common 2024 name per station id; used when GBFS has no record for an id."""
    con = get_connection(read_only=True)
    try:
        return con.execute(
            """
            SELECT start_station_id AS station_id, mode(start_station_name) AS ridership_name
            FROM trips_clean
            GROUP BY start_station_id
            """
        ).fetchdf()
    finally:
        con.close()


def build_app_table() -> tuple[pd.DataFrame, dict]:
    df = load_features()
    test = df[(df["split"] == "test") & df["lag_168h"].notna()].reset_index(drop=True)
    del df

    gbm = joblib.load(MODELS_DIR / "gbm_full_poisson.joblib")
    poisson = joblib.load(MODELS_DIR / "poisson_station.joblib")

    out = pd.DataFrame(
        {
            "station_id": test["start_station_id"].astype("int64"),
            "hour_ts": test["hour_ts"],
            "actual": test[TARGET].astype("float32"),
            "weekly_naive": test["lag_168h"].astype("float32"),
            "gbm_pred": gbm.predict(test[GBM_FEATURES]).astype("float32"),
            "poisson_pred": poisson.predict(
                test[[*POISSON_FEATURES, "start_station_id"]]
            ).astype("float32"),
        }
    )
    for col in APP_COLUMNS:
        if col not in out.columns:
            out[col] = test[col].to_numpy()

    phase4 = pd.read_csv(PROJECT_ROOT / "reports" / "phase4" / "test_results.csv").set_index("model")
    y = out["actual"].to_numpy()
    checks = {}
    for col, model in [("gbm_pred", "gbm_full_poisson"), ("poisson_pred", "poisson_station"),
                       ("weekly_naive", "weekly_naive")]:
        mae = regression_metrics(y, out[col].to_numpy())["mae"]
        expected = float(phase4.loc[model, "mae"])
        checks[model] = {"app_mae": round(mae, 4), "phase4_mae": round(expected, 4)}
        if abs(mae - expected) > MAE_TOLERANCE:
            raise AssertionError(f"{model}: app MAE {mae:.4f} != Phase 4 {expected:.4f}")
    return out[APP_COLUMNS], checks


def check_weather_consistency(app: pd.DataFrame) -> None:
    """Every station in an hour must carry the same weather/calendar values."""
    per_hour = app.groupby("hour_ts")[["temp_c", "precip_mm", "wind_speed_kmh", "is_holiday"]].nunique(
        dropna=False
    )
    bad = per_hour[(per_hour > 1).any(axis=1)]
    if not bad.empty:
        raise AssertionError(f"{len(bad)} hours have inconsistent weather across stations")


def main() -> None:
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)

    print("fetching GBFS station locations…")
    stations = fetch_stations()
    stations.to_parquet(STATIONS_PATH, index=False)
    print(f"  {len(stations):,} stations with valid Toronto coordinates")

    print("scoring September with Phase 4 models…")
    app, mae_checks = build_app_table()
    check_weather_consistency(app)

    names = ridership_station_names()
    ridership_ids = set(app["station_id"].unique())
    geo_ids = set(stations["station_id"])
    mapped = ridership_ids & geo_ids
    missing = sorted(ridership_ids - geo_ids)

    app.to_parquet(APP_PREDS_PATH, index=False)

    meta = {
        "generated_at": pd.Timestamp.now(tz="America/Toronto").isoformat(),
        "source": {"gbfs": GBFS_STATION_INFO, "models": ["gbm_full_poisson", "poisson_station"]},
        "rows": int(len(app)),
        "hours": int(app["hour_ts"].nunique()),
        "hour_min": str(app["hour_ts"].min()),
        "hour_max": str(app["hour_ts"].max()),
        "stations_scored": len(ridership_ids),
        "stations_mapped": len(mapped),
        "stations_missing_geo": len(missing),
        "stations_missing_geo_sample": (
            names[names["station_id"].isin(missing[:10])].to_dict(orient="records")
        ),
        "mae_check": mae_checks,
    }
    with open(APP_META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, default=str)

    print(f"  {meta['rows']:,} station-hours over {meta['hours']} hours")
    print(f"  stations mapped {meta['stations_mapped']} / {meta['stations_scored']} "
          f"(missing geo: {meta['stations_missing_geo']})")
    for model, chk in mae_checks.items():
        print(f"  MAE {model}: app {chk['app_mae']} vs Phase 4 {chk['phase4_mae']}")
    print(f"wrote {STATIONS_PATH.name}, {APP_PREDS_PATH.name}, {APP_META_PATH.name}")


if __name__ == "__main__":
    main()
