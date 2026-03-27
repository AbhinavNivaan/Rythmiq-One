/**
 * yoloPostProcess — decode YOLOv8n-pose TFLite output into document corners.
 *
 * Expected output tensor shape: [1, 17, 8400]
 * Stored as a flat Float32Array of length 17 * 8400 = 142,800.
 * (Batch dimension 1 is stripped by TFLite; we receive [17, 8400] flattened.)
 *
 * Channel layout per anchor (0..8399):
 *   [0..3]   bbox cx, cy, w, h  (in 640px input space)
 *   [4]      detection confidence
 *   [5..7]   keypoint 0: x, y, visibility  (TL corner, 640px space)
 *   [8..10]  keypoint 1: x, y, visibility  (TR)
 *   [11..13] keypoint 2: x, y, visibility  (BR)
 *   [14..16] keypoint 3: x, y, visibility  (BL)
 *
 * Access pattern: output[channel * NUM_ANCHORS + anchorIdx]
 */
import type { NormalisedQuad } from '../stores/captureSession'

export const NUM_ANCHORS = 8400
export const CONFIDENCE_THRESHOLD = 0.5

const MODEL_SIZE = 640

/**
 * Decode TFLite output into 4 normalised corners [0,1] or null.
 *
 * @param output Flat Float32Array from model.runSync() — shape [17 * 8400]
 */
export function decodeYoloPoseOutput(output: Float32Array): NormalisedQuad | null {
  // Find anchor with highest confidence
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

  // Extract 4 keypoints (channels 5–16)
  const corners: [number, number][] = []
  for (let k = 0; k < 4; k++) {
    const rawX = output[(5 + k * 3 + 0) * NUM_ANCHORS + bestAnchor]
    const rawY = output[(5 + k * 3 + 1) * NUM_ANCHORS + bestAnchor]
    const x = Math.max(0, Math.min(1, rawX / MODEL_SIZE))
    const y = Math.max(0, Math.min(1, rawY / MODEL_SIZE))
    corners.push([x, y])
  }

  return corners as NormalisedQuad
}
