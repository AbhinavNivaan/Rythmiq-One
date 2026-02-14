/**
 * useSessionTimeout Hook
 * 
 * Monitors user activity and handles session timeout.
 * Automatically logs out after 30 minutes of inactivity.
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { AppState, AppStateStatus } from 'react-native';
import { router } from 'expo-router';
import {
  isSessionValid,
  updateLastActivity,
  getSessionTimeRemaining,
  clearAuthTokens,
  SESSION_TIMEOUT_MS,
} from '../services/security';

interface UseSessionTimeoutOptions {
  onTimeout?: () => void;
  onWarning?: (secondsRemaining: number) => void;
  warningThreshold?: number; // seconds before timeout to show warning
  enabled?: boolean;
}

interface SessionState {
  isActive: boolean;
  timeRemaining: number;
  showWarning: boolean;
}

export function useSessionTimeout(options: UseSessionTimeoutOptions = {}) {
  const {
    onTimeout,
    onWarning,
    warningThreshold = 300, // 5 minutes warning
    enabled = true,
  } = options;

  const [sessionState, setSessionState] = useState<SessionState>({
    isActive: true,
    timeRemaining: SESSION_TIMEOUT_MS / 1000,
    showWarning: false,
  });

  const checkIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const appStateRef = useRef<AppStateStatus>(AppState.currentState);

  // Check session validity
  const checkSession = useCallback(async () => {
    const valid = await isSessionValid();
    const remaining = await getSessionTimeRemaining();

    setSessionState((prev) => ({
      ...prev,
      isActive: valid,
      timeRemaining: remaining,
      showWarning: valid && remaining <= warningThreshold && remaining > 0,
    }));

    if (!valid) {
      // Session expired
      handleTimeout();
    } else if (remaining <= warningThreshold && remaining > 0) {
      // Show warning
      onWarning?.(remaining);
    }
  }, [warningThreshold, onWarning]);

  // Handle session timeout
  const handleTimeout = useCallback(async () => {
    // Clear tokens
    await clearAuthTokens();

    // Call timeout handler
    onTimeout?.();

    // Redirect to login
    router.replace('/(auth)/login');
  }, [onTimeout]);

  // Update activity on user interaction
  const refreshActivity = useCallback(async () => {
    await updateLastActivity();
    setSessionState((prev) => ({
      ...prev,
      isActive: true,
      timeRemaining: SESSION_TIMEOUT_MS / 1000,
      showWarning: false,
    }));
  }, []);

  // Handle app state changes
  useEffect(() => {
    const subscription = AppState.addEventListener('change', async (nextState) => {
      if (
        appStateRef.current.match(/inactive|background/) &&
        nextState === 'active'
      ) {
        // App came to foreground - check session
        await checkSession();
      }
      appStateRef.current = nextState;
    });

    return () => {
      subscription.remove();
    };
  }, [checkSession]);

  // Start session check interval
  useEffect(() => {
    if (!enabled) return;

    // Check immediately
    checkSession();

    // Check every 30 seconds
    checkIntervalRef.current = setInterval(checkSession, 30000);

    return () => {
      if (checkIntervalRef.current) {
        clearInterval(checkIntervalRef.current);
      }
    };
  }, [enabled, checkSession]);

  return {
    ...sessionState,
    refreshActivity,
    checkSession,
  };
}

export default useSessionTimeout;
