/**
 * API Client for Rythmiq Backend
 * 
 * Handles all HTTP communication with the API gateway.
 * Includes auth token management and error handling.
 * 
 * DEV SANDBOX MODE:
 * When DEV_SANDBOX_MODE is enabled, the client sends x-dev-sandbox: true header
 * which tells the backend to bypass authentication and use a static dev user.
 * All processing pipelines remain production-grade.
 */

import * as SecureStore from 'expo-secure-store';
import * as WebBrowser from 'expo-web-browser';
import { makeRedirectUri } from 'expo-auth-session';
import { createClient } from '@supabase/supabase-js';
import { Platform } from 'react-native';

WebBrowser.maybeCompleteAuthSession();

// API Configuration
const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

// Dev sandbox mode - set via environment variable
const DEV_SANDBOX_MODE = process.env.EXPO_PUBLIC_DEV_SANDBOX === 'true';
const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;

// Token storage keys
const AUTH_TOKEN_KEY = 'rythmiq_auth_token';
const REFRESH_TOKEN_KEY = 'rythmiq_refresh_token';
const OAUTH_TIMEOUT_MS = 120000;
const webMemoryStorage = new Map<string, string>();

function isWebStorageAvailable(): boolean {
  return Platform.OS === 'web' && typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

async function setStoredValue(key: string, value: string): Promise<void> {
  if (Platform.OS === 'web') {
    try {
      if (isWebStorageAvailable()) {
        window.localStorage.setItem(key, value);
      } else {
        webMemoryStorage.set(key, value);
      }
    } catch {
      webMemoryStorage.set(key, value);
    }
    return;
  }

  await SecureStore.setItemAsync(key, value);
}

async function getStoredValue(key: string): Promise<string | null> {
  if (Platform.OS === 'web') {
    try {
      if (isWebStorageAvailable()) {
        return window.localStorage.getItem(key);
      }
    } catch {
      return webMemoryStorage.get(key) ?? null;
    }

    return webMemoryStorage.get(key) ?? null;
  }

  return SecureStore.getItemAsync(key);
}

async function deleteStoredValue(key: string): Promise<void> {
  if (Platform.OS === 'web') {
    try {
      if (isWebStorageAvailable()) {
        window.localStorage.removeItem(key);
      }
    } catch {
      webMemoryStorage.delete(key);
    }

    webMemoryStorage.delete(key);
    return;
  }

  await SecureStore.deleteItemAsync(key);
}

function getOAuthRedirectUri(): string {
  return makeRedirectUri({
    scheme: 'rythmiq',
    path: 'auth/callback',
  });
}

function normalizeRedirectUri(uri: string): string {
  return uri.endsWith('/') ? uri.slice(0, -1) : uri;
}

function isExpoGoRedirectUri(uri: string): boolean {
  return uri.startsWith('exp://');
}

function extractOAuthCallbackData(callbackUrl: string): {
  code: string | null;
  accessToken: string | null;
  refreshToken: string | null;
} {
  const parsed = new URL(callbackUrl);
  const hashParams = new URLSearchParams(parsed.hash.replace(/^#/, ''));

  return {
    code: parsed.searchParams.get('code'),
    accessToken: hashParams.get('access_token') || parsed.searchParams.get('access_token'),
    refreshToken: hashParams.get('refresh_token') || parsed.searchParams.get('refresh_token'),
  };
}

function toAuthResponse(
  session: { access_token: string; refresh_token: string },
  user: { id: string; email?: string | null; created_at?: string; user_metadata?: Record<string, unknown>; email_confirmed_at?: string | null }
): AuthResponse {
  return {
    user: {
      id: user.id,
      email: user.email || '',
      created_at: user.created_at,
      name: (user.user_metadata?.name as string | undefined) || null,
      email_confirmed: user.email_confirmed_at != null,
    },
    access_token: session.access_token,
    refresh_token: session.refresh_token,
  };
}

export function getCurrentOAuthRedirectUri(): string {
  return getOAuthRedirectUri();
}

const supabase = SUPABASE_URL && SUPABASE_ANON_KEY
  ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  : null;

type OAuthProvider = 'google' | 'apple';

function getOAuthProviderLabel(provider: OAuthProvider): string {
  return provider === 'google' ? 'Google' : 'Apple';
}

function normalizeOAuthStartError(provider: OAuthProvider, message?: string): ApiError {
  const providerLabel = getOAuthProviderLabel(provider);
  const lower = (message || '').toLowerCase();
  const redirectUri = getOAuthRedirectUri();
  const isExpoGoRedirect = isExpoGoRedirectUri(redirectUri);
  const redirectHint = isExpoGoRedirect
    ? `Current Expo Go redirect is ${redirectUri}. Add this exact URL (or exp://**) to Supabase Redirect URLs.`
    : `Current app redirect is ${redirectUri}. Add this exact URL (or matching wildcard) in Supabase Redirect URLs.`;

  if (lower.includes('not enabled') || lower.includes('provider is not enabled') || lower.includes('unsupported provider')) {
    return new ApiError(
      400,
      'OAUTH_PROVIDER_NOT_ENABLED',
      `${providerLabel} sign-in is not enabled in Supabase yet. Complete ${providerLabel} provider setup first.`
    );
  }

  if (lower.includes('redirect') || lower.includes('callback')) {
    return new ApiError(
      400,
      'OAUTH_REDIRECT_MISMATCH',
      `${providerLabel} sign-in redirect is not configured. ${redirectHint}`
    );
  }

  return new ApiError(400, 'OAUTH_START_FAILED', message || `Could not start ${providerLabel} sign-in.`);
}

function ensureSupabaseClient() {
  if (!supabase) {
    throw new ApiError(
      500,
      'SUPABASE_NOT_CONFIGURED',
      'Social login is not configured. Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY.'
    );
  }

  return supabase;
}

async function storeAuthTokens(accessToken: string, refreshToken?: string | null): Promise<void> {
  if (accessToken) {
    await setAuthToken(accessToken);
  }

  if (refreshToken) {
    await setStoredValue(REFRESH_TOKEN_KEY, refreshToken);
  }
}

/**
 * Check if running in dev sandbox mode
 */
export function isDevSandboxMode(): boolean {
  return DEV_SANDBOX_MODE;
}

/**
 * API Error with structured error information
 */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: Record<string, unknown>
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Get stored auth token
 */
export async function getAuthToken(): Promise<string | null> {
  try {
    return await getStoredValue(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

/**
 * Store auth token securely
 */
export async function setAuthToken(token: string): Promise<void> {
  await setStoredValue(AUTH_TOKEN_KEY, token);
}

/**
 * Clear auth tokens (logout)
 */
export async function clearAuthTokens(): Promise<void> {
  await deleteStoredValue(AUTH_TOKEN_KEY);
  await deleteStoredValue(REFRESH_TOKEN_KEY);
}

/**
 * Make authenticated API request
 * In dev sandbox mode, sends x-dev-sandbox header to bypass auth
 */
async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = await getAuthToken();
  
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };
  
  // Dev sandbox mode: add header to bypass auth
  if (DEV_SANDBOX_MODE) {
    (headers as Record<string, string>)['x-dev-sandbox'] = 'true';
  } else if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }
  
  const requestUrl = `${API_BASE_URL}${endpoint}`;

  let response: Response;
  try {
    response = await fetch(requestUrl, {
      ...options,
      headers,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Network request failed';
    throw new ApiError(
      0,
      'NETWORK_ERROR',
      `Cannot reach API at ${API_BASE_URL}. ${message}. Ensure backend is running and reachable from your device (for LAN access start API with --host 0.0.0.0).`
    );
  }

  let data: Record<string, any> = {};
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  
  if (!response.ok) {
    const detail = (data.detail && typeof data.detail === 'object')
      ? data.detail
      : data;

    throw new ApiError(
      response.status,
      detail.error_code || detail.code || 'UNKNOWN_ERROR',
      detail.message || data.message || 'An error occurred',
      detail.details || data.details
    );
  }
  
  return data as T;
}

// =============================================================================
// Auth API
// =============================================================================

export interface AuthResponse {
  user: {
    id: string;
    email: string;
    created_at?: string;
    name?: string | null;
    email_confirmed?: boolean;
  };
  access_token: string;
  refresh_token: string;
}

export interface SessionResponse {
  user_id: string;
  email?: string | null;
  name?: string | null;
  expires_at: number;
}

export const authApi = {
  /**
   * Sign up with email and password
   */
  async signup(email: string, password: string, name?: string): Promise<AuthResponse> {
    const response = await apiRequest<AuthResponse>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email, password, name }),
    });

    await storeAuthTokens(response.access_token, response.refresh_token);
    
    return response;
  },
  
  /**
   * Login with email and password
   */
  async login(email: string, password: string): Promise<AuthResponse> {
    const response = await apiRequest<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });

    await storeAuthTokens(response.access_token, response.refresh_token);
    
    return response;
  },

  /**
   * Login with social OAuth provider
   */
  async loginWithOAuth(provider: OAuthProvider): Promise<AuthResponse> {
    const client = ensureSupabaseClient();
    const redirectTo = getOAuthRedirectUri();
    const useImplicitFlow = Platform.OS !== 'web';

    const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

    const tryRecoverExistingSession = async (maxAttempts = 1): Promise<AuthResponse | null> => {
      for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
        const { data: existingSessionData, error: existingSessionError } = await client.auth.getSession();
        if (!existingSessionError && existingSessionData.session) {
          const sessionUser = existingSessionData.session.user;

          if (sessionUser) {
            await storeAuthTokens(
              existingSessionData.session.access_token,
              existingSessionData.session.refresh_token
            );
            return toAuthResponse(existingSessionData.session, sessionUser);
          }

          const { data: existingUserData, error: existingUserError } = await client.auth.getUser(
            existingSessionData.session.access_token
          );

          if (!existingUserError && existingUserData.user) {
            await storeAuthTokens(
              existingSessionData.session.access_token,
              existingSessionData.session.refresh_token
            );
            return toAuthResponse(existingSessionData.session, existingUserData.user);
          }
        }

        if (attempt < maxAttempts) {
          await wait(500);
        }
      }

      return null;
    };

    const { data, error } = await client.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo,
        skipBrowserRedirect: true,
        ...(useImplicitFlow ? { queryParams: { flow_type: 'implicit' } } : {}),
      },
    });

    if (error || !data.url) {
      throw normalizeOAuthStartError(provider, error?.message);
    }

    try {
      const authorizeUrl = new URL(data.url);
      const redirectParam = authorizeUrl.searchParams.get('redirect_to');
      if (!redirectParam) {
        throw new ApiError(
          400,
          'OAUTH_REDIRECT_MISSING',
          `OAuth redirect parameter is missing. Current app redirect is ${redirectTo}. Add this exact value in Supabase Redirect URLs.`
        );
      }

      const normalizedExpected = normalizeRedirectUri(redirectTo);
      const normalizedActual = normalizeRedirectUri(redirectParam);

      const isAcceptedNativeScheme =
        redirectParam.startsWith('rythmiq://') || redirectParam.startsWith('exp://');
      const isExactMatch = normalizedActual === normalizedExpected;

      if (!isAcceptedNativeScheme && !isExactMatch) {
        throw new ApiError(
          400,
          'OAUTH_REDIRECT_UNEXPECTED',
          `OAuth redirect is set to ${redirectParam}, but app expects ${redirectTo}. Add ${redirectTo} in Supabase Redirect URLs.`
        );
      }
    } catch (err) {
      if (err instanceof ApiError) {
        throw err;
      }
    }

    const result = await Promise.race([
      WebBrowser.openAuthSessionAsync(data.url, redirectTo),
      new Promise<never>((_, reject) => {
        setTimeout(() => {
          reject(
            new ApiError(
              408,
              'OAUTH_TIMEOUT',
              `Google sign-in timed out waiting for app callback (${redirectTo}). If browser redirects to Site URL, add ${redirectTo} exactly in Supabase Redirect URLs and retry.`
            )
          );
        }, OAUTH_TIMEOUT_MS);
      }),
    ]);

    if (result.type !== 'success' || !result.url) {
      const recoveredSession = await tryRecoverExistingSession(20);
      if (recoveredSession) {
        return recoveredSession;
      }

      throw new ApiError(
        400,
        'OAUTH_CANCELLED',
        `Social sign-in was cancelled (${result.type}). Current app redirect is ${redirectTo}. If browser went to Site URL/localhost, add ${redirectTo} exactly in Supabase Redirect URLs.`
      );
    }

    const callbackData = extractOAuthCallbackData(result.url);

    if (callbackData.code) {
      const { data: sessionData, error: exchangeError } = await client.auth.exchangeCodeForSession(callbackData.code);
      if (exchangeError || !sessionData.session || !sessionData.user) {
        throw new ApiError(401, 'OAUTH_EXCHANGE_FAILED', exchangeError?.message || 'Could not complete social sign-in.');
      }

      await storeAuthTokens(sessionData.session.access_token, sessionData.session.refresh_token);
      return toAuthResponse(sessionData.session, sessionData.user);
    }

    if (callbackData.accessToken && callbackData.refreshToken) {
      const { data: sessionData, error: setSessionError } = await client.auth.setSession({
        access_token: callbackData.accessToken,
        refresh_token: callbackData.refreshToken,
      });

      if (setSessionError || !sessionData.session || !sessionData.user) {
        throw new ApiError(401, 'OAUTH_SET_SESSION_FAILED', setSessionError?.message || 'Could not establish social sign-in session.');
      }

      await storeAuthTokens(sessionData.session.access_token, sessionData.session.refresh_token);
      return toAuthResponse(sessionData.session, sessionData.user);
    }

    const recoveredSession = await tryRecoverExistingSession(6);
    if (recoveredSession) {
      return recoveredSession;
    }

    throw new ApiError(
      400,
      'OAUTH_CALLBACK_INVALID',
      `OAuth callback did not include auth code or tokens. Callback URL: ${result.url}`
    );
  },
  
  /**
   * Logout current session
   */
  async logout(): Promise<void> {
    try {
      await apiRequest('/auth/logout', { method: 'POST' });
    } finally {
      await clearAuthTokens();
    }
  },
  
  /**
   * Get current session
   */
  async getSession(): Promise<SessionResponse> {
    return apiRequest<SessionResponse>('/auth/session');
  },
};

