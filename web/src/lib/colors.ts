import type { ExpressionSpecification } from 'maplibre-gl'

export interface RampStop {
  at: number
  color: string
}

// Lightness rises at every stop, so the order holds under colour-vision deficiency; no violet end.
export const RAMP: readonly RampStop[] = [
  { at: 0, color: '#35505a' },
  { at: 0.15, color: '#2f7a78' },
  { at: 0.35, color: '#3fa57d' },
  { at: 0.6, color: '#8fcf6f' },
  { at: 1, color: '#dafa9c' },
]

function hexToRgb(hex: string): [number, number, number] {
  const n = Number.parseInt(hex.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function rgbToHex([r, g, b]: [number, number, number]): string {
  return `#${[r, g, b].map((c) => Math.round(c).toString(16).padStart(2, '0')).join('')}`
}

export function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex).map((c) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }) as [number, number, number]
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function colorFor(value: number | null, scaleMax: number): string {
  const first = RAMP[0] as RampStop
  const last = RAMP[RAMP.length - 1] as RampStop
  if (value === null || !Number.isFinite(value) || scaleMax <= 0) return first.color
  const t = value / scaleMax
  if (t <= first.at) return first.color
  if (t >= last.at) return last.color
  for (let i = 1; i < RAMP.length; i += 1) {
    const lo = RAMP[i - 1] as RampStop
    const hi = RAMP[i] as RampStop
    if (t <= hi.at) {
      const f = (t - lo.at) / (hi.at - lo.at)
      const a = hexToRgb(lo.color)
      const b = hexToRgb(hi.color)
      return rgbToHex([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f])
    }
  }
  return last.color
}

export function rampGradientCss(): string {
  return `linear-gradient(90deg, ${RAMP.map((s) => `${s.color} ${s.at * 100}%`).join(', ')})`
}

const predValue: ExpressionSpecification = ['coalesce', ['get', 'gbm_pred'], 0]

export function circleColorExpression(scaleMax: number): ExpressionSpecification {
  const stops = RAMP.flatMap((s) => [s.at * scaleMax, s.color])
  return ['interpolate', ['linear'], predValue, ...stops] as ExpressionSpecification
}

// Size repeats the colour's message (not colour alone). Keep this a single data
// interpolate — MapLibre 6 silently drops layers that nest zoom×data interpolations
// inside circle-radius. Zoom scaling is applied separately by the map's camera.
export function circleRadiusExpression(scaleMax: number): ExpressionSpecification {
  return ['interpolate', ['linear'], predValue, 0, 3, scaleMax, 11]
}
