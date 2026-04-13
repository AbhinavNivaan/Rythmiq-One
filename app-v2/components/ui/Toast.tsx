/**
 * Toast Notification System
 *
 * Provides a context-based toast notification system with
 * support for success, error, warning, and info messages.
 * Exports getToastStyles() for the 3-variant semantic token system.
 */

import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useRef,
  useEffect,
  ReactNode,
} from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Animated,
  ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  Info,
  X,
} from 'lucide-react-native';
import Colors from '../../constants/Colors';
import Typography from '../../constants/Typography';

// ---------------------------------------------------------------------------
// Variant system (design-system tokens)
// ---------------------------------------------------------------------------

export type ToastVariant = 'success' | 'error' | 'info';

interface ToastStyleResult {
  container: ViewStyle;
  dotColor: string;
  textColor: string;
}

export function getToastStyles(variant: ToastVariant): ToastStyleResult {
  const map: Record<ToastVariant, { fill: string; border: string; color: string }> = {
    success: { fill: 'rgba(74,222,128,0.10)',  border: 'rgba(74,222,128,0.20)',  color: Colors.palette.green },
    error:   { fill: 'rgba(239,68,68,0.10)',   border: 'rgba(239,68,68,0.20)',   color: Colors.palette.red   },
    info:    { fill: 'rgba(96,165,250,0.10)',  border: 'rgba(96,165,250,0.20)',  color: Colors.palette.blue  },
  };
  const { fill, border, color } = map[variant];
  return {
    container: { backgroundColor: fill, borderColor: border },
    dotColor: color,
    textColor: color,
  };
}

// ---------------------------------------------------------------------------
// Simple standalone Toast component (used by the provider internally)
// ---------------------------------------------------------------------------

interface ToastProps {
  message: string;
  variant: ToastVariant;
  onDismiss: () => void;
  duration?: number;
}

export function Toast({ message, variant, onDismiss, duration = 3000 }: ToastProps) {
  const opacity = useRef(new Animated.Value(0)).current;
  const { container, dotColor, textColor } = getToastStyles(variant);

  useEffect(() => {
    Animated.sequence([
      Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }),
      Animated.delay(duration),
      Animated.timing(opacity, { toValue: 0, duration: 200, useNativeDriver: true }),
    ]).start(onDismiss);
  }, []);

  return (
    <Animated.View style={[styles.simpleContainer, container, { opacity }]}>
      <View style={[styles.dot, { backgroundColor: dotColor }]} />
      <Text style={[Typography.label, { color: textColor, flex: 1 }]}>{message}</Text>
    </Animated.View>
  );
}

// ---------------------------------------------------------------------------
// Legacy context-based system (backward-compatible)
// ---------------------------------------------------------------------------

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastMessage {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;
  action?: {
    label: string;
    onPress: () => void;
  };
}

interface ToastConfig {
  icon: React.ComponentType<{ size: number; color: string }>;
  color: string;
  backgroundColor: string;
}

const TOAST_CONFIG: Record<ToastType, ToastConfig> = {
  success: {
    icon: CheckCircle,
    color: Colors.palette.green,
    backgroundColor: 'rgba(74,222,128,0.10)',
  },
  error: {
    icon: XCircle,
    color: Colors.palette.red,
    backgroundColor: 'rgba(239,68,68,0.10)',
  },
  warning: {
    icon: AlertTriangle,
    color: Colors.palette.amber,
    backgroundColor: 'rgba(255,149,0,0.15)',
  },
  info: {
    icon: Info,
    color: Colors.palette.blue,
    backgroundColor: 'rgba(96,165,250,0.10)',
  },
};

interface ToastContextValue {
  showToast: (toast: Omit<ToastMessage, 'id'>) => void;
  hideToast: (id: string) => void;
  success: (title: string, message?: string) => void;
  error: (title: string, message?: string) => void;
  warning: (title: string, message?: string) => void;
  info: (title: string, message?: string) => void;
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined);

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}

