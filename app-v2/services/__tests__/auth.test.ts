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

// ─── clearAuthTokens ──────────────────────────────────────────────────────────

import { clearAuthTokens } from '../api';

describe('clearAuthTokens', () => {
  it('calls supabase.auth.signOut with scope local', async () => {
    __mockAuth.signOut.mockResolvedValueOnce({ error: null });
    await clearAuthTokens();
    expect(__mockAuth.signOut).toHaveBeenCalledWith({ scope: 'local' });
  });

  it('does not throw when signOut returns an error', async () => {
    __mockAuth.signOut.mockResolvedValueOnce({ error: new Error('offline') });
    await expect(clearAuthTokens()).resolves.not.toThrow();
  });
});

// ─── authApi session hydration ────────────────────────────────────────────────

import { authApi } from '../api';

global.fetch = jest.fn();

describe('authApi.login', () => {
  it('calls supabase.auth.setSession with tokens from backend response', async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({
        user: { id: 'u1', email: 'a@b.com', created_at: '' },
        access_token: 'at1',
        refresh_token: 'rt1',
      }),
    });
    __mockAuth.setSession.mockResolvedValueOnce({ data: {}, error: null });

    await authApi.login('a@b.com', 'pass');

    expect(__mockAuth.setSession).toHaveBeenCalledWith({
      access_token: 'at1',
      refresh_token: 'rt1',
    });
  });
});

describe('authApi.signup', () => {
  it('calls supabase.auth.setSession with tokens from backend response', async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({
        user: { id: 'u2', email: 'c@d.com', created_at: '' },
        access_token: 'at2',
        refresh_token: 'rt2',
      }),
    });
    __mockAuth.setSession.mockResolvedValueOnce({ data: {}, error: null });

    await authApi.signup('c@d.com', 'pass');

    expect(__mockAuth.setSession).toHaveBeenCalledWith({
      access_token: 'at2',
      refresh_token: 'rt2',
    });
  });
});

// ─── 401 retry ────────────────────────────────────────────────────────────────

describe('apiRequest 401 retry', () => {
  it('calls supabase.auth.refreshSession on expired-token 401, then retries the request', async () => {
    // First fetch call → 401 with token_expired
    // Second fetch call (retry) → 200
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: { get: () => null },
        json: async () => ({ detail: { token_expired: true, message: 'expired' } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => null },
        json: async () => ({
          user: { id: 'u1', email: 'a@b.com', created_at: '' },
          access_token: 'at-retry',
          refresh_token: 'rt-retry',
        }),
      });

    // getAuthToken is called before each request attempt (via Authorization header)
    __mockAuth.getSession
      .mockResolvedValueOnce({ data: { session: { access_token: 'old-token' } } })
      .mockResolvedValueOnce({ data: { session: { access_token: 'new-token' } } });

    __mockAuth.refreshSession.mockResolvedValueOnce({
      data: { session: { access_token: 'new-token' } },
      error: null,
    });
    __mockAuth.setSession.mockResolvedValueOnce({ data: {}, error: null });

    await authApi.login('a@b.com', 'pass');

    // refreshSession should have been called exactly once (on the 401 response)
    expect(__mockAuth.refreshSession).toHaveBeenCalledTimes(1);
    // fetch should have been called twice (original + retry)
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });
});
