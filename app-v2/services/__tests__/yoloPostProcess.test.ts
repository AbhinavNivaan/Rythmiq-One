import { decodeYoloPoseOutput, CONFIDENCE_THRESHOLD, NUM_ANCHORS } from '../yoloPostProcess'

const CHANNELS = 17

/** Build a Float32Array representing [1, 17, 8400] with one detection. */
function makeOutput(
  anchorIdx: number,
  conf: number,
  keypoints: [number, number][],  // 4 pairs in 640px space
): Float32Array {
  const data = new Float32Array(CHANNELS * NUM_ANCHORS)
  // Set confidence
  data[4 * NUM_ANCHORS + anchorIdx] = conf
  // Set keypoints (x, y, visibility=2)
  for (let k = 0; k < 4; k++) {
    data[(5 + k * 3 + 0) * NUM_ANCHORS + anchorIdx] = keypoints[k][0]
    data[(5 + k * 3 + 1) * NUM_ANCHORS + anchorIdx] = keypoints[k][1]
    data[(5 + k * 3 + 2) * NUM_ANCHORS + anchorIdx] = 2.0
  }
  return data
}

test('returns normalised corners for high-confidence detection', () => {
  const kps: [number, number][] = [[64, 64], [576, 64], [576, 576], [64, 576]]
  const output = makeOutput(0, 0.9, kps)

  const result = decodeYoloPoseOutput(output)

  expect(result).not.toBeNull()
  expect(result!.length).toBe(4)
  expect(result![0][0]).toBeCloseTo(64 / 640, 4)   // TL x
  expect(result![0][1]).toBeCloseTo(64 / 640, 4)   // TL y
  expect(result![2][0]).toBeCloseTo(576 / 640, 4)  // BR x
  expect(result![2][1]).toBeCloseTo(576 / 640, 4)  // BR y
})

test('returns null when all confidences below threshold', () => {
  const kps: [number, number][] = [[64, 64], [576, 64], [576, 576], [64, 576]]
  const output = makeOutput(0, CONFIDENCE_THRESHOLD - 0.01, kps)

  expect(decodeYoloPoseOutput(output)).toBeNull()
})

test('returns null for all-zero tensor', () => {
  const output = new Float32Array(CHANNELS * NUM_ANCHORS)
  expect(decodeYoloPoseOutput(output)).toBeNull()
})

test('picks the highest-confidence anchor when multiple exist', () => {
  const output = new Float32Array(CHANNELS * NUM_ANCHORS)
  // Anchor 0: conf=0.6, corners in top-left region
  output[4 * NUM_ANCHORS + 0] = 0.6
  output[(5 + 0 * 3) * NUM_ANCHORS + 0] = 10; output[(5 + 0 * 3 + 1) * NUM_ANCHORS + 0] = 10
  output[(5 + 1 * 3) * NUM_ANCHORS + 0] = 20; output[(5 + 1 * 3 + 1) * NUM_ANCHORS + 0] = 10
  output[(5 + 2 * 3) * NUM_ANCHORS + 0] = 20; output[(5 + 2 * 3 + 1) * NUM_ANCHORS + 0] = 20
  output[(5 + 3 * 3) * NUM_ANCHORS + 0] = 10; output[(5 + 3 * 3 + 1) * NUM_ANCHORS + 0] = 20
  // Anchor 1: conf=0.95, corners near full-frame
  output[4 * NUM_ANCHORS + 1] = 0.95
  output[(5 + 0 * 3) * NUM_ANCHORS + 1] = 64; output[(5 + 0 * 3 + 1) * NUM_ANCHORS + 1] = 64
  output[(5 + 1 * 3) * NUM_ANCHORS + 1] = 576; output[(5 + 1 * 3 + 1) * NUM_ANCHORS + 1] = 64
  output[(5 + 2 * 3) * NUM_ANCHORS + 1] = 576; output[(5 + 2 * 3 + 1) * NUM_ANCHORS + 1] = 576
  output[(5 + 3 * 3) * NUM_ANCHORS + 1] = 64; output[(5 + 3 * 3 + 1) * NUM_ANCHORS + 1] = 576

  const result = decodeYoloPoseOutput(output)
  // Should pick anchor 1 (higher confidence) — TL x ≈ 64/640
  expect(result![0][0]).toBeCloseTo(64 / 640, 4)
})

test('corner coordinates are clamped to [0, 1]', () => {
  // Keypoint slightly outside 640 space (can happen with augmentation artifacts)
  const kps: [number, number][] = [[-10, -10], [660, -10], [660, 660], [-10, 660]]
  const output = makeOutput(0, 0.9, kps)

  const result = decodeYoloPoseOutput(output)!
  for (const [x, y] of result) {
    expect(x).toBeGreaterThanOrEqual(0)
    expect(x).toBeLessThanOrEqual(1)
    expect(y).toBeGreaterThanOrEqual(0)
    expect(y).toBeLessThanOrEqual(1)
  }
})
