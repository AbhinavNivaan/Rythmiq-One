/**
 * Camera Capture Screen
 * 
 * Allows users to take photos or select from gallery.
 * Supports batch capture for multi-page documents.
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Alert,
  Image,
  FlatList,
  ActivityIndicator,
  Dimensions,
  ScrollView,
} from 'react-native';
import { CameraView, useCameraPermissions, CameraType } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import { router, useLocalSearchParams } from 'expo-router';
import { useCaptureSession } from '../../stores/captureSession';
import { Ionicons } from '@expo/vector-icons';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const PREVIEW_SIZE = 60;

interface CapturedImage {
  uri: string;
  width: number;
  height: number;
}

export default function CaptureScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const [facing, setFacing] = useState<CameraType>('back');
  const [capturedImages, setCapturedImages] = useState<CapturedImage[]>([]);
  const [isCapturing, setIsCapturing] = useState(false);
  const [flashMode, setFlashMode] = useState<'off' | 'on' | 'auto'>('auto');
  const [isMuted, setIsMuted] = useState(false);
  const [selectedDocType, setSelectedDocType] = useState('Photo');
  const cameraRef = useRef<CameraView>(null);
  const params = useLocalSearchParams<{ replaceIndex?: string; sessionId?: string }>()
  const replaceIndex = params.replaceIndex !== undefined ? parseInt(params.replaceIndex, 10) : null
  const { startSession, replaceImage } = useCaptureSession()

  const docTypes = ['Photo', 'ID Card', 'Mark Sheet', 'Signature', 'Other'];

  // Get frame dimensions based on document type
  const getFrameDimensions = () => {
    switch (selectedDocType) {
      case 'Photo':
        return { top: '24%', bottom: '30%', left: '8%', right: '8%' }; // 4:3 aspect ratio
      case 'ID Card':
        return { top: '36%', bottom: '32%', left: '6%', right: '6%' }; // Wide horizontal
      case 'Mark Sheet':
        return { top: '20%', bottom: '25%', left: '10%', right: '10%' }; // Portrait A4
      case 'Signature':
        return { top: '38%', bottom: '35%', left: '12%', right: '12%' }; // Small horizontal
      case 'Other':
        return null; // No frame
      default:
        return { top: '26%', bottom: '26%', left: '8%', right: '8%' };
    }
  };

  // Request permissions on mount
  useEffect(() => {
    if (!permission?.granted) {
      requestPermission();
    }
  }, [permission, requestPermission]);

  const takePicture = useCallback(async () => {
    if (!cameraRef.current || isCapturing) return;

    setIsCapturing(true);
    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.9,
        skipProcessing: false,
      });
      
      if (photo) {
        const newImage = { uri: photo.uri, width: photo.width, height: photo.height };
        if (replaceIndex !== null) {
          // Single-shot recapture mode: replace all with just this one image
          setCapturedImages([newImage]);
        } else {
          setCapturedImages(prev => [...prev, newImage]);
        }
      }
    } catch (error) {
      console.error('Failed to take picture:', error);
      Alert.alert('Error', 'Failed to capture image. Please try again.');
    } finally {
      setIsCapturing(false);
    }
  }, [isCapturing, replaceIndex]);

  const pickFromGallery = useCallback(async () => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsMultipleSelection: true,
        quality: 0.9,
        selectionLimit: 10,
      });

      if (!result.canceled && result.assets.length > 0) {
        const newImages = result.assets.map(asset => ({
          uri: asset.uri,
          width: asset.width,
          height: asset.height,
        }));
        setCapturedImages(prev => [...prev, ...newImages]);
      }
    } catch (error) {
      console.error('Failed to pick images:', error);
      Alert.alert('Error', 'Failed to select images. Please try again.');
    }
  }, []);

  const removeImage = useCallback((index: number) => {
    setCapturedImages(prev => prev.filter((_, i) => i !== index));
  }, []);

  const toggleFlash = useCallback(() => {
    setFlashMode(current => {
      if (current === 'off') return 'on';
      if (current === 'on') return 'auto';
      return 'off';
    });
  }, []);

  const toggleCamera = useCallback(() => {
    setFacing(current => current === 'back' ? 'front' : 'back');
  }, []);

  const toggleMute = useCallback(() => {
    setIsMuted(current => !current);
  }, []);

  const proceedToUpload = useCallback(() => {
    if (capturedImages.length === 0) {
      Alert.alert('No Images', 'Please capture or select at least one image.');
      return;
    }

    if (replaceIndex !== null && params.sessionId) {
      // Recapture mode: replace one image in the existing session
      replaceImage(replaceIndex, capturedImages[0]);
      router.replace({
        pathname: '/(tabs)/crop-preview',
        params: { sessionId: params.sessionId, index: String(replaceIndex) },
      });
      return;
    }

    // Normal mode: start a new session, go to crop preview from index 0
    const sessionId = startSession(capturedImages, selectedDocType);
    router.push({
      pathname: '/(tabs)/crop-preview',
      params: { sessionId, index: '0' },
    });
  }, [capturedImages, selectedDocType, replaceIndex, params.sessionId, startSession, replaceImage]);

  // Permission handling
  if (!permission) {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="large" color="#007AFF" />
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.permissionContainer}>
        <Ionicons name="camera-outline" size={64} color="#666" />
        <Text style={styles.permissionTitle}>Camera Access Required</Text>
        <Text style={styles.permissionText}>
          We need camera access to scan your documents.
        </Text>
        <TouchableOpacity style={styles.permissionButton} onPress={requestPermission}>
          <Text style={styles.permissionButtonText}>Grant Access</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Camera View */}
      <CameraView
        ref={cameraRef}
        style={styles.camera}
        facing={facing}
        flash={flashMode}
      >
        {/* Top Controls */}
        <View style={styles.topControls}>
          <TouchableOpacity style={styles.controlButton} onPress={() => router.back()}>
            <Ionicons name="close" size={26} color="white" />
          </TouchableOpacity>

          <View style={styles.topRightControls}>
            <TouchableOpacity style={styles.controlButton} onPress={toggleMute}>
              <Ionicons
                name={isMuted ? 'volume-mute' : 'volume-medium'}
                size={20}
                color="white"
              />
            </TouchableOpacity>
            <TouchableOpacity style={styles.controlButton} onPress={toggleFlash}>
              <Ionicons
                name={flashMode === 'off' ? 'flash-off' : flashMode === 'on' ? 'flash' : 'flash-outline'}
                size={20}
                color="white"
              />
            </TouchableOpacity>
          </View>
        </View>

        {/* Bottom Controls */}
        <View style={styles.bottomControls}>
          {/* Captured images preview */}
          {capturedImages.length > 0 && (
            <View style={styles.previewContainer}>
              <FlatList
                horizontal
                data={capturedImages}
                keyExtractor={(_, index) => index.toString()}
                showsHorizontalScrollIndicator={false}
                renderItem={({ item, index }) => (
                  <View style={styles.previewItem}>
                    <Image source={{ uri: item.uri }} style={styles.previewImage} />
                    <TouchableOpacity
                      style={styles.removeButton}
                      onPress={() => removeImage(index)}
                    >
                      <Ionicons name="close-circle" size={20} color="#FF3B30" />
                    </TouchableOpacity>
                    <View style={styles.previewNumber}>
                      <Text style={styles.previewNumberText}>{index + 1}</Text>
                    </View>
                  </View>
                )}
                contentContainerStyle={styles.previewList}
              />
            </View>
          )}

          {/* Action buttons */}
          <View style={styles.actionRow}>
            {capturedImages.length > 0 ? (
              <>
                {/* Retake button - left */}
                <TouchableOpacity
                  style={styles.sideButtonWithLabel}
                  onPress={() => setCapturedImages([])}
                >
                  <Ionicons name="refresh" size={22} color="white" />
                  <Text style={styles.sideButtonLabel}>Retake</Text>
                </TouchableOpacity>

                {/* Capture button - center */}
                <TouchableOpacity
                  style={[styles.captureButton, isCapturing && styles.captureButtonDisabled]}
                  onPress={takePicture}
                  disabled={isCapturing}
                >
                  {isCapturing ? (
                    <ActivityIndicator color="white" />
                  ) : (
                    <View style={styles.captureButtonInner} />
                  )}
                </TouchableOpacity>

                {/* Done button - right */}
                <TouchableOpacity
                  style={styles.sideButtonWithLabel}
                  onPress={() => proceedToUpload()}
                >
                  <Ionicons name="checkmark-done" size={22} color="white" />
                  <Text style={styles.sideButtonLabel}>Done</Text>
                </TouchableOpacity>
              </>
            ) : (
              <>
                {/* Gallery button */}
                <TouchableOpacity style={styles.sideButton} onPress={pickFromGallery}>
                  <Ionicons name="images-outline" size={26} color="white" />
                </TouchableOpacity>

                {/* Capture button */}
                <TouchableOpacity
                  style={[styles.captureButton, isCapturing && styles.captureButtonDisabled]}
                  onPress={takePicture}
                  disabled={isCapturing}
                >
                  {isCapturing ? (
                    <ActivityIndicator color="white" />
                  ) : (
                    <View style={styles.captureButtonInner} />
                  )}
                </TouchableOpacity>

                {/* Flip camera button */}
                <TouchableOpacity style={styles.sideButtonWithLabel} onPress={toggleCamera}>
                  <Ionicons name="camera-reverse-outline" size={22} color="white" />
                  <Text style={styles.sideButtonLabel}>Flip</Text>
                </TouchableOpacity>
              </>
            )}
          </View>

          {/* Image count */}
          {capturedImages.length > 0 && (
            <Text style={styles.countText}>
              {capturedImages.length} image{capturedImages.length !== 1 ? 's' : ''} captured
            </Text>
          )}
        </View>
      </CameraView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000',
  },
  camera: {
    flex: 1,
  },
  permissionContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#1C1C1E',
    padding: 32,
  },
  permissionTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: 'white',
    marginTop: 16,
    marginBottom: 8,
  },
  permissionText: {
    fontSize: 16,
    color: '#8E8E93',
    textAlign: 'center',
    marginBottom: 24,
  },
  permissionButton: {
    backgroundColor: '#007AFF',
    paddingHorizontal: 32,
    paddingVertical: 14,
    borderRadius: 12,
  },
  permissionButtonText: {
    color: 'white',
    fontSize: 16,
    fontWeight: '600',
  },
  topControls: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: 16,
    paddingTop: 56,
  },
  controlButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(0,0,0,0.45)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  topRightControls: {
    flexDirection: 'row',
    gap: 10,
  },
  chipRow: {
    marginTop: 8,
    paddingHorizontal: 14,
    maxHeight: 42,
  },
  chipContent: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'center',
    paddingRight: 14,
  },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 16,
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
  },
  chipSelected: {
    backgroundColor: 'rgba(255,255,255,0.12)',
    borderColor: 'rgba(255,255,255,0.6)',
  },
  chipText: {
    color: 'rgba(255,255,255,0.85)',
    fontSize: 13,
    fontWeight: '600',
  },
  chipTextSelected: {
    color: 'white',
  },
  guideOverlay: {
    position: 'absolute',
    top: '22%',
    left: '8%',
    right: '8%',
    bottom: '26%',
    alignItems: 'center',
    justifyContent: 'center',
  },
  frame: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    borderRadius: 28,
    borderWidth: 3,
    borderColor: 'rgba(255, 255, 255, 0.3)',
  },
  hintContainer: {
    position: 'absolute',
    bottom: 210,
    left: 0,
    right: 0,
    alignItems: 'center',
  },
  hintText: {
    color: 'white',
    fontSize: 20,
    fontWeight: '600',
    textAlign: 'center',
  },
  bottomControls: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 24,
    paddingBottom: 12,
  },
  previewContainer: {
    paddingVertical: 8,
  },
  previewList: {
    paddingHorizontal: 16,
    gap: 8,
  },
  previewItem: {
    position: 'relative',
    marginRight: 8,
  },
  previewImage: {
    width: PREVIEW_SIZE,
    height: PREVIEW_SIZE,
    borderRadius: 8,
  },
  removeButton: {
    position: 'absolute',
    top: -6,
    right: -6,
    backgroundColor: 'white',
    borderRadius: 10,
  },
  previewNumber: {
    position: 'absolute',
    bottom: 4,
    left: 4,
    backgroundColor: 'rgba(0,0,0,0.6)',
    width: 18,
    height: 18,
    borderRadius: 9,
    justifyContent: 'center',
    alignItems: 'center',
  },
  previewNumberText: {
    color: 'white',
    fontSize: 10,
    fontWeight: '600',
  },
  actionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 16,
    paddingHorizontal: 28,
  },
  sideButton: {
    width: 54,
    height: 54,
    borderRadius: 16,
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  sideButtonWithLabel: {
    width: 70,
    alignItems: 'center',
    gap: 6,
  },
  sideButtonLabel: {
    color: 'rgba(255,255,255,0.9)',
    fontSize: 12,
    fontWeight: '600',
  },
  captureButton: {
    width: 78,
    height: 78,
    borderRadius: 39,
    backgroundColor: 'white',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 6,
    borderColor: 'rgba(255,255,255,0.25)',
  },
  captureButtonDisabled: {
    opacity: 0.5,
  },
  captureButtonInner: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: 'white',
    borderWidth: 2,
    borderColor: 'rgba(0,0,0,0.6)',
  },
  countText: {
    color: 'rgba(255,255,255,0.7)',
    fontSize: 14,
    textAlign: 'center',
  },
});
