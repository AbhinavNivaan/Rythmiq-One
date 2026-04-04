// app-v2/components/ui/ReportFeedbackModal.tsx
import React, { useState } from 'react';
import {
  Modal,
  View,
  Text,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  StyleSheet,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Colors from '../../constants/Colors';
import { documentsApi } from '../../services/api';

type FeedbackCategory =
  | 'wrong_crop'
  | 'poor_quality'
  | 'wrong_orientation'
  | 'wrong_document_type'
  | 'other';

const CATEGORIES: { value: FeedbackCategory; label: string }[] = [
  { value: 'wrong_crop',          label: 'Wrong crop' },
  { value: 'poor_quality',        label: 'Poor quality' },
  { value: 'wrong_orientation',   label: 'Wrong orientation' },
  { value: 'wrong_document_type', label: 'Wrong document type' },
  { value: 'other',               label: 'Other' },
];

interface Props {
  visible: boolean;
  jobId: string;
  reportType?: 'full' | 'output_only';
  onClose: () => void;
  onReported: () => void;
}

export default function ReportFeedbackModal({
  visible,
  jobId,
  reportType = 'full',
  onClose,
  onReported,
}: Props) {
  const insets = useSafeAreaInsets();
  const [category, setCategory] = useState<FeedbackCategory | null>(null);
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setCategory(null);
    setNote('');
    setError(null);
    setSubmitting(false);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSubmit = async () => {
    if (!category) return;
    setSubmitting(true);
    setError(null);
    try {
      await documentsApi.reportFeedback(jobId, {
        category,
        note: note.trim() || undefined,
        consent_granted: true,
        report_type: reportType,
      });
      reset();
      onReported();
    } catch {
      setError("Couldn't send report. Your document was saved normally.");
      setSubmitting(false);
    }
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={handleClose}
    >
      <TouchableOpacity style={styles.backdrop} activeOpacity={1} onPress={handleClose} />
      <View style={[styles.sheet, { paddingBottom: insets.bottom + 16 }]}>
        <View style={styles.handle} />
        <Text style={styles.title}>Report Bad Output</Text>

        <Text style={styles.sectionLabel}>What looks wrong?</Text>
        {CATEGORIES.map((c) => (
          <TouchableOpacity
            key={c.value}
            style={[styles.option, category === c.value && styles.optionSelected]}
            onPress={() => setCategory(c.value)}
            activeOpacity={0.75}
          >
            <View style={[styles.radio, category === c.value && styles.radioSelected]} />
            <Text style={styles.optionLabel}>{c.label}</Text>
          </TouchableOpacity>
        ))}

        <TextInput
          style={styles.noteInput}
          placeholder="Describe what looks wrong (optional)"
          placeholderTextColor="#555"
          value={note}
          onChangeText={setNote}
          multiline
          numberOfLines={2}
          maxLength={500}
        />

        <Text style={styles.consent}>
          Your document will be temporarily shared so we can review what went wrong and fix it. Deleted within 90 days.
        </Text>

        {error && <Text style={styles.errorText}>{error}</Text>}

        <TouchableOpacity
          style={[styles.submitButton, (!category || submitting) && styles.submitDisabled]}
          onPress={handleSubmit}
          disabled={!category || submitting}
          activeOpacity={0.8}
        >
          {submitting
            ? <ActivityIndicator color="#000" size="small" />
            : <Text style={styles.submitText}>Submit Report</Text>
          }
        </TouchableOpacity>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
  },
  sheet: {
    backgroundColor: '#1a1a1a',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 24,
    paddingTop: 12,
  },
  handle: {
    width: 40,
    height: 4,
    backgroundColor: '#333',
    borderRadius: 2,
    alignSelf: 'center',
    marginBottom: 20,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    color: Colors.palette.white,
    marginBottom: 20,
  },
  sectionLabel: {
    fontSize: 13,
    color: '#666',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    marginBottom: 12,
  },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 12,
    marginBottom: 8,
    backgroundColor: '#222',
    gap: 12,
  },
  optionSelected: {
    backgroundColor: '#1e2e1e',
    borderWidth: 1,
    borderColor: Colors.palette.green,
  },
  radio: {
    width: 18,
    height: 18,
    borderRadius: 9,
    borderWidth: 2,
    borderColor: '#444',
  },
  radioSelected: {
    borderColor: Colors.palette.green,
    backgroundColor: Colors.palette.green,
  },
  optionLabel: {
    fontSize: 15,
    color: Colors.palette.white,
  },
  noteInput: {
    backgroundColor: '#222',
    borderRadius: 12,
    padding: 14,
    color: Colors.palette.white,
    fontSize: 14,
    marginTop: 16,
    marginBottom: 12,
    minHeight: 70,
    textAlignVertical: 'top',
  },
  consent: {
    fontSize: 12,
    color: '#555',
    lineHeight: 17,
    marginBottom: 20,
  },
  errorText: {
    fontSize: 13,
    color: Colors.palette.red,
    marginBottom: 12,
  },
  submitButton: {
    backgroundColor: Colors.palette.green,
    borderRadius: 24,
    paddingVertical: 16,
    alignItems: 'center',
  },
  submitDisabled: {
    opacity: 0.4,
  },
  submitText: {
    fontSize: 16,
    fontWeight: '700',
    color: '#000',
  },
});
