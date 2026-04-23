/**
 * Security Service — SecureStore wrappers only.
 *
 * ⚠️ QUARANTINED (security audit S5, 2026-04-20):
 *
 * This file previously exported a set of "cryptographic" helpers
 * (sha256, generateSecureRandom, hashValue, verifyHash, deriveMasterKey,
 * storeMasterKeyHash, verifyMasterKey, generateFileIntegrityHash,
 * verifyFileIntegrity) that were all counterfeit:
 *   - sha256() was a djb2 variant returning a 16-char hex (32-bit output)
 *   - getRandomBytes() used Math.random()
 *   - deriveMasterKey() advertised "PBKDF2" but ran 1000 rounds of djb2
 *
 * None of them had external callers at the time of the audit, but their
 * names were the nearest-neighbour matches when the real SEK flow lands
 * (audit finding S1). To prevent them being wired into future crypto
 * code by mistake, every counterfeit export has been deleted.
 *
 * When you need real cryptography, use:
 *   - `expo-crypto.digestStringAsync(CryptoDigestAlgorithm.SHA256, …)`
 *   - `expo-crypto.getRandomBytesAsync(length)`
 *   - `react-native-argon2` (for password-derived keys)
 *
 * DO NOT re-export anything named hash/verify/derive/generate*Random
 * from this file.
 */

import * as SecureStore from 'expo-secure-store';

const SECURE_STORE_OPTIONS = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

const STORAGE_KEYS = {
  MASTER_KEY_HASH: 'rythmiq_master_key_hash',
  BIOMETRIC_ENABLED: 'rythmiq_biometric_enabled',
} as const;

export async function secureStore(key: string, value: string): Promise<boolean> {
  try {
    await SecureStore.setItemAsync(key, value, SECURE_STORE_OPTIONS);
    return true;
  } catch (error) {
    console.error('SecureStore set error:', error);
    return false;
  }
}

export async function secureRetrieve(key: string): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(key, SECURE_STORE_OPTIONS);
  } catch (error) {
    console.error('SecureStore get error:', error);
    return null;
  }
}

export async function secureDelete(key: string): Promise<boolean> {
  try {
    await SecureStore.deleteItemAsync(key, SECURE_STORE_OPTIONS);
    return true;
  } catch (error) {
    console.error('SecureStore delete error:', error);
    return false;
  }
}

export async function isBiometricEnabled(): Promise<boolean> {
  const enabled = await secureRetrieve(STORAGE_KEYS.BIOMETRIC_ENABLED);
  return enabled === 'true';
}

export async function setBiometricEnabled(enabled: boolean): Promise<boolean> {
  return await secureStore(STORAGE_KEYS.BIOMETRIC_ENABLED, enabled.toString());
}

export { STORAGE_KEYS };
