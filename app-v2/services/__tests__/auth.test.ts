// Set env vars before module load so supabase client is not null in tests
process.env.EXPO_PUBLIC_SUPABASE_URL = 'https://test.supabase.co';
process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY = 'test-anon-key';

import * as SecureStore from 'expo-secure-store';

// __mockAuth is used by getAuthToken, clearAuthTokens, authApi, and 401 retry tests below.
const { __mockAuth } = require('@supabase/supabase-js');

// Import after mocks are set up
import { ExpoSecureStoreAdapter, getAuthToken } from '../api';

beforeEach(() => jest.clearAllMocks());

// ─── ExpoSecureStoreAdapter ───────────────────────────────────────────────────

describe('ExpoSecureStoreAdapter', () => {
  it('getItem returns value from SecureStore', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValueOnce('tok123');
    const result = await ExpoSecureStoreAdapter.getItem('my-key');
    expect(SecureStore.getItemAsync).toHaveBeenCalledWith('my-key');
    expect(result).toBe('tok123');
  });

  it('getItem returns null when SecureStore throws', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockRejectedValueOnce(new Error('locked'));
    const result = await ExpoSecureStoreAdapter.getItem('my-key');
    expect(result).toBeNull();
  });

  it('setItem writes to SecureStore', async () => {
    (SecureStore.setItemAsync as jest.Mock).mockResolvedValueOnce(undefined);
    await ExpoSecureStoreAdapter.setItem('my-key', 'my-value');
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith('my-key', 'my-value');
  });

  it('removeItem deletes from SecureStore', async () => {
    (SecureStore.deleteItemAsync as jest.Mock).mockResolvedValueOnce(undefined);
    await ExpoSecureStoreAdapter.removeItem('my-key');
    expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('my-key');
  });
});

// ─── getAuthToken ─────────────────────────────────────────────────────────────

describe('getAuthToken', () => {
  it('returns access_token from active session', async () => {
    __mockAuth.getSession.mockResolvedValueOnce({
      data: { session: { access_token: 'access-abc' } },
    });
    const token = await getAuthToken();
    expect(token).toBe('access-abc');
  });

  it('returns null when session is null', async () => {
    __mockAuth.getSession.mockResolvedValueOnce({ data: { session: null } });
    const token = await getAuthToken();
    expect(token).toBeNull();
  });

  it('returns null when getSession throws', async () => {
    __mockAuth.getSession.mockRejectedValueOnce(new Error('storage error'));
    const token = await getAuthToken();
    expect(token).toBeNull();
  });
});
