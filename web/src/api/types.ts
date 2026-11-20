export interface HourContext {
  hour_ts: string
  weekday: string
  hour_of_day: number
  is_weekend: boolean
  is_holiday: boolean
  temp_c: number | null
  precip_mm: number | null
  wind_speed_kmh: number | null
  horizon: string
}

export interface Demo {
  from_clock: boolean
  clock_local: string | null
  note: string
}

export interface StationProps {
  station_id: number
  name: string
  gbm_pred: number | null
  actual: number | null
}

export interface StationFeature {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: [number, number] }
  properties: StationProps
}

export interface StationCollection {
  type: 'FeatureCollection'
  features: StationFeature[]
}

export interface MapStats {
  stations_on_map: number
  stations_missing_geo: number
  predicted_total: number | null
  actual_total: number | null
}

export interface MapResponse {
  context: HourContext
  demo: Demo
  stats: MapStats
  features: StationCollection
}

export interface SeriesPoint {
  hour_ts: string
  actual: number | null
  gbm_pred: number | null
  weekly_naive: number | null
}

export interface StationResponse {
  station: {
    station_id: number
    name: string
    lat: number
    lon: number
    capacity: number | null
  }
  context: HourContext
  predictions: {
    actual: number | null
    weekly_naive: number | null
    gbm_pred: number | null
    poisson_pred: number | null
  }
  lags: {
    lag_1h: number | null
    lag_24h: number | null
    lag_168h: number | null
    roll_mean_24h: number | null
  }
  series: SeriesPoint[]
}

export interface Attribution {
  label: string
  url: string
}

export interface MetaResponse {
  hour_min: string
  hour_max: string
  hours: number
  stations_on_map: number
  stations_missing_geo: number
  pred_scale_max: number
  mae_check: Record<string, unknown>
  attribution: Attribution[]
}
