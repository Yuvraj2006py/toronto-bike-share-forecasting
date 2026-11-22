# Toronto Bike Share demand-forecasting pipeline — feasibility

**Verdict: viable with caveats**

Toronto publishes a live GBFS station feed and multi-year anonymized trip CSVs that are downloadable today. Together they are enough to train a station-level demand model on historical trips and to serve predictions from live (and self-polled) station snapshots. The main caveats are: (1) GBFS only exposes **net** bikes/docks at stations, not departures vs arrivals, so trip files (or inferred events from dense polling) are required for demand labels; (2) published trip files lag live operations by weeks; (3) station IDs churn over time; (4) Open Data portal HTML pages can look “Retired” even while the CKAN API still serves active packages—use the API and direct download URLs as the source of truth.

Research date: **2026-11-22** (America/Toronto). No production pipeline was built; only throwaway probes.

---

## How to read this document

- **VERIFIED** — fetched, downloaded, or measured in this research session.
- **ASSUMED** — from docs, secondary catalogues, or reasoning (not re-tested here).
- Endpoint URLs and schemas below were not guessed: they come from live HTTP responses or official catalogue JSON.

---

## 1. Live data (GBFS)

### 1.1 Official feed URLs

**VERIFIED** — Mobility Database lists Bike Share Toronto’s auto-discovery URL as GBFS v3.0. The same producer also serves v2 and a legacy v1 tree. All three responded HTTP 200 on 2026-11-22.