// =============================================================================
// Health API
// =============================================================================

export interface HealthResponse {
  status: string;
  dev_sandbox?: {
    enabled: boolean;
    storage_ttl_hours: number;
    message: string;
  };
}

export const healthApi = {
  /**
   * Check API health and get dev sandbox status
   */
  async check(): Promise<HealthResponse> {
    const response = await fetch(`${API_BASE_URL}/health`);
    return response.json();
  },
  
  /**
   * Check if backend is in dev sandbox mode
   */
  async isDevSandbox(): Promise<boolean> {
    try {
      const health = await this.check();
      return health.dev_sandbox?.enabled ?? false;
    } catch {
      return false;
    }
  },
};

// =============================================================================
// Documents API
// =============================================================================

export interface Document {
  id: string;
  type: string;
  filename: string;
  status: 'uploading' | 'uploaded' | 'processing' | 'ready' | 'failed';
  quality_score?: number;
  created_at: string;
  updated_at: string;
}

export interface UploadResponse {
  document_id: string;
  upload_url: string;
}

export interface JobStatus {
  job_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  job_type?: 'master' | 'adapt';
  document_type?: 'photo' | 'signature' | 'document';
  document_name?: string;
  portal_schema_name?: string;
  quality_score?: number;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  updated_at?: string;
  output_file_path?: string;
  download_url?: string;
  preview_url?: string;
  error_details?: {
    code?: string;
    message?: string;
  };
  error?: {
    code: string;
    message: string;
  };
}

