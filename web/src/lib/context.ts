import type { HourContext } from '../api/types'

export type DayType = 'weekday' | 'weekend' | 'holiday'

export function dayType(ctx: Pick<HourContext, 'is_weekend' | 'is_holiday'>): DayType {
  if (ctx.is_holiday) return 'holiday'
  if (ctx.is_weekend) return 'weekend'
  return 'weekday'
}

export function dayTypeLabel(kind: DayType): string {
  switch (kind) {
    case 'weekday':
      return 'Weekday'
    case 'weekend':
      return 'Weekend'
    case 'holiday':
      return 'Holiday'
    default: {
      const unreachable: never = kind
      return unreachable
    }
  }
}

export function precipLabel(mm: number | null): string {
  if (mm === null) return 'Rain n/a'
  if (mm < 0.1) return 'Dry'
  return `${mm.toFixed(1)} mm rain`
}

export function tempLabel(c: number | null): string {
  return c === null ? 'n/a' : `${Math.round(c)}°C`
}

export function windLabel(kmh: number | null): string {
  return kmh === null ? 'Wind n/a' : `${Math.round(kmh)} km/h wind`
}

export function fmt(value: number | null, digits = 1): string {
  if (value === null || !Number.isFinite(value)) return '–'
  return value.toFixed(digits)
}
