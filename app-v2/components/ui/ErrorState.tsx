/**
 * ErrorState Component
 * 
 * Comprehensive error display with user-friendly messages and actions.
 * Supports different error types: network, processing, schema, generic.
 */

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
} from 'react-native';
import {
  WifiOff,
  AlertTriangle,
  FileWarning,
  RefreshCw,
  Camera,
  MessageCircle,
  XCircle,
  HelpCircle,
} from 'lucide-react-native';
import Colors from '../../constants/Colors';

export type ErrorType = 
  | 'network' 
  | 'processing' 
  | 'schema' 
  | 'timeout' 
  | 'expired' 
  | 'corrupt' 
  | 'generic';

export interface ErrorAction {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary';
}

export interface ErrorStateProps {
  type: ErrorType;
  title?: string;
  message?: string;
  errorCode?: string;
  actions?: ErrorAction[];
  onReport?: () => void;
  compact?: boolean;
}

interface ErrorConfig {
  icon: React.ComponentType<{ size: number; color: string }>;
  defaultTitle: string;
  defaultMessage: string;
  color: string;
}

const ERROR_CONFIG: Record<ErrorType, ErrorConfig> = {
  network: {
    icon: WifiOff,
    defaultTitle: 'Connection Lost',
    defaultMessage: 'Please check your internet connection and try again.',
    color: '#FF9500',
  },
  processing: {
    icon: AlertTriangle,
    defaultTitle: 'Processing Failed',
    defaultMessage: 'We couldn\'t process your document. Please try retaking the photo with better lighting.',
    color: '#FF3B30',
  },
  schema: {
    icon: FileWarning,
    defaultTitle: 'Adaptation Failed',
    defaultMessage: 'Your file doesn\'t meet the portal requirements. Try a higher quality image.',
    color: '#FF9500',
  },
  timeout: {
    icon: RefreshCw,
    defaultTitle: 'Request Timed Out',
    defaultMessage: 'The server took too long to respond. Please try again.',
    color: '#FF9500',
  },
  expired: {
    icon: XCircle,
    defaultTitle: 'Link Expired',
    defaultMessage: 'This download link has expired. Please regenerate the file.',
    color: '#FF3B30',
  },
  corrupt: {
    icon: FileWarning,
    defaultTitle: 'Invalid File',
    defaultMessage: 'This file appears to be corrupted or in an unsupported format.',
    color: '#FF3B30',
  },
  generic: {
    icon: HelpCircle,
    defaultTitle: 'Something Went Wrong',
    defaultMessage: 'An unexpected error occurred. Please try again or contact support.',
    color: '#FF3B30',
  },
};

export function ErrorState({
  type,
  title,
  message,
  errorCode,
  actions,
  onReport,
  compact = false,
}: ErrorStateProps) {
  const config = ERROR_CONFIG[type];
  const Icon = config.icon;

  if (compact) {
    return (
      <View style={styles.compactContainer}>
        <View style={[styles.compactIconContainer, { backgroundColor: config.color + '20' }]}>
          <Icon size={20} color={config.color} />
        </View>
        <View style={styles.compactContent}>
          <Text style={[styles.compactTitle, { color: config.color }]}>
            {title || config.defaultTitle}
          </Text>
          <Text style={styles.compactMessage} numberOfLines={2}>
            {message || config.defaultMessage}
          </Text>
        </View>
        {actions && actions.length > 0 && (
          <TouchableOpacity
            style={styles.compactAction}
            onPress={actions[0].onPress}
            activeOpacity={0.7}
          >
            <RefreshCw size={18} color='#89C7FE' />
          </TouchableOpacity>
        )}
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.iconContainer, { backgroundColor: config.color + '15' }]}>
        <Icon size={48} color={config.color} />
      </View>

      <Text style={[styles.title, { color: config.color }]}>
        {title || config.defaultTitle}
      </Text>

      <Text style={styles.message}>
        {message || config.defaultMessage}
      </Text>

      {errorCode && (
        <View style={styles.errorCodeContainer}>
          <Text style={styles.errorCodeLabel}>Error Code:</Text>
          <Text style={styles.errorCode}>{errorCode}</Text>
        </View>
      )}

      {actions && actions.length > 0 && (
        <View style={styles.actionsContainer}>
          {actions.map((action, index) => (
            <TouchableOpacity
              key={index}
              style={[
                styles.actionButton,
                action.variant === 'secondary' ? styles.secondaryButton : styles.primaryButton,
              ]}
              onPress={action.onPress}
              activeOpacity={0.8}
            >
              {action.label === 'Retry' && (
                <RefreshCw 
                  size={18} 
                  color={action.variant === 'secondary' ? '#89C7FE' : Colors.palette.white} 
                />
              )}
              {action.label === 'Retake Photo' && (
                <Camera 
                  size={18} 
                  color={action.variant === 'secondary' ? '#89C7FE' : Colors.palette.white} 
                />
              )}
              <Text style={[
                styles.actionText,
                action.variant === 'secondary' ? styles.secondaryText : styles.primaryText,
              ]}>
                {action.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {onReport && (
        <TouchableOpacity
          style={styles.reportButton}
          onPress={onReport}
          activeOpacity={0.7}
        >
          <MessageCircle size={16} color="#999" />
          <Text style={styles.reportText}>Report this issue</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    padding: 24,
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 20,
  },
  iconContainer: {
    width: 96,
    height: 96,
    borderRadius: 48,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 20,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 8,
    textAlign: 'center',
  },
  message: {
    fontSize: 14,
    color: '#999',
    textAlign: 'center',
    lineHeight: 20,
    marginBottom: 16,
    paddingHorizontal: 16,
  },
  errorCodeContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    marginBottom: 20,
    gap: 6,
  },
  errorCodeLabel: {
    fontSize: 12,
    color: '#666',
  },
  errorCode: {
    fontSize: 12,
    fontFamily: 'monospace',
    color: '#999',
  },
  actionsContainer: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 8,
  },
  actionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
    paddingVertical: 14,
    borderRadius: 12,
    gap: 8,
    minWidth: 120,
  },
  primaryButton: {
    backgroundColor: '#1A2595',
  },
  secondaryButton: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: '#89C7FE',
  },
  actionText: {
    fontSize: 16,
    fontWeight: '600',
  },
  primaryText: {
    color: Colors.palette.white,
  },
  secondaryText: {
    color: '#89C7FE',
  },
  reportButton: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 20,
    gap: 6,
  },
  reportText: {
    fontSize: 14,
    color: '#999',
  },
  // Compact styles
  compactContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    backgroundColor: Colors.palette.shadowGrey,
    borderRadius: 12,
    gap: 12,
  },
  compactIconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  compactContent: {
    flex: 1,
  },
  compactTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 2,
  },
  compactMessage: {
    fontSize: 12,
    color: '#999',
  },
  compactAction: {
    width: 40,
    height: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
});

export default ErrorState;
