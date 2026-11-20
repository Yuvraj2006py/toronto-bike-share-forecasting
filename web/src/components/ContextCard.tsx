import { useState } from 'react'
import { dayType, dayTypeLabel, fmt, precipLabel, tempLabel, windLabel } from '../lib/context'
import { formatClock, formatDay, formatHour } from '../lib/hour'
import { useMapApp } from '../state/MapAppContext'

function Chevron({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <path
        d={open ? 'M4 10l4-4 4 4' : 'M4 6l4 4 4-4'}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function ContextCard() {
  const { state, actions, meta } = useMapApp()
  const [detailsOpen, setDetailsOpen] = useState(false)
  const data = meta.mapData
  const ctx = data?.context ?? null
  const stats = data?.stats ?? null
  const collapsed = state.contextCollapsed

  const origin =
    meta.isNow && state.clockLocal
      ? `Your clock reads ${formatClock(state.clockLocal)}, so the map shows the same weekday and hour from the September 2024 test month.`
      : 'You picked this hour from the September 2024 test month.'

  if (collapsed) {
    return (
      <button
        type="button"
        className="edge-tab edge-tab--left panel"
        onClick={() => actions.setContextCollapsed(false)}
        aria-expanded={false}
        aria-controls="context-panel"
      >
        <span className="edge-tab__time mono">{ctx ? formatHour(ctx.hour_ts) : '—'}</span>
        <span className="edge-tab__label">Hour context</span>
      </button>
    )
  }

  return (
    <section className="hero panel context" id="context-panel" data-enter aria-labelledby="hero-title">
      <header className="context__head">
        <p className="eyebrow">Toronto Bike Share · next-hour demand</p>
        <button
          type="button"
          className="btn btn--secondary btn--icon context__hide"
          onClick={() => actions.setContextCollapsed(true)}
          aria-label="Hide hour context"
          title="Hide to free the map"
        >
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
            <path d="M3.5 8h9M3.5 8l3-3M3.5 8l3 3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </header>

      <h1 id="hero-title">
        {stats
          ? `${stats.stations_on_map} stations · next hour`
          : 'Toronto stations · next hour'}
      </h1>

      <div className="context__time" aria-live="polite">
        <span className="context__hour mono">{ctx ? formatHour(ctx.hour_ts) : '—'}</span>
        <span className="context__day">{ctx ? formatDay(ctx.hour_ts) : 'Loading the city…'}</span>
      </div>

      <ul className="chips" aria-label="Conditions the forecast used">
        <li className="chip mono">{ctx ? tempLabel(ctx.temp_c) : '—'}</li>
        <li className="chip mono">{ctx ? precipLabel(ctx.precip_mm) : '—'}</li>
        <li className="chip mono">{ctx ? windLabel(ctx.wind_speed_kmh) : '—'}</li>
        <li className="chip" data-tone={ctx ? dayType(ctx) : undefined}>
          {ctx ? dayTypeLabel(dayType(ctx)) : '—'}
        </li>
      </ul>

      <button
        type="button"
        className="context__more"
        aria-expanded={detailsOpen}
        onClick={() => setDetailsOpen((v) => !v)}
      >
        <Chevron open={detailsOpen} />
        {detailsOpen ? 'Less about this hour' : 'About this hour'}
      </button>

      {detailsOpen && (
        <div className="context__details">
          <p className="context__origin">{origin}</p>
          <dl className="totals">
            <div>
              <dt>Predicted rides</dt>
              <dd className="mono">{stats ? fmt(stats.predicted_total, 0) : '—'}</dd>
            </div>
            <div>
              <dt>Actual rides</dt>
              <dd className="mono">{stats ? fmt(stats.actual_total, 0) : '—'}</dd>
            </div>
            <div>
              <dt>Stations</dt>
              <dd className="mono">{stats ? stats.stations_on_map : '—'}</dd>
            </div>
          </dl>
        </div>
      )}
    </section>
  )
}
