# Phase 5 findings — interpretation

**Models read (not refit):** `poisson_station`, `gbm_full_poisson` from Phase 4.
**Evidence:** coefficient tables, SHAP on a fixed 4,000-row September sample, three
station-hour case studies. Start with `narrative.md` / `walkthrough.md`.

## What interpretation showed

1. **Hour-of-day is the strongest global GBM signal** (mean |SHAP| ≈ 0.68), then
   weekly/daily rolling means and `lag_1h`. A lone `lag_168h` ranks lower — which
   is why weekly naive underperforms at peaks.
2. **Poisson’s readable story is commute shape × station identity.** Overnight
   weekday hours multiply expected departures by ~0.13–0.30; weekday 8am / 5–6pm
   multiply by ~2.4–2.7. Waterfront/downtown stations (e.g. York/Queens Quay,
   Bay/College, Union) carry large positive intercepts; outer low-demand docks
   carry large negatives. Milder effects: warmer → more (+), rain → less (−),
   log1p(weekly lag) → more (+).
3. **Local SHAP matches the Phase 4 walkthrough numbers.** Bay/College Mon 8am
   2024-09-23: actual 7, weekly 16, Poisson ~12.7, GBM ~7.3. GBM lifts from
   `lag_1h`, rolling means, 8am, and last week, with rain pulling down — not a
   paste of 16.

## Artifacts

| File | Contents |
|------|----------|
| `narrative.md` | Interview-ready writeup |
| `walkthrough.md` | 90-second spoken script |
| `poisson_shared_coefs.csv` / `poisson_station_coefs.csv` | Full coefficient tables |
| `gbm_shap_importance.csv` / `case_shap.csv` | Global + local SHAP |
| `figures/*.png` | Coefficient bars, SHAP summary, case waterfalls |
| `phase5_metadata.json` | Sample size, case keys, top features |

Reproduce: `python -m src.phase5_interpret`