export const documentsApi = {
  /**
   * Create a MASTER document job (Scan flow - no portal)
   * This creates an enhanced master document stored in the vault.
   * 
   * NOTE: Current backend requires portal_schema_name, so we use a generic
   * schema for master documents. In future, backend will support true "master" jobs.
   */
  async createMasterJob(
    documentType: 'photo' | 'signature' | 'document',
    filename: string,
    mimeType: string,
    fileSizeBytes: number
  ): Promise<{ job_id: string; upload_url: string; expires_at: string }> {
    return apiRequest<{ job_id: string; upload_url: string; expires_at: string }>('/jobs', {
      method: 'POST',
      body: JSON.stringify({
        job_type: 'master',
        document_type: documentType,
        filename,
        mime_type: mimeType,
        file_size_bytes: fileSizeBytes,
        defer_processing: true,
      }),
    });
  },

  /**
   * Submit a previously created pending job for processing.
   * Used after uploading to the presigned URL.
   */
  async submitJob(jobId: string): Promise<{ job_id: string; status: string }> {
    return apiRequest<{ job_id: string; status: string }>(`/jobs/${jobId}/submit`, {
      method: 'POST',
    });
  },

  /**
   * Create an ADAPTATION job (Export flow - requires portal)
   * This adapts an existing master document for a specific portal.
   */
  async createAdaptJob(
    masterJobId: string,
    portalSchemaName: string
  ): Promise<{ job_id: string }> {
    return apiRequest<{ job_id: string }>('/adapt', {
      method: 'POST',
      body: JSON.stringify({
        master_job_id: masterJobId,
        portal_schema_name: portalSchemaName,
      }),
    });
  },

  /**
   * Create a new job and get upload URL (legacy - kept for compatibility)
   */
  async createJob(
    portalSchemaName: string,
    filename: string,
    mimeType: string,
    fileSizeBytes: number
  ): Promise<{ job_id: string; upload_url: string; expires_at: string }> {
    return apiRequest<{ job_id: string; upload_url: string; expires_at: string }>('/jobs', {
      method: 'POST',
      body: JSON.stringify({
        portal_schema_name: portalSchemaName,
        filename,
        mime_type: mimeType,
        file_size_bytes: fileSizeBytes,
      }),
    });
  },
  
  /**
   * Upload file directly to storage using presigned URL
   */
  async uploadToPresignedUrl(
    uploadUrl: string,
    fileUri: string,
    mimeType: string
  ): Promise<void> {
    const response = await fetch(fileUri);
    const blob = await response.blob();
    
    const uploadResponse = await fetch(uploadUrl, {
      method: 'PUT',
      headers: {
        'Content-Type': mimeType,
      },
      body: blob,
    });
    
    if (!uploadResponse.ok) {
      throw new ApiError(
        uploadResponse.status,
        'UPLOAD_FAILED',
        'Failed to upload file to storage'
      );
    }
  },
  
  /**
   * Get job status
   */
  async getJobStatus(jobId: string): Promise<JobStatus> {
    return apiRequest<JobStatus>(`/jobs/${jobId}`);
  },
  
  /**
   * Get job output download URL
   */
  async getJobOutput(jobId: string): Promise<{ download_url: string; expires_at: string }> {
    return apiRequest<{ download_url: string; expires_at: string }>(`/jobs/${jobId}/output`);
  },
  
  /**
   * List user's jobs
   */
  async listJobs(): Promise<{ jobs: JobStatus[] }> {
    return apiRequest<{ jobs: JobStatus[] }>('/jobs');
  },
};

