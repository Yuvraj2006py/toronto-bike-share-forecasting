# Phase 4 findings — baselines, Poisson, gradient boosting

**Split (locked before any fit):** train Jan–Jul 2024 · validate Aug · test Sep (scored once).
Final models refit on Jan–Aug. All models scored on the same rows: station-hours where
`lag_168h` exists (cold-start rows from newly opened stations excluded: 2,834 in Sep).

## September test results

Mean actual departures per station-hour: 1.455. Lower is better for every metric.

| Model | Horizon | MAE | RMSE | Poisson dev. | vs weekly naive (MAE) | vs station×hour-of-week mean (MAE) |
|-------|---------|-----|------|--------------|------------------------|--------------------------------------|
| weekly_naive | 1 week | 1.080 | 2.238 | 6.477 | — | −13.5% |
| station_how_mean | any | 0.951 | 2.010 | 1.553 | +11.9% | — |
| poisson_interact (locked features) | 1 week | 1.102 | 1.988 | 1.646 | −2.0% | −15.8% |
| poisson_station (exploratory) | 1 week | 0.948 | 1.836 | 1.277 | +12.2% | +0.4% |
| gbm_dayahead_poisson | 1 day | 1.003 | 1.851 | 1.384 | +7.1% | −5.4% |
| **gbm_full_poisson** | **1 hour** | **0.874** | **1.668** | **1.077** | **+19.1%** | **+8.2%** |

Validation (August) produced the same ranking, so the choices made on August held up on unseen data.

## What the experiments showed

1. **The weekly naive baseline is weak.** A train-period average per station × hour-of-week beats it by
   ~12% MAE. One week's count is a single noisy draw; averaging ~30 weeks removes that noise.
   Models are judged against both.
2. **How a feature enters a GLM matters more than which features it gets.** With raw `lag_168h`
   under Poisson's log link, prediction = exp(coef × lag): a station with 157 departures last week
   was predicted at 10,291 (actual 3). `log1p(lag_168h)` fixed it (RMSE 14.4 → 2.05).
   Hour-of-day as one number (linear) is also wrong — demand has two commute peaks; one-hot fixes that.
3. **Poisson's main weakness was not knowing which station it was predicting.** Its only
   station-level signal was one week's count. Adding station identity (one-hot) cut validation
   MAE 1.154 → 0.994 and deviance 1.72 → 1.33. This is outside the locked Poisson feature set.
4. **Forecast horizon changes the problem.** `lag_1h` and every rolling window include hour t−1,
   so the full GBM is a 1-hour-ahead model. Restricted to features available 24h ahead, GBM drops
   from 0.874 to 1.003 MAE and no longer beats the historical average on MAE. The 24h-safe set lacks
   a smooth station-level signal (e.g. a rolling mean that ends 24h before the forecast hour).
5. **Loss function barely mattered for GBM** (squared vs Poisson: 0.9022 vs 0.9018 on August).
   Poisson loss is kept because it can't predict negative counts.
6. **Tree count was tuned on August, not with built-in early stopping** — sklearn's early stopping
   holds out a random slice of train, which would mix future hours into validation. Full GBM
   deviance bottomed out near 450 trees; the day-ahead GBM began overfitting after ~50–100.
7. **Seasonal drift is visible.** Models fit on Jan–Aug under-predict September on average
   (station_how_mean mean prediction 0.93 vs actual 1.46). Winter months pull averages down.
   Models with recent lags (GBM full) track the level correctly.
8. **MAE and deviance can disagree.** Over half of station-hours are 0, so a model that often predicts
   exactly 0 (weekly naive) can do well on MAE while being badly calibrated (deviance 6.5 vs ~1.1–1.6).

## Decisions

- **App default (Phase 6):** `gbm_full_poisson` — most accurate; labelled in the app as a 1-hour-ahead forecast.
- **Official Poisson model:** `poisson_station` — the locked Poisson features plus station identity
  (adopted after finding 3). `poisson_interact` is kept only as the comparison point.

## Caveats

- Weather is observed, not forecast — real deployment needs weather forecasts.
- Cold-start station-hours (no `lag_168h`) are excluded from scoring; GBM can predict them, the
  baselines and Poisson cannot.
- Single holdout month; a rolling-origin backtest would give a variance estimate.

Artifacts: `models/*.joblib`, `models/phase4_metadata.json`; raw numbers in this folder's CSVs.
Reproduce: `python -m src.phase4_experiments {baselines|poisson|poisson_station|gbm|gbm_tune}`
then `python -m src.phase4_final`.
