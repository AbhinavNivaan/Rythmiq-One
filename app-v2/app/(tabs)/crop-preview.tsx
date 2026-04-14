/**
 * Crop Preview Screen
 *
 * Shows one captured image at a time with an interactive document quad overlay.
 * User adjusts corners if needed, then confirms ("Looks Good") or recaptures.
 * Confirmed quads accumulate in the capture session store.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react'
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Image,
  Dimensions,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router, useLocalSearchParams } from 'expo-router'
import * as ImageManipulator from 'expo-image-manipulator'
import { useCaptureSession, type NormalisedQuad } from '../../stores/captureSession'
import { detectDocument, defaultQuad } from '../../services/documentDetector'
import { documentsApi } from '../../services/api'
import CropOverlay from '../../components/CropOverlay'

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window')

const colors = {
  inkBlack: '#070712',
  mayaBlue: '#89C7FE',
  trueCobalt: '#1A2595',
  shadowGrey: '#191B26',
  white: '#FCFEFF',
}

export default function CropPreviewScreen() {
  const params = useLocalSearchParams<{ sessionId?: string; index?: string }>()
  const index = parseInt(params.index ?? '0', 10)

  const { images, confirmCrop, setCategorizationResult } = useCaptureSession()
  const currentImage = images[index]

  const [isDetecting, setIsDetecting] = useState(true)
  const [isConfirming, setIsConfirming] = useState(false)
  const [currentQuad, setCurrentQuad] = useState<NormalisedQuad>(defaultQuad())
  const [quadSource, setQuadSource] = useState<'model' | 'manual'>('manual')
  const [hintVisible, setHintVisible] = useState(true)
  const hasInteracted = useRef(false)
  const hasTriggeredCategorization = useRef(false)

  const [imageLayout, setImageLayout] = useState({ width: SCREEN_WIDTH - 32, height: SCREEN_HEIGHT * 0.6 })

  useEffect(() => {
    if (!currentImage) return
    setIsDetecting(true)
    setHintVisible(true)
    hasInteracted.current = false

    detectDocument(currentImage.uri, currentImage.width, currentImage.height)
      .then(result => {
        if (result) {
          setCurrentQuad(result.quad)
          setQuadSource('model')
        } else {
          setCurrentQuad(defaultQuad())
          setQuadSource('manual')
        }
      })
      .catch(() => {
        setCurrentQuad(defaultQuad())
        setQuadSource('manual')
      })
      .finally(() => setIsDetecting(false))

    if (index === 0 && !hasTriggeredCategorization.current) {
      hasTriggeredCategorization.current = true

      // Run Gemini categorization in parallel with on-device crop detection.
      ;(async () => {
        try {
          const maxDim = 800
          const scaleFactor = Math.min(
            1,
            maxDim / Math.max(currentImage.width, currentImage.height),
          )
          const targetWidth = Math.max(1, Math.round(currentImage.width * scaleFactor))

          const compressed = await ImageManipulator.manipulateAsync(
            currentImage.uri,
            [{ resize: { width: targetWidth } }],
            { compress: 0.7, format: ImageManipulator.SaveFormat.JPEG },
          )
          const result = await documentsApi.categorize(
            compressed.uri,
            compressed.width ?? targetWidth,
            compressed.height ?? Math.max(1, Math.round(currentImage.height * scaleFactor)),
          )
          setCategorizationResult(result)
        } catch (error) {
          // Non-fatal: upload path can still proceed without categorization.
          setCategorizationResult(null)
          console.warn('[crop-preview] auto-categorization failed (non-fatal)', error)
        }
      })()
    }
  }, [currentImage?.uri])

  const handleQuadChange = useCallback((quad: NormalisedQuad) => {
    setCurrentQuad(quad)
    if (!hasInteracted.current) {
      hasInteracted.current = true
      setHintVisible(false)
    }
  }, [])

  const handleLooksGood = useCallback(async () => {
    if (!currentImage || isConfirming) return
    setIsConfirming(true)

    // Generate a bounding-box crop for the upload screen thumbnail.
    // Not perspective-corrected, but shows the document area the user confirmed.
    let previewUri: string | undefined
    try {
      const xs = currentQuad.map(p => p[0])
      const ys = currentQuad.map(p => p[1])
      const originX = Math.max(0, Math.min(...xs)) * currentImage.width
      const originY = Math.max(0, Math.min(...ys)) * currentImage.height
      const width = Math.max(1, (Math.max(...xs) - Math.min(...xs)) * currentImage.width)
      const height = Math.max(1, (Math.max(...ys) - Math.min(...ys)) * currentImage.height)
      const result = await ImageManipulator.manipulateAsync(
        currentImage.uri,
        [{ crop: { originX, originY, width, height } }],
        { compress: 0.85, format: ImageManipulator.SaveFormat.JPEG },
      )
      previewUri = result.uri
    } catch {
      // Non-fatal: fall back to original
    }

    confirmCrop(index, {
      originalUri: currentImage.uri,
      croppedUri: previewUri,
      quad: currentQuad,
      quadSource,
    })

    const nextIndex = index + 1
    if (nextIndex < images.length) {
      router.replace({
        pathname: '/(tabs)/crop-preview',
        params: { sessionId: params.sessionId, index: String(nextIndex) },
      })
    } else {
      router.replace('/(tabs)/upload')
    }
  }, [currentImage, currentQuad, isConfirming, index, images.length, confirmCrop, params.sessionId])

  const handleRecapture = useCallback(() => {
    router.push({
      pathname: '/(tabs)/capture',
      params: { replaceIndex: String(index), sessionId: params.sessionId },
    })
  }, [index, params.sessionId])

  if (!currentImage) {
    return (
      <View style={styles.container}>
        <ActivityIndicator color={colors.mayaBlue} />
      </View>
    )
  }

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.progressPill}>
          <Text style={styles.progressText}>Image {index + 1} of {images.length}</Text>
        </View>
        <Text style={styles.headerTitle}>Review Crop</Text>
        <View style={{ width: 80 }} />
      </View>

      {/* Image + overlay */}
      <View style={styles.imageContainer}>
        <View
          style={[styles.imageWrapper, { width: imageLayout.width, height: imageLayout.height }]}
          onLayout={e => {
            const { width, height } = e.nativeEvent.layout
            setImageLayout({ width, height })
          }}
        >
          <Image
            source={{ uri: currentImage.uri }}
            style={StyleSheet.absoluteFillObject}
            resizeMode="contain"
          />
          {!isDetecting && (
            <CropOverlay
              containerWidth={imageLayout.width}
              containerHeight={imageLayout.height}
              imageNativeWidth={currentImage.width}
              imageNativeHeight={currentImage.height}
              initialQuad={currentQuad}
              onQuadChange={handleQuadChange}
              imageUri={currentImage.uri}
            />
          )}
          {isDetecting && (
            <View style={styles.detectingOverlay}>
              <ActivityIndicator color={colors.mayaBlue} size="large" />
            </View>
          )}
        </View>
      </View>

      {/* Hint text */}
      <View style={styles.hintContainer}>
        {hintVisible && (
          <Text style={styles.hintText}>
            Drag the corners to adjust the crop
          </Text>
        )}
      </View>

      {/* Buttons */}
      <View style={styles.footer}>
        <TouchableOpacity style={styles.recaptureButton} onPress={handleRecapture}>
          <Text style={styles.recaptureText}>↺  Recapture</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.looksGoodButton, (isDetecting || isConfirming) && styles.buttonDisabled]}
          onPress={handleLooksGood}
          disabled={isDetecting || isConfirming}
        >
          {isConfirming
            ? <ActivityIndicator color={colors.white} size="small" />
            : <Text style={styles.looksGoodText}>Looks Good  →</Text>}
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#070712',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.shadowGrey,
  },
  progressPill: {
    backgroundColor: colors.shadowGrey,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
  },
  progressText: {
    color: colors.mayaBlue,
    fontSize: 13,
    fontWeight: '600',
  },
  headerTitle: {
    color: colors.white,
    fontSize: 16,
    fontWeight: '600',
  },
  imageContainer: {
    flex: 1,
    padding: 16,
    justifyContent: 'center',
    alignItems: 'center',
  },
  imageWrapper: {
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: '#0a0a14',
  },
  detectingOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  hintContainer: {
    height: 32,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 16,
  },
  hintText: {
    color: 'rgba(255,255,255,0.5)',
    fontSize: 13,
    textAlign: 'center',
  },
  footer: {
    flexDirection: 'row',
    gap: 12,
    padding: 16,
    paddingBottom: 8,
    borderTopWidth: 1,
    borderTopColor: colors.shadowGrey,
  },
  recaptureButton: {
    flex: 1,
    backgroundColor: colors.shadowGrey,
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.15)',
    borderRadius: 14,
    padding: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  recaptureText: {
    color: colors.white,
    fontSize: 15,
    fontWeight: '600',
  },
  looksGoodButton: {
    flex: 1,
    backgroundColor: colors.trueCobalt,
    borderRadius: 14,
    padding: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  looksGoodText: {
    color: colors.white,
    fontSize: 15,
    fontWeight: '600',
  },
  buttonDisabled: {
    opacity: 0.4,
  },
})
