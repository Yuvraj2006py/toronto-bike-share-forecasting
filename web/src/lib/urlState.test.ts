import { afterEach, describe, expect, it } from 'vitest'
import { readStationParam, stationUrl } from './urlState'

describe('urlState', () => {
  afterEach(() => {
    window.history.replaceState(null, '', '/')
  })

  it('reads a positive station id from the query string', () => {
    expect(readStationParam('?station=7001')).toBe(7001)
  })

  it('rejects missing or invalid station ids', () => {
    expect(readStationParam('')).toBeNull()
    expect(readStationParam('?station=0')).toBeNull()
    expect(readStationParam('?station=abc')).toBeNull()
  })

  it('builds a station url without wiping other params', () => {
    window.history.replaceState(null, '', '/?hour=demo')
    expect(stationUrl(42)).toContain('station=42')
    expect(stationUrl(42)).toContain('hour=demo')
    expect(stationUrl(null)).not.toContain('station=')
    expect(stationUrl(null)).toContain('hour=demo')
  })
})
