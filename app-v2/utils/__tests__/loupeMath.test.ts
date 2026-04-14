import { calcImageTranslation, calcLoupePosition } from '../loupeMath'

// ─── calcImageTranslation ───────────────────────────────────────────────────

describe('calcImageTranslation', () => {
  const ZOOM = 2.5
  const LOUPE_RADIUS = 55

  it('centres the image when corner is at frame origin (no letterbox offset)', () => {
    // Corner at pixel (100, 150), frame starts at (0, 0)
    // translateX = 55 - (100 - 0) * 2.5 = 55 - 250 = -195
    // translateY = 55 - (150 - 0) * 2.5 = 55 - 375 = -320
    const result = calcImageTranslation(100, 150, 0, 0, ZOOM, LOUPE_RADIUS)
    expect(result.translateX).toBe(-195)
    expect(result.translateY).toBe(-320)
  })

  it('returns (55, 55) when corner is exactly at the frame top-left edge', () => {
    // Corner at (offsetX, offsetY) → zero frame-relative position → image pinned at loupe centre
    const result = calcImageTranslation(20, 30, 20, 30, ZOOM, LOUPE_RADIUS)
    expect(result.translateX).toBe(55)
    expect(result.translateY).toBe(55)
  })

  it('accounts for letterbox offsets correctly (non-zero offsetX/Y)', () => {
    // Corner at pixel (150, 100), frame starts at (50, 20)
    // frame-relative: (100, 80)
    // translateX = 55 - 100 * 2.5 = 55 - 250 = -195
    // translateY = 55 - 80 * 2.5  = 55 - 200 = -145
    const result = calcImageTranslation(150, 100, 50, 20, ZOOM, LOUPE_RADIUS)
    expect(result.translateX).toBe(-195)
    expect(result.translateY).toBe(-145)
  })

  it('produces positive translations for corners close to the frame origin', () => {
    // Corner at (25, 35), offset (20, 30) → frame-relative (5, 5)
    // translateX = 55 - 5 * 2.5 = 42.5
    // translateY = 55 - 5 * 2.5 = 42.5
    const result = calcImageTranslation(25, 35, 20, 30, ZOOM, LOUPE_RADIUS)
    expect(result.translateX).toBeCloseTo(42.5)
    expect(result.translateY).toBeCloseTo(42.5)
  })
})

// ─── calcLoupePosition ──────────────────────────────────────────────────────

describe('calcLoupePosition', () => {
  const CONTAINER_WIDTH = 400
  const LOUPE_DIAMETER = 110
  const FLIP_THRESHOLD = 120
  const ABOVE_OFFSET = 75
  const BELOW_OFFSET = 40
  const OFFSET_Y = 0

  it('places the loupe above the corner when corner is below flip threshold', () => {
    // activeCY = 300, not near top → loupe above
    // top = 300 - 75 - 110 = 115
    // left = clamp(0, 290, 200 - 55) = 145
    const result = calcLoupePosition(200, 300, OFFSET_Y, CONTAINER_WIDTH, LOUPE_DIAMETER, FLIP_THRESHOLD, ABOVE_OFFSET, BELOW_OFFSET)
    expect(result.top).toBe(115)
    expect(result.left).toBe(145)
  })

  it('places the loupe below the corner when corner is above flip threshold', () => {
    // activeCY = 50, near top → loupe below
    // top = 50 + 40 = 90
    // left = clamp(0, 290, 200 - 55) = 145
    const result = calcLoupePosition(200, 50, OFFSET_Y, CONTAINER_WIDTH, LOUPE_DIAMETER, FLIP_THRESHOLD, ABOVE_OFFSET, BELOW_OFFSET)
    expect(result.top).toBe(90)
    expect(result.left).toBe(145)
  })

  it('uses strict less-than for the flip threshold (exactly 120 = no flip)', () => {
    // activeCY - offsetY === 120 → NOT near top (120 < 120 is false)
    // top = 120 - 75 - 110 = -65
    const result = calcLoupePosition(200, 120, OFFSET_Y, CONTAINER_WIDTH, LOUPE_DIAMETER, FLIP_THRESHOLD, ABOVE_OFFSET, BELOW_OFFSET)
    expect(result.top).toBe(-65)
  })

  it('clamps left to 0 when corner is near the left edge', () => {
    // activeCX = 30 → unclamped left = 30 - 55 = -25 → clamped to 0
    const result = calcLoupePosition(30, 300, OFFSET_Y, CONTAINER_WIDTH, LOUPE_DIAMETER, FLIP_THRESHOLD, ABOVE_OFFSET, BELOW_OFFSET)
    expect(result.left).toBe(0)
  })

  it('clamps left to containerWidth - loupeDiameter when corner is near the right edge', () => {
    // activeCX = 380 → unclamped left = 380 - 55 = 325 → clamped to 400 - 110 = 290
    const result = calcLoupePosition(380, 300, OFFSET_Y, CONTAINER_WIDTH, LOUPE_DIAMETER, FLIP_THRESHOLD, ABOVE_OFFSET, BELOW_OFFSET)
    expect(result.left).toBe(290)
  })
})
