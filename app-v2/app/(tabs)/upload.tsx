/**
 * Upload Screen (Scan Flow)
 * 
 * Creates master documents from captured images.
 * NO portal selection - that happens in the Export flow.
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Alert,
  Image,
  FlatList,
  ActivityIndicator,
  ScrollView,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { ArrowLeft, Camera, X, Upload, CheckCircle, FileImage, PenTool, File, ChevronUp, Check } from 'lucide-react-native';
import { useMutation } from '@tanstack/react-query';
import Colors from '../../constants/Colors';
import { documentsApi } from '../../services/api';

// Theme colors
const colors = {
  inkBlack: '#070712',
  mayaBlue: '#89C7FE',
  trueCobalt: '#1A2595',
  shadowGrey: '#191B26',
  white: '#FCFEFF',
};

type DocumentCategory = 
  | 'identity' 
  | 'academic' 
  | 'address' 
  | 'financial' 
  | 'photograph' 
  | 'signature' 
  | 'certificate' 
  | 'other';

type DocumentType = string;

interface UploadProgress {
  current: number;
  total: number;
  status: 'idle' | 'uploading' | 'processing' | 'complete' | 'error';
  message: string;
}

// Document category to type mapping
const DOCUMENT_CATEGORIES: Record<DocumentCategory, { label: string; types: string[] }> = {
  identity: {
    label: 'Identity Document',
    types: ['Aadhaar Card', 'PAN Card', 'Passport', 'Voter ID', 'Driving Licence', 'Ration Card'],
  },
  academic: {
    label: 'Academic Document',
    types: ['Certificate', 'Diploma', 'Degree', 'Transcript', 'Grade Card'],
  },
  address: {
    label: 'Address Proof',
    types: ['Utility Bill', 'Ration Card', 'Voter ID', 'Bank Statement', 'Lease Agreement'],
  },
  financial: {
    label: 'Financial Document',
    types: ['Bank Statement', 'Tax Return', 'Salary Slip', 'Investment Certificate', 'Loan Document'],
  },
  photograph: {
    label: 'Photograph',
    types: ['Passport Photo', 'Profile Photo', 'ID Photo', 'Document Photo'],
  },
  signature: {
    label: 'Signature',
    types: ['Personal Signature'],
  },
  certificate: {
    label: 'Certificate',
    types: ['Birth Certificate', 'Death Certificate', 'Marriage Certificate', 'Educational Certificate'],
  },
  other: {
    label: 'Other',
    types: ['Other Document'],
  },
};

// Dropdown component
function Dropdown({ 
  isOpen, 
  onToggle, 
  label,
  selectedValue, 
  options, 
  onSelect 
}: { 
  isOpen: boolean; 
  onToggle: () => void; 
  label: string;
  selectedValue: string; 
  options: string[]; 
  onSelect: (value: string) => void;
}) {
  return (
    <View style={styles.dropdownContainer}>
      <TouchableOpacity 
        style={styles.dropdownButton}
        onPress={onToggle}
        activeOpacity={0.7}
      >
        <View style={styles.dropdownButtonContent}>
          <Text style={styles.dropdownLabel}>{label}</Text>
          <Text style={styles.dropdownValue}>{selectedValue}</Text>
        </View>
        <ChevronUp 
          size={24} 
          color={colors.mayaBlue}
          style={[styles.dropdownIcon, !isOpen && { transform: [{ rotate: '180deg' }] }]}
        />
      </TouchableOpacity>
      
      {isOpen && (
        <View style={styles.dropdownMenu}>
          {options.map((option) => (
            <TouchableOpacity
              key={option}
              style={[
                styles.dropdownOption,
                selectedValue === option && styles.dropdownOptionSelected,
              ]}
              onPress={() => {
                onSelect(option);
                onToggle();
              }}
              activeOpacity={0.7}
            >
              <Text 
                style={[
                  styles.dropdownOptionText,
                  selectedValue === option && styles.dropdownOptionTextSelected,
                ]}
              >
                {option}
              </Text>
              {selectedValue === option && (
                <Check size={20} color={colors.mayaBlue} />
              )}
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}

export default function UploadScreen() {
  const params = useLocalSearchParams<{ images?: string }>();
  const [imageUris, setImageUris] = useState<string[]>([]);
  const [documentName, setDocumentName] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<DocumentCategory>('identity');
  const [selectedType, setSelectedType] = useState<string>('Aadhaar Card');
  const [isCategoryOpen, setIsCategoryOpen] = useState(false);
  const [isTypeOpen, setIsTypeOpen] = useState(false);
  const [progress, setProgress] = useState<UploadProgress>({
    current: 0,
    total: 0,
    status: 'idle',
    message: '',
  });

  // Parse images from params
  useEffect(() => {
    if (params.images) {
      try {
        const parsed = JSON.parse(params.images);
        setImageUris(parsed);
      } catch (e) {
        console.error('Failed to parse images:', e);
      }
    }
  }, [params.images]);

  // Upload mutation - creates MASTER documents (no portal needed)
  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (imageUris.length === 0) {
        throw new Error('Please capture images first');
      }

      setProgress({
        current: 0,
        total: imageUris.length,
        status: 'uploading',
        message: 'Creating master documents...',
      });

      const jobIds: string[] = [];

      // Upload each image as a master document
      for (let i = 0; i < imageUris.length; i++) {
        const uri = imageUris[i];
        const name = documentName || `${selectedType}_${Date.now()}`;
        const filename = `${name}_${i + 1}.jpg`;
        
        setProgress({
          current: i + 1,
          total: imageUris.length,
          status: 'uploading',
          message: `Processing ${i + 1} of ${imageUris.length}...`,
        });

        // Get file blob
        const response = await fetch(uri);
        const blob = await response.blob();
        const fileSize = blob.size;

        // Map selected type to API document type
        let apiDocumentType: 'photo' | 'signature' | 'document' = 'document';
        if (selectedCategory === 'photograph') {
          apiDocumentType = 'photo';
        } else if (selectedCategory === 'signature') {
          apiDocumentType = 'signature';
        }

        // Create MASTER job (no portal schema - just "master" type)
        const { job_id, upload_url } = await documentsApi.createMasterJob(
          apiDocumentType,
          filename,
          'image/jpeg',
          fileSize
        );

        // Upload to presigned URL
        await documentsApi.uploadToPresignedUrl(upload_url, uri, 'image/jpeg');

        jobIds.push(job_id);
      }

      setProgress({
        current: imageUris.length,
        total: imageUris.length,
        status: 'processing',
        message: 'Enhancing documents...',
      });

      return jobIds;
    },
    onSuccess: (jobIds) => {
      setProgress({
        current: imageUris.length,
        total: imageUris.length,
        status: 'complete',
        message: 'Master documents created!',
      });

      // Navigate to jobs list after short delay
      setTimeout(() => {
        router.replace({
          pathname: '/(tabs)/jobs',
          params: { newJobIds: JSON.stringify(jobIds) },
        });
      }, 1500);
    },
    onError: (error: Error) => {
      setProgress({
        current: 0,
        total: 0,
        status: 'error',
        message: error.message,
      });
      Alert.alert('Upload Failed', error.message);
    },
  });

  const handleUpload = useCallback(() => {
    if (imageUris.length === 0) {
      Alert.alert('No Images', 'Please capture or select images first.');
      return;
    }
    uploadMutation.mutate();
  }, [imageUris, uploadMutation]);

  const removeImage = useCallback((index: number) => {
    setImageUris(prev => prev.filter((_, i) => i !== index));
  }, []);

  // Uploading/Processing state
  if (progress.status === 'uploading' || progress.status === 'processing') {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <View style={styles.centeredContainer}>
          <View style={styles.progressCircle}>
            <ActivityIndicator size="large" color={colors.mayaBlue} />
          </View>
          <Text style={styles.progressTitle}>
            {progress.status === 'uploading' ? 'Uploading' : 'Enhancing'}
          </Text>
          <Text style={styles.progressMessage}>{progress.message}</Text>
          {progress.total > 0 && (
            <View style={styles.progressBar}>
              <View 
                style={[
                  styles.progressFill, 
                  { width: `${(progress.current / progress.total) * 100}%` }
                ]} 
              />
            </View>
          )}
        </View>
      </SafeAreaView>
    );
  }

  // Success state
  if (progress.status === 'complete') {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <View style={styles.centeredContainer}>
          <View style={styles.successCircle}>
            <CheckCircle size={48} color="#34C759" />
          </View>
          <Text style={styles.successTitle}>Masters Created!</Text>
          <Text style={styles.successMessage}>
            Your documents are being enhanced and stored securely.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <ArrowLeft size={24} color={colors.white} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Create Master</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {/* Image Preview */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>
            Captured Images ({imageUris.length})
          </Text>
          {imageUris.length > 0 ? (
            <FlatList
              horizontal
              data={imageUris}
              keyExtractor={(_, index) => index.toString()}
              showsHorizontalScrollIndicator={false}
              renderItem={({ item, index }) => (
                <View style={styles.imagePreview}>
                  <Image source={{ uri: item }} style={styles.previewImage} />
                  <TouchableOpacity 
                    style={styles.removeButton}
                    onPress={() => removeImage(index)}
                  >
                    <X size={16} color={colors.white} />
                  </TouchableOpacity>
                </View>
              )}
              contentContainerStyle={styles.imageList}
            />
          ) : (
            <TouchableOpacity 
              style={styles.addImagesButton}
              onPress={() => router.push('/(tabs)/capture')}
            >
              <Camera size={32} color={colors.mayaBlue} />
              <Text style={styles.addImagesText}>Capture Documents</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Document Category and Type Selection */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Document Category</Text>
          <Text style={styles.sectionSubtitle}>
            What category of document is this?
          </Text>
          
          <Dropdown
            isOpen={isCategoryOpen}
            onToggle={() => setIsCategoryOpen(!isCategoryOpen)}
            label="Document Category"
            selectedValue={DOCUMENT_CATEGORIES[selectedCategory].label}
            options={Object.entries(DOCUMENT_CATEGORIES).map(([_, value]) => value.label)}
            onSelect={(label) => {
              const category = Object.entries(DOCUMENT_CATEGORIES).find(
                ([_, value]) => value.label === label
              )?.[0] as DocumentCategory;
              if (category) {
                setSelectedCategory(category);
                setSelectedType(DOCUMENT_CATEGORIES[category].types[0]);
                setIsTypeOpen(false);
              }
            }}
          />
        </View>

        {/* Document Type Selection */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Document Type</Text>
          <Text style={styles.sectionSubtitle}>
            Select the specific type of document
          </Text>
          
          <Dropdown
            isOpen={isTypeOpen}
            onToggle={() => setIsTypeOpen(!isTypeOpen)}
            label="Document Type"
            selectedValue={selectedType}
            options={DOCUMENT_CATEGORIES[selectedCategory].types}
            onSelect={setSelectedType}
          />
        </View>

        {/* Document Name (Optional) */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Name (Optional)</Text>
          <TextInput
            style={styles.nameInput}
            placeholder="e.g., Passport Photo, My Signature"
            placeholderTextColor={colors.white + '50'}
            value={documentName}
            onChangeText={setDocumentName}
          />
        </View>

        {/* Info Box */}
        <View style={styles.infoBox}>
          <Text style={styles.infoTitle}>What happens next?</Text>
          <Text style={styles.infoText}>
            • Your images will be enhanced for maximum quality{'\n'}
            • A master document will be created and stored securely{'\n'}
            • You can then export it for any portal using the Export button
          </Text>
        </View>
      </ScrollView>

      {/* Upload Button */}
      <View style={styles.footer}>
        <TouchableOpacity
          style={[
            styles.uploadButton,
            imageUris.length === 0 && styles.uploadButtonDisabled,
          ]}
          onPress={handleUpload}
          disabled={imageUris.length === 0 || uploadMutation.isPending}
        >
          {uploadMutation.isPending ? (
            <ActivityIndicator color={colors.white} />
          ) : (
            <>
              <Upload size={24} color={colors.white} />
              <Text style={styles.uploadButtonText}>
                Create Master{imageUris.length > 1 ? 's' : ''}
              </Text>
            </>
          )}
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.inkBlack,
  },
  centeredContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  progressCircle: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: colors.shadowGrey,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  progressTitle: {
    fontSize: 24,
    fontWeight: '600',
    color: colors.white,
  },
  progressMessage: {
    fontSize: 16,
    color: colors.white + 'AA',
    marginTop: 8,
    textAlign: 'center',
  },
  progressBar: {
    width: '80%',
    height: 8,
    backgroundColor: colors.shadowGrey,
    borderRadius: 4,
    marginTop: 24,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: colors.mayaBlue,
    borderRadius: 4,
  },
  successCircle: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: colors.shadowGrey,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 24,
  },
  successTitle: {
    fontSize: 24,
    fontWeight: '600',
    color: colors.white,
  },
  successMessage: {
    fontSize: 16,
    color: colors.white + 'AA',
    marginTop: 8,
    textAlign: 'center',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: colors.shadowGrey,
  },
  backButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.shadowGrey,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.white,
  },
  content: {
    flex: 1,
  },
  section: {
    marginTop: 24,
    paddingHorizontal: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.white,
    marginBottom: 4,
  },
  sectionSubtitle: {
    fontSize: 14,
    color: colors.white + '80',
    marginBottom: 16,
  },
  imageList: {
    paddingVertical: 8,
    gap: 12,
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  imagePreview: {
    position: 'relative',
    marginRight: 12,
  },
  previewImage: {
    width: 100,
    height: 130,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: colors.shadowGrey,
  },
  removeButton: {
    position: 'absolute',
    top: -8,
    right: -8,
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#FF3B30',
    justifyContent: 'center',
    alignItems: 'center',
  },
  addImagesButton: {
    backgroundColor: colors.shadowGrey,
    padding: 32,
    borderRadius: 16,
    alignItems: 'center',
    borderWidth: 2,
    borderColor: colors.mayaBlue + '30',
    borderStyle: 'dashed',
  },
  addImagesText: {
    marginTop: 8,
    fontSize: 16,
    color: colors.mayaBlue,
    fontWeight: '500',
  },
  dropdownContainer: {
    marginTop: 8,
    zIndex: 1000,
  },
  dropdownButton: {
    backgroundColor: colors.shadowGrey,
    borderRadius: 14,
    borderWidth: 2.5,
    borderColor: colors.mayaBlue,
    paddingHorizontal: 16,
    paddingVertical: 14,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  dropdownButtonContent: {
    flex: 1,
    justifyContent: 'space-between',
  },
  dropdownLabel: {
    fontSize: 13,
    color: colors.white + '80',
    marginBottom: 4,
    fontWeight: '500',
  },
  dropdownValue: {
    fontSize: 18,
    color: colors.white,
    fontWeight: '600',
  },
  dropdownIcon: {
    marginLeft: 12,
  },
  dropdownMenu: {
    backgroundColor: colors.white,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.mayaBlue + '30',
    marginTop: 8,
    overflow: 'hidden',
    maxHeight: 280,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 5,
  },
  dropdownOption: {
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: colors.mayaBlue + '15',
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  dropdownOptionSelected: {
    backgroundColor: colors.mayaBlue + '10',
  },
  dropdownOptionText: {
    color: colors.inkBlack + 'CC',
    fontSize: 15,
    flex: 1,
    fontWeight: '500',
  },
  dropdownOptionTextSelected: {
    color: colors.mayaBlue,
    fontWeight: '700',
  },
  nameInput: {
    backgroundColor: colors.shadowGrey,
    borderRadius: 12,
    padding: 16,
    fontSize: 16,
    color: colors.white,
    marginTop: 8,
  },
  infoBox: {
    margin: 16,
    marginTop: 32,
    backgroundColor: colors.trueCobalt + '30',
    borderRadius: 12,
    padding: 16,
    borderLeftWidth: 4,
    borderLeftColor: colors.trueCobalt,
  },
  infoTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.white,
    marginBottom: 8,
  },
  infoText: {
    fontSize: 14,
    color: colors.white + 'CC',
    lineHeight: 22,
  },
  footer: {
    padding: 16,
    paddingBottom: 8,
    borderTopWidth: 1,
    borderTopColor: colors.shadowGrey,
  },
  uploadButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.trueCobalt,
    padding: 16,
    borderRadius: 14,
    gap: 8,
  },
  uploadButtonDisabled: {
    backgroundColor: colors.shadowGrey,
    opacity: 0.5,
  },
  uploadButtonText: {
    color: colors.white,
    fontSize: 17,
    fontWeight: '600',
  },
});
