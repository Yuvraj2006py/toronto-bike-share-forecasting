# Phase 3 feature safety notes

Each feature: one-line **safe at predict time?** answer.

| Feature | Safe at predict time? |
|---------|------------------------|
| `departures` | **Target only** — never use as a feature for the same row. |
| `hour_of_day` | Yes — known from the forecast timestamp. |
| `day_of_week` | Yes — known from the forecast timestamp. |
| `month` | Yes — known from the forecast timestamp. |
| `is_weekend` | Yes — known from the forecast timestamp. |
| `is_holiday` | Yes — Ontario holiday calendar is known in advance. |
| `lag_1h` | Yes — uses departures at t−1 only (needs that hour observed / forecasted recursively). |
| `lag_24h` | Yes — uses departures at t−24 only. |
| `lag_168h` | Yes — uses departures at t−168 only (same signal as weekly naive baseline). |
| `roll_mean_24h` | Yes — AVG over t−24…t−1 only (current hour excluded). |
| `roll_std_24h` | Yes — STDDEV over t−24…t−1 only. |
| `roll_mean_168h` | Yes — AVG over t−168…t−1 only. |
| `roll_std_168h` | Yes — STDDEV over t−168…t−1 only. |
| `temp_c` | **POC yes / ops no as-is** — historical observed weather. Production needs a weather *forecast* available before the hour. |
| `precip_mm` | **POC yes / ops no as-is** — same as temp. |
| `wind_speed_kmh` | **POC yes / ops no as-is** — same as temp. |

## Leakage controls baked into SQL

- Window frames use `ROWS BETWEEN N PRECEDING AND 1 PRECEDING` (never include current `departures`).
- Lags use `LAG` only (past offsets).
- No global train/test aggregates in this table.
- Station spines start at first appearance (Phase 2 Option B), so early lags are NULL (cold start), not fabricated zeros from pre-open periods.

## Locked model feature sets (accepted)

**Poisson GLM (small / interpretable):**
`hour_of_day`, `day_of_week`, `is_weekend`, `is_holiday`, `lag_168h`, `temp_c`, `precip_mm`,
plus `start_station_id` (one-hot) — added in Phase 4 after it fixed the model's missing station level.

**Gradient boosting (fuller):**
all non-target columns (calendar + all lags + all rolling + weather).
