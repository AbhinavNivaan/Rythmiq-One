/**
 * imageToTensor — converts an image URI to a Float32Array for TFLite input.
 *
 * Uses letterboxing: resize preserving aspect ratio, pad with grey to 640×640.
 * Returns both the tensor and padding metadata needed for coordinate correction.
 *
 * Output shape: [MODEL_INPUT_SIZE * MODEL_INPUT_SIZE * 3] (HWC, RGB, normalized to [0,1])
 */
import * as ImageManipulator from 'expo-image-manipulator'
import * as jpeg from 'jpeg-js'

export const MODEL_INPUT_SIZE = 640

export interface TensorWithPadding {
  tensor: Float32Array
  padLeft: number   // pixels of padding on the left  (in 640px space)
  padTop: number    // pixels of padding on the top   (in 640px space)
  scaledW: number   // width of the image content after scaling (in 640px space)
  scaledH: number   // height of the image content after scaling (in 640px space)
}

/**
 * Resize image at `uri` to fit within 640×640 with letterboxing.
 * Returns tensor + padding info for coordinate correction in post-processing.
 * Throws if the image cannot be decoded.
 */
export async function imageUriToTensor(
  imageUri: string,
  nativeWidth: number,
  nativeHeight: number,
): Promise<TensorWithPadding> {
  // Compute letterbox dimensions
  const scale = Math.min(MODEL_INPUT_SIZE / nativeWidth, MODEL_INPUT_SIZE / nativeHeight)
  const scaledW = Math.round(nativeWidth * scale)
  const scaledH = Math.round(nativeHeight * scale)
  const padLeft = Math.floor((MODEL_INPUT_SIZE - scaledW) / 2)
  const padTop = Math.floor((MODEL_INPUT_SIZE - scaledH) / 2)

  // Step 1: Resize to scaledW × scaledH (aspect-ratio preserving)
  const resized = await ImageManipulator.manipulateAsync(
    imageUri,
    [{ resize: { width: scaledW, height: scaledH } }],
    { format: ImageManipulator.SaveFormat.JPEG, base64: true },
  )

  if (!resized.base64) {
    throw new Error('[imageToTensor] manipulateAsync did not return base64 data')
  }

  // Step 2: base64 → raw bytes
  const binaryStr = atob(resized.base64)
  const bytes = new Uint8Array(binaryStr.length)
  for (let i = 0; i < binaryStr.length; i++) {
    bytes[i] = binaryStr.charCodeAt(i)
  }

  // Step 3: Decode JPEG → RGBA Uint8Array
  const { data: rgba, width: decodedW, height: decodedH } = jpeg.decode(
    bytes.buffer as ArrayBuffer,
    { useTArray: true },
  )

  // Step 4: Build padded 640×640 Float32 tensor (grey = 0.498 ≈ 127/255)
  const numPixels = MODEL_INPUT_SIZE * MODEL_INPUT_SIZE
  const tensor = new Float32Array(numPixels * 3).fill(0.498)

  for (let row = 0; row < decodedH; row++) {
    for (let col = 0; col < decodedW; col++) {
      const srcIdx = (row * decodedW + col) * 4
      const dstRow = padTop + row
      const dstCol = padLeft + col
      const dstIdx = (dstRow * MODEL_INPUT_SIZE + dstCol) * 3
      tensor[dstIdx + 0] = rgba[srcIdx + 0] / 255.0  // R
      tensor[dstIdx + 1] = rgba[srcIdx + 1] / 255.0  // G
      tensor[dstIdx + 2] = rgba[srcIdx + 2] / 255.0  // B
    }
  }

  return { tensor, padLeft, padTop, scaledW, scaledH }
}
