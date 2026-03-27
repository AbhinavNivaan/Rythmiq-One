/**
 * Tests for imageToTensor — image URI → TensorWithPadding (letterboxed Float32Array [640×640×3]).
 * Mocks expo-image-manipulator and jpeg-js to stay pure JS.
 */
import { imageUriToTensor, MODEL_INPUT_SIZE } from '../imageToTensor'
import type { TensorWithPadding } from '../imageToTensor'

jest.mock('expo-image-manipulator', () => ({
  manipulateAsync: jest.fn(),
  SaveFormat: { JPEG: 'jpeg' },
}))

jest.mock('jpeg-js', () => ({
  decode: jest.fn(),
}))

import * as ImageManipulator from 'expo-image-manipulator'
import * as jpeg from 'jpeg-js'

const mockManipulate = ImageManipulator.manipulateAsync as jest.Mock
const mockDecode = jpeg.decode as jest.Mock

function makeRgbaData(w: number, h: number): Uint8Array {
  // Solid red image: R=255, G=0, B=0, A=255
  const data = new Uint8Array(w * h * 4)
  for (let i = 0; i < w * h; i++) {
    data[i * 4 + 0] = 255  // R
    data[i * 4 + 1] = 0    // G
    data[i * 4 + 2] = 0    // B
    data[i * 4 + 3] = 255  // A
  }
  return data
}

beforeEach(() => {
  jest.clearAllMocks()
  // atob polyfill for Jest (Node doesn't have it natively)
  global.atob = (b64: string) => Buffer.from(b64, 'base64').toString('binary')
})

test('returns TensorWithPadding with tensor of length 640*640*3', async () => {
  // Square image — no padding expected
  const W = MODEL_INPUT_SIZE
  const H = MODEL_INPUT_SIZE
  mockManipulate.mockResolvedValue({ uri: 'file://resized.jpg', base64: btoa('fakejpeg') })
  mockDecode.mockReturnValue({
    data: makeRgbaData(W, H),
    width: W,
    height: H,
  })

  const result: TensorWithPadding = await imageUriToTensor('file://test.jpg', W, H)

  expect(result.tensor).toBeInstanceOf(Float32Array)
  expect(result.tensor.length).toBe(MODEL_INPUT_SIZE * MODEL_INPUT_SIZE * 3)
})

test('returns zero padding for a square image', async () => {
  const W = 1000
  const H = 1000
  const scaledW = MODEL_INPUT_SIZE  // scale = 640/1000, scaledW = round(1000 * 0.64) = 640
  const scaledH = MODEL_INPUT_SIZE
  mockManipulate.mockResolvedValue({ uri: 'file://resized.jpg', base64: btoa('fakejpeg') })
  mockDecode.mockReturnValue({
    data: makeRgbaData(scaledW, scaledH),
    width: scaledW,
    height: scaledH,
  })

  const result = await imageUriToTensor('file://test.jpg', W, H)

  expect(result.padLeft).toBe(0)
  expect(result.padTop).toBe(0)
  expect(result.scaledW).toBe(scaledW)
  expect(result.scaledH).toBe(scaledH)
})

test('letterboxes a landscape image with padTop > 0', async () => {
  // 1280×720 landscape — scale = 640/1280 = 0.5, scaledW=640, scaledH=360
  // padTop = floor((640-360)/2) = 140, padLeft = 0
  const nativeW = 1280
  const nativeH = 720
  const scaledW = 640
  const scaledH = 360
  mockManipulate.mockResolvedValue({ uri: 'file://resized.jpg', base64: btoa('fakejpeg') })
  mockDecode.mockReturnValue({
    data: makeRgbaData(scaledW, scaledH),
    width: scaledW,
    height: scaledH,
  })

  const result = await imageUriToTensor('file://test.jpg', nativeW, nativeH)

  expect(result.padLeft).toBe(0)
  expect(result.padTop).toBe(140)
  expect(result.scaledW).toBe(scaledW)
  expect(result.scaledH).toBe(scaledH)
})

