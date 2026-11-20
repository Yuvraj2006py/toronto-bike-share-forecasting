-- Phase 2: hourly departures per station with zero-filled missing hours.
--
-- Grain: one row per (start_station_id, hour_ts)
-- Target: departures = COUNT of cleaned trips starting in that station-hour
--
-- Locked rulings:
--   * Zero-fill: YES — after a station exists, no trips in an hour = 0.
--   * Mid-year stations (B): each station's spine starts at its FIRST observed
--     departure hour, then runs through the global MAX hour in the data.
--     Pre-open hours are omitted so "didn't exist yet" is not treated as
--     zero demand. Trailing hours after first appearance stay (quiet ≠ real 0).

CREATE OR REPLACE TABLE hourly_departures AS
WITH trip_hours AS (
    SELECT
        start_station_id,
        date_trunc('hour', start_time) AS hour_ts
    FROM trips_clean
    WHERE start_station_id IS NOT NULL
),
counts AS (
    SELECT
        start_station_id,
        hour_ts,
        COUNT(*)::BIGINT AS departures
    FROM trip_hours
    GROUP BY 1, 2
),
station_bounds AS (
    SELECT
        start_station_id,
        MIN(hour_ts) AS first_hour,
        (SELECT MAX(hour_ts) FROM trip_hours) AS max_hour
    FROM trip_hours
    GROUP BY start_station_id
),
spine AS (
    SELECT
        sb.start_station_id,
        gs.generate_series AS hour_ts
    FROM station_bounds sb
    CROSS JOIN LATERAL generate_series(
        sb.first_hour,
        sb.max_hour,
        INTERVAL 1 HOUR
    ) AS gs
)
SELECT
    sp.start_station_id,
    sp.hour_ts,
    COALESCE(c.departures, 0)::BIGINT AS departures
FROM spine sp
LEFT JOIN counts c
  ON c.start_station_id = sp.start_station_id
 AND c.hour_ts = sp.hour_ts
ORDER BY sp.start_station_id, sp.hour_ts;
