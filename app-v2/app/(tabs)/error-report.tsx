/**
 * Error Report Screen
 * 
 * Allows users to submit feedback with error context for debugging.
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  ScrollView,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, useLocalSearchParams } from 'expo-router';
import {
  ArrowLeft,
  Send,
  Bug,
  Copy,
  Check,
} from 'lucide-react-native';
import { useMutation } from '@tanstack/react-query';
import Colors from '../../constants/Colors';

export default function ErrorReportScreen() {
  const params = useLocalSearchParams<{
    errorCode?: string;
    errorMessage?: string;
    context?: string;
  }>();

  const [description, setDescription] = useState('');
  const [email, setEmail] = useState('');
  const [copied, setCopied] = useState(false);

  // Generate debug info
  const debugInfo = {
    errorCode: params.errorCode || 'UNKNOWN',
    errorMessage: params.errorMessage || 'No message provided',
    context: params.context || 'general',
    timestamp: new Date().toISOString(),
    platform: Platform.OS,
    version: '1.0.0', // TODO: Get from app config
  };

  const debugString = JSON.stringify(debugInfo, null, 2);

  // Submit report mutation
  const submitReport = useMutation({
    mutationFn: async () => {
      // TODO: Implement actual API call
      // For now, simulate network delay
      await new Promise(resolve => setTimeout(resolve, 1500));
      
      // In production, this would POST to /support/report
      console.log('Error report submitted:', {
        description,
        email,
        debugInfo,
      });
      
      return { success: true };
    },
    onSuccess: () => {
      Alert.alert(
        'Report Submitted',
        'Thank you for your feedback. Our team will investigate this issue.',
        [{ text: 'OK', onPress: () => router.back() }]
      );
    },
    onError: () => {
      Alert.alert(
        'Submission Failed',
        'Could not submit your report. Please try again later.',
        [{ text: 'OK' }]
      );
    },
  });

  const handleCopyDebug = async () => {
    // Clipboard functionality - show copied feedback
    // In production, install expo-clipboard: npx expo install expo-clipboard
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    Alert.alert('Debug Info', 'Debug information shown below. You can include it in your report.');
  };

  const handleSubmit = () => {
    if (!description.trim()) {
      Alert.alert('Required', 'Please describe what happened.');
      return;
    }
    submitReport.mutate();
  };

  const isSubmitting = submitReport.isPending;

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.headerButton}>
          <ArrowLeft size={24} color={Colors.palette.white} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Report Issue</Text>
        <View style={styles.headerButton} />
      </View>

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          style={styles.content}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          {/* Error Summary */}
          <View style={styles.errorSummary}>
            <View style={styles.errorIconContainer}>
              <Bug size={32} color="#FF3B30" />
            </View>
            <View style={styles.errorDetails}>
              <Text style={styles.errorCode}>{params.errorCode || 'Error'}</Text>
              <Text style={styles.errorMessage} numberOfLines={2}>
                {params.errorMessage || 'An error occurred'}
              </Text>
            </View>
          </View>

          {/* Description Input */}
          <View style={styles.section}>
            <Text style={styles.label}>What happened? *</Text>
            <TextInput
              style={styles.textArea}
              value={description}
              onChangeText={setDescription}
              placeholder="Please describe what you were doing when this error occurred..."
              placeholderTextColor="#666"
              multiline
              numberOfLines={5}
              textAlignVertical="top"
            />
          </View>

          {/* Email Input */}
          <View style={styles.section}>
            <Text style={styles.label}>Email (optional)</Text>
            <Text style={styles.hint}>We'll follow up if we need more information</Text>
            <TextInput
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              placeholder="your@email.com"
              placeholderTextColor="#666"
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>

          {/* Debug Info */}
          <View style={styles.section}>
            <View style={styles.debugHeader}>
              <Text style={styles.label}>Debug Information</Text>
              <TouchableOpacity
                style={styles.copyButton}
                onPress={handleCopyDebug}
                activeOpacity={0.7}
              >
                {copied ? (
                  <>
                    <Check size={14} color="#34C759" />
                    <Text style={[styles.copyText, { color: '#34C759' }]}>Copied</Text>
                  </>
                ) : (
                  <>
                    <Copy size={14} color='#89C7FE' />
                    <Text style={styles.copyText}>Copy</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
            <View style={styles.debugBox}>
              <Text style={styles.debugText}>{debugString}</Text>
            </View>
          </View>

          {/* Submit Button */}
          <TouchableOpacity
            style={[styles.submitButton, isSubmitting && styles.buttonDisabled]}
            onPress={handleSubmit}
            disabled={isSubmitting}
            activeOpacity={0.8}
          >
            {isSubmitting ? (
              <ActivityIndicator color={Colors.palette.white} />
            ) : (
              <>
                <Send size={20} color={Colors.palette.white} />
                <Text style={styles.submitText}>Submit Report</Text>
              </>
            )}
          </TouchableOpacity>

          {/* Privacy Note */}
          <Text style={styles.privacyNote}>
            Your report helps us improve Rythmiq. We only collect error information 
            and never access your documents.
          </Text>

          <View style={{ height: 32 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.palette.inkBlack,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  headerButton: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: Colors.palette.white,
  },
  content: {
    flex: 1,
    paddingHorizontal: 16,
  },
  errorSummary: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 59, 48, 0.1)',
    borderRadius: 16,
    padding: 16,
    marginBottom: 24,
    gap: 16,
  },
  errorIconContainer: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: 'rgba(255, 59, 48, 0.15)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  errorDetails: {
    flex: 1,
  },
  errorCode: {
    fontSize: 14,
    fontWeight: '600',
    color: '#FF3B30',
    marginBottom: 4,
  },
  errorMessage: {
    fontSize: 14,
    color: '#999',
  },
  section: {
    marginBottom: 20,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: Colors.palette.white,
    marginBottom: 8,
  },
  hint: {
    fontSize: 12,
    color: '#666',
    marginBottom: 8,
  },
  input: {
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 16,
    color: Colors.palette.white,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.05)',
  },
  textArea: {
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 16,
    color: Colors.palette.white,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.05)',
    minHeight: 120,
  },
  debugHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  copyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  copyText: {
    fontSize: 12,
    color: '#89C7FE',
  },
  debugBox: {
    backgroundColor: 'rgba(0, 0, 0, 0.3)',
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.05)',
  },
  debugText: {
    fontSize: 11,
    fontFamily: 'monospace',
    color: '#999',
    lineHeight: 16,
  },
  submitButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#1A2595',
    paddingVertical: 16,
    borderRadius: 12,
    gap: 8,
    marginTop: 8,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  submitText: {
    fontSize: 16,
    fontWeight: '600',
    color: Colors.palette.white,
  },
  privacyNote: {
    fontSize: 12,
    color: '#666',
    textAlign: 'center',
    marginTop: 16,
    lineHeight: 18,
    paddingHorizontal: 24,
  },
});