// =============================================================================
// Schemas API
// =============================================================================

export interface PortalSchema {
  id: string;
  name: string;
  portal?: string;
  document_type?: string;
  version?: number;
  requirements?: {
    photo?: { dimensions: [number, number]; dpi: number; max_kb: number; format: string };
    signature?: { dimensions: [number, number]; dpi: number; max_kb: number; format: string };
  };
  requirements_summary?: {
    photo?: { dimensions: [number, number]; dpi: number; max_kb: number; format: string };
    signature?: { dimensions: [number, number]; dpi: number; max_kb: number; format: string };
  };
}

export interface AdaptResponse {
  job_id: string;
  status: string;
}

export interface AdaptStatusResponse {
  job_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  zip_url?: string;
  expires_at?: string;
  error?: {
    code: string;
    message: string;
  };
}

/**
 * Mock portal schemas for development/testing
 * These match the portal_schemas.json structure
 */
const MOCK_PORTAL_SCHEMAS: PortalSchema[] = [
  {
    id: 'upsc_photo',
    name: 'UPSC Photo',
    portal: 'UPSC',
    document_type: 'photo',
    requirements: {
      photo: { dimensions: [140, 180], dpi: 300, max_kb: 40, format: 'jpeg' },
    },
  },
  {
    id: 'upsc_signature',
    name: 'UPSC Signature',
    portal: 'UPSC',
    document_type: 'signature',
    requirements: {
      signature: { dimensions: [140, 60], dpi: 200, max_kb: 20, format: 'jpeg' },
    },
  },
  {
    id: 'ssc_photo',
    name: 'SSC Photo',
    portal: 'SSC',
    document_type: 'photo',
    requirements: {
      photo: { dimensions: [100, 120], dpi: 100, max_kb: 100, format: 'jpeg' },
    },
  },
  {
    id: 'ssc_signature',
    name: 'SSC Signature',
    portal: 'SSC',
    document_type: 'signature',
    requirements: {
      signature: { dimensions: [140, 60], dpi: 100, max_kb: 50, format: 'jpeg' },
    },
  },
  {
    id: 'ibps_photo',
    name: 'IBPS Photo',
    portal: 'IBPS',
    document_type: 'photo',
    requirements: {
      photo: { dimensions: [200, 230], dpi: 200, max_kb: 50, format: 'jpeg' },
    },
  },
  {
    id: 'ibps_signature',
    name: 'IBPS Signature',
    portal: 'IBPS',
    document_type: 'signature',
    requirements: {
      signature: { dimensions: [140, 60], dpi: 200, max_kb: 20, format: 'jpeg' },
    },
  },
  {
    id: 'neet_photo',
    name: 'NEET Photo',
    portal: 'NTA NEET',
    document_type: 'photo',
    requirements: {
      photo: { dimensions: [181, 244], dpi: 200, max_kb: 200, format: 'jpeg' },
    },
  },
  {
    id: 'neet_signature',
    name: 'NEET Signature',
    portal: 'NTA NEET',
    document_type: 'signature',
    requirements: {
      signature: { dimensions: [181, 89], dpi: 200, max_kb: 50, format: 'jpeg' },
    },
  },
  {
    id: 'jee_photo',
    name: 'JEE Photo',
    portal: 'NTA JEE',
    document_type: 'photo',
    requirements: {
      photo: { dimensions: [181, 244], dpi: 200, max_kb: 200, format: 'jpeg' },
    },
  },
  {
    id: 'jee_signature',
    name: 'JEE Signature',
    portal: 'NTA JEE',
    document_type: 'signature',
    requirements: {
      signature: { dimensions: [181, 89], dpi: 200, max_kb: 50, format: 'jpeg' },
    },
  },
  {
    id: 'passport_photo',
    name: 'Passport Photo',
    portal: 'Passport Seva',
    document_type: 'photo',
    requirements: {
      photo: { dimensions: [413, 531], dpi: 300, max_kb: 300, format: 'jpeg' },
    },
  },
  {
    id: 'rrb_photo',
    name: 'RRB Photo',
    portal: 'RRB',
    document_type: 'photo',
    requirements: {
      photo: { dimensions: [165, 213], dpi: 200, max_kb: 50, format: 'jpeg' },
    },
  },
  {
    id: 'rrb_signature',
    name: 'RRB Signature',
    portal: 'RRB',
    document_type: 'signature',
    requirements: {
      signature: { dimensions: [165, 55], dpi: 200, max_kb: 30, format: 'jpeg' },
    },
  },
];

