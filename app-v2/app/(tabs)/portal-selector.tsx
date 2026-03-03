/**
 * Portal Selector Screen (Export Flow)
 *
 * Entry point for Export flow from Dashboard.
 * 1. User selects a target form (e.g. "NEET 2026")
 * 2. Shows the full document checklist from form_schemas
 * 3. Shows which documents the user already has in their vault
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
  Switch,
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
  FileText,
  ArrowLeftRight,
} from 'lucide-react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useFocusEffect } from 'expo-router';
import { portalsApi, documentsApi, Portal, FormSchema, FormSchemaDocUpload } from '../../services/api';

// Theme colors
const colors = {
  inkBlack: '#070712',
  mayaBlue: '#89C7FE',
  trueCobalt: '#1A2595',
  shadowGrey: '#191B26',
  white: '#FCFEFF',
};

// Category display config
const CATEGORY_DISPLAY: Record<string, { color: string; label: string }> = {
  medical_entrance:     { color: '#4CAF50', label: 'Medical' },
  engineering_entrance: { color: '#2196F3', label: 'Engineering' },
  management_entrance:  { color: '#9C27B0', label: 'Management' },
  government:           { color: '#FF9800', label: 'Government' },
  recruitment:          { color: '#FF9800', label: 'Recruitment' },
  government_id:        { color: '#607D8B', label: 'Govt ID' },
  banking:              { color: '#F44336', label: 'Banking' },
  railways:             { color: '#795548', label: 'Railways' },
};

function getCategoryDisplay(category: string): { color: string; label: string } {
  return CATEGORY_DISPLAY[category] ?? { color: colors.mayaBlue, label: 'Exam' };
}

/**
 * Client-side fallback annotations for well-known doc_ids.
 * Used when the API-returned form schema body predates the document_category/
 * document_subtype fields (i.e. the DB schema hasn't been re-injected yet).
 * The API schema fields always take precedence; this is purely a fallback.
 */
const DOC_ID_ANNOTATIONS: Record<string, Pick<FormSchemaDocUpload, 'document_category' | 'document_subtype'>> = {
  photograph_passport:     { document_category: 'photograph',  document_subtype: 'Passport Photo' },
  photograph_postcard:     { document_category: 'photograph',  document_subtype: 'Postcard Photo' },
  signature:               { document_category: 'signature',   document_subtype: 'Personal Signature' },
  id_proof:                { document_category: 'identity' },
  class_10_certificate:    { document_category: 'academic',    document_subtype: 'Class 10 Marksheet' },
  class_12_certificate:    { document_category: 'academic',    document_subtype: 'Class 12 Marksheet' },
  category_certificate:    { document_category: 'certificate', document_subtype: 'Category Certificate' },
  pwd_medical_certificate: { document_category: 'certificate', document_subtype: 'PwD Medical Certificate' },
  scribe_documents:        { document_category: 'other',       document_subtype: 'Scribe Document' },
};

/**
 * Map a document's doc_id to the master document type stored in the vault.
 * Photos and signatures are processed by the worker; everything else is a raw document upload.
 */
function inferDocType(docId: string): 'photo' | 'signature' | 'document' {
  if (docId.startsWith('photograph') || docId.includes('photo')) return 'photo';
  if (docId === 'signature') return 'signature';
  return 'document';
}

/**
 * Find the best matching vault master for a form schema document requirement.
 *
 * Priority:
 *  1. Exact category + subtype match  (e.g. 'academic' + 'Class 10 Marksheet')
 *  2. Category-only match             (e.g. 'identity' → any government ID)
 *  3. Backward-compat fallback for photos/signatures ONLY: untagged old masters
 *     (uploaded before the category/subtype tagging system was added) can satisfy
 *     photo and signature requirements because those are unambiguous types.
 *     Documents do NOT get a backward-compat fallback — a Voter ID, Class 10
 *     marksheet and category certificate are all completely different things and
 *     we cannot safely guess which document slot an untagged upload belongs to.
 */
