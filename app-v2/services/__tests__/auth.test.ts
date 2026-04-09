import * as SecureStore from 'expo-secure-store';

const { __mockAuth } = require('@supabase/supabase-js');

// Import after mocks are set up
import { ExpoSecureStoreAdapter } from '../api';

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
