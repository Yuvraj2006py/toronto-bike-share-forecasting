# Phase 5 — why the models predict what they predict

Interview-ready interpretation of the Phase 4 finalists (`poisson_station` and `gbm_full_poisson`). Numbers come from the Jan–Aug refit artifacts and a September holdout sample.

## The three drivers (say this first)

1. **Time of day sets the floor and the peak.** SHAP ranks `hour_of_day` first globally; Poisson’s largest coefficients are overnight drops (~0.13× at 3am) and commute lifts (~2.4–2.7× at 8am / 5–6pm weekdays).
2. **Recent station activity beats a single weekly copy.** After hour-of-day, GBM importance is `roll_mean_168h`, `roll_mean_24h`, and `lag_1h` — what this dock has been doing lately. `lag_168h` still helps, but it is not the whole story (and weekly naive uses only that).
3. **Which station you are at is huge for the GLM.** Poisson without station identity leaned too hard on one weekly lag; with station one-hots, waterfront/downtown docks get a permanent lift and low-demand docks stay low.

## Poisson coefficients (official `poisson_station`)

Poisson uses a log link: a coefficient of `c` multiplies expected departures by `exp(c)` when that feature turns on / increases (after scaling / one-hot).

### Shared (non-station) drivers — strongest up and down

| Feature | Coef | × multiplier | Plain reading |
|---------|-----:|-------------:|---------------|
| weekday hour 17:00 | 0.994 | 2.702 | pulls prediction up |
| weekday hour 18:00 | 0.899 | 2.457 | pulls prediction up |
| weekday hour 08:00 | 0.895 | 2.447 | pulls prediction up |
| weekday hour 03:00 | -2.033 | 0.131 | pulls prediction down |
| weekday hour 04:00 | -1.956 | 0.141 | pulls prediction down |
| weekend/holiday hour 05:00 | -1.579 | 0.206 | pulls prediction down |

Weather / weekly lag (scaled):

| Feature | Coef | × multiplier |
|---------|-----:|-------------:|
| temperature (°C) | 0.375 | 1.455 |
| log1p(weekly lag) | 0.274 | 1.315 |
| precipitation (mm) | -0.104 | 0.902 |
| holiday | 0.018 | 1.019 |

Top busy station effect: **station 7076 (York St / Queens Quay W)** (coef 1.60).
Top quiet station effect: **station 7875 (Oakdale Community Centre)** (coef -1.33).

Plots: `figures/poisson_shared_coefs.png`, `figures/poisson_station_coefs.png`.

## GBM SHAP (app default `gbm_full_poisson`)

Global importance from TreeExplainer on a fixed sample of 4,000 September station-hours:

| Feature | mean \|SHAP\| |
|---------|-------------:|
| hour_of_day | 0.6848 |
| roll_mean_168h | 0.6406 |
| roll_mean_24h | 0.4527 |
| lag_1h | 0.3361 |
| lag_168h | 0.2533 |

Plots: `figures/gbm_shap_importance.png`, `figures/gbm_shap_beeswarm.png`.

## Case study — Bay St / College St (East Side), Monday 2024-09-23 08:00

Actual departures: **7**. Weekly naive copied last Monday (16). Poisson predicted **12.7**; GBM **7.3**.

Largest SHAP pushes for the GBM on this hour:

| Feature | Value | SHAP |
|---------|------:|-----:|
| lag_1h | 5 | 1.067 |
| lag_168h | 16 | 0.919 |
| roll_mean_168h | 9.8631 | 0.854 |
| roll_mean_24h | 6.25 | 0.626 |
| precip_mm | 1.5 | -0.619 |
| hour_of_day | 8 | 0.491 |

Verbal line: *weekly naive pasted 16. Poisson (busy station + big weekly lag) climbed to ~13. The GBM also saw last week’s spike, but balanced it with last-hour activity (5), a moderate 24h level (~6), 8am commute lift, and light rain pulling down — landing at ~7.3 next to the actual 7.*

More cases (quiet night + rainy quieter station) are in `case_shap.csv` and `figures/case_*.png`.

## How to reproduce

```bash
python -m src.phase5_interpret
```

Artifacts: this folder’s CSVs + figures. Models are loaded from `models/` (Phase 4 final fit); nothing is refit here.
