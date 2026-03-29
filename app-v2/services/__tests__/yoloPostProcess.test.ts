import { decodeYoloPoseOutput, CONFIDENCE_THRESHOLD, NUM_ANCHORS, NUM_CHANNELS, MODEL_SIZE } from '../yoloPostProcess'
import type { TensorPadding } from '../yoloPostProcess'

/**
 * Build a Float32Array representing [17, 8400] (channel-first).
 * Keypoints are in normalised [0,1] space (TFLite export normalises by MODEL_SIZE).
 */
function makeOutput(
  anchorIdx: number,
  conf: number,
  keypoints: [number, number][],  // 4 pairs, normalised [0,1] in 640px space
): Float32Array {
  const data = new Float32Array(NUM_CHANNELS * NUM_ANCHORS)
  data[4 * NUM_ANCHORS + anchorIdx] = conf
  for (let k = 0; k < 4; k++) {
    data[(5 + k * 3 + 0) * NUM_ANCHORS + anchorIdx] = keypoints[k][0]
    data[(5 + k * 3 + 1) * NUM_ANCHORS + anchorIdx] = keypoints[k][1]
    data[(5 + k * 3 + 2) * NUM_ANCHORS + anchorIdx] = 2.0
  }
  return data
}

/** No-padding case: image fills the full 640×640 space. */
const NO_PADDING: TensorPadding = { padLeft: 0, padTop: 0, scaledW: 640, scaledH: 640 }

/** Convert pixel coord to normalised model output value. */
const px = (v: number) => v / MODEL_SIZE

test('returns normalised corners for high-confidence detection', () => {
  const kps: [number, number][] = [[px(64), px(64)], [px(576), px(64)], [px(576), px(576)], [px(64), px(576)]]
  const output = makeOutput(0, 0.9, kps)

  const result = decodeYoloPoseOutput(output, NO_PADDING)

  expect(result).not.toBeNull()
  expect(result!.length).toBe(4)
  expect(result![0][0]).toBeCloseTo(64 / 640, 4)   // TL x
  expect(result![0][1]).toBeCloseTo(64 / 640, 4)   // TL y
  expect(result![2][0]).toBeCloseTo(576 / 640, 4)  // BR x
  expect(result![2][1]).toBeCloseTo(576 / 640, 4)  // BR y
})

test('returns null when all confidences below threshold', () => {
  const kps: [number, number][] = [[px(64), px(64)], [px(576), px(64)], [px(576), px(576)], [px(64), px(576)]]
  const output = makeOutput(0, CONFIDENCE_THRESHOLD - 0.01, kps)

  expect(decodeYoloPoseOutput(output, NO_PADDING)).toBeNull()
})

test('returns null for all-zero tensor', () => {
  const output = new Float32Array(NUM_CHANNELS * NUM_ANCHORS)
  expect(decodeYoloPoseOutput(output, NO_PADDING)).toBeNull()
})

test('picks the highest-confidence anchor when multiple exist', () => {
  const output = new Float32Array(NUM_CHANNELS * NUM_ANCHORS)
  // Anchor 0: conf=0.6, corners in top-left region
  output[4 * NUM_ANCHORS + 0] = 0.6
  output[(5 + 0 * 3) * NUM_ANCHORS + 0] = px(10); output[(5 + 0 * 3 + 1) * NUM_ANCHORS + 0] = px(10)
  output[(5 + 1 * 3) * NUM_ANCHORS + 0] = px(20); output[(5 + 1 * 3 + 1) * NUM_ANCHORS + 0] = px(10)
  output[(5 + 2 * 3) * NUM_ANCHORS + 0] = px(20); output[(5 + 2 * 3 + 1) * NUM_ANCHORS + 0] = px(20)
  output[(5 + 3 * 3) * NUM_ANCHORS + 0] = px(10); output[(5 + 3 * 3 + 1) * NUM_ANCHORS + 0] = px(20)
  // Anchor 1: conf=0.95, corners near full-frame
  output[4 * NUM_ANCHORS + 1] = 0.95
  output[(5 + 0 * 3) * NUM_ANCHORS + 1] = px(64);  output[(5 + 0 * 3 + 1) * NUM_ANCHORS + 1] = px(64)
  output[(5 + 1 * 3) * NUM_ANCHORS + 1] = px(576); output[(5 + 1 * 3 + 1) * NUM_ANCHORS + 1] = px(64)
  output[(5 + 2 * 3) * NUM_ANCHORS + 1] = px(576); output[(5 + 2 * 3 + 1) * NUM_ANCHORS + 1] = px(576)
  output[(5 + 3 * 3) * NUM_ANCHORS + 1] = px(64);  output[(5 + 3 * 3 + 1) * NUM_ANCHORS + 1] = px(576)

  const result = decodeYoloPoseOutput(output, NO_PADDING)
  // Should pick anchor 1 (higher confidence) — TL x ≈ 64/640
  expect(result![0][0]).toBeCloseTo(64 / 640, 4)
})

test('corner coordinates are clamped to [0, 1]', () => {
  // Keypoint slightly outside [0,1] (can happen with augmentation artifacts)
  const kps: [number, number][] = [[px(-10), px(-10)], [px(660), px(-10)], [px(660), px(660)], [px(-10), px(660)]]
  const output = makeOutput(0, 0.9, kps)

  const result = decodeYoloPoseOutput(output, NO_PADDING)!
  for (const [x, y] of result) {
    expect(x).toBeGreaterThanOrEqual(0)
    expect(x).toBeLessThanOrEqual(1)
    expect(y).toBeGreaterThanOrEqual(0)
    expect(y).toBeLessThanOrEqual(1)
  }
})

test('applies letterbox padding offset correctly', () => {
  // Landscape image: padTop=140, padLeft=0, scaledW=640, scaledH=360
  // A keypoint at pixel (320, 180) → normalised (0.5, 0.28125)
  // Expected: x = (320-0)/640 = 0.5, y = (180-140)/360 ≈ 0.111
  const padding: TensorPadding = { padLeft: 0, padTop: 140, scaledW: 640, scaledH: 360 }
  const kps: [number, number][] = [[px(320), px(180)], [px(320), px(180)], [px(320), px(180)], [px(320), px(180)]]
  const output = makeOutput(0, 0.9, kps)

  const result = decodeYoloPoseOutput(output, padding)!
  expect(result[0][0]).toBeCloseTo(320 / 640, 4)
  expect(result[0][1]).toBeCloseTo((180 - 140) / 360, 4)
})

test('applies portrait letterbox padding offset correctly', () => {
  // Portrait image: padLeft=140, padTop=0, scaledW=360, scaledH=640
  // A keypoint at pixel (140, 320) → normalised (0.21875, 0.5)
  // Expected: x = (140-140)/360 = 0.0, y = (320-0)/640 = 0.5
  const padding: TensorPadding = { padLeft: 140, padTop: 0, scaledW: 360, scaledH: 640 }
  const kps: [number, number][] = [[px(140), px(320)], [px(140), px(320)], [px(140), px(320)], [px(140), px(320)]]
  const output = makeOutput(0, 0.9, kps)

  const result = decodeYoloPoseOutput(output, padding)!
  expect(result[0][0]).toBeCloseTo(0.0, 4)
  expect(result[0][1]).toBeCloseTo(0.5, 4)
})
