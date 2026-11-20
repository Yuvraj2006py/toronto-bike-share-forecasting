# Phase 5 walkthrough — say it out loud

Use this as a 90-second interview answer. Details and plots live in `narrative.md` / `figures/`.

## Hook (10s)
“On a Monday 8am at Bay St / College St (East Side), seven bikes left. Copying last week said sixteen; Poisson said ~13; our 1-hour-ahead GBM said ~7.3 — by balancing last week with that morning’s activity and light rain.”

## Setup (20s)
Target is hourly departures per station. Baseline = same station, same hour last week. Official Poisson adds calendar, weather, weekly lag, and station identity. App default GBM adds last-hour and rolling activity (so it’s explicitly 1-hour-ahead).

## Conflict (30s)
Weekly naive is brittle at peaks. Poisson without station ID blew up on raw weekly lags until we used log1p and one-hots. Even then, station identity was the big GLM fix. Day-ahead GBM (no last hour) loses to a simple station×hour-of-week average on MAE — horizon matters.

## Resolution (20s)
Three drivers: (1) hour-of-day / commute shape, (2) recent local activity (rolling means + lag_1h), (3) which station (Poisson). SHAP ranks hour and rolling activity above a lone weekly lag.

## One number to remember
Bay/College Mon 8am: actual 7, weekly 16, Poisson 12.7, GBM 7.3.

Quiet night check: everyone roughly agrees near zero (actual 0, GBM 0.5). Disagreements live at peaks.
