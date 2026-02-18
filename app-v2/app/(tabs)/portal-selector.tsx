/**
 * Portal Selector Screen (Export Flow)
 * 
 * Entry point for Export flow from Dashboard.
 * 1. User selects a target portal
 * 2. Shows what documents the portal requires
 * 3. Shows which master documents user already has
 * 4. If all required docs exist → Process and download
 * 5. If missing docs → Prompt to upload them first
 */

import React, { useState, useMemo, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  FlatList,
  TextInput,
  ActivityIndicator,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import { 
  Search, 
  ArrowLeft, 
  FileCheck, 
  ChevronRight, 
  CheckCircle, 
  AlertCircle,
  Camera,
  FileImage,
  PenTool,
} from 'lucide-react-native';
import { useQuery, useMutation } from '@tanstack/react-query';
import Colors from '../../constants/Colors';
import { schemasApi, documentsApi, PortalSchema, groupSchemasByPortal } from '../../services/api';

// Theme colors
const colors = {
  inkBlack: '#070712',
  mayaBlue: '#89C7FE',
  trueCobalt: '#1A2595',
  shadowGrey: '#191B26',
  white: '#FCFEFF',
};

// Portal category icons/colors for visual distinction
const PORTAL_CATEGORIES: Record<string, { color: string; label: string }> = {
  medical: { color: '#4CAF50', label: 'Medical' },
  engineering: { color: '#2196F3', label: 'Engineering' },
  management: { color: '#9C27B0', label: 'Management' },
  government: { color: '#FF9800', label: 'Government' },
  default: { color: colors.mayaBlue, label: 'Portal' },
};

function getPortalCategory(name: string): { color: string; label: string } {
  const lower = name.toLowerCase();
  if (lower.includes('neet') || lower.includes('aiims') || lower.includes('jipmer')) {
    return PORTAL_CATEGORIES.medical;
  }
  if (lower.includes('jee') || lower.includes('bitsat') || lower.includes('engineering')) {
    return PORTAL_CATEGORIES.engineering;
  }
  if (lower.includes('cat') || lower.includes('xat') || lower.includes('snap')) {
    return PORTAL_CATEGORIES.management;
  }
  if (lower.includes('upsc') || lower.includes('ssc') || lower.includes('bank')) {
    return PORTAL_CATEGORIES.government;
  }
  return PORTAL_CATEGORIES.default;
}

// Document requirement types
interface RequirementStatus {
  type: 'photo' | 'signature' | 'document';
  label: string;
  required: boolean;
  available: boolean;
  masterId?: string;
}

export default function PortalSelectorScreen() {
  // Optional: can be called from job-detail with a specific document
  const params = useLocalSearchParams<{ documentId?: string }>();
  const preSelectedDocId = params.documentId;
  
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPortal, setSelectedPortal] = useState<PortalSchema | null>(null);
  const [step, setStep] = useState<'select-portal' | 'review-requirements'>('select-portal');

  // Fetch available portal schemas
  const { data: schemas, isLoading: schemasLoading } = useQuery({
    queryKey: ['schemas'],
    queryFn: schemasApi.list,
  });

  // Fetch user's master documents (completed jobs)
  const { data: jobsData, isLoading: jobsLoading } = useQuery({
    queryKey: ['jobs'],
    queryFn: documentsApi.listJobs,
  });

  // Get user's available master documents
  const availableMasters = useMemo(() => {
    if (!jobsData?.jobs) return { photo: [], signature: [], document: [] };
    
    const completed = jobsData.jobs.filter(j => j.status === 'completed');
    return {
      photo: completed.filter(j => j.document_type === 'photo' || j.job_type === 'master'),
      signature: completed.filter(j => j.document_type === 'signature'),
      document: completed.filter(j => j.document_type === 'document'),
    };
  }, [jobsData]);

  // Check requirements against available masters
  const requirementStatus = useMemo((): RequirementStatus[] => {
    if (!selectedPortal?.requirements) return [];
    
    const requirements: RequirementStatus[] = [];
    
    if (selectedPortal.requirements.photo) {
      requirements.push({
        type: 'photo',
        label: 'Photo',
        required: true,
        available: availableMasters.photo.length > 0,
        masterId: availableMasters.photo[0]?.job_id,
      });
    }
    
    if (selectedPortal.requirements.signature) {
      requirements.push({
        type: 'signature',
        label: 'Signature',
        required: true,
        available: availableMasters.signature.length > 0,
        masterId: availableMasters.signature[0]?.job_id,
      });
    }
    
    return requirements;
  }, [selectedPortal, availableMasters]);

  const allRequirementsMet = useMemo(() => {
    return requirementStatus.every(r => r.available);
  }, [requirementStatus]);

  const missingRequirements = useMemo(() => {
    return requirementStatus.filter(r => !r.available);
  }, [requirementStatus]);

  // Adapt mutation
  const adaptMutation = useMutation({
    mutationFn: async () => {
      if (!selectedPortal) throw new Error('No portal selected');
      
      // Create adapt jobs for each required document
      const jobIds: string[] = [];
      
      for (const req of requirementStatus) {
        if (req.available && req.masterId) {
          const result = await documentsApi.createAdaptJob(
            req.masterId,
            selectedPortal.name
          );
          jobIds.push(result.job_id);
        }
      }
      
      return jobIds;
    },
    onSuccess: (jobIds) => {
      // Navigate to adaptation status screen
      router.push({
        pathname: '/(tabs)/adapt-status',
        params: { 
          jobIds: JSON.stringify(jobIds),
          portalName: selectedPortal?.name,
        },
      });
    },
  });

  // Filter schemas based on search
  const filteredSchemas = useMemo(() => {
    if (!schemas) return [];
    if (!searchQuery.trim()) return schemas;
    
    const query = searchQuery.toLowerCase();
    return schemas.filter(schema => 
      schema.name.toLowerCase().includes(query) ||
      (schema.portal && schema.portal.toLowerCase().includes(query))
    );
  }, [schemas, searchQuery]);

  // Group filtered schemas by portal for display
  const groupedPortals = useMemo(() => {
    const grouped = groupSchemasByPortal(filteredSchemas);
    // Convert to array of { portal, schemas } for SectionList-style rendering
    return Object.entries(grouped).map(([portal, portalSchemas]) => ({
      portal,
      schemas: portalSchemas,
      // Combine requirements from all schemas in this portal
      combinedRequirements: {
        photo: portalSchemas.some(s => s.requirements?.photo),
        signature: portalSchemas.some(s => s.requirements?.signature),
      },
    }));
  }, [filteredSchemas]);

  const handleProcess = useCallback(() => {
    adaptMutation.mutate();
  }, [adaptMutation]);

  const handleUploadMissing = useCallback((type: 'photo' | 'signature' | 'document') => {
    // Navigate to capture flow with the required document type
    router.push({
      pathname: '/(tabs)/capture',
      params: { requiredType: type },
    });
  }, []);

  // When user selects a portal group, we use its first schema as the "main" one
  // but track all schemas under that portal for combined requirements
  const handleSelectPortalGroup = useCallback((portalGroup: typeof groupedPortals[0]) => {
    // Find the first schema or create a combined one
    const firstSchema = portalGroup.schemas[0];
    // Merge requirements from all schemas in the group
    const combinedSchema: PortalSchema = {
      ...firstSchema,
      name: portalGroup.portal, // Use portal name instead of individual schema name
      requirements: {
        photo: portalGroup.schemas.find(s => s.requirements?.photo)?.requirements?.photo,
        signature: portalGroup.schemas.find(s => s.requirements?.signature)?.requirements?.signature,
      },
    };
    setSelectedPortal(combinedSchema);
    setStep('review-requirements');
  }, []);

  const renderPortalGroupItem = useCallback(({ item }: { item: typeof groupedPortals[0] }) => {
    const category = getPortalCategory(item.portal);
    
    return (
      <TouchableOpacity
        style={styles.portalItem}
        onPress={() => handleSelectPortalGroup(item)}
        activeOpacity={0.7}
      >
        <View style={[styles.portalIcon, { backgroundColor: category.color + '20' }]}>
          <FileCheck size={24} color={category.color} />
        </View>
        <View style={styles.portalInfo}>
          <Text style={styles.portalName}>{item.portal}</Text>
          <Text style={styles.portalCategory}>{category.label}</Text>
          <Text style={styles.portalRequirements}>
            Requires: {item.combinedRequirements.photo ? 'Photo' : ''}
            {item.combinedRequirements.photo && item.combinedRequirements.signature ? ' + ' : ''}
            {item.combinedRequirements.signature ? 'Signature' : ''}
          </Text>
        </View>
        <ChevronRight size={20} color={colors.white + '60'} />
      </TouchableOpacity>
    );
  }, [handleSelectPortalGroup]);

  // Step 1: Portal Selection
  if (step === 'select-portal') {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.headerButton}>
            <ArrowLeft size={24} color={colors.white} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Export for Portal</Text>
          <View style={styles.headerButton} />
        </View>

        {/* Search Bar */}
        <View style={styles.searchContainer}>
          <View style={styles.searchBar}>
            <Search size={20} color="#999" />
            <TextInput
              style={styles.searchInput}
              placeholder="Search portals..."
              placeholderTextColor="#666"
              value={searchQuery}
              onChangeText={setSearchQuery}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>
        </View>

        {/* Portal List */}
        {schemasLoading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color={colors.mayaBlue} />
            <Text style={styles.loadingText}>Loading portals...</Text>
          </View>
        ) : (
          <FlatList
            data={groupedPortals}
            keyExtractor={(item) => item.portal}
            renderItem={renderPortalGroupItem}
            contentContainerStyle={styles.listContent}
            showsVerticalScrollIndicator={false}
            ListEmptyComponent={
              <View style={styles.emptyContainer}>
                <Text style={styles.emptyText}>No portals found</Text>
                <Text style={styles.emptySubtext}>Try a different search term</Text>
              </View>
            }
          />
        )}
      </SafeAreaView>
    );
  }

  // Step 2: Review Requirements
  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => setStep('select-portal')} style={styles.headerButton}>
          <ArrowLeft size={24} color={colors.white} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>{selectedPortal?.name}</Text>
        <View style={styles.headerButton} />
      </View>

      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {/* Status Banner */}
        <View style={[
          styles.statusBanner,
          allRequirementsMet ? styles.statusBannerSuccess : styles.statusBannerWarning
        ]}>
          {allRequirementsMet ? (
            <>
              <CheckCircle size={24} color="#34C759" />
              <Text style={styles.statusText}>All required documents ready!</Text>
            </>
          ) : (
            <>
              <AlertCircle size={24} color="#FF9500" />
              <Text style={styles.statusText}>
                {missingRequirements.length} document{missingRequirements.length !== 1 ? 's' : ''} missing
              </Text>
            </>
          )}
        </View>

        {/* Requirements List */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Required Documents</Text>
          
          {requirementStatus.map((req) => (
            <View key={req.type} style={styles.requirementItem}>
              <View style={styles.requirementIcon}>
                {req.type === 'photo' && <FileImage size={24} color={colors.mayaBlue} />}
                {req.type === 'signature' && <PenTool size={24} color={colors.mayaBlue} />}
              </View>
              
              <View style={styles.requirementInfo}>
                <Text style={styles.requirementLabel}>{req.label}</Text>
                <Text style={[
                  styles.requirementStatus,
                  req.available ? styles.requirementStatusOk : styles.requirementStatusMissing
                ]}>
                  {req.available ? 'Available' : 'Not uploaded'}
                </Text>
              </View>
              
              {req.available ? (
                <CheckCircle size={24} color="#34C759" />
              ) : (
                <TouchableOpacity
                  style={styles.uploadMissingButton}
                  onPress={() => handleUploadMissing(req.type)}
                >
                  <Camera size={18} color={colors.white} />
                  <Text style={styles.uploadMissingText}>Add</Text>
                </TouchableOpacity>
              )}
            </View>
          ))}
        </View>

        {/* Portal Requirements Info */}
        {selectedPortal?.requirements && (
          <View style={styles.infoBox}>
            <Text style={styles.infoTitle}>Export Specifications</Text>
            <Text style={styles.infoText}>
              Your documents will be formatted to meet {selectedPortal.name} requirements:
              {'\n'}• Correct dimensions and resolution
              {'\n'}• File size under the limit
              {'\n'}• Proper format (JPG/PNG)
            </Text>
          </View>
        )}
      </ScrollView>

      {/* Bottom Action */}
      <View style={styles.bottomContainer}>
        {allRequirementsMet ? (
          <TouchableOpacity
            style={[styles.processButton, adaptMutation.isPending && styles.processButtonDisabled]}
            onPress={handleProcess}
            disabled={adaptMutation.isPending}
            activeOpacity={0.8}
          >
            {adaptMutation.isPending ? (
              <ActivityIndicator size="small" color={colors.white} />
            ) : (
              <>
                <Text style={styles.processButtonText}>
                  Process & Download
                </Text>
                <ChevronRight size={20} color={colors.white} />
              </>
            )}
          </TouchableOpacity>
        ) : (
          <View style={styles.missingWarning}>
            <Text style={styles.missingWarningText}>
              Upload missing documents to continue
            </Text>
          </View>
        )}
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
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: colors.shadowGrey,
  },
  headerButton: {
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
  searchContainer: {
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.shadowGrey,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 12,
  },
  searchInput: {
    flex: 1,
    fontSize: 16,
    color: colors.white,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    marginTop: 12,
    fontSize: 16,
    color: colors.white + '80',
  },
  listContent: {
    paddingHorizontal: 16,
    paddingBottom: 24,
  },
  portalItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.shadowGrey,
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    gap: 12,
  },
  portalIcon: {
    width: 48,
    height: 48,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  portalInfo: {
    flex: 1,
  },
  portalName: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.white,
  },
  portalCategory: {
    fontSize: 13,
    color: colors.white + '80',
    marginTop: 2,
  },
  portalRequirements: {
    fontSize: 12,
    color: colors.mayaBlue,
    marginTop: 4,
  },
  emptyContainer: {
    paddingVertical: 60,
    alignItems: 'center',
  },
  emptyText: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.white,
  },
  emptySubtext: {
    fontSize: 14,
    color: colors.white + '60',
    marginTop: 8,
  },
  content: {
    flex: 1,
  },
  statusBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    margin: 16,
    padding: 16,
    borderRadius: 12,
  },
  statusBannerSuccess: {
    backgroundColor: '#34C75920',
    borderWidth: 1,
    borderColor: '#34C75950',
  },
  statusBannerWarning: {
    backgroundColor: '#FF950020',
    borderWidth: 1,
    borderColor: '#FF950050',
  },
  statusText: {
    fontSize: 16,
    fontWeight: '500',
    color: colors.white,
  },
  section: {
    paddingHorizontal: 16,
    marginTop: 8,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.white,
    marginBottom: 16,
  },
  requirementItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.shadowGrey,
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    gap: 12,
  },
  requirementIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.mayaBlue + '20',
    justifyContent: 'center',
    alignItems: 'center',
  },
  requirementInfo: {
    flex: 1,
  },
  requirementLabel: {
    fontSize: 16,
    fontWeight: '500',
    color: colors.white,
  },
  requirementStatus: {
    fontSize: 13,
    marginTop: 2,
  },
  requirementStatusOk: {
    color: '#34C759',
  },
  requirementStatusMissing: {
    color: '#FF9500',
  },
  uploadMissingButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.trueCobalt,
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 8,
    gap: 6,
  },
  uploadMissingText: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.white,
  },
  infoBox: {
    margin: 16,
    marginTop: 24,
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
  bottomContainer: {
    padding: 16,
    paddingBottom: 8,
    borderTopWidth: 1,
    borderTopColor: colors.shadowGrey,
  },
  processButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.trueCobalt,
    padding: 16,
    borderRadius: 14,
    gap: 8,
  },
  processButtonDisabled: {
    opacity: 0.6,
  },
  processButtonText: {
    fontSize: 17,
    fontWeight: '600',
    color: colors.white,
  },
  missingWarning: {
    backgroundColor: colors.shadowGrey,
    padding: 16,
    borderRadius: 14,
    alignItems: 'center',
  },
  missingWarningText: {
    fontSize: 15,
    color: colors.white + '80',
  },
});
