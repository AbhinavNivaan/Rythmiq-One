/**
 * Tests for documentDetector — TFLite adapter.
 * Mocks loadTensorflowModel and the image/post-process utilities.
 */
jest.mock('react-native-fast-tflite', () => ({
  loadTensorflowModel: jest.fn(),
}))

jest.mock('../imageToTensor', () => ({
  imageUriToTensor: jest.fn(),
}))

jest.mock('../yoloPostProcess', () => ({
  ...jest.requireActual('../yoloPostProcess'),
  decodeYoloPoseOutput: jest.fn(),
}))

import { loadTensorflowModel } from 'react-native-fast-tflite'
import { imageUriToTensor } from '../imageToTensor'
import { decodeYoloPoseOutput } from '../yoloPostProcess'
import { detectDocument, defaultQuad } from '../documentDetector'

const mockLoad = loadTensorflowModel as jest.Mock
const mockToTensor = imageUriToTensor as jest.Mock
const mockDecode = decodeYoloPoseOutput as jest.Mock

const FAKE_QUAD: [[number,number],[number,number],[number,number],[number,number]] = [
  [0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9],
]

/** A TensorWithPadding for a square 640×640 image (no letterboxing). */
const FAKE_TENSOR_WITH_PADDING = {
  tensor: new Float32Array(640 * 640 * 3),
  padLeft: 0,
  padTop: 0,
  scaledW: 640,
  scaledH: 640,
}

beforeEach(() => {
  jest.clearAllMocks()
  // Reset module-level model cache between tests
  jest.resetModules()
})

test('defaultQuad returns 4 corner points near image edges', () => {
  const q = defaultQuad()
  expect(q).toHaveLength(4)
  expect(q[0][0]).toBeLessThan(0.1)  // TL x near left
  expect(q[0][1]).toBeLessThan(0.1)  // TL y near top
})

test('returns detected quad on success', async () => {
  const fakeArrayBuffer = new Float32Array(17 * 8400).buffer
  const mockModel = { runSync: jest.fn().mockReturnValue([fakeArrayBuffer]) }
  mockLoad.mockResolvedValue(mockModel)
  mockToTensor.mockResolvedValue(FAKE_TENSOR_WITH_PADDING)
  mockDecode.mockReturnValue(FAKE_QUAD)

  const result = await detectDocument('file://photo.jpg', 1200, 900)

  expect(result).not.toBeNull()
  expect(result!.quad).toEqual(FAKE_QUAD)
})

test('passes padding from imageUriToTensor to decodeYoloPoseOutput', async () => {
  const paddedTensor = {
    tensor: new Float32Array(640 * 640 * 3),
    padLeft: 0,
    padTop: 140,
    scaledW: 640,
    scaledH: 360,
  }
  const fakeArrayBuffer = new Float32Array(17 * 8400).buffer
  const mockModel = { runSync: jest.fn().mockReturnValue([fakeArrayBuffer]) }
  mockLoad.mockResolvedValue(mockModel)
  mockToTensor.mockResolvedValue(paddedTensor)
  mockDecode.mockReturnValue(FAKE_QUAD)

  await detectDocument('file://photo.jpg', 1280, 720)

  // decodeYoloPoseOutput should receive padding (not the tensor)
  expect(mockDecode).toHaveBeenCalledWith(
    expect.any(Float32Array),
    { padLeft: 0, padTop: 140, scaledW: 640, scaledH: 360 },
  )
})

test('wraps runSync output in new Float32Array (ArrayBuffer fix)', async () => {
  const fakeArrayBuffer = new Float32Array(17 * 8400).buffer  // pure ArrayBuffer
  const mockModel = { runSync: jest.fn().mockReturnValue([fakeArrayBuffer]) }
  mockLoad.mockResolvedValue(mockModel)
  mockToTensor.mockResolvedValue(FAKE_TENSOR_WITH_PADDING)
  mockDecode.mockReturnValue(FAKE_QUAD)

  await detectDocument('file://photo.jpg', 1200, 900)

  // The first arg to decodeYoloPoseOutput must be a Float32Array, not an ArrayBuffer
  const firstArg = mockDecode.mock.calls[0][0]
  expect(firstArg).toBeInstanceOf(Float32Array)
})

test('returns null when model detects nothing (decode returns null)', async () => {
  const fakeArrayBuffer = new Float32Array(17 * 8400).buffer
  const mockModel = { runSync: jest.fn().mockReturnValue([fakeArrayBuffer]) }
  mockLoad.mockResolvedValue(mockModel)
  mockToTensor.mockResolvedValue(FAKE_TENSOR_WITH_PADDING)
  mockDecode.mockReturnValue(null)

  const result = await detectDocument('file://photo.jpg', 1200, 900)

  expect(result).toBeNull()
})

test('returns null when model loading fails', async () => {
  mockLoad.mockRejectedValue(new Error('model not found'))
  mockToTensor.mockResolvedValue(FAKE_TENSOR_WITH_PADDING)

  const result = await detectDocument('file://photo.jpg', 1200, 900)

  expect(result).toBeNull()
})