// Individual Toast item for the provider
function ToastItem({
  toast,
  onDismiss,
}: {
  toast: ToastMessage;
  onDismiss: () => void;
}) {
  const [slideAnim] = useState(new Animated.Value(-100));
  const [fadeAnim] = useState(new Animated.Value(0));

  React.useEffect(() => {
    Animated.parallel([
      Animated.spring(slideAnim, {
        toValue: 0,
        useNativeDriver: true,
        tension: 50,
        friction: 9,
      }),
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 200,
        useNativeDriver: true,
      }),
    ]).start();

    const duration = toast.duration || 4000;
    const timer = setTimeout(() => {
      handleDismiss();
    }, duration);

    return () => clearTimeout(timer);
  }, []);

  const handleDismiss = () => {
    Animated.parallel([
      Animated.timing(slideAnim, {
        toValue: -100,
        duration: 200,
        useNativeDriver: true,
      }),
      Animated.timing(fadeAnim, {
        toValue: 0,
        duration: 200,
        useNativeDriver: true,
      }),
    ]).start(() => onDismiss());
  };

  const config = TOAST_CONFIG[toast.type];
  const Icon = config.icon;

  return (
    <Animated.View
      style={[
        styles.toast,
        { backgroundColor: config.backgroundColor },
        {
          transform: [{ translateY: slideAnim }],
          opacity: fadeAnim,
        },
      ]}
    >
      <View style={styles.toastContent}>
        <View style={[styles.iconContainer, { backgroundColor: config.color + '20' }]}>
          <Icon size={20} color={config.color} />
        </View>
        <View style={styles.textContainer}>
          <Text style={[styles.toastTitle, { color: config.color }]}>
            {toast.title}
          </Text>
          {toast.message && (
            <Text style={styles.toastMessage} numberOfLines={2}>
              {toast.message}
            </Text>
          )}
        </View>
        {toast.action && (
          <TouchableOpacity
            style={styles.actionButton}
            onPress={() => {
              toast.action?.onPress();
              handleDismiss();
            }}
            activeOpacity={0.7}
          >
            <Text style={[styles.actionText, { color: config.color }]}>
              {toast.action.label}
            </Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity
          style={styles.dismissButton}
          onPress={handleDismiss}
          activeOpacity={0.7}
        >
          <X size={18} color="#999" />
        </TouchableOpacity>
      </View>
    </Animated.View>
  );
}

// Provider Component
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const insets = useSafeAreaInsets();

  const showToast = useCallback((toast: Omit<ToastMessage, 'id'>) => {
    const id = Date.now().toString() + Math.random().toString(36).substr(2, 9);
    setToasts((prev) => [...prev, { ...toast, id }]);
  }, []);

  const hideToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const success = useCallback((title: string, message?: string) => {
    showToast({ type: 'success', title, message });
  }, [showToast]);

  const error = useCallback((title: string, message?: string) => {
    showToast({ type: 'error', title, message, duration: 5000 });
  }, [showToast]);

  const warning = useCallback((title: string, message?: string) => {
    showToast({ type: 'warning', title, message });
  }, [showToast]);

  const info = useCallback((title: string, message?: string) => {
    showToast({ type: 'info', title, message });
  }, [showToast]);

  return (
    <ToastContext.Provider value={{ showToast, hideToast, success, error, warning, info }}>
      {children}
      <View style={[styles.container, { top: insets.top + 8 }]} pointerEvents="box-none">
        {toasts.map((toast) => (
          <ToastItem
            key={toast.id}
            toast={toast}
            onDismiss={() => hideToast(toast.id)}
          />
        ))}
      </View>
    </ToastContext.Provider>
  );
}

const styles = StyleSheet.create({
  simpleContainer: {
    position: 'absolute',
    bottom: 24,
    left: 24,
    right: 24,
    borderRadius: 24,
    borderWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    gap: 10,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    flexShrink: 0,
  },
  container: {
    position: 'absolute',
    left: 16,
    right: 16,
    zIndex: 9999,
    gap: 8,
  },
  toast: {
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
  toastContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  iconContainer: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  textContainer: {
    flex: 1,
  },
  toastTitle: {
    fontSize: 14,
    fontWeight: '700',
  },
  toastMessage: {
    fontSize: 12,
    color: '#999',
    marginTop: 2,
  },
  actionButton: {
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  actionText: {
    fontSize: 12,
    fontWeight: '700',
  },
  dismissButton: {
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: -8,
  },
});

export default ToastProvider;
