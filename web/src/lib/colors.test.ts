import { describe, expect, it } from 'vitest'
import { RAMP, colorFor, relativeLuminance } from './colors'

describe('demand ramp', () => {
  it('gets lighter at every stop so order survives colour-vision deficiency', () => {
    const lum = RAMP.map((stop) => relativeLuminance(stop.color))
    for (let i = 1; i < lum.length; i += 1) {
      expect(lum[i]).toBeGreaterThan(lum[i - 1] ?? 0)
    }
  })

  it('clamps at both ends of the fixed scale', () => {
    expect(colorFor(-3, 10)).toBe(RAMP[0]?.color)
    expect(colorFor(0, 10)).toBe(RAMP[0]?.color)
    expect(colorFor(50, 10)).toBe(RAMP[RAMP.length - 1]?.color)
  })

  it('interpolates between stops', () => {
    const mid = colorFor(0.075 * 10, 10)
    expect(mid).not.toBe(RAMP[0]?.color)
    expect(mid).not.toBe(RAMP[1]?.color)
    expect(mid).toMatch(/^#[0-9a-f]{6}$/)
  })

  it('treats missing values as the lowest colour', () => {
    expect(colorFor(null, 10)).toBe(RAMP[0]?.color)
  })
})
