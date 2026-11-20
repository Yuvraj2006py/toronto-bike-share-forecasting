"""Phase 6 API: bundled context + predictions, station detail, error states.

Uses a tiny synthetic data directory so tests never depend on data/processed/.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.app_data import TORONTO

HOURS = pd.date_range("2024-09-23 00:00", "2024-09-24 23:00", freq="h")  # Mon + Tue


def _write_fixture(data_dir: Path) -> None:
    stations = pd.DataFrame(
        {
            "station_id": [7006, 7629],
            "name": ["Bay St / College St (East Side)", "Lundy Ave / Etienne Brule Park"],
            "lat": [43.6608, 43.6515],
            "lon": [-79.3856, -79.4930],
            "capacity": [31, 15],
        }
    )
    stations.to_parquet(data_dir / "stations_geo.parquet", index=False)

    rows = []
    for sid in (7006, 7629, 9999):  # 9999 has no location -> never on the map
        for i, ts in enumerate(HOURS):
            rows.append(
                {
                    "station_id": sid,
                    "hour_ts": ts,
                    "actual": float(i % 5),
                    "weekly_naive": float((i + 1) % 5),
                    "gbm_pred": 1.5 + 0.1 * i,
                    "poisson_pred": 1.2,
                    "hour_of_day": ts.hour,
                    "day_of_week": ts.dayofweek,
                    "is_weekend": 0.0,
                    "is_holiday": 0.0,
                    # weather varies by hour but is identical across stations
                    "temp_c": 10.0 + ts.hour,
                    "precip_mm": 1.5 if ts.hour == 8 else 0.0,
                    "wind_speed_kmh": 12.0,
                    "lag_1h": 5.0,
                    "lag_24h": 3.0,
                    "lag_168h": 16.0,
                    "roll_mean_24h": 6.25,
                }
            )
    pd.DataFrame(rows).to_parquet(data_dir / "app_hourly_preds_2024_09.parquet", index=False)
    (data_dir / "app_meta.json").write_text(
        json.dumps({"stations_missing_geo": 1, "mae_check": {}}), encoding="utf-8"
    )


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    _write_fixture(tmp_path)
    # Monday 08:20 Toronto -> latest Monday 08:00 in fixture = 2024-09-23 08:00
    app = create_app(data_dir=tmp_path, clock=lambda: datetime(2026, 11, 16, 8, 20, tzinfo=TORONTO))
    with TestClient(app) as c:
        yield c


def test_health_reports_data_loaded(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["data_loaded"] is True


def test_map_default_hour_comes_from_toronto_clock(client: TestClient):
    r = client.get("/api/map")
    assert r.status_code == 200
    body = r.json()
    assert body["context"]["hour_ts"] == "2024-09-23T08:00:00"
    assert body["context"]["weekday"] == "Monday"
    assert body["demo"]["from_clock"] is True
    assert body["demo"]["clock_local"].startswith("2026-11-16T08:20")


def test_map_only_includes_stations_with_locations(client: TestClient):
    body = client.get("/api/map").json()
    ids = sorted(f["properties"]["station_id"] for f in body["features"]["features"])
    assert ids == [7006, 7629]
    first = body["features"]["features"][0]
    assert first["geometry"]["type"] == "Point"
    lon, lat = first["geometry"]["coordinates"]
    assert -80 < lon < -79 and 43 < lat < 44
    assert body["stats"]["stations_on_map"] == 2
    assert body["stats"]["stations_missing_geo"] == 1


def test_map_hour_param_returns_that_hours_weather(client: TestClient):
    for hour in ("2024-09-23T08:00:00", "2024-09-24T15:00:00"):
        body = client.get("/api/map", params={"hour": hour}).json()
        ts = pd.Timestamp(hour)
        assert body["context"]["hour_ts"] == hour
        assert body["context"]["temp_c"] == pytest.approx(10.0 + ts.hour)
        assert body["context"]["precip_mm"] == pytest.approx(1.5 if ts.hour == 8 else 0.0)
        assert body["demo"]["from_clock"] is False


def test_map_stats_sum_mapped_stations(client: TestClient):
    body = client.get("/api/map", params={"hour": "2024-09-23T08:00:00"}).json()
    preds = [f["properties"]["gbm_pred"] for f in body["features"]["features"]]
    assert body["stats"]["predicted_total"] == pytest.approx(sum(preds), rel=1e-4)


def test_map_unknown_hour_is_404_with_message(client: TestClient):
    r = client.get("/api/map", params={"hour": "2023-01-01T00:00:00"})
    assert r.status_code == 404
    assert "outside" in r.json()["detail"].lower()


def test_station_detail_bundles_context_lags_and_series(client: TestClient):
    r = client.get("/api/station/7006", params={"hour": "2024-09-23T08:00:00"})
    assert r.status_code == 200
    body = r.json()
    assert body["station"]["name"].startswith("Bay St")
    assert body["context"]["hour_ts"] == "2024-09-23T08:00:00"
    assert body["context"]["precip_mm"] == pytest.approx(1.5)
    assert body["lags"] == {"lag_1h": 5.0, "lag_24h": 3.0, "lag_168h": 16.0, "roll_mean_24h": 6.25}
    assert set(body["predictions"]) == {"actual", "weekly_naive", "gbm_pred", "poisson_pred"}
    hours = [p["hour_ts"] for p in body["series"]]
    assert hours == sorted(hours)
    assert "2024-09-23T08:00:00" in hours
    assert len(body["series"]) <= 24


def test_station_without_location_is_404(client: TestClient):
    r = client.get("/api/station/9999", params={"hour": "2024-09-23T08:00:00"})
    assert r.status_code == 404


def test_missing_data_dir_returns_503(tmp_path: Path):
    app = create_app(data_dir=tmp_path / "nope")
    with TestClient(app) as c:
        assert c.get("/api/health").json()["data_loaded"] is False
        r = c.get("/api/map")
        assert r.status_code == 503
        assert "phase6_prep" in r.json()["detail"]


def test_meta_lists_hour_range_and_attribution(client: TestClient):
    body = client.get("/api/meta").json()
    assert body["hour_min"] == "2024-09-23T00:00:00"
    assert body["hour_max"] == "2024-09-24T23:00:00"
    assert len(body["attribution"]) >= 3
    assert np.isfinite(body["pred_scale_max"])