test('letterboxes a portrait image with padLeft > 0', async () => {
  // 720×1280 portrait — scale = 640/1280 = 0.5, scaledW=360, scaledH=640
  // padLeft = floor((640-360)/2) = 140, padTop = 0
  const nativeW = 720
  const nativeH = 1280
  const scaledW = 360
  const scaledH = 640
  mockManipulate.mockResolvedValue({ uri: 'file://resized.jpg', base64: btoa('fakejpeg') })
  mockDecode.mockReturnValue({
    data: makeRgbaData(scaledW, scaledH),
    width: scaledW,
    height: scaledH,
  })

  const result = await imageUriToTensor('file://test.jpg', nativeW, nativeH)

  expect(result.padLeft).toBe(140)
  expect(result.padTop).toBe(0)
  expect(result.scaledW).toBe(scaledW)
  expect(result.scaledH).toBe(scaledH)
})

test('normalises pixel values to [0, 1] in image content area', async () => {
  // Square image, no padding — all pixels are red
  const W = MODEL_INPUT_SIZE
  const H = MODEL_INPUT_SIZE
  mockManipulate.mockResolvedValue({ uri: 'file://resized.jpg', base64: btoa('fakejpeg') })
  mockDecode.mockReturnValue({
    data: makeRgbaData(W, H),
    width: W,
    height: H,
  })

  const result = await imageUriToTensor('file://test.jpg', W, H)
  const { tensor } = result

  // With no padding (padTop=0, padLeft=0), first pixel is top-left of image
  expect(tensor[0]).toBeCloseTo(1.0)  // R
  expect(tensor[1]).toBeCloseTo(0.0)  // G
  expect(tensor[2]).toBeCloseTo(0.0)  // B
  // All values in range [0, 1]
  for (let i = 0; i < tensor.length; i++) {
    expect(tensor[i]).toBeGreaterThanOrEqual(0.0)
    expect(tensor[i]).toBeLessThanOrEqual(1.0)
  }
})

test('padding area is filled with grey (≈ 0.498)', async () => {
  // Landscape 1280×720: padTop=140, padLeft=0
  const nativeW = 1280
  const nativeH = 720
  const scaledW = 640
  const scaledH = 360
  mockManipulate.mockResolvedValue({ uri: 'file://resized.jpg', base64: btoa('fakejpeg') })
  mockDecode.mockReturnValue({
    data: makeRgbaData(scaledW, scaledH),
    width: scaledW,
    height: scaledH,
  })

  const result = await imageUriToTensor('file://test.jpg', nativeW, nativeH)
  const { tensor, padTop } = result

  // First row (row 0) is padding — should be grey ≈ 0.498
  expect(tensor[0]).toBeCloseTo(0.498, 2)  // R of top-left padding pixel
  expect(tensor[1]).toBeCloseTo(0.498, 2)  // G
  expect(tensor[2]).toBeCloseTo(0.498, 2)  // B

  // Row at padTop should be red (start of image content)
  const firstContentIdx = padTop * MODEL_INPUT_SIZE * 3
  expect(tensor[firstContentIdx + 0]).toBeCloseTo(1.0)  // R
  expect(tensor[firstContentIdx + 1]).toBeCloseTo(0.0)  // G
  expect(tensor[firstContentIdx + 2]).toBeCloseTo(0.0)  // B
})

test('passes correct resize dimensions to manipulateAsync', async () => {
  // 1280×720 → scaledW=640, scaledH=360
  const nativeW = 1280
  const nativeH = 720
  mockManipulate.mockResolvedValue({ uri: 'file://resized.jpg', base64: btoa('x') })
  mockDecode.mockReturnValue({
    data: makeRgbaData(640, 360),
    width: 640,
    height: 360,
  })

  await imageUriToTensor('file://test.jpg', nativeW, nativeH)

  expect(mockManipulate).toHaveBeenCalledWith(
    'file://test.jpg',
    [{ resize: { width: 640, height: 360 } }],
    expect.objectContaining({ base64: true }),
  )
})

test('throws if manipulateAsync returns no base64', async () => {
  mockManipulate.mockResolvedValue({ uri: 'file://resized.jpg', base64: undefined })

  await expect(imageUriToTensor('file://test.jpg', 640, 640)).rejects.toThrow()
})
