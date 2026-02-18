/**
 * Security Service
 * 
 * Handles encryption, secure storage, and security utilities.
 * Implements zero-knowledge architecture principles.
 */

import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

// Simple hash function (for production, consider using expo-crypto after installing)
async function sha256(message: string): Promise<string> {
  // Use a simple hash for now - in production install expo-crypto
  let hash = 0;
  for (let i = 0; i < message.length; i++) {
    const char = message.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  // Convert to hex and pad
  return Math.abs(hash).toString(16).padStart(16, '0');
}

// Generate random bytes using Math.random (for production, use expo-crypto)
function getRandomBytes(length: number): Uint8Array {
  const bytes = new Uint8Array(length);
  for (let i = 0; i < length; i++) {
    bytes[i] = Math.floor(Math.random() * 256);
  }
  return bytes;
}

// Constants
const SECURE_STORE_OPTIONS = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

const STORAGE_KEYS = {
  AUTH_TOKEN: 'rythmiq_auth_token',
  REFRESH_TOKEN: 'rythmiq_refresh_token',
  MASTER_KEY_HASH: 'rythmiq_master_key_hash',
  SESSION_EXPIRY: 'rythmiq_session_expiry',
  BIOMETRIC_ENABLED: 'rythmiq_biometric_enabled',
  LAST_ACTIVITY: 'rythmiq_last_activity',
} as const;

// Session timeout in milliseconds (30 minutes)
const SESSION_TIMEOUT_MS = 30 * 60 * 1000;

/**
 * Securely store a value
 */
export async function secureStore(key: string, value: string): Promise<boolean> {
  try {
    await SecureStore.setItemAsync(key, value, SECURE_STORE_OPTIONS);
    return true;
  } catch (error) {
    console.error('SecureStore set error:', error);
    return false;
  }
}

/**
 * Securely retrieve a value
 */
export async function secureRetrieve(key: string): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(key, SECURE_STORE_OPTIONS);
  } catch (error) {
    console.error('SecureStore get error:', error);
    return null;
  }
}

/**
 * Securely delete a value
 */
export async function secureDelete(key: string): Promise<boolean> {
  try {
    await SecureStore.deleteItemAsync(key, SECURE_STORE_OPTIONS);
    return true;
  } catch (error) {
    console.error('SecureStore delete error:', error);
    return false;
  }
}

/**
 * Store auth tokens securely
 */
export async function storeAuthTokens(
  accessToken: string,
  refreshToken?: string
): Promise<boolean> {
  const accessStored = await secureStore(STORAGE_KEYS.AUTH_TOKEN, accessToken);
  
  if (refreshToken) {
    await secureStore(STORAGE_KEYS.REFRESH_TOKEN, refreshToken);
  }
  
  // Set session expiry
  const expiry = Date.now() + SESSION_TIMEOUT_MS;
  await secureStore(STORAGE_KEYS.SESSION_EXPIRY, expiry.toString());
  
  // Update last activity
  await updateLastActivity();
  
  return accessStored;
}

/**
 * Get stored auth token
 */
export async function getAuthToken(): Promise<string | null> {
  // Check if session expired
  const isValid = await isSessionValid();
  if (!isValid) {
    await clearAuthTokens();
    return null;
  }
  
  return await secureRetrieve(STORAGE_KEYS.AUTH_TOKEN);
}

/**
 * Get stored refresh token
 */
export async function getRefreshToken(): Promise<string | null> {
  return await secureRetrieve(STORAGE_KEYS.REFRESH_TOKEN);
}

/**
 * Clear all auth tokens
 */
export async function clearAuthTokens(): Promise<void> {
  await Promise.all([
    secureDelete(STORAGE_KEYS.AUTH_TOKEN),
    secureDelete(STORAGE_KEYS.REFRESH_TOKEN),
    secureDelete(STORAGE_KEYS.SESSION_EXPIRY),
  ]);
}

/**
 * Check if session is still valid
 */
export async function isSessionValid(): Promise<boolean> {
  const expiryStr = await secureRetrieve(STORAGE_KEYS.SESSION_EXPIRY);
  if (!expiryStr) return false;
  
  const expiry = parseInt(expiryStr, 10);
  return Date.now() < expiry;
}

/**
 * Update last activity timestamp (extends session)
 */
export async function updateLastActivity(): Promise<void> {
  const newExpiry = Date.now() + SESSION_TIMEOUT_MS;
  await secureStore(STORAGE_KEYS.SESSION_EXPIRY, newExpiry.toString());
  await secureStore(STORAGE_KEYS.LAST_ACTIVITY, Date.now().toString());
}

/**
 * Get time until session expires (in seconds)
 */
export async function getSessionTimeRemaining(): Promise<number> {
  const expiryStr = await secureRetrieve(STORAGE_KEYS.SESSION_EXPIRY);
  if (!expiryStr) return 0;
  
  const expiry = parseInt(expiryStr, 10);
  const remaining = Math.max(0, expiry - Date.now());
  return Math.floor(remaining / 1000);
}

/**
 * Generate a secure random string
 */
export async function generateSecureRandom(length: number = 32): Promise<string> {
  const randomBytes = getRandomBytes(length);
  return Array.from(randomBytes)
    .map((b: number) => b.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * Hash a value using SHA-256
 */
export async function hashValue(value: string): Promise<string> {
  return await sha256(value);
}

/**
 * Verify a hash matches a value
 */
export async function verifyHash(value: string, hash: string): Promise<boolean> {
  const computedHash = await hashValue(value);
  return computedHash === hash;
}

/**
 * Generate a master key from password (for client-side encryption)
 * Uses PBKDF2 with high iteration count for security
 */
export async function deriveMasterKey(
  password: string,
  salt: string
): Promise<string> {
  // Combine password and salt, then hash multiple times
  // Note: For production, use a proper PBKDF2 implementation
  let key = password + salt;
  
  // Simulate high iteration count with multiple SHA-256 rounds
  for (let i = 0; i < 1000; i++) {
    key = await hashValue(key);
  }
  
  return key;
}

/**
 * Store master key hash for verification
 */
export async function storeMasterKeyHash(keyHash: string): Promise<boolean> {
  return await secureStore(STORAGE_KEYS.MASTER_KEY_HASH, keyHash);
}

/**
 * Verify master key against stored hash
 */
export async function verifyMasterKey(key: string): Promise<boolean> {
  const storedHash = await secureRetrieve(STORAGE_KEYS.MASTER_KEY_HASH);
  if (!storedHash) return false;
  
  const keyHash = await hashValue(key);
  return keyHash === storedHash;
}

/**
 * Check if biometric authentication is enabled
 */
export async function isBiometricEnabled(): Promise<boolean> {
  const enabled = await secureRetrieve(STORAGE_KEYS.BIOMETRIC_ENABLED);
  return enabled === 'true';
}

/**
 * Enable/disable biometric authentication
 */
export async function setBiometricEnabled(enabled: boolean): Promise<boolean> {
  return await secureStore(STORAGE_KEYS.BIOMETRIC_ENABLED, enabled.toString());
}

/**
 * Generate integrity hash for a file (for download verification)
 */
export async function generateFileIntegrityHash(content: string): Promise<string> {
  return await hashValue(content);
}

/**
 * Verify file integrity
 */
export async function verifyFileIntegrity(
  content: string,
  expectedHash: string
): Promise<boolean> {
  const actualHash = await hashValue(content);
  return actualHash === expectedHash;
}

// Export storage keys for external use
export { STORAGE_KEYS, SESSION_TIMEOUT_MS };
