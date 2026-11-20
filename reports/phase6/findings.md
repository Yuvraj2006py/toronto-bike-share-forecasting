# Phase 6 findings — map app + lab + Docker

## What shipped

| Surface | URL (Docker) | Role |
|---|---|---|
| Map app | http://localhost:8080 | User-friendly city map of next-hour GBM predictions |
| API | http://localhost:8000/api | `/map`, `/station/{id}`, `/meta`, `/health` |
| Streamlit lab | http://localhost:8501 | Phase 4 metrics, Phase 5 figures, station explorer |

Prep: `python -m src.phase6_prep` → `stations_geo.parquet`, `app_hourly_preds_2024_09.parquet`, `app_meta.json`.

## Spot-check (Bay St / College St East Side, 2024-09-23 08:00)

Via nginx → API: actual **7**, weekly naive **16**, Poisson **12.68**, GBM **7.29**, Monday, 18.9°C. Matches Phase 4/5.

## Dynamics

- **Time:** visitor America/Toronto clock → latest Sep 2024 hour with same weekday + hour-of-day (DST-aware).
- **Weather / calendar:** taken from that hour's feature row and bundled in every `/map` and `/station` payload so the UI cannot drift from the predictions.
- **Colour scale:** fixed `pred_scale_max` (99th pct of GBM over September). Size + colour encode demand (not colour alone).

## Design / visual QA

- Firecrawl refs: Bike Share Toronto system map + Windy → `DESIGN.md`, screenshots in `refs/`.
- Taste-skill deal: `soot-pale-lime` + IBM Plex (`plex`), software page.
- Screenshots: `shots/v2-1440.png`, `shots/v2-390.png`.
- Figma capture: https://www.figma.com/design/R9tosLGA1qkhH6cj6PYCeA?node-id=1-2
- Gate: **GATE: OPEN 2** after three rounds. Remaining marketing-layout checks (`copy-fact` truncation on the h1, MapLibre attribution `container-edges`) do not fit a full-screen map tool; waivers for the other tool-vs-marketing mismatches are in `web/.taste-skill/waivers.json` (max 5).

## Bugs fixed while building

1. Weekday labels used Monday=0; features use DuckDB Sunday=0. Fixed in `app_data` (label from timestamp) and Phase 5 humanizer; Phase 5 CSVs regenerated.
2. MapLibre 6 silently dropped the station layer when `circle-radius` nested zoom×data interpolations. Simplified to a single data interpolate.
3. Docker nginx served the MapLibre worker `.mjs` as `application/octet-stream`, so the tile worker never started and the map stayed black. Fixed MIME to `application/javascript` in `web/nginx.conf`.

## Skills used

find-skills, design-taste-frontend (taste-skill), maplibre-tile-sources, maplibre-cartography, vercel-composition-patterns, fastapi, multi-stage-dockerfile, developing-with-streamlit (discover needed Streamlit ≥1.57 / `python3`; lab built against installed 1.52), Firecrawl design scrape, Figma MCP capture.

## Deferred

Live weather, AWS/S3, multi-year data, arrivals forecasting.
