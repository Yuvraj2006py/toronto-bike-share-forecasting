"""In-memory store behind the Phase 6 API.

Loads the prep outputs once, indexes rows by hour, and builds the payloads the map
and station panel need. Every payload for an hour takes its weather and calendar
from that hour's rows, so the context strip can never drift from the predictions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.app_data import build_hour_context

PREDS_FILE = "app_hourly_preds_2024_09.parquet"
STATIONS_FILE = "stations_geo.parquet"
META_FILE = "app_meta.json"

PREDICTION_COLUMNS = ["actual", "weekly_naive", "gbm_pred", "poisson_pred"]
LAG_COLUMNS = ["lag_1h", "lag_24h", "lag_168h", "roll_mean_24h"]
SERIES_HOURS = 24

ATTRIBUTION = [
    {"label": "Ridership: City of Toronto, Open Government Licence – Toronto",
     "url": "https://open.toronto.ca/open-data-licence/"},
    {"label": "Weather: Open-Meteo (observed, historical)", "url": "https://open-meteo.com/"},
    {"label": "Stations: Bike Share Toronto GBFS",
     "url": "https://tor.publicbikesystem.net/ube/gbfs/v1/"},
    {"label": "Basemap: OpenFreeMap, © OpenStreetMap contributors",
     "url": "https://openfreemap.org/"},
]


class DataUnavailable(RuntimeError):
    """Prep outputs are missing; the API answers 503 instead of a blank map."""


class HourNotFound(LookupError):
    pass


class StationNotFound(LookupError):
    pass


def _round(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    f = float(value)
    return None if np.isnan(f) else round(f, digits)


@dataclass
class AppStore:
    preds: pd.DataFrame
    stations: pd.DataFrame
    meta: dict[str, Any]

    @classmethod
    def load(cls, data_dir: Path) -> "AppStore":
        preds_path = data_dir / PREDS_FILE
        stations_path = data_dir / STATIONS_FILE
        missing = [p.name for p in (preds_path, stations_path) if not p.exists()]
        if missing:
            raise DataUnavailable(
                f"missing {', '.join(missing)} in {data_dir}; run `python -m src.phase6_prep` first"
            )
        preds = pd.read_parquet(preds_path)
        preds["hour_ts"] = pd.to_datetime(preds["hour_ts"])
        stations = pd.read_parquet(stations_path).set_index("station_id")
        meta_path = data_dir / META_FILE
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        return cls(preds=preds, stations=stations, meta=meta)

    def __post_init__(self) -> None:
        self.preds = self.preds.sort_values(["hour_ts", "station_id"]).reset_index(drop=True)
        self.hours = pd.DatetimeIndex(self.preds["hour_ts"].unique()).sort_values()
        self._hour_slices: dict[pd.Timestamp, slice] = {}
        hour_values = self.preds["hour_ts"].to_numpy()
        starts = np.searchsorted(hour_values, self.hours.to_numpy(), side="left")
        ends = np.searchsorted(hour_values, self.hours.to_numpy(), side="right")
        for ts, s, e in zip(self.hours, starts, ends):
            self._hour_slices[pd.Timestamp(ts)] = slice(int(s), int(e))
        on_map = self.preds["station_id"].isin(self.stations.index)
        # Fixed colour scale across every hour so scrubbing time shows real change.
        self.pred_scale_max = float(np.quantile(self.preds.loc[on_map, "gbm_pred"], 0.99))

    def hour_rows(self, hour: pd.Timestamp) -> pd.DataFrame:
        key = pd.Timestamp(hour)
        if key not in self._hour_slices:
            raise HourNotFound(
                f"hour {key.isoformat()} is outside the demo window "
                f"({self.hours.min().isoformat()} – {self.hours.max().isoformat()})"
            )
        return self.preds.iloc[self._hour_slices[key]]

    def context(self, hour: pd.Timestamp) -> dict[str, Any]:
        rows = self.hour_rows(hour)
        return build_hour_context(rows.iloc[0])

    def map_payload(self, hour: pd.Timestamp) -> dict[str, Any]:
        rows = self.hour_rows(hour)
        mapped = rows[rows["station_id"].isin(self.stations.index)]
        geo = self.stations.loc[mapped["station_id"]]
        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                "properties": {
                    "station_id": int(sid),
                    "name": name,
                    "gbm_pred": _round(gbm),
                    "actual": _round(actual, 0),
                },
            }
            for sid, name, lat, lon, gbm, actual in zip(
                mapped["station_id"], geo["name"], geo["lat"], geo["lon"],
                mapped["gbm_pred"], mapped["actual"],
            )
        ]
        return {
            "context": build_hour_context(rows.iloc[0]),
            "stats": {
                "stations_on_map": len(features),
                "stations_missing_geo": int(self.meta.get("stations_missing_geo", 0)),
                "predicted_total": _round(mapped["gbm_pred"].sum(), 1),
                "actual_total": _round(mapped["actual"].sum(), 0),
            },
            "features": {"type": "FeatureCollection", "features": features},
        }

    def station_payload(self, station_id: int, hour: pd.Timestamp) -> dict[str, Any]:
        if station_id not in self.stations.index:
            raise StationNotFound(f"station {station_id} has no known location")
        rows = self.hour_rows(hour)
        match = rows[rows["station_id"] == station_id]
        if match.empty:
            raise StationNotFound(f"station {station_id} has no scored row at {hour.isoformat()}")
        row = match.iloc[0]
        geo = self.stations.loc[station_id]

        hist = self.preds[self.preds["station_id"] == station_id]
        start = pd.Timestamp(hour) - pd.Timedelta(hours=SERIES_HOURS - 1)
        window = hist[(hist["hour_ts"] >= start) & (hist["hour_ts"] <= hour)]
        series = [
            {"hour_ts": ts.isoformat(), "actual": _round(a, 0), "gbm_pred": _round(g),
             "weekly_naive": _round(w, 0)}
            for ts, a, g, w in zip(window["hour_ts"], window["actual"], window["gbm_pred"],
                                   window["weekly_naive"])
        ]
        return {
            "station": {
                "station_id": int(station_id),
                "name": str(geo["name"]),
                "lat": float(geo["lat"]),
                "lon": float(geo["lon"]),
                "capacity": None if pd.isna(geo.get("capacity")) else int(geo["capacity"]),
            },
            "context": build_hour_context(row),
            "predictions": {c: _round(row[c]) for c in PREDICTION_COLUMNS},
            "lags": {c: _round(row[c]) for c in LAG_COLUMNS},
            "series": series,
        }

    def meta_payload(self) -> dict[str, Any]:
        return {
            "hour_min": self.hours.min().isoformat(),
            "hour_max": self.hours.max().isoformat(),
            "hours": len(self.hours),
            "stations_on_map": int(self.preds["station_id"].isin(self.stations.index)
                                   .groupby(self.preds["station_id"]).first().sum()),
            "stations_missing_geo": int(self.meta.get("stations_missing_geo", 0)),
            "pred_scale_max": round(self.pred_scale_max, 2),
            "mae_check": self.meta.get("mae_check", {}),
            "attribution": ATTRIBUTION,
        }
