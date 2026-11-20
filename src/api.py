"""Phase 6 prediction API for the Toronto map app.

Run from project root (after `python -m src.phase6_prep`):
    uvicorn src.api:app --reload --port 8000
"""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, FastAPI, HTTPException, Path as PathParam, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.app_data import TORONTO, resolve_demo_hour, to_toronto_local
from src.app_store import AppStore, DataUnavailable, HourNotFound, StationNotFound
from src.db import DATA_PROCESSED

Clock = Callable[[], datetime]


class Health(BaseModel):
    status: str
    data_loaded: bool
    detail: str | None = None


class Demo(BaseModel):
    from_clock: bool
    clock_local: str | None = None
    note: str


class MapResponse(BaseModel):
    context: dict[str, Any]
    demo: Demo
    stats: dict[str, Any]
    features: dict[str, Any]


class StationResponse(BaseModel):
    station: dict[str, Any]
    context: dict[str, Any]
    predictions: dict[str, float | None]
    lags: dict[str, float | None]
    series: list[dict[str, Any]]


class MetaResponse(BaseModel):
    hour_min: str
    hour_max: str
    hours: int
    stations_on_map: int
    stations_missing_geo: int
    pred_scale_max: float
    mae_check: dict[str, Any]
    attribution: list[dict[str, str]]


def _store(request: Request) -> AppStore:
    store: AppStore | None = request.app.state.store
    if store is None:
        raise HTTPException(status_code=503, detail=request.app.state.load_error)
    return store


def _resolve_hour(request: Request, store: AppStore, hour: datetime | None) -> tuple[pd.Timestamp, Demo]:
    if hour is not None:
        ts = pd.Timestamp(to_toronto_local(hour)).floor("h")
        return ts, Demo(from_clock=False, note="Hour chosen by you, Sep 2024 holdout")
    now = request.app.state.clock()
    ts = resolve_demo_hour(now, store.hours)
    return ts, Demo(
        from_clock=True,
        clock_local=to_toronto_local(now).isoformat(timespec="minutes"),
        note="Mapped from your Toronto clock to the same weekday and hour in Sep 2024",
    )


router = APIRouter(prefix="/api", tags=["map"])


@router.get("/health")
def health(request: Request) -> Health:
    loaded = request.app.state.store is not None
    return Health(status="ok", data_loaded=loaded,
                  detail=None if loaded else request.app.state.load_error)


@router.get("/meta")
def meta(request: Request) -> MetaResponse:
    return MetaResponse(**_store(request).meta_payload())


@router.get("/map")
def city_map(
    request: Request,
    hour: Annotated[datetime | None, Query(description="Demo hour (Toronto local, ISO 8601)")] = None,
) -> MapResponse:
    store = _store(request)
    ts, demo = _resolve_hour(request, store, hour)
    try:
        payload = store.map_payload(ts)
    except HourNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MapResponse(demo=demo, **payload)


@router.get("/station/{station_id}")
def station_detail(
    request: Request,
    station_id: Annotated[int, PathParam(ge=1)],
    hour: Annotated[datetime | None, Query(description="Demo hour (Toronto local, ISO 8601)")] = None,
) -> StationResponse:
    store = _store(request)
    ts, _ = _resolve_hour(request, store, hour)
    try:
        payload = store.station_payload(station_id, ts)
    except (HourNotFound, StationNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StationResponse(**payload)


def _default_clock() -> datetime:
    return datetime.now(TORONTO)


def create_app(data_dir: Path | None = None, clock: Clock = _default_clock) -> FastAPI:
    directory = Path(data_dir or os.environ.get("APP_DATA_DIR", DATA_PROCESSED))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            app.state.store = AppStore.load(directory)
            app.state.load_error = None
        except DataUnavailable as exc:
            app.state.store = None
            app.state.load_error = str(exc)
            print(f"[api] data unavailable: {exc}")
        yield

    app = FastAPI(title="Toronto Bike Share demand map", version="1.0.0", lifespan=lifespan)
    app.state.clock = clock
    app.state.store = None
    app.state.load_error = "data not loaded yet"
    origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:8080")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins.split(",") if o.strip()],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