function findMatchingMaster(
  doc: FormSchemaDocUpload,
  bucket: JobStatus[],
  docType: 'photo' | 'signature' | 'document',
): JobStatus | undefined {
  if (!bucket.length) return undefined;

  if (!doc.document_category) {
    // No category annotation (e.g. biometrics) → no automatic match.
    return undefined;
  }

  if (doc.document_subtype) {
    // 1. Exact category + subtype match (best).
    const exact = bucket.find(
      m => m.document_category === doc.document_category &&
           m.document_subtype === doc.document_subtype,
    );
    if (exact) return exact;
    // 2. Backward compat for photos/signatures: untagged old masters can fill the slot.
    //    Not applicable for documents — an untagged document could be anything.
    if (docType !== 'document') {
      return bucket.find(m => !m.document_category && !m.document_subtype);
    }
    return undefined;
  }

  // Category-only requirement (e.g. id_proof → any identity document).
  // 1. Any master tagged with the right category.
  const catMatch = bucket.find(m => m.document_category === doc.document_category);
  if (catMatch) return catMatch;
  // 2. Backward compat for photos/signatures only.
  if (docType !== 'document') {
    return bucket.find(m => !m.document_category && !m.document_subtype);
  }
  return undefined;
}

/**
 * Return ALL vault masters that qualify for a given requirement, in match-quality
 * order. Used to populate the swap alternatives list.
 */
function findAllMatchingMasters(
  doc: FormSchemaDocUpload,
  bucket: JobStatus[],
  docType: 'photo' | 'signature' | 'document',
): JobStatus[] {
  if (!bucket.length || !doc.document_category) return [];

  if (doc.document_subtype) {
    const exact = bucket.filter(
      m => m.document_category === doc.document_category &&
           m.document_subtype === doc.document_subtype,
    );
    const untagged = docType !== 'document'
      ? bucket.filter(m => !m.document_category && !m.document_subtype)
      : [];
    return [...exact, ...untagged];
  }

  const catMatch = bucket.filter(m => m.document_category === doc.document_category);
  const untagged = docType !== 'document'
    ? bucket.filter(m => !m.document_category && !m.document_subtype)
    : [];
  return [...catMatch, ...untagged];
}

/**
 * Derive the portal_schema_name for adapt jobs from the form schema id.
 * Convention: first segment of the id + '_' + doc type.
 * e.g. 'neet_2026_registration' + 'photo' → 'neet_photo'
 */
function portalSchemaName(formSchemaId: string, docType: 'photo' | 'signature'): string {
  const prefix = formSchemaId.split('_')[0];
  return `${prefix}_${docType}`;
}

interface RequirementStatus {
  type: 'photo' | 'signature' | 'document';
  doc_id: string;
  label: string;
  required: boolean;
  required_if?: string | null;
  available: boolean;
  masterId?: string;
  matchedDocumentName?: string;
  /** All vault masters that qualify for this slot (including the selected one). */
  allCandidates: { job_id: string; document_name?: string }[];
  formats: string[];
  max_kb?: number;
}

