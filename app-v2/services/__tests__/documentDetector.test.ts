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
  const mockModel = { runSync: jest.fn().mockReturnValue([new Float32Array(17 * 8400)]) }
  mockLoad.mockResolvedValue(mockModel)
  mockToTensor.mockResolvedValue(new Float32Array(640 * 640 * 3))
  mockDecode.mockReturnValue(FAKE_QUAD)

  const result = await detectDocument('file://photo.jpg', 1200, 900)

  expect(result).not.toBeNull()
  expect(result!.quad).toEqual(FAKE_QUAD)
})

test('returns null when model detects nothing (decode returns null)', async () => {
  const mockModel = { runSync: jest.fn().mockReturnValue([new Float32Array(17 * 8400)]) }
  mockLoad.mockResolvedValue(mockModel)
  mockToTensor.mockResolvedValue(new Float32Array(640 * 640 * 3))
  mockDecode.mockReturnValue(null)

  const result = await detectDocument('file://photo.jpg', 1200, 900)

  expect(result).toBeNull()
})

test('returns null when model loading fails', async () => {
  mockLoad.mockRejectedValue(new Error('model not found'))
  mockToTensor.mockResolvedValue(new Float32Array(640 * 640 * 3))

  const result = await detectDocument('file://photo.jpg', 1200, 900)

  expect(result).toBeNull()
})
