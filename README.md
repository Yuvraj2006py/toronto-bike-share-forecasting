# Toronto Bike Share — Hourly Station Demand Forecasting

**GBM beats the weekly naive baseline by ~19% MAE** on the September 2024 holdout (1-hour-ahead MAE **0.874** vs **1.080**).

Predict next-hour bike *departures* for every Bike Share Toronto station from open ridership data, weather, and calendar features — then explore the city on a map or dig into the metrics in a Streamlit lab.

```text
raw trips → DuckDB clean → hourly station departures → features + weather
        → time-split models vs weekly naive → map app + analytical lab
```

## Demo (Docker)

You need Phase 6 prep artifacts under `data/processed/` first (see pipeline below), then:

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| Map app | http://localhost:8080 |
| API | http://localhost:8000/api/health |
| Streamlit lab | http://localhost:8501 |

The map uses your America/Toronto clock, maps it to the same weekday and hour in **September 2024**, and colours ~814 stations by predicted next-hour departures. Click a station for GBM / weekly naive / Poisson, lags, weather, and a 24h sparkline. The lab shows Phase 4 metrics, Phase 5 SHAP/coefficients, and a station explorer.

## Local (without Docker)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python -m src.phase6_prep          # once: GBFS geo + September scored parquet
uvicorn src.api:app --port 8000

cd web && npm install && npm run dev   # http://localhost:5173 (proxies /api)

streamlit run app/streamlit_lab.py     # http://localhost:8501
```

## Data

- **Source:** Bike Share Toronto ridership via the [CUDC catalogue](https://data.urbandatacentre.ca/en/catalogue/city-toronto-bike-share-toronto-ridership-data) (2024 POC; 2022–2023 kept for later)
- **Licence:** [Open Government Licence – Toronto](https://open.toronto.ca/open-data-licence/)
- **Weather:** [Open-Meteo](https://open-meteo.com/en/docs/historical-weather-api) historical hourly for Toronto (observed values only — the demo does not call live 2026 weather)
- **Stations:** Bike Share Toronto GBFS `station_information`
- **Processed grain:** `(station_id, hour_ts) → departures`, then lags / rolling / calendar / weather in `features_2024`

Raw CSVs, DuckDB, parquet, and model joblibs stay local (`data/`, `models/` are gitignored).

## Model card

| Item | Choice |
|---|---|
| Target | Hourly *departures* per station |
| Split | Train Jan–Jul 2024 · validate Aug · test Sep (scored once); finals refit Jan–Aug |
| Baseline | Same station, same hour-of-week, 168h earlier |
| App default | `gbm_full_poisson` (1-hour-ahead HistGradientBoosting) |
| Interpretable Poisson | `poisson_station` (locked features + station identity) |
| Leakage rules | Time-only splits; no future rows in lags/rolling; no random shuffle |

September test (MAE; lower is better): weekly naive **1.080** · Poisson station **0.948** · **GBM 0.874**. Details in [`reports/phase4/findings.md`](reports/phase4/findings.md); interpretation in [`reports/phase5/`](reports/phase5/).

## Reproduce the pipeline

```bash
python -m src.phase1_load_explore
python -m src.phase1_clean
python -m src.phase2_hourly
python -m src.phase3_weather
python -m src.phase3_features
python -m src.phase4_experiments baselines   # also: poisson, poisson_station, gbm, gbm_tune
python -m src.phase4_final
python -m src.phase5_interpret
python -m src.phase6_prep
python -m pytest tests
cd web && npm test
```

## Repo layout

```text
sql/        versioned aggregation SQL
src/        pipeline, models, FastAPI
app/        Streamlit analytical lab
web/        Vite + React + MapLibre map
reports/    phase findings, figures, walkthroughs
tests/      API / data / modeling tests
```

## Next steps

- Multi-year expand (2022–2023 + schema normalization)
- Weather *forecasts* for an ops-style deploy (POC uses observed history)
- Public hosting for the map + Streamlit lab (Docker already works locally)
