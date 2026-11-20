"""Phase 4 validation experiments: fit on Jan–Jul, score on August only.

September (test) is never loaded into a model here.

Run from project root (one group at a time, results append to the CSV):
    python -m src.phase4_experiments baselines
    python -m src.phase4_experiments poisson
    python -m src.phase4_experiments poisson_station
    python -m src.phase4_experiments gbm
"""

from __future__ import annotations

import sys
import time
import warnings

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning

from src.db import PROJECT_ROOT
from src.modeling import (
    DAY_AHEAD_FEATURES,
    GBM_FEATURES,
    POISSON_FEATURES,
    TARGET,
    StationHourOfWeekMean,
    build_gbm,
    build_poisson,
    load_features,
    regression_metrics,
)

REPORT_DIR = PROJECT_ROOT / "reports" / "phase4"
RESULTS_CSV = REPORT_DIR / "validation_results.csv"


def load_train_val() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = load_features()
    train = df[df["split"] == "train"].reset_index(drop=True)
    # Common scoring rows: weekly naive must be defined so every model sees the same hours
    val = df[(df["split"] == "val") & df["lag_168h"].notna()].reset_index(drop=True)
    n_val_all = int((df["split"] == "val").sum())
    print(f"train rows: {len(train):,} | val rows scored: {len(val):,} "
          f"(dropped {n_val_all - len(val):,} cold-start rows without lag_168h)")
    return train, val


def record(rows: list[dict], name: str, family: str, horizon: str, y, pred,
           fit_seconds: float = 0.0, notes: str = "") -> None:
    m = regression_metrics(y, pred)
    rows.append({"model": name, "family": family, "horizon": horizon, **m,
                 "fit_seconds": round(fit_seconds, 1), "notes": notes})
    print(f"  {name:<28} MAE {m['mae']:.4f}  RMSE {m['rmse']:.4f}  "
          f"dev {m['poisson_deviance']:.4f}  mean_pred {m['mean_pred']:.3f}  ({fit_seconds:.0f}s)")


def run_baselines(train: pd.DataFrame, val: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    y = val[TARGET].to_numpy()
    print("\nBaselines:")
    record(rows, "zero", "baseline", "any", y, np.zeros(len(val)),
           notes="always predict 0 — floor any model must clear")
    record(rows, "weekly_naive", "baseline", "1 week", y, val["lag_168h"].to_numpy(),
           notes="same station, same hour last week (plan baseline)")
    daily = val["lag_24h"].fillna(val["lag_168h"]).to_numpy()
    record(rows, "daily_naive", "baseline", "1 day", y, daily,
           notes="same station, same hour yesterday")
    t0 = time.time()
    hist = StationHourOfWeekMean().fit(train)
    record(rows, "station_how_mean", "baseline", "any", y, hist.predict(val), time.time() - t0,
           notes="train-period mean per station x hour-of-week")
    return rows


def _fit_poisson_variants(train: pd.DataFrame, val: pd.DataFrame, variants: list[str],
                          features: list[str], family: str) -> list[dict]:
    rows: list[dict] = []
    tr = train[train["lag_168h"].notna()]
    y = val[TARGET].to_numpy()
    print(f"\nPoisson GLM (train rows with lag_168h: {len(tr):,}):")
    for variant in variants:
        model = build_poisson(variant)
        t0 = time.time()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ConvergenceWarning)
            model.fit(tr[features], tr[TARGET])
        converged = not any(issubclass(w.category, ConvergenceWarning) for w in caught)
        n_iter = model.named_steps["glm"].n_iter_
        record(rows, f"poisson_{variant}", family, "1 week", y,
               model.predict(val[features]), time.time() - t0,
               notes=f"lbfgs iters={n_iter}, converged={converged}")
    return rows


def run_poisson(train: pd.DataFrame, val: pd.DataFrame) -> list[dict]:
    return _fit_poisson_variants(train, val, ["numeric", "onehot", "onehot_log", "interact"],
                                 POISSON_FEATURES, "poisson")


