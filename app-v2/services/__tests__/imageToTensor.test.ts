/**
 * Tests for imageToTensor — image URI → Float32Array [640×640×3].
 * Mocks expo-image-manipulator and jpeg-js to stay pure JS.
 */
import { imageUriToTensor, MODEL_INPUT_SIZE } from '../imageToTensor'

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

test('returns Float32Array of length 640*640*3', async () => {
  mockManipulate.mockResolvedValue({ uri: 'file://resized.jpg', base64: btoa('fakejpeg') })
  mockDecode.mockReturnValue({
    data: makeRgbaData(MODEL_INPUT_SIZE, MODEL_INPUT_SIZE),
    width: MODEL_INPUT_SIZE,
    height: MODEL_INPUT_SIZE,
  })

  const result = await imageUriToTensor('file://test.jpg')

  expect(result).toBeInstanceOf(Float32Array)
  expect(result.length).toBe(MODEL_INPUT_SIZE * MODEL_INPUT_SIZE * 3)
})

test('normalises pixel values to [0, 1]', async () => {
  mockManipulate.mockResolvedValue({ uri: 'file://resized.jpg', base64: btoa('fakejpeg') })
  mockDecode.mockReturnValue({
    data: makeRgbaData(MODEL_INPUT_SIZE, MODEL_INPUT_SIZE),
    width: MODEL_INPUT_SIZE,
    height: MODEL_INPUT_SIZE,
  })

  const result = await imageUriToTensor('file://test.jpg')

  // Solid red: R channel = 1.0, G = 0.0, B = 0.0
  expect(result[0]).toBeCloseTo(1.0)  // R
  expect(result[1]).toBeCloseTo(0.0)  // G
  expect(result[2]).toBeCloseTo(0.0)  // B
  // All values in range
  for (let i = 0; i < result.length; i++) {
    expect(result[i]).toBeGreaterThanOrEqual(0.0)
    expect(result[i]).toBeLessThanOrEqual(1.0)
  }
})

test('resizes image to MODEL_INPUT_SIZE × MODEL_INPUT_SIZE', async () => {
  mockManipulate.mockResolvedValue({ uri: 'file://resized.jpg', base64: btoa('x') })
  mockDecode.mockReturnValue({
    data: makeRgbaData(MODEL_INPUT_SIZE, MODEL_INPUT_SIZE),
    width: MODEL_INPUT_SIZE,
    height: MODEL_INPUT_SIZE,
  })

  await imageUriToTensor('file://test.jpg')

  expect(mockManipulate).toHaveBeenCalledWith(
    'file://test.jpg',
    [{ resize: { width: MODEL_INPUT_SIZE, height: MODEL_INPUT_SIZE } }],
    expect.objectContaining({ base64: true }),
  )
})

test('throws if manipulateAsync returns no base64', async () => {
  mockManipulate.mockResolvedValue({ uri: 'file://resized.jpg', base64: undefined })

  await expect(imageUriToTensor('file://test.jpg')).rejects.toThrow()
})