export default function PortalSelectorScreen() {
  const {
    documentId: sourceDocumentId,
    documentCategory: sourceDocumentCategory,
    documentSubtype: sourceDocumentSubtype,
    documentName: sourceDocumentName,
  } = useLocalSearchParams<{
    documentId?: string;
    documentCategory?: string;
    documentSubtype?: string;
    documentName?: string;
  }>();

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSchema, setSelectedSchema] = useState<FormSchema | null>(null);
  const [step, setStep] = useState<'select-portal' | 'review-requirements'>('select-portal');
  // Tracks which conditional docs the user has opted into (applicable to them)
  const [conditionalOptIns, setConditionalOptIns] = useState<Record<string, boolean>>({});
  // Manual overrides: doc_id → job_id chosen by the user via Swap
  const [slotOverrides, setSlotOverrides] = useState<Record<string, string>>({});

  // Fetch the portal registry (each portal carries its form schemas)
  const { data: portals, isLoading: portalsLoading } = useQuery({
    queryKey: ['portals'],
    queryFn: portalsApi.list,
  });

  const queryClient = useQueryClient();

  // Refetch vault jobs whenever this screen is focused so uploads made on other
  // tabs (Upload, Capture) are immediately reflected in the checklist.
  useFocusEffect(useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['jobs'] });
  }, [queryClient]));

  // Fetch user's master documents (completed jobs)
  const { data: jobsData } = useQuery({
    queryKey: ['jobs'],
    queryFn: documentsApi.listJobs,
  });

  // Vault: which document types does the user already have?
  // In document-centric export mode (sourceDocumentId set), only match the
  // source document — other vault docs must be added manually by the user.
  const availableMasters = useMemo(() => {
    if (!jobsData?.jobs) return { photo: [], signature: [], document: [] };
    const completed = jobsData.jobs.filter(j => j.status === 'completed');
    const candidates = sourceDocumentId
      ? completed.filter(j => j.job_id === sourceDocumentId)
      : completed;
    return {
      photo: candidates.filter(j => j.document_type === 'photo' && j.job_type === 'master'),
      signature: candidates.filter(j => j.document_type === 'signature'),
      document: candidates.filter(j => j.document_type === 'document'),
    };
  }, [jobsData, sourceDocumentId]);

  // Build requirement status list from the selected form schema
  const requirementStatus = useMemo((): RequirementStatus[] => {
    if (!selectedSchema?.document_uploads) return [];

    // Track which master job IDs have already been claimed by a requirement.
    // Each physical document can only satisfy one slot.
    const claimedMasterIds = new Set<string>();

    return selectedSchema.document_uploads.map((doc: FormSchemaDocUpload) => {
      const type = inferDocType(doc.doc_id);

      // Merge API schema fields with client-side fallback annotations.
      const fallback = DOC_ID_ANNOTATIONS[doc.doc_id] ?? {};
      const effectiveCategory = doc.document_category ?? fallback.document_category;
      const effectiveSubtype  = doc.document_subtype  ?? fallback.document_subtype;
      const annotatedDoc = { ...doc, document_category: effectiveCategory, document_subtype: effectiveSubtype };

      const bucket =
        type === 'photo' ? availableMasters.photo :
        type === 'signature' ? availableMasters.signature :
        availableMasters.document;

      // All qualifying masters (used for Swap alternatives list — ignores claimed state).
      const allCandidates = findAllMatchingMasters(annotatedDoc, bucket, type);

      // Default: first unclaimed candidate via normal matching.
      const availableBucket = bucket.filter(m => !claimedMasterIds.has(m.job_id));
      const defaultMaster = findMatchingMaster(annotatedDoc, availableBucket, type);

      // Apply manual override if the user has swapped this slot and the chosen
      // master is still a valid candidate (guards against deleted jobs).
      const overrideId = slotOverrides[doc.doc_id];
      const matchedMaster =
        (overrideId ? allCandidates.find(m => m.job_id === overrideId) : undefined)
        ?? defaultMaster;

      if (matchedMaster) claimedMasterIds.add(matchedMaster.job_id);

      const available = matchedMaster !== undefined;
      const masterId = matchedMaster?.job_id;
      const matchedDocumentName = matchedMaster?.document_name?.replace(/\.[^.]+$/, '');

      return {
        type,
        doc_id: doc.doc_id,
        label: doc.label,
        required: doc.required,
        required_if: doc.required_if,
        available,
        masterId,
        matchedDocumentName,
        allCandidates: allCandidates.map(m => ({ job_id: m.job_id, document_name: m.document_name })),
        formats: doc.allowed_formats,
        max_kb: doc.size_max_kb,
      };
    });
  }, [selectedSchema, availableMasters, slotOverrides]);

  // Only unconditionally required docs must be satisfied to proceed
  const mandatoryRequirements = useMemo(
    () => requirementStatus.filter(r => r.required),
    [requirementStatus]
  );

  const allRequirementsMet = useMemo(() => {
    if (sourceDocumentId) {
      // Source doc mode: only the exported document's slot needs to be matched.
      return requirementStatus.some(r => r.masterId === sourceDocumentId);
    }
    return mandatoryRequirements.every(r => r.available);
  }, [requirementStatus, mandatoryRequirements, sourceDocumentId]);

  const missingRequirements = useMemo(
    () => mandatoryRequirements.filter(r => !r.available),
    [mandatoryRequirements]
  );

  const conditionalRequirements = useMemo(
    () => requirementStatus.filter(r => !r.required && r.required_if),
    [requirementStatus]
  );

  // Adapt mutation: create processing jobs for photo and signature.
  // In source doc mode, only process the slot matched to the source document.
  const adaptMutation = useMutation({
    mutationFn: async () => {
      if (!selectedSchema) throw new Error('No schema selected');

      const jobIds: string[] = [];

      const slotsToProcess = sourceDocumentId
        ? requirementStatus.filter(r => r.masterId === sourceDocumentId)
        : mandatoryRequirements;

      for (const req of slotsToProcess) {
        if (req.available && req.masterId && (req.type === 'photo' || req.type === 'signature')) {
          const schemaName = portalSchemaName(selectedSchema.id, req.type);
          const result = await documentsApi.createAdaptJob(req.masterId, schemaName);
          jobIds.push(result.job_id);
        }
      }

      return jobIds;
    },
    onSuccess: (jobIds) => {
      router.push({
        pathname: '/(tabs)/adapt-status',
        params: {
          jobIds: JSON.stringify(jobIds),
          portalName: selectedSchema?.short_name,
        },
      });
    },
  });

  // Filter portals: only show those with a form schema, then apply search.
  // In source doc mode, further narrow to portals that actually require this
  // document's category (and subtype when specified).
  const filteredPortals = useMemo(() => {
    if (!portals) return [];
    let candidates = portals.filter(p => p.has_form_schema);

    if (sourceDocumentCategory) {
      candidates = candidates.filter(p =>
        p.form_schemas.some(schema =>
          schema.document_uploads.some(doc => {
            const effectiveCategory =
              doc.document_category ?? DOC_ID_ANNOTATIONS[doc.doc_id]?.document_category;
            if (effectiveCategory !== sourceDocumentCategory) return false;
            if (
              sourceDocumentSubtype &&
              doc.document_subtype &&
              doc.document_subtype !== sourceDocumentSubtype
            ) return false;
            return true;
          })
        )
      );
    }

    if (!searchQuery.trim()) return candidates;
    const query = searchQuery.toLowerCase();
    return candidates.filter(p =>
      p.display_name.toLowerCase().includes(query) ||
      p.short_name.toLowerCase().includes(query)
    );
  }, [portals, searchQuery, sourceDocumentCategory, sourceDocumentSubtype]);

  const handleSelectPortal = useCallback((portal: Portal) => {
    // Pick the latest form schema (API returns them newest-first)
    const schema = portal.form_schemas[0] ?? null;
    setSelectedSchema(schema);
    setConditionalOptIns({});

    // In source doc mode, pre-select the source document in the first slot
    // whose category (and optionally subtype) matches.
    const initialOverrides: Record<string, string> = {};
    if (sourceDocumentId && sourceDocumentCategory && schema) {
      for (const doc of schema.document_uploads) {
        const fallback = DOC_ID_ANNOTATIONS[doc.doc_id] ?? {};
        const effectiveCategory = doc.document_category ?? fallback.document_category;
        if (effectiveCategory !== sourceDocumentCategory) continue;
        if (
          sourceDocumentSubtype &&
          doc.document_subtype &&
          doc.document_subtype !== sourceDocumentSubtype
        ) continue;
        initialOverrides[doc.doc_id] = sourceDocumentId;
        break;
      }
    }
    setSlotOverrides(initialOverrides);
    setStep('review-requirements');
  }, [sourceDocumentId, sourceDocumentCategory, sourceDocumentSubtype]);

  // Cycle to the next qualifying master for a slot.
  const handleSwap = useCallback((
    docId: string,
    candidates: { job_id: string }[],
    currentId?: string,
  ) => {
    const currentIdx = candidates.findIndex(c => c.job_id === currentId);
    const nextIdx = (currentIdx + 1) % candidates.length;
    setSlotOverrides(prev => ({ ...prev, [docId]: candidates[nextIdx].job_id }));
  }, []);

  const handleUploadMissing = useCallback((type: 'photo' | 'signature' | 'document') => {
    router.push({
      pathname: '/(tabs)/capture',
      params: { requiredType: type },
    });
  }, []);

  const renderPortalItem = useCallback(({ item }: { item: Portal }) => {
    const cat = getCategoryDisplay(item.category);
    // Derive doc counts from the most recent form schema, if one exists
    const latestSchema = item.form_schemas[0];
    const requiredCount = latestSchema?.document_uploads.filter(d => d.required).length ?? 0;
    const conditionalCount = latestSchema?.document_uploads.filter(d => !d.required && d.required_if).length ?? 0;

    return (
      <TouchableOpacity
        style={styles.portalItem}
        onPress={() => handleSelectPortal(item)}
        activeOpacity={0.7}
      >
        <View style={[styles.portalIcon, { backgroundColor: cat.color + '20' }]}>
          <FileCheck size={24} color={cat.color} />
        </View>
        <View style={styles.portalInfo}>
          <Text style={styles.portalName}>{item.display_name}</Text>
          <Text style={styles.portalCategory}>{cat.label}</Text>
          {requiredCount > 0 ? (
            <Text style={styles.portalRequirements}>
              {requiredCount} required docs
              {conditionalCount > 0 ? ` + ${conditionalCount} conditional` : ''}
            </Text>
          ) : (
            <Text style={styles.portalRequirements}>No form schema yet</Text>
          )}
        </View>
        <ChevronRight size={20} color={colors.white + '60'} />
      </TouchableOpacity>
    );
  }, [handleSelectPortal]);

  // ─── Step 1: Portal Selection ─────────────────────────────────────────────
  if (step === 'select-portal') {
    return (
      <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.headerButton}>
            <ArrowLeft size={24} color={colors.white} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Export for Portal</Text>
          <View style={styles.headerButton} />
        </View>

        {(sourceDocumentName || sourceDocumentSubtype || sourceDocumentCategory) && (
          <View style={styles.exportContextBanner}>
            <Text style={styles.exportContextLabel}>Exporting</Text>
            <Text style={styles.exportContextDoc} numberOfLines={1}>
              {sourceDocumentName || sourceDocumentSubtype || sourceDocumentCategory}
            </Text>
          </View>
        )}

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

        {portalsLoading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color={colors.mayaBlue} />
            <Text style={styles.loadingText}>Loading portals...</Text>
          </View>
        ) : (
          <FlatList
            data={filteredPortals}
            keyExtractor={(item) => item.id}
            renderItem={renderPortalItem}
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

  // ─── Step 2: Review Requirements ─────────────────────────────────────────
  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => setStep('select-portal')} style={styles.headerButton}>
          <ArrowLeft size={24} color={colors.white} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>{selectedSchema?.short_name}</Text>
        <View style={styles.headerButton} />
      </View>

      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {/* Status Banner */}
        <View style={[
          styles.statusBanner,
          allRequirementsMet ? styles.statusBannerSuccess : styles.statusBannerWarning,
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

        {/* Required Documents */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Required Documents</Text>

          {mandatoryRequirements.map((req) => (
            <View key={req.doc_id} style={styles.requirementItem}>
              <View style={styles.requirementIcon}>
                {req.type === 'photo' && <FileImage size={22} color={colors.mayaBlue} />}
                {req.type === 'signature' && <PenTool size={22} color={colors.mayaBlue} />}
                {req.type === 'document' && <FileText size={22} color={colors.mayaBlue} />}
              </View>

              <View style={styles.requirementInfo}>
                <Text style={styles.requirementLabel}>{req.label}</Text>
                <Text style={[
                  styles.requirementStatus,
                  req.available ? styles.requirementStatusOk : styles.requirementStatusMissing,
                ]}>
                  {req.available
                    ? req.matchedDocumentName
                      ? `Matched: ${req.matchedDocumentName}`
                      : 'Available'
                    : 'Not uploaded'}
                </Text>
                <Text style={styles.requirementFormats}>
                  {req.formats.join(' / ')}{req.max_kb ? ` · max ${req.max_kb} KB` : ''}
                </Text>
              </View>

              {req.available ? (
                req.allCandidates.length > 1 ? (
                  <View style={styles.matchActions}>
                    <CheckCircle size={20} color="#34C759" />
                    <TouchableOpacity
                      style={styles.swapButton}
                      onPress={() => handleSwap(req.doc_id, req.allCandidates, req.masterId)}
                    >
                      <ArrowLeftRight size={14} color={colors.mayaBlue} />
                      <Text style={styles.swapText}>Swap</Text>
                    </TouchableOpacity>
                  </View>
                ) : (
                  <CheckCircle size={24} color="#34C759" />
                )
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

        {/* Conditional Documents */}
        {conditionalRequirements.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Conditional Documents</Text>
            <Text style={styles.conditionalNote}>
              Required only if applicable to you.
            </Text>

            {conditionalRequirements.map((req) => {
              const isOptedIn = conditionalOptIns[req.doc_id] ?? false;
              const iconColor = isOptedIn ? colors.mayaBlue : colors.white + '50';

              return (
                <View key={req.doc_id} style={[styles.requirementItem, !isOptedIn && styles.conditionalItem]}>
                  <View style={[styles.requirementIcon, !isOptedIn && styles.conditionalIcon]}>
                    {req.type === 'photo' && <FileImage size={22} color={iconColor} />}
                    {req.type === 'signature' && <PenTool size={22} color={iconColor} />}
                    {req.type === 'document' && <FileText size={22} color={iconColor} />}
                  </View>

                  <View style={styles.requirementInfo}>
                    <Text style={[styles.requirementLabel, !isOptedIn && { color: colors.white + 'AA' }]}>
                      {req.label}
                    </Text>
                    {isOptedIn && (
                      <Text style={[
                        styles.requirementStatus,
                        req.available ? styles.requirementStatusOk : styles.requirementStatusMissing,
                      ]}>
                        {req.available
                          ? req.matchedDocumentName
                            ? `Matched: ${req.matchedDocumentName}`
                            : 'Available'
                          : 'Not uploaded'}
                      </Text>
                    )}
                    <Text style={styles.conditionalCondition}>
                      If: {req.required_if}
                    </Text>
                    {isOptedIn && (
                      <Text style={styles.requirementFormats}>
                        {req.formats.join(' / ')}{req.max_kb ? ` · max ${req.max_kb} KB` : ''}
                      </Text>
                    )}
                  </View>

                  {isOptedIn ? (
                    req.available ? (
                      req.allCandidates.length > 1 ? (
                        <View style={styles.matchActions}>
                          <CheckCircle size={20} color="#34C759" />
                          <TouchableOpacity
                            style={styles.swapButton}
                            onPress={() => handleSwap(req.doc_id, req.allCandidates, req.masterId)}
                          >
                            <ArrowLeftRight size={14} color={colors.mayaBlue} />
                            <Text style={styles.swapText}>Swap</Text>
                          </TouchableOpacity>
                        </View>
                      ) : (
                        <CheckCircle size={24} color="#34C759" />
                      )
                    ) : (
                      <TouchableOpacity
                        style={styles.uploadMissingButton}
                        onPress={() => handleUploadMissing(req.type)}
                      >
                        <Camera size={18} color={colors.white} />
                        <Text style={styles.uploadMissingText}>Add</Text>
                      </TouchableOpacity>
                    )
                  ) : (
                    <Switch
                      value={false}
                      onValueChange={() =>
                        setConditionalOptIns(prev => ({ ...prev, [req.doc_id]: true }))
                      }
                      trackColor={{ false: colors.shadowGrey, true: colors.trueCobalt }}
                      thumbColor={colors.white}
                    />
                  )}
                </View>
              );
            })}
          </View>
        )}

        {/* Conducting body info */}
        {selectedSchema?.conducting_body && (
          <View style={styles.infoBox}>
            <Text style={styles.infoText}>
              {selectedSchema.conducting_body}
              {selectedSchema.applicable_year ? ` · ${selectedSchema.applicable_year}` : ''}
            </Text>
          </View>
        )}
      </ScrollView>

      {/* Bottom Action */}
      <View style={styles.bottomContainer}>
        {allRequirementsMet ? (
          <TouchableOpacity
            style={[styles.processButton, adaptMutation.isPending && styles.processButtonDisabled]}
            onPress={() => adaptMutation.mutate()}
            disabled={adaptMutation.isPending}
            activeOpacity={0.8}
          >
            {adaptMutation.isPending ? (
              <ActivityIndicator size="small" color={colors.white} />
            ) : (
              <>
                <Text style={styles.processButtonText}>
                  {sourceDocumentId ? 'Export Document' : 'Process & Download'}
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
  exportContextBanner: {
    marginHorizontal: 16,
    marginTop: 8,
    marginBottom: 4,
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: colors.trueCobalt + '40',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: colors.trueCobalt,
  },
  exportContextLabel: {
    fontSize: 10,
    fontWeight: '600',
    color: colors.mayaBlue,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    marginBottom: 2,
  },
  exportContextDoc: {
    fontSize: 14,
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
    marginBottom: 12,
  },
  conditionalNote: {
    fontSize: 13,
    color: colors.white + '60',
    marginBottom: 12,
  },
  requirementItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.shadowGrey,
    borderRadius: 12,
    padding: 14,
    marginBottom: 10,
    gap: 12,
  },
  conditionalItem: {
    opacity: 0.65,
  },
  conditionalIcon: {
    backgroundColor: colors.shadowGrey,
  },
  requirementIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.mayaBlue + '20',
    justifyContent: 'center',
    alignItems: 'center',
  },
  requirementInfo: {
    flex: 1,
  },
  requirementLabel: {
    fontSize: 15,
    fontWeight: '500',
    color: colors.white,
  },
  requirementStatus: {
    fontSize: 12,
    marginTop: 2,
  },
  requirementStatusOk: {
    color: '#34C759',
  },
  requirementStatusMissing: {
    color: '#FF9500',
  },
  requirementFormats: {
    fontSize: 11,
    color: colors.white + '50',
    marginTop: 2,
  },
  conditionalCondition: {
    fontSize: 11,
    color: colors.white + '50',
    marginTop: 2,
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
  matchActions: {
    alignItems: 'center',
    gap: 6,
  },
  swapButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingVertical: 4,
    paddingHorizontal: 8,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: colors.mayaBlue + '60',
  },
  swapText: {
    fontSize: 11,
    fontWeight: '500',
    color: colors.mayaBlue,
  },
  infoBox: {
    margin: 16,
    marginTop: 20,
    backgroundColor: colors.shadowGrey,
    borderRadius: 10,
    padding: 12,
  },
  infoText: {
    fontSize: 13,
    color: colors.white + '80',
    textAlign: 'center',
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
