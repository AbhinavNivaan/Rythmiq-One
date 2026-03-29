/**
 * DocumentDetector — on-device document corner detection via TFLite.
 *
 * Uses a YOLOv8n-pose model trained to detect 4 document corners (TL, TR, BR, BL).
 * Returns a normalised quad [0,1] or null if confidence < 0.5.
 *
 * The model is extracted to local device storage on first use (via expo-asset),
 * then loaded from a file:// URI. This avoids the Android GC invalidating the
 * native TFLite interpreter that occurs when loading from an HTTP Metro URL.
 *
 * Falls back to null on any error — caller shows defaultQuad() and lets user adjust.
 */
import { loadTensorflowModel } from 'react-native-fast-tflite'
import { Asset } from 'expo-asset'
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

// eslint-disable-next-line @typescript-eslint/no-require-imports
const MODEL_ASSET = require('../assets/models/doc_corners.tflite')

/** Resolves the model to a local file:// URI, downloading once if needed. */
async function getLocalModelUri(): Promise<string> {
  const asset = Asset.fromModule(MODEL_ASSET)
  await asset.downloadAsync()
  if (!asset.localUri) throw new Error('[DocumentDetector] No local URI after download')
  return asset.localUri
}

// Cache the local URI after first resolution.
let _localUriPromise: Promise<string> | null = null

/**
 * Detect document corners in a static image URI.
 * Returns DetectionResult or null on failure/low confidence.
 */
export async function detectDocument(
  imageUri: string,
  imageWidth: number,
  imageHeight: number,
): Promise<DetectionResult | null> {
  try {
    if (!_localUriPromise) _localUriPromise = getLocalModelUri()

    // Resolve local URI and preprocess image in parallel.
    const [localUri, { tensor, ...padding }] = await Promise.all([
      _localUriPromise,
      imageUriToTensor(imageUri, imageWidth, imageHeight),
    ])

    const model = await loadTensorflowModel({ url: localUri })
    const [rawOutput] = await model.run([tensor])
    const corners = decodeYoloPoseOutput(new Float32Array(rawOutput.buffer), padding)

    if (!corners) return null
    return { quad: corners }
  } catch (e) {
    console.warn('[DocumentDetector] Detection failed:', e)
    return null
  }
}
