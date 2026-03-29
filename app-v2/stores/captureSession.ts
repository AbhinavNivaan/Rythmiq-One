import { create } from 'zustand'

export type NormalisedPoint = [number, number] // [x, y] in 0.0–1.0 space
export type NormalisedQuad = [NormalisedPoint, NormalisedPoint, NormalisedPoint, NormalisedPoint]

export interface CapturedImage {
  uri: string
  width: number
  height: number
}

export interface ConfirmedCrop {
  originalUri: string
  croppedUri?: string   // perspective-corrected preview if library provides it
  quad: NormalisedQuad  // normalised 0.0–1.0 relative to original image dimensions
  quadSource: 'model' | 'manual'  // 'model' = on-device TFLite detected; 'manual' = user positioned corners
}

interface CaptureSessionState {
  sessionId: string | null
  images: CapturedImage[]
  docType: string
  confirmed: (ConfirmedCrop | undefined)[]

  startSession: (images: CapturedImage[], docType: string) => string
  confirmCrop: (index: number, crop: ConfirmedCrop) => void
  replaceImage: (index: number, image: CapturedImage) => void
  clearSession: () => void
  getSession: () => { images: CapturedImage[]; docType: string; confirmed: (ConfirmedCrop | undefined)[] }
}

export const useCaptureSession = create<CaptureSessionState>((set, get) => ({
  sessionId: null,
  images: [],
  docType: '',
  confirmed: [],

  startSession: (images, docType) => {
    const sessionId = `session_${Date.now()}`
    set({ sessionId, images, docType, confirmed: [] })
    return sessionId
  },

  confirmCrop: (index, crop) => {
    set(state => {
      const confirmed = [...state.confirmed]
      confirmed[index] = crop
      return { confirmed }
    })
  },

  replaceImage: (index, image) => {
    set(state => {
      const images = [...state.images]
      images[index] = image
      // Clear the confirmed entry for this index so it re-runs detection
      const confirmed = [...state.confirmed]
      confirmed[index] = undefined
      return { images, confirmed }
    })
  },

  clearSession: () => {
    set({ sessionId: null, images: [], docType: '', confirmed: [] })
  },

  getSession: () => {
    const { images, docType, confirmed } = get()
    return { images: [...images], docType, confirmed: [...confirmed] }
  },
}))