// Group schemas by portal for the UI
export function groupSchemasByPortal(schemas: PortalSchema[]): Record<string, PortalSchema[]> {
  const grouped: Record<string, PortalSchema[]> = {};
  for (const schema of schemas) {
    const portal = schema.portal || 'Other';
    if (!grouped[portal]) {
      grouped[portal] = [];
    }
    grouped[portal].push(schema);
  }
  return grouped;
}

export const schemasApi = {
  /**
   * List available portal schemas
   * Falls back to mock data if API is unavailable or returns empty
   */
  async list(): Promise<PortalSchema[]> {
    try {
      const result = await apiRequest<PortalSchema[]>('/schemas');
      // If API returns empty, use mock data for development
      if (!result || result.length === 0) {
        console.log('[schemasApi] API returned empty, using mock schemas');
        return MOCK_PORTAL_SCHEMAS;
      }
      return result;
    } catch (error) {
      // Fallback to mock data on error (e.g., during development)
      console.log('[schemasApi] API error, using mock schemas:', error);
      return MOCK_PORTAL_SCHEMAS;
    }
  },
  
  /**
   * Get specific schema
   */
  async get(schemaId: string): Promise<PortalSchema> {
    try {
      return await apiRequest<PortalSchema>(`/schemas/${schemaId}`);
    } catch (error) {
      // Fallback to mock data
      const mock = MOCK_PORTAL_SCHEMAS.find(s => s.id === schemaId);
      if (mock) return mock;
      throw error;
    }
  },
  
  /**
   * Adapt document to portal schema
   */
  async adapt(documentId: string, portalId: string): Promise<AdaptResponse> {
    return apiRequest<AdaptResponse>('/adapt', {
      method: 'POST',
      body: JSON.stringify({ document_id: documentId, portal_id: portalId }),
    });
  },
  
  /**
   * Get adaptation job status
   */
  async getAdaptStatus(jobId: string): Promise<AdaptStatusResponse> {
    return apiRequest<AdaptStatusResponse>(`/adapt/${jobId}`);
  },
};

export default {
  auth: authApi,
  health: healthApi,
  documents: documentsApi,
  schemas: schemasApi,
  isDevSandboxMode,
};
