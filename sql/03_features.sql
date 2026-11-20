-- Phase 3: modeling feature table (leakage-safe lags / rolling windows).
--
-- Input:  hourly_departures, weather_hourly, ontario_holidays
-- Output: features_2024
-- Grain:  one row per (start_station_id, hour_ts) — same as hourly_departures
--
-- Leakage rules encoded here:
--   * LAG(..., n) looks only at past hours.
--   * Rolling AVG/STD use ROWS BETWEEN N PRECEDING AND 1 PRECEDING
--     (explicitly excludes the current hour's departures).
--   * Weather is observed historical (POC OK); ops would need forecasts.

CREATE OR REPLACE TABLE features_2024 AS
WITH base AS (
    SELECT
        h.start_station_id,
        h.hour_ts,
        h.departures,
        EXTRACT(hour FROM h.hour_ts)::INTEGER AS hour_of_day,
        EXTRACT(dow FROM h.hour_ts)::INTEGER AS day_of_week,  -- 0=Sun .. 6=Sat
        EXTRACT(month FROM h.hour_ts)::INTEGER AS month,
        CASE
            WHEN EXTRACT(dow FROM h.hour_ts) IN (0, 6) THEN 1
            ELSE 0
        END AS is_weekend,
        CASE WHEN hol.holiday_date IS NOT NULL THEN 1 ELSE 0 END AS is_holiday,
        w.temp_c,
        w.precip_mm,
        w.wind_speed_kmh
    FROM hourly_departures h
    LEFT JOIN weather_hourly w
      ON w.hour_ts = h.hour_ts
    LEFT JOIN ontario_holidays hol
      ON hol.holiday_date = CAST(h.hour_ts AS DATE)
),
with_history AS (
    SELECT
        b.*,
        LAG(departures, 1) OVER (
            PARTITION BY start_station_id ORDER BY hour_ts
        ) AS lag_1h,
        LAG(departures, 24) OVER (
            PARTITION BY start_station_id ORDER BY hour_ts
        ) AS lag_24h,
        LAG(departures, 168) OVER (
            PARTITION BY start_station_id ORDER BY hour_ts
        ) AS lag_168h,
        -- Past-only windows: exclude current row (AND 1 PRECEDING)
        AVG(departures) OVER (
            PARTITION BY start_station_id
            ORDER BY hour_ts
            ROWS BETWEEN 24 PRECEDING AND 1 PRECEDING
        ) AS roll_mean_24h,
        STDDEV_SAMP(departures) OVER (
            PARTITION BY start_station_id
            ORDER BY hour_ts
            ROWS BETWEEN 24 PRECEDING AND 1 PRECEDING
        ) AS roll_std_24h,
        AVG(departures) OVER (
            PARTITION BY start_station_id
            ORDER BY hour_ts
            ROWS BETWEEN 168 PRECEDING AND 1 PRECEDING
        ) AS roll_mean_168h,
        STDDEV_SAMP(departures) OVER (
            PARTITION BY start_station_id
            ORDER BY hour_ts
            ROWS BETWEEN 168 PRECEDING AND 1 PRECEDING
        ) AS roll_std_168h
    FROM base b
)
SELECT
    start_station_id,
    hour_ts,
    departures,
    hour_of_day,
    day_of_week,
    month,
    is_weekend,
    is_holiday,
    lag_1h,
    lag_24h,
    lag_168h,
    roll_mean_24h,
    roll_std_24h,
    roll_mean_168h,
    roll_std_168h,
    temp_c,
    precip_mm,
    wind_speed_kmh
FROM with_history
ORDER BY start_station_id, hour_ts;
