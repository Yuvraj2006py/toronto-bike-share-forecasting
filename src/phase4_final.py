"""Phase 4 final evaluation: refit finalists on Jan–Aug, score September once.

Finalists and their settings were fixed from August validation results
(reports/phase4/validation_results.csv) before this script touched September.
Do not change a finalist's settings after reading these test numbers.

Run from project root:
    python -m src.phase4_final
"""

from __future__ import annotations

import json
import time

import joblib
import numpy as np
import pandas as pd

from src.db import PROJECT_ROOT
from src.modeling import (
    DAY_AHEAD_FEATURES,
    GBM_FEATURES,
    POISSON_FEATURES,
    TARGET,
    TRAIN_END,
    VAL_END,
    StationHourOfWeekMean,
    build_gbm,
    build_poisson,
    load_features,
    regression_metrics,
)

REPORT_DIR = PROJECT_ROOT / "reports" / "phase4"
MODELS_DIR = PROJECT_ROOT / "models"

# Tree counts chosen on August validation curves
GBM_FULL_TREES = 450
GBM_DAYAHEAD_TREES = 100

APP_DEFAULT = "gbm_full_poisson"


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    df = load_features()
    fit = df[df["split"].isin(["train", "val"])].reset_index(drop=True)
    fit_lag = fit[fit["lag_168h"].notna()]
    n_test_all = int((df["split"] == "test").sum())
    test = df[(df["split"] == "test") & df["lag_168h"].notna()].reset_index(drop=True)
    del df
    y = test[TARGET].to_numpy()
    print(f"fit rows (Jan–Aug): {len(fit):,} | test rows scored (Sep): {len(test):,} "
          f"(dropped {n_test_all - len(test):,} cold-start rows)")

    preds: dict[str, np.ndarray] = {}
    meta: dict[str, dict] = {}

    preds["weekly_naive"] = test["lag_168h"].to_numpy()
    meta["weekly_naive"] = {"horizon": "1 week", "family": "baseline"}

    hist = StationHourOfWeekMean().fit(fit)
    preds["station_how_mean"] = hist.predict(test)
    meta["station_how_mean"] = {"horizon": "any", "family": "baseline"}
    joblib.dump(hist, MODELS_DIR / "station_how_mean.joblib")

    poisson_specs = [
        ("poisson_interact", "interact", POISSON_FEATURES, "poisson_comparison"),
        ("poisson_station", "station", [*POISSON_FEATURES, "start_station_id"], "poisson"),
    ]
    for name, variant, features, family in poisson_specs:
        t0 = time.time()
        model = build_poisson(variant).fit(fit_lag[features], fit_lag[TARGET])
        preds[name] = model.predict(test[features])
        meta[name] = {"horizon": "1 week", "family": family, "features": features,
                      "fit_seconds": round(time.time() - t0, 1)}
        joblib.dump(model, MODELS_DIR / f"{name}.joblib")
        print(f"fitted {name} ({meta[name]['fit_seconds']}s)")

    gbm_specs = [
        ("gbm_dayahead_poisson", DAY_AHEAD_FEATURES, GBM_DAYAHEAD_TREES, "1 day"),
        ("gbm_full_poisson", GBM_FEATURES, GBM_FULL_TREES, "1 hour"),
    ]
    for name, features, trees, horizon in gbm_specs:
        t0 = time.time()
        model = build_gbm(loss="poisson", max_iter=trees).fit(fit[features], fit[TARGET])
        preds[name] = model.predict(test[features])
        meta[name] = {"horizon": horizon, "family": "gbm", "features": features, "trees": trees,
                      "fit_seconds": round(time.time() - t0, 1)}
        joblib.dump(model, MODELS_DIR / f"{name}.joblib")
        print(f"fitted {name} ({meta[name]['fit_seconds']}s)")

    weekly_mae = regression_metrics(y, preds["weekly_naive"])["mae"]
    hist_mae = regression_metrics(y, preds["station_how_mean"])["mae"]
    rows = []
    for name, pred in preds.items():
        m = regression_metrics(y, pred)
        rows.append({
            "model": name,
            "family": meta[name]["family"],
            "horizon": meta[name]["horizon"],
            **m,
            "mae_vs_weekly_pct": round(100 * (weekly_mae - m["mae"]) / weekly_mae, 2),
            "beats_weekly_naive": m["mae"] < weekly_mae,
            "mae_vs_station_how_mean_pct": round(100 * (hist_mae - m["mae"]) / hist_mae, 2),
            "beats_station_how_mean": m["mae"] < hist_mae,
        })
        meta[name]["test_metrics"] = m
    results = pd.DataFrame(rows)
    results.to_csv(REPORT_DIR / "test_results.csv", index=False)

    # Per-station view: 5 busiest stations in September + 5 random ones
    station_totals = test.groupby("start_station_id")[TARGET].sum().sort_values(ascending=False)
    busiest = station_totals.index[:5].tolist()
    rng = np.random.default_rng(0)
    others = station_totals.index[5:].to_numpy()
    sampled = rng.choice(others, size=5, replace=False).tolist()
    per_station = []
    for sid in busiest + sampled:
        mask = (test["start_station_id"] == sid).to_numpy()
        row = {"start_station_id": sid, "group": "busiest" if sid in busiest else "random",
               "sep_departures": int(station_totals[sid]),
               "mean_per_hour": float(y[mask].mean())}
        for name, pred in preds.items():
            row[f"mae_{name}"] = float(np.abs(y[mask] - pred[mask]).mean())
        per_station.append(row)
    pd.DataFrame(per_station).to_csv(REPORT_DIR / "test_per_station.csv", index=False)

    with open(MODELS_DIR / "phase4_metadata.json", "w", encoding="utf-8") as f:
        json.dump({
            "split": {"train": f"< {TRAIN_END.date()}", "val": f"{TRAIN_END.date()} – {VAL_END.date()}",
                      "test": f">= {VAL_END.date()}", "final_fit": "train + val (Jan–Aug)"},
            "test_rows": len(test),
            "app_default": APP_DEFAULT,
            "official_poisson": "poisson_station",
            "models": meta,
        }, f, indent=2, default=str)

    pd.set_option("display.width", 200)
    cols = ["model", "horizon", "mae", "rmse", "poisson_deviance", "mean_pred",
            "mae_vs_weekly_pct", "mae_vs_station_how_mean_pct"]
    print("\nSeptember test results (mean actual = {:.3f}):".format(y.mean()))
    print(results[cols].round(4).to_string(index=False))
    print("\nPer-station MAE (busiest + random):")
    print(pd.DataFrame(per_station).round(3).to_string(index=False))
    print(f"\nwrote {REPORT_DIR / 'test_results.csv'}, {REPORT_DIR / 'test_per_station.csv'}")
    print(f"saved models + metadata under {MODELS_DIR}")


if __name__ == "__main__":
    main()
