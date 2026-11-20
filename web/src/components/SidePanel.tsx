import { useEffect, useMemo, useRef, useState } from 'react'
import type { StationFeature, StationResponse } from '../api/types'
import { colorFor } from '../lib/colors'
import { fmt, precipLabel, tempLabel, windLabel } from '../lib/context'
import { formatHour } from '../lib/hour'
import { dataOf, useMapApp } from '../state/MapAppContext'
import { Sparkline } from './Sparkline'

function errorPhrase(pred: number | null, actual: number | null): string {
  if (pred === null || actual === null) return '–'
  const diff = pred - actual
  if (Math.abs(diff) < 0.5) return 'within half a ride'
  return `${Math.abs(diff).toFixed(1)} ${diff > 0 ? 'over' : 'under'}`
}

function HideSideButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button type="button" className="btn btn--secondary btn--icon side__hide" onClick={onClick} aria-label={label} title="Hide to free the map">
      <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
        <path d="M12.5 8h-9M12.5 8l-3-3M12.5 8l-3 3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  )
}

function StationRows({ rows, scaleMax, onSelect }: {
  rows: StationFeature[]
  scaleMax: number
  onSelect: (id: number) => void
}) {
  return (
    <ol className="busiest" id="station-list">
      {rows.map((f, i) => (
        <li key={f.properties.station_id}>
          <button
            type="button"
            className="busiest__row"
            aria-label={`${f.properties.name}, ${fmt(f.properties.gbm_pred)} predicted`}
            onClick={() => onSelect(f.properties.station_id)}
          >
            <span className="busiest__rank mono" aria-hidden="true">#{i + 1}</span>
            <span className="busiest__swatch" style={{ background: colorFor(f.properties.gbm_pred, scaleMax) }} aria-hidden="true" />
            <span className="busiest__name">{f.properties.name}</span>
            <span className="busiest__value mono">{fmt(f.properties.gbm_pred)}</span>
          </button>
        </li>
      ))}
    </ol>
  )
}

export function BusiestList() {
  const { state, actions, meta } = useMapApp()
  const [query, setQuery] = useState('')
  const collapsed = state.sideCollapsed && !state.listOpen

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const features = meta.mapData?.features.features ?? []
    if (!needle) return meta.busiest
    return [...features]
      .filter((f) => f.properties.name.toLowerCase().includes(needle))
      .sort((a, b) => (b.properties.gbm_pred ?? 0) - (a.properties.gbm_pred ?? 0))
      .slice(0, 12)
  }, [meta.busiest, meta.mapData, query])

  if (collapsed) {
    return (
      <button
        type="button"
        id="busiest-panel"
        className="edge-tab edge-tab--right panel"
        onClick={() => actions.setSideCollapsed(false)}
        aria-expanded={false}
      >
        <span className="edge-tab__label">Busiest</span>
        <span className="edge-tab__meta mono">{meta.busiest[0] ? fmt(meta.busiest[0].properties.gbm_pred) : '—'}</span>
      </button>
    )
  }

  return (
    <section
      className="panel side side--list"
      id="busiest-panel"
      aria-labelledby="busiest-title"
      data-open={state.listOpen || undefined}
    >
      <header className="side__head">
        <p className="eyebrow">This hour</p>
        <p className="side__title" id="busiest-title" role="heading" aria-level={2}>Busiest stations</p>
        <HideSideButton onClick={() => actions.setSideCollapsed(true)} label="Hide busiest stations" />
        <button type="button" className="btn btn--secondary btn--icon side__close" onClick={() => actions.setListOpen(false)} aria-label="Close the busiest stations list">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M3.5 3.5l9 9m0-9l-9 9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
        </button>
      </header>

      <label className="side__search">
        <span className="visually-hidden">Search stations</span>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search stations"
          autoComplete="off"
          enterKeyHint="search"
        />
      </label>

      {rows.length === 0 ? (
        <p className="side__hint">No stations match “{query.trim()}”.</p>
      ) : (
        <StationRows rows={rows} scaleMax={meta.scaleMax} onSelect={(id) => actions.select(id, 'list')} />
      )}
      <p className="side__hint">
        {query.trim() ? 'Matches by name, ranked by predicted departures.' : 'Select any dot on the map for its forecast, recent history and weather.'}
      </p>
    </section>
  )
}

