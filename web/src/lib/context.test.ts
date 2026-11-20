import { describe, expect, it } from 'vitest'
import type { HourContext } from '../api/types'
import { dayType, dayTypeLabel, precipLabel } from './context'

const base: HourContext = {
  hour_ts: '2024-09-23T08:00:00',
  weekday: 'Monday',
  hour_of_day: 8,
  is_weekend: false,
  is_holiday: false,
  temp_c: 18.9,
  precip_mm: 1.5,
  wind_speed_kmh: 12.3,
  horizon: '1h',
}

describe('dayType', () => {
  it('ranks holiday over weekend over weekday', () => {
    expect(dayType(base)).toBe('weekday')
    expect(dayType({ ...base, is_weekend: true })).toBe('weekend')
    expect(dayType({ ...base, is_weekend: true, is_holiday: true })).toBe('holiday')
    expect(dayType({ ...base, is_holiday: true })).toBe('holiday')
  })

  it('labels each kind', () => {
    expect(dayTypeLabel('weekday')).toBe('Weekday')
    expect(dayTypeLabel('weekend')).toBe('Weekend')
    expect(dayTypeLabel('holiday')).toBe('Holiday')
  })
})

describe('precipLabel', () => {
  it('reads dry, light and heavier rain', () => {
    expect(precipLabel(0)).toBe('Dry')
    expect(precipLabel(0.05)).toBe('Dry')
    expect(precipLabel(1.5)).toBe('1.5 mm rain')
    expect(precipLabel(null)).toBe('Rain n/a')
  })
})
