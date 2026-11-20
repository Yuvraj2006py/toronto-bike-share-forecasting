import { describe, expect, it } from 'vitest'
import { canStep, dayHours, formatClock, formatDay, formatHour, stepHour } from './hour'

describe('stepHour', () => {
  it('moves by whole hours across midnight without timezone drift', () => {
    expect(stepHour('2024-09-23T23:00:00', 1)).toBe('2024-09-24T00:00:00')
    expect(stepHour('2024-09-01T00:00:00', -1)).toBe('2024-08-31T23:00:00')
  })
})

describe('canStep', () => {
  const min = '2024-09-01T00:00:00'
  const max = '2024-09-30T23:00:00'
  it('blocks stepping outside the demo window', () => {
    expect(canStep(min, -1, min, max)).toBe(false)
    expect(canStep(max, 1, min, max)).toBe(false)
    expect(canStep('2024-09-15T12:00:00', 1, min, max)).toBe(true)
  })
})

describe('dayHours', () => {
  it('returns the 24 hours of the same calendar day', () => {
    const hours = dayHours('2024-09-23T08:00:00')
    expect(hours).toHaveLength(24)
    expect(hours[0]).toBe('2024-09-23T00:00:00')
    expect(hours[23]).toBe('2024-09-23T23:00:00')
  })
})

describe('formatting', () => {
  it('labels the demo hour by weekday and 12-hour clock', () => {
    expect(formatHour('2024-09-23T08:00:00')).toBe('Mon 8:00 AM')
    expect(formatHour('2024-09-26T22:00:00')).toBe('Thu 10:00 PM')
    expect(formatHour('2024-09-29T00:00:00')).toBe('Sun 12:00 AM')
  })
  it('formats the calendar day', () => {
    expect(formatDay('2024-09-23T08:00:00')).toBe('Sep 23, 2024')
  })
  it('formats the visitor clock from the API', () => {
    expect(formatClock('2026-11-19T22:32')).toBe('Thu 10:32 PM')
  })
})
