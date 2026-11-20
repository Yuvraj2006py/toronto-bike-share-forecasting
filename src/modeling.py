"""Shared Phase 4 pieces: time split, feature sets, metrics, baselines, model builders.

Every experiment and the final evaluation import from here so the split and
metrics can't drift between scripts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import mean_absolute_error, mean_poisson_deviance, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from src.db import get_connection

# Locked split: train Jan–Jul, validate Aug, test Sep (test scored once, at the end)
TRAIN_END = pd.Timestamp("2024-08-01")
VAL_END = pd.Timestamp("2024-09-01")

TARGET = "departures"
KEYS = ["start_station_id", "hour_ts"]

POISSON_FEATURES = [
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "is_holiday",
    "lag_168h",
    "temp_c",
    "precip_mm",
]

GBM_FEATURES = [
    "hour_of_day",
    "day_of_week",
    "month",
    "is_weekend",
    "is_holiday",
    "lag_1h",
    "lag_24h",
    "lag_168h",
    "roll_mean_24h",
    "roll_std_24h",
    "roll_mean_168h",
    "roll_std_168h",
    "temp_c",
    "precip_mm",
    "wind_speed_kmh",
]

# lag_1h and every rolling window include hour t-1, so a model using them can
# only forecast one hour ahead. This subset is usable 24 hours ahead.
DAY_AHEAD_FEATURES = [
    "hour_of_day",
    "day_of_week",
    "month",
    "is_weekend",
    "is_holiday",
    "lag_24h",
    "lag_168h",
    "temp_c",
    "precip_mm",
    "wind_speed_kmh",
]

# Poisson deviance is undefined at a prediction of exactly 0
MIN_PRED = 1e-6


def load_features() -> pd.DataFrame:
    con = get_connection(read_only=True)
    try:
        df = con.execute("SELECT * FROM features_2024").fetchdf()
    finally:
        con.close()
    float_cols = [c for c in GBM_FEATURES if c not in ("hour_of_day", "day_of_week", "month")]
    df[float_cols] = df[float_cols].astype("float32")
    df[TARGET] = df[TARGET].astype("float32")
    df["split"] = assign_split(df["hour_ts"])
    return df


def assign_split(hour_ts: pd.Series) -> pd.Series:
    split = np.where(hour_ts < TRAIN_END, "train", np.where(hour_ts < VAL_END, "val", "test"))
    return pd.Series(split, index=hour_ts.index)


def regression_metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    y = np.asarray(y, dtype="float64")
    pred = np.asarray(pred, dtype="float64")
    return {
        "n": int(len(y)),
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(np.sqrt(mean_squared_error(y, pred))),
        "poisson_deviance": float(mean_poisson_deviance(y, np.clip(pred, MIN_PRED, None))),
        "mean_y": float(y.mean()),
        "mean_pred": float(pred.mean()),
    }


def hour_of_week(hour_ts: pd.Series) -> pd.Series:
    """0 = Monday 00:00 … 167 = Sunday 23:00."""
    return hour_ts.dt.dayofweek * 24 + hour_ts.dt.hour


class StationHourOfWeekMean:
    """Historical-average baseline: mean departures per (station, hour-of-week) on train.

    Stations with no train history fall back to the all-station hour-of-week mean.
    """

    def fit(self, train: pd.DataFrame) -> "StationHourOfWeekMean":
        how = hour_of_week(train["hour_ts"])
        frame = pd.DataFrame(
            {"start_station_id": train["start_station_id"].to_numpy(), "how": how.to_numpy(),
             "y": train[TARGET].to_numpy()}
        )
        self.station_how_ = frame.groupby(["start_station_id", "how"])["y"].mean().rename("pred")
        self.global_how_ = frame.groupby("how")["y"].mean().rename("fallback")
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        keys = pd.DataFrame(
            {"start_station_id": df["start_station_id"].to_numpy(),
             "how": hour_of_week(df["hour_ts"]).to_numpy()}
        )
        out = keys.join(self.station_how_, on=["start_station_id", "how"]).join(
            self.global_how_, on="how"
        )
        return out["pred"].fillna(out["fallback"]).to_numpy(dtype="float64")


def _offday_hour(X: pd.DataFrame) -> pd.DataFrame:
    """Hour-of-day crossed with weekend/holiday: lets commute peaks exist only on workdays."""
    offday = ((X["is_weekend"] == 1) | (X["is_holiday"] == 1)).astype(int)
    return pd.DataFrame({"offday_hour": X["hour_of_day"].astype(int) + 24 * offday})


def _log1p(X):
    # DataFrame + float32 can trip numpy's ufunc path; cast explicitly.
    return np.log1p(np.asarray(X, dtype="float64"))


def build_poisson(variant: str, alpha: float = 1e-4, max_iter: int = 1000) -> Pipeline:
    """Poisson GLM variants over the locked Poisson feature set.

    numeric  : every feature enters linearly (hour 0–23 as a single number)
    onehot   : hour and weekday as categories; lag_168h raw
    onehot_log : as onehot, but log1p(lag_168h) — matches the GLM's log link
    interact : onehot_log + hour × off-day categories (weekday vs weekend/holiday shapes)
    station  : interact + one-hot start_station_id (exploratory: outside the locked set;
               expects POISSON_FEATURES + start_station_id columns)
    """
    weather = ["temp_c", "precip_mm"]
    interact_parts = [
        ("offday_hour",
         Pipeline([("cross", FunctionTransformer(_offday_hour)),
                   ("oh", OneHotEncoder(handle_unknown="ignore"))]),
         ["hour_of_day", "is_weekend", "is_holiday"]),
        ("dow", OneHotEncoder(handle_unknown="ignore"), ["day_of_week"]),
        ("lag", Pipeline([("log", FunctionTransformer(_log1p)), ("sc", StandardScaler())]),
         ["lag_168h"]),
        ("num", StandardScaler(), ["is_holiday", *weather]),
    ]
    if variant == "numeric":
        pre = ColumnTransformer([("num", StandardScaler(), POISSON_FEATURES)])
    elif variant == "onehot":
        pre = ColumnTransformer(
            [
                ("cat", OneHotEncoder(handle_unknown="ignore"), ["hour_of_day", "day_of_week"]),
                ("num", StandardScaler(), ["is_weekend", "is_holiday", "lag_168h", *weather]),
            ]
        )
    elif variant == "onehot_log":
        pre = ColumnTransformer(
            [
                ("cat", OneHotEncoder(handle_unknown="ignore"), ["hour_of_day", "day_of_week"]),
                ("lag", Pipeline([("log", FunctionTransformer(_log1p)), ("sc", StandardScaler())]),
                 ["lag_168h"]),
                ("num", StandardScaler(), ["is_weekend", "is_holiday", *weather]),
            ]
        )
    elif variant == "interact":
        pre = ColumnTransformer(interact_parts)
    elif variant == "station":
        pre = ColumnTransformer(
            [*interact_parts,
             ("station", OneHotEncoder(handle_unknown="ignore"), ["start_station_id"])]
        )
    else:
        raise ValueError(f"unknown Poisson variant: {variant}")
    return Pipeline([("pre", pre), ("glm", PoissonRegressor(alpha=alpha, max_iter=max_iter))])


def build_gbm(loss: str = "poisson", max_iter: int = 300, learning_rate: float = 0.1,
              max_leaf_nodes: int = 63, random_state: int = 0) -> HistGradientBoostingRegressor:
    # Built-in early stopping holds out a *random* slice of train, which leaks
    # future hours into validation — iteration count is tuned on August instead.
    return HistGradientBoostingRegressor(
        loss=loss,
        max_iter=max_iter,
        learning_rate=learning_rate,
        max_leaf_nodes=max_leaf_nodes,
        min_samples_leaf=100,
        early_stopping=False,
        random_state=random_state,
    )
