/**
 * DocumentDetector — on-device document corner detection via TFLite.
 *
 * Uses a YOLOv8n-pose model trained to detect 4 document corners (TL, TR, BR, BL).
 * Returns a normalised quad [0,1] or null if confidence < 0.5.
 *
 * The model is loaded once and cached for the lifetime of the app.
 * Falls back to null on any error — caller shows defaultQuad() and lets user adjust.
 */
import { loadTensorflowModel } from 'react-native-fast-tflite'
import type { TensorflowModel } from 'react-native-fast-tflite'
import type { NormalisedQuad } from '../stores/captureSession'
import { imageUriToTensor } from './imageToTensor'
import { decodeYoloPoseOutput } from './yoloPostProcess'

export interface DetectionResult {
  quad: NormalisedQuad
}

/**
 * Full-image default quad — shown when detection returns null.
 * Corners at 2% inset from each edge.
 */
export function defaultQuad(): NormalisedQuad {
  return [
    [0.02, 0.02],
    [0.98, 0.02],
    [0.98, 0.98],
    [0.02, 0.98],
  ]
}

// Module-level model cache — loaded once, reused across screens.
let _model: TensorflowModel | null = null
let _loading: Promise<TensorflowModel | null> | null = null

async function getModel(): Promise<TensorflowModel | null> {
  if (_model) return _model
  if (_loading) return _loading

  _loading = (async () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const modelAsset = require('../assets/models/doc_corners.tflite')
      const m = await loadTensorflowModel(modelAsset)
      _model = m
      return m
    } catch (e) {
      console.warn('[DocumentDetector] Failed to load model:', e)
      _loading = null
      return null
    }
  })()

  return _loading
}

/**
 * Detect document corners in a static image URI.
 * Returns DetectionResult or null on failure/low confidence.
 */
export async function detectDocument(
  imageUri: string,
  _imageWidth: number,
  _imageHeight: number,
): Promise<DetectionResult | null> {
  try {
    const model = await getModel()
    if (!model) return null

    const tensor = await imageUriToTensor(imageUri)
    const [output] = model.runSync([tensor])
    const corners = decodeYoloPoseOutput(output as Float32Array)

    if (!corners) return null
    return { quad: corners }
  } catch (e) {
    console.warn('[DocumentDetector] Detection failed:', e)
    return null
  }
}
