import numpy as np
import pandas as pd
import pytest

from src.modeling import (
    DAY_AHEAD_FEATURES,
    GBM_FEATURES,
    POISSON_FEATURES,
    StationHourOfWeekMean,
    assign_split,
    regression_metrics,
)


def test_split_boundaries_are_exact():
    ts = pd.Series(
        pd.to_datetime(
            [
                "2024-01-01 00:00",
                "2024-07-31 23:00",
                "2024-08-01 00:00",
                "2024-08-31 23:00",
                "2024-09-01 00:00",
                "2024-09-30 23:00",
            ]
        )
    )
    assert assign_split(ts).tolist() == ["train", "train", "val", "val", "test", "test"]


def test_day_ahead_features_never_use_last_hour():
    # lag_1h and every rolling window include t-1, so they need a 1-hour horizon
    for col in ("lag_1h", "roll_mean_24h", "roll_std_24h", "roll_mean_168h", "roll_std_168h"):
        assert col not in DAY_AHEAD_FEATURES
    assert set(DAY_AHEAD_FEATURES) < set(GBM_FEATURES)
    assert set(POISSON_FEATURES) < set(GBM_FEATURES)
    assert "departures" not in GBM_FEATURES


def test_regression_metrics_known_values():
    y = np.array([0.0, 2.0, 4.0])
    pred = np.array([1.0, 2.0, 2.0])
    m = regression_metrics(y, pred)
    assert m["mae"] == pytest.approx(1.0)
    assert m["rmse"] == pytest.approx(np.sqrt(5 / 3))
    assert m["n"] == 3


def test_regression_metrics_tolerates_zero_predictions():
    # Poisson deviance is undefined at pred=0; weekly naive predicts 0 a lot
    m = regression_metrics(np.array([0.0, 1.0]), np.array([0.0, 0.0]))
    assert np.isfinite(m["poisson_deviance"])


def test_station_how_mean_learns_from_train_only_and_falls_back():
    train = pd.DataFrame(
        {
            "start_station_id": [1, 1, 1, 2],
            "hour_ts": pd.to_datetime(
                ["2024-01-01 08:00", "2024-01-08 08:00", "2024-01-01 09:00", "2024-01-01 08:00"]
            ),
            "departures": [2, 4, 10, 6],
        }
    )
    model = StationHourOfWeekMean().fit(train)
    val = pd.DataFrame(
        {
            # station 1 Monday 08:00 seen -> mean(2,4)=3
            # station 3 never seen -> global Monday 08:00 mean over train = mean(2,4,6)=4
            "start_station_id": [1, 3],
            "hour_ts": pd.to_datetime(["2024-08-05 08:00", "2024-08-05 08:00"]),
        }
    )
    assert model.predict(val).tolist() == pytest.approx([3.0, 4.0])
