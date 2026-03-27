/**
 * imageToTensor — converts an image URI to a Float32Array for TFLite input.
 *
 * Pipeline:
 *   1. Resize to MODEL_INPUT_SIZE × MODEL_INPUT_SIZE using expo-image-manipulator
 *   2. Get raw JPEG bytes via base64
 *   3. Decode JPEG → RGBA Uint8Array via jpeg-js
 *   4. Convert RGBA [0,255] → RGB Float32 [0,1]
 *
 * Output shape: [MODEL_INPUT_SIZE * MODEL_INPUT_SIZE * 3] (HWC, RGB)
 * Maps to TFLite input tensor of shape [1, 640, 640, 3].
 */
import * as ImageManipulator from 'expo-image-manipulator'
import * as jpeg from 'jpeg-js'

export const MODEL_INPUT_SIZE = 640

/**
 * Resize image at `uri` and return a Float32Array ready for TFLite.
 * Throws if the image cannot be decoded.
 */
export async function imageUriToTensor(imageUri: string): Promise<Float32Array> {
  // Step 1: Resize to 640×640, get as base64 JPEG
  const resized = await ImageManipulator.manipulateAsync(
    imageUri,
    [{ resize: { width: MODEL_INPUT_SIZE, height: MODEL_INPUT_SIZE } }],
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
  const { data: rgba } = jpeg.decode(bytes.buffer as ArrayBuffer, { useTArray: true })

  // Step 4: RGBA Uint8 [0,255] → RGB Float32 [0,1]
  const numPixels = MODEL_INPUT_SIZE * MODEL_INPUT_SIZE
  const tensor = new Float32Array(numPixels * 3)
  for (let i = 0; i < numPixels; i++) {
    tensor[i * 3 + 0] = rgba[i * 4 + 0] / 255.0  // R
    tensor[i * 3 + 1] = rgba[i * 4 + 1] / 255.0  // G
    tensor[i * 3 + 2] = rgba[i * 4 + 2] / 255.0  // B
  }

  return tensor
}
