import type { SeriesPoint } from '../api/types'
import { formatHourShort } from '../lib/hour'

const W = 300
const H = 96
const PAD = { top: 8, right: 8, bottom: 18, left: 8 }

type SeriesKey = 'actual' | 'gbm_pred' | 'weekly_naive'

function pathFor(points: SeriesPoint[], key: SeriesKey, yMax: number): string {
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const step = points.length > 1 ? innerW / (points.length - 1) : 0
  let d = ''
  let pen = false
  points.forEach((p, i) => {
    const v = p[key]
    if (v === null) {
      pen = false
      return
    }
    const x = PAD.left + i * step
    const y = PAD.top + innerH - (v / yMax) * innerH
    d += `${pen ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`
    pen = true
  })
  return d
}

export function Sparkline({ series }: { series: SeriesPoint[] }) {
  if (series.length < 2) return <p className="muted">Not enough history for a trend.</p>
  const values = series.flatMap((p) => [p.actual, p.gbm_pred, p.weekly_naive]).filter((v): v is number => v !== null)
  const yMax = Math.max(1, ...values)
  const first = series[0] as SeriesPoint
  const last = series[series.length - 1] as SeriesPoint
  const lastX = W - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const lastY = last.gbm_pred === null ? null : PAD.top + innerH - (last.gbm_pred / yMax) * innerH

  return (
    <figure className="spark">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Departures over the last ${series.length} hours: actual, model prediction and last week's count`}>
        <line x1={PAD.left} x2={W - PAD.right} y1={H - PAD.bottom} y2={H - PAD.bottom} className="spark__axis" />
        <path d={pathFor(series, 'weekly_naive', yMax)} className="spark__weekly" />
        <path d={pathFor(series, 'actual', yMax)} className="spark__actual" />
        <path d={pathFor(series, 'gbm_pred', yMax)} className="spark__gbm" />
        {lastY !== null && <circle cx={lastX} cy={lastY} r={3.5} className="spark__dot" />}
        <text x={PAD.left} y={H - 4} className="spark__tick">{formatHourShort(first.hour_ts)}</text>
        <text x={W - PAD.right} y={H - 4} textAnchor="end" className="spark__tick">{formatHourShort(last.hour_ts)}</text>
      </svg>
      <ul className="spark__key" aria-hidden="true">
        <li><i className="key key--gbm" />Model</li>
        <li><i className="key key--actual" />Actual</li>
        <li><i className="key key--weekly" />Last week</li>
      </ul>
    </figure>
  )
}
