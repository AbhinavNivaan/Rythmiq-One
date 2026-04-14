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

export interface CategorizationResult {
  document_category: string | null
  document_subtype: string | null
  suggested_name: string | null
  suggested_owner: string | null
  confidence: number | null
}

interface CaptureSessionState {
  sessionId: string | null
  images: CapturedImage[]
  docType: string
  confirmed: (ConfirmedCrop | undefined)[]
  categorizationResult: CategorizationResult | null

  startSession: (images: CapturedImage[], docType: string) => string
  confirmCrop: (index: number, crop: ConfirmedCrop) => void
  replaceImage: (index: number, image: CapturedImage) => void
  setCategorizationResult: (result: CategorizationResult | null) => void
  clearSession: () => void
  getSession: () => {
    images: CapturedImage[]
    docType: string
    confirmed: (ConfirmedCrop | undefined)[]
    categorizationResult: CategorizationResult | null
  }
}

export const useCaptureSession = create<CaptureSessionState>((set, get) => ({
  sessionId: null,
  images: [],
  docType: '',
  confirmed: [],
  categorizationResult: null,

  startSession: (images, docType) => {
    const sessionId = `session_${Date.now()}`
    set({ sessionId, images, docType, confirmed: [], categorizationResult: null })
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

  setCategorizationResult: result => {
    set({ categorizationResult: result })
  },

  clearSession: () => {
    set({ sessionId: null, images: [], docType: '', confirmed: [], categorizationResult: null })
  },

  getSession: () => {
    const { images, docType, confirmed, categorizationResult } = get()
    return { images: [...images], docType, confirmed: [...confirmed], categorizationResult }
  },
}))