function StationBody({ data }: { data: StationResponse }) {
  const { predictions: p, lags, context: ctx, station } = data
  return (
    <>
      <div className="figure">
        <span className="figure__value mono">{fmt(p.gbm_pred)}</span>
        <span className="figure__label">predicted departures, {formatHour(ctx.hour_ts)}</span>
      </div>

      <dl className="compare">
        <div>
          <dt>Actual</dt>
          <dd className="mono">{fmt(p.actual, 0)}</dd>
        </div>
        <div>
          <dt>Last week</dt>
          <dd className="mono">{fmt(p.weekly_naive, 0)}</dd>
        </div>
        <div>
          <dt>Poisson</dt>
          <dd className="mono">{fmt(p.poisson_pred)}</dd>
        </div>
      </dl>
      <p className="verdict">
        Model <strong>{errorPhrase(p.gbm_pred, p.actual)}</strong> · copying last week{' '}
        <strong>{errorPhrase(p.weekly_naive, p.actual)}</strong>
      </p>

      <h3>Last 24 hours</h3>
      <Sparkline series={data.series} />

      <h3>What the model looked at</h3>
      <dl className="facts">
        <div><dt>Previous hour</dt><dd className="mono">{fmt(lags.lag_1h, 0)}</dd></div>
        <div><dt>Same hour yesterday</dt><dd className="mono">{fmt(lags.lag_24h, 0)}</dd></div>
        <div><dt>Same hour last week</dt><dd className="mono">{fmt(lags.lag_168h, 0)}</dd></div>
        <div><dt>24-hour average</dt><dd className="mono">{fmt(lags.roll_mean_24h, 2)}</dd></div>
        <div><dt>Weather</dt><dd className="mono">{tempLabel(ctx.temp_c)} · {precipLabel(ctx.precip_mm)} · {windLabel(ctx.wind_speed_kmh)}</dd></div>
        <div><dt>Docks</dt><dd className="mono">{station.capacity ?? '–'}</dd></div>
      </dl>
      <p className="side__hint">
        Forecast one hour ahead: it uses rides up to the previous hour, so it cannot see this hour's count.
      </p>
    </>
  )
}

export function StationPanel() {
  const { state, actions } = useMapApp()
  const headingRef = useRef<HTMLParagraphElement>(null)
  const load = state.station
  const data = dataOf(load)
  const stationId = state.selection?.stationId
  const collapsed = state.sideCollapsed

  useEffect(() => {
    if (!collapsed) headingRef.current?.focus()
  }, [stationId, collapsed])

  const close = () => actions.select(null)

  if (collapsed) {
    const label = data?.station.name ?? (stationId != null ? `Station ${stationId}` : 'Station')
    return (
      <button
        type="button"
        className="edge-tab edge-tab--right panel"
        onClick={() => actions.setSideCollapsed(false)}
        aria-expanded={false}
        aria-controls="station-panel"
      >
        <span className="edge-tab__label">{label}</span>
        <span className="edge-tab__meta mono">{data ? fmt(data.predictions.gbm_pred) : '…'}</span>
      </button>
    )
  }

  return (
    <section className="panel side side--station" id="station-panel" aria-labelledby="station-title" data-loading={load?.status === 'loading' || undefined}>
      <header className="side__head">
        <p className="eyebrow">Station {stationId}</p>
        <p className="side__title" id="station-title" role="heading" aria-level={2} ref={headingRef} tabIndex={-1}>
          {data?.station.name ?? 'Loading station…'}
        </p>
        <HideSideButton onClick={() => actions.setSideCollapsed(true)} label="Hide station details" />
        <button type="button" className="btn btn--secondary btn--icon side__close" onClick={close} aria-label="Close station details">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M3.5 3.5l9 9m0-9l-9 9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
        </button>
      </header>
      {load?.status === 'error' ? (
        <p className="muted">{load.error.message}</p>
      ) : data ? (
        <StationBody data={data} />
      ) : (
        <div className="skeleton" aria-hidden="true" />
      )}
    </section>
  )
}