def run_poisson_station(train: pd.DataFrame, val: pd.DataFrame) -> list[dict]:
    return _fit_poisson_variants(train, val, ["station"],
                                 [*POISSON_FEATURES, "start_station_id"], "poisson_exploratory")


def run_gbm(train: pd.DataFrame, val: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    y = val[TARGET].to_numpy()
    configs = [
        ("gbm_full_squared", GBM_FEATURES, "squared_error", "1 hour"),
        ("gbm_full_poisson", GBM_FEATURES, "poisson", "1 hour"),
        ("gbm_dayahead_poisson", DAY_AHEAD_FEATURES, "poisson", "1 day"),
    ]
    curves = []
    print(f"\nGradient boosting (train rows: {len(train):,}):")
    for name, features, loss, horizon in configs:
        model = build_gbm(loss=loss, max_iter=300)
        t0 = time.time()
        model.fit(train[features], train[TARGET])
        fit_s = time.time() - t0
        # Validation curve: is 300 trees too few (still improving) or too many (overfitting)?
        for i, staged in enumerate(model.staged_predict(val[features]), start=1):
            if i % 25 == 0 or i == 1:
                m = regression_metrics(y, staged)
                curves.append({"model": name, "iteration": i, "mae": m["mae"],
                               "poisson_deviance": m["poisson_deviance"]})
        record(rows, name, "gbm", horizon, y, model.predict(val[features]), fit_s,
               notes=f"loss={loss}, {len(features)} features, 300 trees, lr=0.1")
    pd.DataFrame(curves).to_csv(REPORT_DIR / "gbm_validation_curves.csv", index=False)
    print(f"  wrote {REPORT_DIR / 'gbm_validation_curves.csv'}")
    return rows


def run_gbm_tune(train: pd.DataFrame, val: pd.DataFrame) -> list[dict]:
    """Longer run for the 1-hour GBM (its 300-tree curve was still falling)."""
    rows: list[dict] = []
    y = val[TARGET].to_numpy()
    curves = []
    model = build_gbm(loss="poisson", max_iter=800)
    t0 = time.time()
    model.fit(train[GBM_FEATURES], train[TARGET])
    fit_s = time.time() - t0
    for i, staged in enumerate(model.staged_predict(val[GBM_FEATURES]), start=1):
        if i % 50 == 0:
            m = regression_metrics(y, staged)
            curves.append({"model": "gbm_full_poisson_800", "iteration": i, "mae": m["mae"],
                           "poisson_deviance": m["poisson_deviance"], "rmse": m["rmse"]})
            print(f"  iter {i:>3}: MAE {m['mae']:.4f}  dev {m['poisson_deviance']:.4f}")
    pd.DataFrame(curves).to_csv(REPORT_DIR / "gbm_full_tuning_curve.csv", index=False)
    record(rows, "gbm_full_poisson_800", "gbm", "1 hour", y,
           model.predict(val[GBM_FEATURES]), fit_s, notes="loss=poisson, 15 features, 800 trees")
    return rows


GROUPS = {
    "baselines": run_baselines,
    "poisson": run_poisson,
    "poisson_station": run_poisson_station,
    "gbm": run_gbm,
    "gbm_tune": run_gbm_tune,
}


def main() -> None:
    group = sys.argv[1] if len(sys.argv) > 1 else ""
    if group not in GROUPS:
        raise SystemExit(f"usage: python -m src.phase4_experiments {{{'|'.join(GROUPS)}}}")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    train, val = load_train_val()
    rows = GROUPS[group](train, val)

    new = pd.DataFrame(rows)
    if RESULTS_CSV.exists():
        old = pd.read_csv(RESULTS_CSV)
        new = pd.concat([old[~old["model"].isin(new["model"])], new], ignore_index=True)
    new.to_csv(RESULTS_CSV, index=False)
    print(f"\nwrote {RESULTS_CSV}")


if __name__ == "__main__":
    main()
