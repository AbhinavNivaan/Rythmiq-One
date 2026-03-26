/**
 * Upload Screen (Scan Flow)
 * 
 * Creates master documents from captured images.
 * NO portal selection - that happens in the Export flow.
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
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
  Switch,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import { ArrowLeft, Camera, Upload, CheckCircle, FileImage, PenTool, File, ChevronUp, Check } from 'lucide-react-native';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Colors from '../../constants/Colors';
import { documentsApi, formSchemasApi } from '../../services/api';
import { startBackgroundUpload } from '../../services/backgroundUpload';
import { useCaptureSession, type ConfirmedCrop } from '../../stores/captureSession';

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

/**
 * Merges portal-specific document subtypes (seeded by form schemas) into the
 * base DOCUMENT_CATEGORIES. Returns a copy with any new types appended.
 * Uses react-query so form schemas are fetched once and cached globally.
 */
function useSeededDocumentCategories(): typeof DOCUMENT_CATEGORIES {
  const { data: schemas } = useQuery({
    queryKey: ['form-schemas'],
    queryFn: formSchemasApi.list,
    staleTime: 5 * 60 * 1000,
  });

  if (!schemas?.length) return DOCUMENT_CATEGORIES;

  // Deep-copy base categories so we never mutate the constant
  const merged: typeof DOCUMENT_CATEGORIES = {} as typeof DOCUMENT_CATEGORIES;
  for (const cat of Object.keys(DOCUMENT_CATEGORIES) as DocumentCategory[]) {
    merged[cat] = { ...DOCUMENT_CATEGORIES[cat], types: [...DOCUMENT_CATEGORIES[cat].types] };
  }

  for (const schema of schemas) {
    for (const doc of schema.document_uploads ?? []) {
      const cat = doc.document_category as DocumentCategory | undefined;
      if (!cat || !doc.seeds_document_subtypes?.length || !merged[cat]) continue;
      for (const subtype of doc.seeds_document_subtypes) {
        if (!merged[cat].types.includes(subtype)) {
          merged[cat].types.push(subtype);
        }
      }
    }
  }

  return merged;
}

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
          <ScrollView nestedScrollEnabled showsVerticalScrollIndicator>
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
          </ScrollView>
        </View>
      )}
    </View>
  );
}

export default function UploadScreen() {
  const queryClient = useQueryClient();
  const clearSession = useCaptureSession(s => s.clearSession);
  const confirmed = useCaptureSession(s => s.confirmed);
  const docType = useCaptureSession(s => s.docType);
  const confirmedCrops = confirmed.filter((c): c is ConfirmedCrop => c !== undefined);
  const imageUris = confirmedCrops.map(c => c.croppedUri ?? c.originalUri);
  const [documentName, setDocumentName] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<DocumentCategory>('identity');
  const [selectedType, setSelectedType] = useState<string>('Aadhaar Card');
  const documentCategories = useSeededDocumentCategories();
  const [isCategoryOpen, setIsCategoryOpen] = useState(false);
  const [isTypeOpen, setIsTypeOpen] = useState(false);
  const [useLossless, setUseLossless] = useState(false);

  // Pre-select document category/type from session — runs once when docType is known.
  // Must not re-run when documentCategories changes (async query resolving would
  // reset any user override back to the session default).
  const hasPreSelected = useRef(false);
  useEffect(() => {
    if (!docType || hasPreSelected.current) return;

    const docTypeToCategory: Record<string, DocumentCategory> = {
      Photo: 'photograph',
      Signature: 'signature',
      'ID Card': 'identity',
      'Mark Sheet': 'academic',
      Other: 'other',
    };

    const mappedCategory = docTypeToCategory[docType] ?? 'identity';
    setSelectedCategory(mappedCategory);
    setSelectedType(documentCategories[mappedCategory].types[0]);
    hasPreSelected.current = true;
  }, [docType, documentCategories]);

  const handleUpload = useCallback(() => {
    if (imageUris.length === 0) {
      Alert.alert('No Images', 'Please capture or select images first.');
      return;
    }

    let apiDocumentType: 'photo' | 'signature' | 'document' = 'document';
    if (selectedCategory === 'photograph') apiDocumentType = 'photo';
    else if (selectedCategory === 'signature') apiDocumentType = 'signature';

    // Fire upload in the background — it continues after navigation
    startBackgroundUpload(
      confirmedCrops,
      documentName,
      selectedCategory,
      selectedType,
      apiDocumentType,
      queryClient,
      useLossless ? 'pdf_mrc' : 'jpeg',
    );
    clearSession();

    // Go to jobs immediately so the user can see progress and explore freely
    router.replace('/(tabs)/jobs');
  }, [confirmedCrops, documentName, selectedCategory, selectedType, queryClient, useLossless, clearSession]);


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
              renderItem={({ item }) => (
                <View style={styles.imagePreview}>
                  <Image source={{ uri: item }} style={styles.previewImage} />
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
            selectedValue={documentCategories[selectedCategory].label}
            options={Object.entries(documentCategories).map(([_, value]) => value.label)}
            onSelect={(label) => {
              const category = Object.entries(documentCategories).find(
                ([_, value]) => value.label === label
              )?.[0] as DocumentCategory;
              if (category) {
                setSelectedCategory(category);
                setSelectedType(documentCategories[category].types[0]);
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
            options={documentCategories[selectedCategory].types}
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

        {/* Pipeline Toggle */}
        <View style={styles.section}>
          <View style={styles.toggleRow}>
            <View style={styles.toggleTextContainer}>
              <Text style={styles.sectionTitle}>Lossless Quality</Text>
              <Text style={styles.toggleDescription}>
                {useLossless
                  ? 'MRC PDF — JBIG2 + JPEG2000 with searchable text layer'
                  : 'Standard JPEG — fast, widely compatible'}
              </Text>
            </View>
            <Switch
              value={useLossless}
              onValueChange={setUseLossless}
              trackColor={{ false: colors.shadowGrey, true: colors.trueCobalt }}
              thumbColor={useLossless ? colors.mayaBlue : colors.white + 'CC'}
            />
          </View>
        </View>

        {/* Info Box */}
        <View style={styles.infoBox}>
          <Text style={styles.infoTitle}>What happens next?</Text>
          <Text style={styles.infoText}>
            {useLossless
              ? `• MRC pipeline: foreground separated and compressed with JBIG2\n• Background compressed with JPEG2000\n• Invisible OCR text layer embedded \u2014 document is searchable\n• Output is a PDF/A-3b archive file`
              : `• Your images will be enhanced for maximum quality\n• A master document will be created and stored securely\n• You can then export it for any portal using the Export button`}
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
          disabled={imageUris.length === 0}
        >
          <Upload size={24} color={colors.white} />
          <Text style={styles.uploadButtonText}>
            Create Master{imageUris.length > 1 ? 's' : ''}
          </Text>
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
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.shadowGrey,
    borderRadius: 14,
    padding: 16,
    marginTop: 8,
  },
  toggleTextContainer: {
    flex: 1,
    marginRight: 12,
  },
  toggleDescription: {
    fontSize: 13,
    color: colors.white + '80',
    marginTop: 4,
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
