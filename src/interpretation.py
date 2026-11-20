"""Phase 5 helpers: turn fitted models into readable coefficient / SHAP tables.

Kept free of I/O so unit tests don't need DuckDB or joblib artifacts.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

_STATION_RE = re.compile(r"station__start_station_id_(.+)$")
_HOUR_RE = re.compile(r"offday_hour__offday_hour_(\d+)$")
_DOW_RE = re.compile(r"dow__day_of_week_(\d+)$")


def group_poisson_feature(name: str) -> str:
    """Bucket a ColumnTransformer output name into a narrative group."""
    if name.startswith("offday_hour__"):
        return "hour_pattern"
    if name.startswith("dow__"):
        return "day_of_week"
    if name.startswith("lag__"):
        return "weekly_lag"
    if name.startswith("station__"):
        return "station"
    if name in ("num__temp_c", "num__precip_mm") or name.endswith("temp_c") or name.endswith(
        "precip_mm"
    ):
        return "weather"
    if name.startswith("num__"):
        return "calendar"
    return "other"


def poisson_multiplier(coefficient: float) -> float:
    """Poisson GLM uses a log link: exp(coef) multiplies expected departures."""
    return float(np.exp(coefficient))


def tidy_poisson_coefficients(feature_names: np.ndarray, coefficients: np.ndarray) -> pd.DataFrame:
    """One row per GLM feature, sorted by |coefficient| descending."""
    frame = pd.DataFrame(
        {
            "feature": np.asarray(feature_names, dtype=object),
            "coefficient": np.asarray(coefficients, dtype="float64"),
        }
    )
    frame["group"] = frame["feature"].map(group_poisson_feature)
    frame["multiplier"] = frame["coefficient"].map(poisson_multiplier)
    frame = frame.sort_values("coefficient", key=np.abs, ascending=False).reset_index(drop=True)
    return frame[["feature", "group", "coefficient", "multiplier"]]


def humanize_poisson_feature(name: str) -> str:
    """Short label for tables and plots."""
    m = _STATION_RE.search(name)
    if m:
        return f"station {m.group(1)}"
    m = _HOUR_RE.search(name)
    if m:
        hour = int(m.group(1))
        if hour >= 24:
            return f"weekend/holiday hour {hour - 24:02d}:00"
        return f"weekday hour {hour:02d}:00"
    m = _DOW_RE.search(name)
    if m:
        # features_2024.day_of_week is DuckDB dayofweek: Sunday=0.
        labels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        idx = int(m.group(1))
        return f"day={labels[idx]}" if 0 <= idx < 7 else name
    mapping = {
        "lag__lag_168h": "log1p(weekly lag)",
        "num__temp_c": "temperature (°C)",
        "num__precip_mm": "precipitation (mm)",
        "num__is_holiday": "holiday",
    }
    return mapping.get(name, name)


def rank_mean_abs_shap(shap_values: np.ndarray, feature_names: list[str]) -> pd.DataFrame:
    """Global importance: mean |SHAP| per feature, largest first."""
    values = np.asarray(shap_values, dtype="float64")
    if values.ndim != 2:
        raise ValueError(f"expected 2-D shap matrix, got shape {values.shape}")
    mean_abs = np.abs(values).mean(axis=0)
    frame = pd.DataFrame({"feature": feature_names, "mean_abs_shap": mean_abs})
    return frame.sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)


def highlight_signed(frame: pd.DataFrame, value_col: str = "coefficient", n: int = 3) -> pd.DataFrame:
    """Top n positive and top n negative rows by a signed value column."""
    pos = frame.nlargest(n, value_col)
    neg = frame.nsmallest(n, value_col)
    out = pd.concat([pos, neg], ignore_index=True)
    return out.drop_duplicates(subset=frame.columns.intersection(["feature", "label"]).tolist())


def case_shap_rows(
    shap_row: np.ndarray,
    feature_names: list[str],
    feature_values: np.ndarray,
    top_n: int = 8,
) -> pd.DataFrame:
    """Local explanation for one station-hour: top features by |SHAP|."""
    shap_row = np.asarray(shap_row, dtype="float64")
    feature_values = np.asarray(feature_values, dtype="float64")
    frame = pd.DataFrame(
        {
            "feature": feature_names,
            "feature_value": feature_values,
            "shap": shap_row,
        }
    )
    frame["abs_shap"] = frame["shap"].abs()
    frame = frame.sort_values("abs_shap", ascending=False).head(top_n).reset_index(drop=True)
    return frame.drop(columns=["abs_shap"])