| Version | Auto-discovery URL | Notes |
|---|---|---|
| **v3.0 (preferred)** | `https://toronto.publicbikesystem.net/customer/gbfs/v3.0/gbfs.json` | Listed by [Mobility Database — Bike Share Toronto](https://mobilitydatabase.org/feeds/gbfs/gbfs-bike_share_toronto) |
| **v2.3** | `https://toronto.publicbikesystem.net/customer/gbfs/v2/gbfs.json` | Language-scoped under `/en/` and `/fr/` |
| **v1.1 (legacy)** | `https://toronto.publicbikesystem.net/ube/gbfs/v1/gbfs.json` | Also reachable via `https://tor.publicbikesystem.net/ube/gbfs/v1/gbfs.json` |

**VERIFIED** — v3.0 `gbfs.json` feed list (no `free_bike_status` / `vehicle_status`):

```json
{
  "last_updated": "2026-11-22T16:01:57Z",
  "ttl": 6,
  "version": "3.0",
  "data": {
    "feeds": [
      {"name": "gbfs_versions", "url": "https://toronto.publicbikesystem.net/customer/gbfs/v3.0/gbfs_versions"},
      {"name": "geofencing_zones", "url": "https://toronto.publicbikesystem.net/customer/gbfs/v3.0/geofencing_zones"},
      {"name": "station_information", "url": "https://toronto.publicbikesystem.net/customer/gbfs/v3.0/station_information"},
      {"name": "station_status", "url": "https://toronto.publicbikesystem.net/customer/gbfs/v3.0/station_status"},
      {"name": "system_information", "url": "https://toronto.publicbikesystem.net/customer/gbfs/v3.0/system_information"},
      {"name": "system_pricing_plans", "url": "https://toronto.publicbikesystem.net/customer/gbfs/v3.0/system_pricing_plans"},
      {"name": "system_regions", "url": "https://toronto.publicbikesystem.net/customer/gbfs/v3.0/system_regions"},
      {"name": "vehicle_types", "url": "https://toronto.publicbikesystem.net/customer/gbfs/v3.0/vehicle_types"}
    ]
  }
}
```

**VERIFIED** — corresponding v2 English URLs:

- `https://toronto.publicbikesystem.net/customer/gbfs/v2/en/station_information`
- `https://toronto.publicbikesystem.net/customer/gbfs/v2/en/station_status`
- `https://toronto.publicbikesystem.net/customer/gbfs/v2/en/system_information`
- `https://toronto.publicbikesystem.net/customer/gbfs/v2/en/vehicle_types`

**VERIFIED** — `free_bike_status` and `vehicle_status` are **not** in discovery and return **HTTP 404** on both v2 and v3. This is a docked system in the public feed; there is no public free-floating bike list.

**VERIFIED** — City of Toronto Open Data also has a “Bike Share Toronto” package (`refresh_rate: Real-time`) whose JSON resources still point at the **legacy v1** URLs and are themselves stale snapshots (`last_updated`: 1563373889 ≈ 2019). Prefer the producer URLs above, not the CKAN-hosted JSON copies.

### 1.2 Sample payloads and fields

**VERIFIED** — `system_information` (v2):

```json
{
  "last_updated": 1795363343,
  "ttl": 10,
  "version": "2.3",
  "data": {
    "system_id": "bike_share_toronto",
    "timezone": "America/Toronto",
    "name": "bike_share_toronto",
    "language": "en",
    "_station_count": 1072,
    "_vehicle_count": {"_mechanical_count": 8456, "_ebike_count": 2817}
  }
}
```

**VERIFIED** — one `station_information` row (v2; **1072** stations total):

```json
{
  "station_id": "7000",
  "external_id": "f8aa7900-e9c7-11ef-984e-124c66246c7d",
  "name": "Fort York  Blvd / Capreol Ct",
  "lat": 43.63970679931218,
  "lon": -79.39614309573555,
  "address": "Fort York  Blvd / Capreol Ct",
  "capacity": 47,
  "is_charging_station": false,
  "is_virtual_station": false,
  "rental_methods": ["key", "transitcard", "creditcard", "phone"],
  "groups": ["South", "Fort York - Entertainment District"],
  "short_name": "647-643-9607"
}
```

Other station_information keys observed: `altitude`, `geofenced_capacity`, `physical_configuration`, `nearby_distance`, `obcn`, `rental_uris`, plus vendor fields `_bluetooth_id`, `_ride_code_support`.

**VERIFIED** — one `station_status` row (v2):

```json
{
  "station_id": "7000",
  "num_bikes_available": 19,
  "num_bikes_disabled": 0,
  "num_docks_available": 28,
  "num_docks_disabled": 0,
  "is_installed": true,
  "is_renting": true,
  "is_returning": true,
  "status": "IN_SERVICE",
  "last_reported": 1795363233,
  "vehicle_types_available": [
    {"vehicle_type_id": "ICONIC", "count": 19},
    {"vehicle_type_id": "BOOST", "count": 0},
    {"vehicle_type_id": "EFIT", "count": 0},
    {"vehicle_type_id": "ASTRO", "count": 0}
  ],
  "vehicle_docks_available": [
    {"vehicle_type_ids": ["ICONIC", "BOOST", "EFIT", "ASTRO"], "count": 28}
  ]
}
```

**VERIFIED** — v3 `station_status` uses GBFS 3 names (`num_vehicles_available` instead of `num_bikes_available`) and ISO-8601 timestamps. Same station_id space (`"7000"`, etc.).

### 1.3 TTL / update frequency in practice

**VERIFIED**:

| Signal | Observation |
|---|---|
| Feed `ttl` field | Usually small integers (0–10 seconds) on status/info responses |
| HTTP `Cache-Control` | `public, s-maxage=10, max-age=10` on `station_status` |
| Polling test | 6 polls ~10s apart → **6 distinct** body hashes and `last_updated` values |
| Burst test | 20 rapid requests → all HTTP 200; **no** `X-RateLimit-*` / `Retry-After` headers seen |

Practical polling cadence: about **every 10–30 seconds** is enough to track inventory; denser than `max-age=10` is unlikely to buy fresher CDN-cached content and is less polite.

**ASSUMED** — GBFS docs say station status should not be more than ~5 minutes stale; Toronto’s feed appears much fresher than that bound.

### 1.4 Rate limits, license, attribution

**VERIFIED**:

- No rate-limit headers or 429s observed in light probing. That does **not** prove there is no limit under heavier load.
- Mobility Database lists the feed license as **CC-BY-4.0**.
- `system_information` itself did **not** embed a `license_url` / attribution string in the payload we fetched.
- Historical ridership Open Data uses **Open Government Licence – Toronto**, which requires attribution such as: *Contains information licensed under the Open Government Licence – Toronto.* ([licence text](https://open.toronto.ca/open-data-licence/))

**ASSUMED** — For a public demo, attribute both Bike Share Toronto / Lyft Mobility Data contact (`mobility-data-client@lyft.com` on v3 system_information) for GBFS and the City of Toronto OGL for trip files.

### 1.5 Individual bike IDs or trip-level info in the live feed?

**VERIFIED** — **No.** Live GBFS here is **per-station counts** (optionally split by `vehicle_type_id`). Searches of `station_status` bodies found no `bike_id`, `vehicle_id`, or trip objects. Trip-level and bike-level identifiers appear only in the **historical ridership CSVs** (see §2).

---

## 2. Historical trip data

### 2.1 Where it is published

**VERIFIED**:

| Source | URL | What we saw |
|---|---|---|
| CKAN API (source of truth) | `https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_show?id=bike-share-toronto-ridership-data` | `state: active`, `is_retired: false`, `refresh_rate: Monthly`, `last_refreshed: 2026-11-17 11:03:21` |
| Direct ZIP downloads | `https://opendata.toronto.ca/toronto.parking.authority/bike-share-toronto-ridership-data/bikeshare-ridership-YYYY.zip` | Years **2017–2026** downloadable (plus older XLSX for 2014–2016) |
| Portal HTML page | [open.toronto.ca dataset page](https://open.toronto.ca/dataset/bike-share-toronto-ridership-data/) | Scraped page title/body showed **“Retired”** with empty resource UI — **do not trust the HTML alone** |
| CUDC mirror catalogue | [CUDC entry](https://data.urbandatacentre.ca/en/catalogue/city-toronto-bike-share-toronto-ridership-data) | Lists the same CKAN download links |

Package notes list fields: Trip ID, duration, start/end station ID + name + time, Bike ID, User type. Licence: Open Government Licence – Toronto. Owner: Toronto Parking Authority (`customerservice@greenp.com`).

### 2.2 Format, time range, update cadence

**VERIFIED** by downloading ZIPs:

| Year file | Packaging | Coverage in file | Approx rows |
|---|---|---|---|
| 2017 | Quarterly CSVs inside ZIP | 2017 Q1–Q4 | (not fully counted) |
| 2024 | Single `bikeshare-ridership-2024.csv` | 2024-01-01 → 2024-12-31 | ~6.95M |
| 2025 | 12 monthly CSVs `bikeshare_2025_MM.csv` | Full calendar 2025 | ~7.81M |
| 2026 | Single `bikeshare-ridership-2026.csv` | 2026-01-01 → **2026-09-30** | ~6.83M |

**VERIFIED** — CKAN `refresh_rate: Monthly`; resources for 2024/2025/2026 were last modified **2026-11-17 11:03 UTC** (≈ **06:03 America/Toronto**). The 2026 file still ends at **2026-09-30**, so at probe time there was roughly a **6–7 week lag** between the newest trip in the published file and the publish timestamp. Treat “monthly” as a target, not a guarantee of “complete through last month.”

**VERIFIED** — package `limitations` note: schema/software changed around mid-2016; 2014–2019 often quarterly; 2020+ monthly (packaging still varies by year, as above).

### 2.3 Columns (sample)

**VERIFIED** — 2017 Q1 header:

```text
trip_id,trip_start_time,trip_stop_time,trip_duration_seconds,from_station_id,from_station_name,to_station_id,to_station_name,user_type
712382,1/1/2017 0:00,1/1/2017 0:03,223,7051,Wellesley St E / Yonge St Green P,7089,Church St  / Wood St,Member
```

**VERIFIED** — 2024 / 2026 header (same columns; 2026 adds continuous YTD):

```text
Trip_Id,Trip_Duration,Start_Station_Id,Start_Time,Start_Station_Name,End_Station_Id,End_Time,End_Station_Name,Bike_Id,User_Type,Bike_Model
43682415,248,7719,2026-01-01 00:00:26,Wolseley St / Augusta Ave,7037.0,2026-01-01 00:04:34,Bathurst St / Dundas St W,122,Member,ICONIC
```

Notes from samples:

- Start/end **station IDs**, timestamps, duration, **user type** (Member/Casual), and (recent years) **Bike_Id** + **Bike_Model** are present.
- `End_Station_Id` sometimes appears as a float string (`7037.0`) in annual CSVs; monthly 2025 files often use integers. Normalize before joins.
- Some trips have missing end stations (~874 / 250k in a 2026 sample ≈ 0.35%).

### 2.4 Join to GBFS station IDs?

**VERIFIED** — IDs are the same namespace (e.g. `"7000"`, `"7719"`). Against live v2 `station_information` (1072 stations):

| Check | Result |
|---|---|
| 2026 sample (250k trips) start IDs in current GBFS | **97.35%** of trip rows |
| Unique start IDs in that sample not in current GBFS | 24 IDs (e.g. 7009, 7047, 7083…) |
| 2017 Q1 sample unique starts still in current GBFS | **88.5%** of unique IDs |

So joins work well for recent years, but **station churn is real**. Keep a slowly changing station dimension (first/last seen, name, lat/lon) rather than assuming today’s GBFS is a complete key for all history.

**ASSUMED** — `external_id` (UUID) in GBFS may be more stable than numeric `station_id` across operator migrations, but historical trip files only carry the numeric ID / name, so numeric `station_id` remains the practical join key.

---

## 3. How the two fit together

### 3.1 Can GBFS alone separate departures from arrivals?

**VERIFIED reasoning from feed contents** — `station_status` gives `num_bikes_available` / `num_docks_available` (and vehicle-type splits). A change of −1 bikes could be:

- a rental (departure),
- an operator removal / rebalance truck,
- a dock failure reclassification,
- or a missed intermediate update.

A change of +1 could be a return, a rebalance drop-off, or a repair return. **You cannot reliably label demand (departures) vs supply (arrivals) from net inventory alone.**

**ASSUMED / industry practice** — High-frequency polling can *approximate* event counts when changes are ±1 between polls, but simultaneous events, rebalancing, and outages break that. For training labels, **trip files are the reliable source of departures and arrivals**.

### 3.2 Recommended use of historical trips + live polling

| Role | Data | Why |
|---|---|---|
| **Training labels** | Historical trips aggregated to `(station_id, hour)` departures and/or arrivals | Explicit OD events with timestamps |
| **Training features** | Calendar, lags, rolling history, weather, station capacity/location | Standard demand features |
| **Inference-time state** | Polled GBFS `station_status` (+ `station_information`) | Live bikes/docks, is_renting/returning, vehicle mix |
| **Growing history** | Store every poll into a time-series table | Builds your own inventory history; later can train inventory / stockout models that trip files alone cannot |
| **Delayed label backfill** | When monthly ZIPs update, append new trips and recompute metrics | Live system never waits on Open Data for serving |

Mental model:

```text
Open Data trips ──► clean ──► hourly demand labels ──► train model
GBFS poll ───────► feature store (inventory, capacity) ──► score next hour
monthly ZIP ─────► backfill truth / monitoring (lagged)
```

---

## 4. Pipeline design options

### 4.1 Architecture A — “Cron + lakehouse-lite” (recommended start)

**Tools:** Python, `cron` or systemd timer, DuckDB or Postgres, Parquet on disk, scikit-learn / HistGradientBoosting, small FastAPI or Streamlit UI.

| | |
|---|---|
| **Cost** | Free locally; a few dollars/month on a small VPS if hosted |
| **Tradeoffs** | Least moving parts; weaker scheduling/retry/observability |
| **Skills** | Ingestion, schema discipline, SQL/analytics engineering, batch ML, simple serving |

Enough to learn the full loop before adding orchestration theatre.

### 4.2 Architecture B — “Orchestrated batch + warehouse”

**Tools:** Prefect or Airflow, Postgres or BigQuery/Snowflake (free tiers / student credits), dbt optional, model registry (MLflow local), containerized API.

| | |
|---|---|
| **Cost** | Free–low if self-hosted Prefect + Postgres; cloud warehouse optional |
| **Tradeoffs** | More ops surface; clearer industry resume signal |
| **Skills** | DAG orchestration, data quality checks, warehouse modeling, CI for pipelines |

### 4.3 Architecture C — “Streaming-ish inventory”

**Tools:** Kafka/Redpanda or cloud pub/sub, stream processor, real-time feature store, plus still-batch trip backfill.

| | |
|---|---|
| **Cost** | Higher complexity; infra cost rises quickly |
| **Tradeoffs** | Overkill for a 10s-cache JSON poll; teaches streaming but adds little accuracy vs 1-minute batch polls for a 1-hour forecast |
| **Skills** | Event streaming, exactly-once/at-least-once debates, real-time serving |

**Recommendation:** start with **A**, graduate scheduling/quality pieces toward **B**. Skip **C** unless the learning goal is specifically streaming.

### 4.4 Forecasting target and models

**Primary target (demand):** for each station, **departures in the next 1 hour**  
(`count of trips starting at station_id with Start_Time in [t, t+1h)`).

Why this target: it matches the trip files cleanly, is actionable for rebalancing, and avoids pretending GBFS net counts are demand.

**Secondary target (ops / later phase):** **bikes available at t+1h** (inventory). Needs your polled GBFS history and still will be confounded by rebalancing—treat as a separate project slice.

| Model | Role |
|---|---|
| **Baseline** | Same station, same hour-of-week, 168 hours earlier (seasonal naive) |
| **Stronger** | Histogram-based gradient boosting (e.g. sklearn `HistGradientBoostingRegressor` with Poisson objective) on lags, rolling means, hour/dow/month, holiday flag, weather, station capacity / zone |

**ASSUMED** — Weather from Open-Meteo (or Environment Canada) is a useful exogenous feature; not required for an MVP baseline comparison.

---

## 5. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Trip publish lag** (weeks) | High for “online learning” from official labels | Use trips for offline train/eval; poll GBFS for serving; backfill when ZIPs update |
| **Portal “Retired” confusion** | Medium | Automate off CKAN API + direct `opendata.toronto.ca` URLs; alert if package `state` / downloads fail |
| **Schema drift** (headers, date formats, float IDs, monthly vs annual ZIP layout) | High | Contract tests on raw headers; normalize in one ingestion module |
| **Station churn / renames** | Medium | SCD station dimension; don’t drop history when an ID leaves live GBFS |
| **Rebalancing & outages** | High for inventory targets | Prefer departure demand; flag `is_renting` / `is_returning` / `status` |
| **Seasonality & weather** | Medium | Multi-season training data; weather features; evaluate by month |
| **GBFS version / field renames** (v2 `num_bikes_*` vs v3 `num_vehicles_*`) | Medium | Pin a version (v2 or v3) and adapter layer |
| **CKAN-hosted GBFS JSON stale** | Medium | Hit producer URLs only |
| **Rate limits under heavy polling** | Low–medium (unverified ceiling) | Respect `max-age=10`; exponential backoff |
| **Missing trip ends / bad rows** | Low | Quality filters already needed for any ML pipeline |
| **License / attribution slip** | Low | OGL + CC-BY attribution in app footer / README |

---

## 6. Recommended phased build plan

Each phase should end with an artifact you can review before approving the next.

### Phase 0 — Contracts (this doc)

- Freeze GBFS base URL (prefer v3.0 or v2.3 explicitly).
- Freeze trip download strategy (CKAN `package_show` → resource URLs).
- Decision: target = **1h departures**; baseline = weekly naive; stronger = HGBR/Poisson GBM.

### Phase 1 — Historical ingest only

- Download one recent year (e.g. 2025 monthly or 2024 annual).
- Normalize columns, timestamps (America/Toronto), station IDs.
- Write Parquet + a one-page data-quality report (null ends, duration outliers, ID overlap vs live GBFS).

### Phase 2 — Labels + simple features

- Aggregate hourly departures (and arrivals) per station.
- Add calendar features + 1h/24h/168h lags.
- Time-based split (no random shuffle).

### Phase 3 — Baseline vs stronger model

- Fit weekly naive + one GBM.
- Report MAE/RMSE by hour-of-day and by station volume tier.
- Stop if GBM does not beat naive in a way you care about—debug features before infra.

### Phase 4 — Live GBFS poller

- Poll `station_status` every 15–30s (or 1 min to start).
- Persist snapshots; expose “as-of” inventory for a station.
- Still no need for Airflow.

### Phase 5 — Serving stub

- API: given `station_id` + timestamp, return baseline + model forecast + current bikes/docks.
- Attribution footer for OGL + GBFS.

### Phase 6 — Hardening (optional)

- Prefect/Airflow for monthly ZIP pull + retrains.
- Weather join.
- Monitoring for schema changes and feed downtime.
- Only then consider warehouse / streaming upgrades.

---

## 7. Sources

**VERIFIED fetches / pages used in this research:**

- [Mobility Database — Bike Share Toronto GBFS](https://mobilitydatabase.org/feeds/gbfs/gbfs-bike_share_toronto)
- Producer GBFS: `https://toronto.publicbikesystem.net/customer/gbfs/v3.0/gbfs.json` (and v2 / v1 trees)
- CKAN: `package_show?id=bike-share-toronto-ridership-data` and `package_show?id=bike-share-toronto`
- Direct ZIPs under `https://opendata.toronto.ca/toronto.parking.authority/bike-share-toronto-ridership-data/`
- [Open Government Licence – Toronto](https://open.toronto.ca/open-data-licence/)
- [CUDC catalogue mirror](https://data.urbandatacentre.ca/en/catalogue/city-toronto-bike-share-toronto-ridership-data)
- [open.toronto.ca ridership dataset page](https://open.toronto.ca/dataset/bike-share-toronto-ridership-data/) (HTML showed “Retired”; contradicted by CKAN API)

**ASSUMED / reference only:**

- [GBFS specification](https://gbfs.org/documentation/reference/) for field semantics and latency guidance

---

## Bottom line

Build it. Use **Open Data trips for labels**, **GBFS polls for live features and a growing inventory history**, start with **cron + DuckDB/Parquet + a naive baseline + one GBM**, and treat portal UI quirks, publish lag, and station churn as first-class design constraints—not surprises.
