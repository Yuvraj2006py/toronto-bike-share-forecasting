"""Unit tests for Phase 5 interpretation helpers (no model artifacts required)."""

import numpy as np
import pandas as pd
import pytest

from src.interpretation import (
    case_shap_rows,
    group_poisson_feature,
    highlight_signed,
    humanize_poisson_feature,
    poisson_multiplier,
    rank_mean_abs_shap,
    tidy_poisson_coefficients,
)


def test_group_poisson_feature_buckets():
    assert group_poisson_feature("offday_hour__offday_hour_8") == "hour_pattern"
    assert group_poisson_feature("dow__day_of_week_0") == "day_of_week"
    assert group_poisson_feature("lag__lag_168h") == "weekly_lag"
    assert group_poisson_feature("num__temp_c") == "weather"
    assert group_poisson_feature("num__precip_mm") == "weather"
    assert group_poisson_feature("num__is_holiday") == "calendar"
    assert group_poisson_feature("station__start_station_id_7006") == "station"


def test_humanize_day_of_week_uses_sunday_zero():
    assert humanize_poisson_feature("dow__day_of_week_0") == "day=Sun"
    assert humanize_poisson_feature("dow__day_of_week_1") == "day=Mon"
    assert humanize_poisson_feature("dow__day_of_week_6") == "day=Sat"


def test_poisson_multiplier_is_exp_coef():
    assert poisson_multiplier(0.0) == pytest.approx(1.0)
    assert poisson_multiplier(np.log(2.0)) == pytest.approx(2.0)


def test_tidy_poisson_coefficients_sorted_by_abs():
    names = np.array(["num__temp_c", "lag__lag_168h", "station__start_station_id_1"])
    coef = np.array([0.1, -0.5, 2.0])
    out = tidy_poisson_coefficients(names, coef)
    assert list(out.columns) == ["feature", "group", "coefficient", "multiplier"]
    assert out.iloc[0]["feature"] == "station__start_station_id_1"
    assert out.iloc[1]["feature"] == "lag__lag_168h"
    assert out.loc[out["feature"] == "lag__lag_168h", "multiplier"].iloc[0] == pytest.approx(
        np.exp(-0.5)
    )


def test_rank_mean_abs_shap():
    # Two rows, three features: f1 dominates mean |shap|
    values = np.array([[1.0, 0.0, -0.5], [3.0, 0.2, 0.5]])
    out = rank_mean_abs_shap(values, ["f1", "f2", "f3"])
    assert list(out["feature"]) == ["f1", "f3", "f2"]
    assert out.iloc[0]["mean_abs_shap"] == pytest.approx(2.0)


def test_case_shap_rows_sorted_by_abs_contribution():
    values = np.array([0.2, -1.5, 0.8])
    feature_values = np.array([8.0, 16.0, 18.0])
    out = case_shap_rows(values, ["hour", "lag_168h", "temp_c"], feature_values, top_n=2)
    assert len(out) == 2
    assert out.iloc[0]["feature"] == "lag_168h"
    assert out.iloc[0]["shap"] == pytest.approx(-1.5)
    assert out.iloc[0]["feature_value"] == pytest.approx(16.0)


def test_highlight_signed_keeps_both_tails():
    frame = pd.DataFrame(
        {"feature": ["a", "b", "c", "d"], "coefficient": [2.0, -3.0, 0.1, -0.2]}
    )
    out = highlight_signed(frame, n=1)
    assert set(out["feature"]) == {"a", "b"}
