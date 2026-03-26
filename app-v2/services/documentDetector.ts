/**
 * DocumentDetector — adapter for server-side document corner detection.
 *
 * Returns a quad in normalised 0.0–1.0 space relative to the original image
 * dimensions. Order: TL, TR, BR, BL.
 *
 * When detection fails or the server is unreachable, returns null.
 * The caller (crop-preview.tsx) falls back to a full-image default quad.
 */

import * as FileSystem from 'expo-file-system'
import type { NormalisedPoint, NormalisedQuad } from '../stores/captureSession'

export interface DetectionResult {
  quad: NormalisedQuad
  croppedUri?: string
}

/**
 * Full-image default quad. Used when detection fails so the user still
 * sees the image with adjustable corners at the four edges.
 */
export function defaultQuad(): NormalisedQuad {
  return [
    [0.02, 0.02],
    [0.98, 0.02],
    [0.98, 0.98],
    [0.02, 0.98],
  ]
}

/**
 * Detect document corners in a static image URI via the worker /detect endpoint.
 * Returns DetectionResult or null on failure/no detection.
 */
export async function detectDocument(
  imageUri: string,
  imageWidth: number,
  imageHeight: number,
): Promise<DetectionResult | null> {
  try {
    const API_BASE_URL =
      process.env.EXPO_PUBLIC_WORKER_URL ||
      'https://rythmiq-worker-1048753379343.asia-south1.run.app'

    const b64 = await FileSystem.readAsStringAsync(imageUri, {
      encoding: 'base64',
    })

    const resp = await fetch(`${API_BASE_URL}/detect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_b64: b64 }),
    })

    if (!resp.ok) return null

    const data = await resp.json()
    if (!data.quad || data.quad.length !== 4) return null

    return { quad: data.quad as NormalisedQuad }
  } catch (e) {
    console.warn('[DocumentDetector] detection failed:', e)
    return null
  }
}
