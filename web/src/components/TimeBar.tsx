import { useEffect, useRef } from 'react'
import { rampGradientCss } from '../lib/colors'
import { dayHours, formatHour, formatHourShort, isWithin } from '../lib/hour'
import { useMapApp } from '../state/MapAppContext'

function Chevron({ dir }: { dir: 'left' | 'right' }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <path d={dir === 'left' ? 'M10 3.5 5.5 8l4.5 4.5' : 'M6 3.5 10.5 8 6 12.5'} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function Legend() {
  const { meta } = useMapApp()
  return (
    <div className="legend" aria-label={`Colour scale: predicted departures in the next hour, from 0 to ${meta.scaleMax.toFixed(0)} or more`}>
      <span className="legend__title">Predicted departures, next hour</span>
      <span className="legend__ramp" style={{ background: rampGradientCss() }} aria-hidden="true" />
      <span className="legend__ticks mono" aria-hidden="true">
        <span>0</span>
        <span>{(meta.scaleMax / 2).toFixed(0)}</span>
        <span>{meta.scaleMax.toFixed(0)}+</span>
      </span>
    </div>
  )
}

export function TimeBar() {
  const { state, actions, meta } = useMapApp()
  const hour = meta.hour
  const hours = hour ? dayHours(hour) : []
  const bounds = state.meta
  const currentRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    currentRef.current?.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' })
  }, [hour])

  return (
    <nav className="panel timebar" aria-label="Choose the hour. Arrow keys change the hour while this bar is focused.">
      <div className="timebar__controls">
        <button type="button" className="btn btn--secondary btn--icon" onClick={() => actions.step(-1)} disabled={!meta.canStepBack} aria-label="Previous hour">
          <Chevron dir="left" />
        </button>
        <span className="timebar__label mono" aria-live="polite" tabIndex={0}>{hour ? formatHour(hour) : '—'}</span>
        <button type="button" className="btn btn--secondary btn--icon" onClick={() => actions.step(1)} disabled={!meta.canStepForward} aria-label="Next hour">
          <Chevron dir="right" />
        </button>
        <button type="button" className="btn btn--primary" onClick={actions.goNow} disabled={meta.isNow} aria-pressed={meta.isNow}>
          Show my hour
        </button>
        <button
          type="button"
          className="btn btn--secondary list-toggle"
          onClick={() => {
            actions.setSideCollapsed(false)
            actions.setListOpen(true)
          }}
          aria-controls="station-list"
        >
          Busiest
        </button>
      </div>
      <ol className="hours" aria-label="Hours of this day">
        {hours.map((h) => {
          const available = !bounds || isWithin(h, bounds.hour_min, bounds.hour_max)
          const current = h === hour
          return (
            <li key={h}>
              <button
                ref={current ? currentRef : undefined}
                type="button"
                className="hours__tick"
                data-current={current || undefined}
                data-now={h === state.clockHour || undefined}
                disabled={!available}
                aria-current={current ? 'time' : undefined}
                aria-label={formatHour(h)}
                onClick={() => actions.goToHour(h)}
              >
                <span className="hours__bar" />
                <span className="hours__text mono">{formatHourShort(h)}</span>
              </button>
            </li>
          )
        })}
      </ol>
      <Legend />
    </nav>
  )
}
