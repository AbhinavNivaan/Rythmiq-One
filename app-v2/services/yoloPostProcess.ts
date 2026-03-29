/**
 * yoloPostProcess — decode YOLOv8n-pose TFLite output into document corners.
 *
 * TFLite output shape: [1, 17, 8400] — batch dim stripped by runtime → [17, 8400] channel-first.
 * Stored as a flat Float32Array of length 17 * 8400 = 142,800.
 *
 * Channel layout (row = channel, col = anchor):
 *   ch 0..3   bbox cx, cy, w, h  (in 640px input space)
 *   ch 4      detection confidence
 *   ch 5..7   keypoint 0: x, y, visibility  (TL corner, normalised [0,1] in 640px space)
 *   ch 8..10  keypoint 1: x, y, visibility  (TR)
 *   ch 11..13 keypoint 2: x, y, visibility  (BR)
 *   ch 14..16 keypoint 3: x, y, visibility  (BL)
 *
 * NOTE: Ultralytics TFLite export normalises keypoint coords to [0,1] (not raw pixels).
 * Multiply by MODEL_SIZE before letterbox correction.
 *
 * Access pattern: output[channel * NUM_ANCHORS + anchorIdx]
 */
import type { NormalisedQuad } from '../stores/captureSession'

export const NUM_ANCHORS = 8400
export const NUM_CHANNELS = 17
export const CONFIDENCE_THRESHOLD = 0.5

const MODEL_SIZE = 640

export interface TensorPadding {
  padLeft: number
  padTop: number
  scaledW: number
  scaledH: number
}

/**
 * Decode TFLite output into 4 normalised corners [0,1] or null.
 *
 * @param output Flat Float32Array from model.runSync() — shape [17 * 8400]
 * @param padding letterbox info from imageUriToTensor — corrects for grey borders.
 */
export function decodeYoloPoseOutput(
  output: Float32Array,
  padding: TensorPadding,
): NormalisedQuad | null {
  // Find anchor with highest confidence — layout is [17, 8400] (channel-first)
  let bestConf = 0
  let bestAnchor = -1

  for (let a = 0; a < NUM_ANCHORS; a++) {
    const conf = output[4 * NUM_ANCHORS + a]
    if (conf > bestConf) {
      bestConf = conf
      bestAnchor = a
    }
  }

  if (bestConf < CONFIDENCE_THRESHOLD || bestAnchor === -1) {
    return null
  }

  // TFLite export normalises keypoints to [0,1] in 640px space.
  // Multiply by MODEL_SIZE to recover pixel coordinates before letterbox correction.
  const { padLeft, padTop, scaledW, scaledH } = padding
  const corners: [number, number][] = []
  for (let k = 0; k < 4; k++) {
    const pxX = output[(5 + k * 3 + 0) * NUM_ANCHORS + bestAnchor] * MODEL_SIZE
    const pxY = output[(5 + k * 3 + 1) * NUM_ANCHORS + bestAnchor] * MODEL_SIZE
    // Remove letterbox padding, normalise to [0,1] in original image space
    const x = Math.max(0, Math.min(1, (pxX - padLeft) / scaledW))
    const y = Math.max(0, Math.min(1, (pxY - padTop) / scaledH))
    corners.push([x, y])
  }

  return corners as NormalisedQuad
}

// Re-export MODEL_SIZE for tests that may reference it
export { MODEL_SIZE }
