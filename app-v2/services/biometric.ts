/**
 * Biometric Authentication Service
 * 
 * Handles fingerprint/Face ID authentication for app access.
 * Note: Requires expo-local-authentication to be installed.
 */

import { Platform, Alert } from 'react-native';
import { isBiometricEnabled, setBiometricEnabled } from './security';

// Type definitions (will use actual types when expo-local-authentication is installed)
interface LocalAuthModule {
  hasHardwareAsync: () => Promise<boolean>;
  supportedAuthenticationTypesAsync: () => Promise<number[]>;
  isEnrolledAsync: () => Promise<boolean>;
  getEnrolledLevelAsync: () => Promise<number>;
  authenticateAsync: (options: any) => Promise<{ success: boolean; error?: string }>;
}

const AuthenticationType = {
  FINGERPRINT: 1,
  FACIAL_RECOGNITION: 2,
  IRIS: 3,
};

const SecurityLevel = {
  NONE: 0,
  SECRET: 1,
  BIOMETRIC: 2,
};

// Lazy load the module
let LocalAuthentication: LocalAuthModule | null = null;

async function getLocalAuth(): Promise<LocalAuthModule | null> {
  if (LocalAuthentication) return LocalAuthentication;
  try {
    // @ts-ignore - dynamic import for optional dependency
    LocalAuthentication = require('expo-local-authentication');
    return LocalAuthentication;
  } catch {
    return null;
  }
}

export interface BiometricCapability {
  isAvailable: boolean;
  biometricTypes: number[];
  isEnrolled: boolean;
  securityLevel: number;
}

export interface AuthenticationResult {
  success: boolean;
  error?: string;
  warning?: string;
}

/**
 * Check device biometric capabilities
 */
export async function getBiometricCapability(): Promise<BiometricCapability> {
  try {
    const auth = await getLocalAuth();
    if (!auth) {
      return {
        isAvailable: false,
        biometricTypes: [],
        isEnrolled: false,
        securityLevel: SecurityLevel.NONE,
      };
    }

    const [hasHardware, supportedTypes, isEnrolled, securityLevel] = await Promise.all([
      auth.hasHardwareAsync(),
      auth.supportedAuthenticationTypesAsync(),
      auth.isEnrolledAsync(),
      auth.getEnrolledLevelAsync(),
    ]);

    return {
      isAvailable: hasHardware && isEnrolled,
      biometricTypes: supportedTypes,
      isEnrolled,
      securityLevel,
    };
  } catch (error) {
    console.error('Error checking biometric capability:', error);
    return {
      isAvailable: false,
      biometricTypes: [],
      isEnrolled: false,
      securityLevel: SecurityLevel.NONE,
    };
  }
}

/**
 * Get human-readable biometric type name
 */
export function getBiometricTypeName(types: number[]): string {
  if (types.includes(AuthenticationType.FACIAL_RECOGNITION)) {
    return Platform.OS === 'ios' ? 'Face ID' : 'Face Recognition';
  }
  if (types.includes(AuthenticationType.FINGERPRINT)) {
    return Platform.OS === 'ios' ? 'Touch ID' : 'Fingerprint';
  }
  if (types.includes(AuthenticationType.IRIS)) {
    return 'Iris Recognition';
  }
  return 'Biometric';
}

/**
 * Authenticate user with biometrics
 */
export async function authenticateWithBiometrics(
  reason: string = 'Authenticate to access Rythmiq'
): Promise<AuthenticationResult> {
  try {
    const auth = await getLocalAuth();
    if (!auth) {
      return {
        success: false,
        error: 'Biometric authentication is not available.',
      };
    }

    const capability = await getBiometricCapability();

    if (!capability.isAvailable) {
      return {
        success: false,
        error: 'Biometric authentication is not available on this device.',
      };
    }

    const result = await auth.authenticateAsync({
      promptMessage: reason,
      cancelLabel: 'Cancel',
      disableDeviceFallback: false,
      fallbackLabel: 'Use Passcode',
    });

    if (result.success) {
      return { success: true };
    }

    // Handle specific error cases
    switch (result.error) {
      case 'user_cancel':
        return {
          success: false,
          error: 'Authentication cancelled.',
        };
      case 'user_fallback':
        return {
          success: false,
          warning: 'User chose to use passcode.',
        };
      case 'lockout':
        return {
          success: false,
          error: 'Too many failed attempts. Please try again later.',
        };
      case 'not_enrolled':
        return {
          success: false,
          error: 'No biometrics enrolled. Please set up biometrics in device settings.',
        };
      default:
        return {
          success: false,
          error: 'Authentication failed. Please try again.',
        };
    }
  } catch (error) {
    console.error('Biometric authentication error:', error);
    return {
      success: false,
      error: 'An unexpected error occurred during authentication.',
    };
  }
}

/**
 * Enable biometric authentication for app access
 */
export async function enableBiometricAuth(): Promise<boolean> {
  const capability = await getBiometricCapability();

  if (!capability.isAvailable) {
    Alert.alert(
      'Not Available',
      'Biometric authentication is not available on this device. Please set up fingerprint or face recognition in your device settings.',
      [{ text: 'OK' }]
    );
    return false;
  }

  // Verify user identity before enabling
  const authResult = await authenticateWithBiometrics(
    'Verify your identity to enable biometric unlock'
  );

  if (!authResult.success) {
    if (authResult.error) {
      Alert.alert('Error', authResult.error, [{ text: 'OK' }]);
    }
    return false;
  }

  // Save preference
  await setBiometricEnabled(true);
  return true;
}

/**
 * Disable biometric authentication
 */
export async function disableBiometricAuth(): Promise<boolean> {
  await setBiometricEnabled(false);
  return true;
}

/**
 * Check if biometric auth should be shown on app launch
 */
export async function shouldShowBiometricPrompt(): Promise<boolean> {
  const isEnabled = await isBiometricEnabled();
  if (!isEnabled) return false;

  const capability = await getBiometricCapability();
  return capability.isAvailable;
}

/**
 * Perform biometric check on app resume
 */
export async function performBiometricCheck(): Promise<boolean> {
  const shouldShow = await shouldShowBiometricPrompt();
  if (!shouldShow) return true; // Skip if not enabled

  const result = await authenticateWithBiometrics('Unlock Rythmiq');
  return result.success;
}

export default {
  getBiometricCapability,
  getBiometricTypeName,
  authenticateWithBiometrics,
  enableBiometricAuth,
  disableBiometricAuth,
  shouldShowBiometricPrompt,
  performBiometricCheck,
};
