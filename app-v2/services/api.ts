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
 * Attempt to refresh the Supabase session using the stored refresh token.
 * Returns the new access token, or null if refresh failed.
 */
async function tryRefreshToken(): Promise<string | null> {
  const client = supabase;
  if (!client) return null;

  const refreshToken = await getStoredValue(REFRESH_TOKEN_KEY);
  if (!refreshToken) return null;

  try {
    const { data, error } = await client.auth.refreshSession({ refresh_token: refreshToken });
    if (error || !data.session) return null;

    await storeAuthTokens(data.session.access_token, data.session.refresh_token);
    return data.session.access_token;
  } catch {
    return null;
  }
}

/**
 * Make authenticated API request
 * In dev sandbox mode, sends x-dev-sandbox header to bypass auth.
 * Automatically retries once on 401 by refreshing the Supabase session.
 */
async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {},
  _isRetry = false
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

  // Auto-refresh on 401 (expired token) — retry once
  if (response.status === 401 && !_isRetry && !DEV_SANDBOX_MODE) {
    const detail = (data.detail && typeof data.detail === 'object') ? data.detail : data;
    const isExpired = detail.token_expired === true
      || (detail.message || '').toLowerCase().includes('expired')
      || (detail.message || '').toLowerCase().includes('invalid token');

    if (isExpired) {
      const newToken = await tryRefreshToken();
      if (newToken) {
        return apiRequest<T>(endpoint, options, true);
      }
    }
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
  document_category?: string;
  document_subtype?: string;
  document_name?: string;
  portal_schema_name?: string;
  /** Quality of the raw uploaded image before any processing (0–1). */
  input_quality_score?: number | null;
  /** Quality of the final processed output image (0–1). */
  output_quality_score?: number | null;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  updated_at?: string;
  output_file_path?: string;
  download_url?: string;
  preview_url?: string;
  /** Signed URL to the actual master/adapted output file (JPEG or PDF). */
  output_url?: string;
  /** True if the output file at output_url is AES-256-GCM encrypted. */
  output_encrypted?: boolean;
  /** Base64-encoded nonce for decryption (only present when output_encrypted is true). */
  output_nonce?: string;
  /** Format of the output file: "jpeg" | "pdf". Use to determine MIME type and file extension. */
  output_format?: string;
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
    fileSizeBytes: number,
    documentCategory?: string,
    documentSubtype?: string,
  ): Promise<{ job_id: string; upload_url: string; expires_at: string }> {
    return apiRequest<{ job_id: string; upload_url: string; expires_at: string }>('/jobs', {
      method: 'POST',
      body: JSON.stringify({
        job_type: 'master',
        document_type: documentType,
        document_category: documentCategory,
        document_subtype: documentSubtype,
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
   * @param outputFormat - 'jpeg' (default), 'jpeg2000', or 'pdf_mrc' (lossless MRC)
   */
  async submitJob(
    jobId: string,
    outputFormat: string = 'jpeg',
    confirmedCropQuad?: [[number,number],[number,number],[number,number],[number,number]],
    documentCategory?: string,
    documentSubtype?: string,
    quadSource?: 'model' | 'manual',
  ): Promise<{ job_id: string; status: string }> {
    return apiRequest<{ job_id: string; status: string }>(`/jobs/${jobId}/submit`, {
      method: 'POST',
      body: JSON.stringify({
        output_format: outputFormat,
        ...(confirmedCropQuad ? { confirmed_crop_quad: confirmedCropQuad } : {}),
        ...(documentCategory ? { document_category: documentCategory } : {}),
        ...(documentSubtype ? { document_subtype: documentSubtype } : {}),
        ...(quadSource ? { quad_source: quadSource } : {}),
      }),
    });
  },

  /**
   * Create an ADAPTATION job (Export flow - requires portal)
   * Adapts an existing completed master job for a specific portal schema.
   * No file upload needed — the backend reuses the master's stored input.
   * Uses the form_schema_id + doc_id path (all document types supported).
   */
  async createAdaptJob(
    masterJobId: string,
    formSchemaId: string,
    docId: string,
  ): Promise<{ job_id: string }> {
    return apiRequest<{ job_id: string }>('/jobs', {
      method: 'POST',
      body: JSON.stringify({
        job_type: 'adapt',
        source_job_id: masterJobId,
        form_schema_id: formSchemaId,
        doc_id: docId,
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

  /**
   * Delete a job and its associated storage objects
   */
  async deleteJob(jobId: string): Promise<void> {
    await apiRequest<void>(`/jobs/${jobId}`, { method: 'DELETE' });
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

// =============================================================================
// Form Schemas API  (document checklists for registration forms)
// =============================================================================

export interface FormSchemaDocUpload {
  doc_id: string;
  label: string;
  description?: string;
  allowed_formats: string[];
  size_min_kb?: number;
  size_max_kb?: number;
  required: boolean;
  required_if?: string | null;
  specifications?: string[];
  /** Maps this requirement to a vault document category (e.g. 'identity', 'academic', 'photograph') */
  document_category?: string;
  /** Exact subtype required; omit to accept any doc in the category */
  document_subtype?: string;
  /** Portal-specific subtypes to inject into the upload UI for this category */
  seeds_document_subtypes?: string[];
}

export interface FormSchema {
  id: string;
  schema_type: string;
  schema_version?: string;
  display_name: string;
  short_name: string;
  category: string;
  conducting_body?: string;
  applicable_year?: number;
  document_uploads: FormSchemaDocUpload[];
  key_dates?: Record<string, string>;
}

const MOCK_FORM_SCHEMAS: FormSchema[] = [
  {
    id: 'neet_2026_registration',
    schema_type: 'exam_form',
    schema_version: '1.0.0',
    display_name: 'NEET UG 2026 Registration Form',
    short_name: 'NEET 2026',
    category: 'medical_entrance',
    conducting_body: 'National Testing Agency (NTA)',
    applicable_year: 2026,
    document_uploads: [
      { doc_id: 'photograph_passport', label: 'Passport-size Photograph (2×2 inch)', allowed_formats: ['JPG', 'JPEG'], size_max_kb: 200, required: true, document_category: 'photograph', document_subtype: 'Passport Photo' },
      { doc_id: 'photograph_postcard', label: 'Postcard-size Photograph (4×6 inch)', allowed_formats: ['JPG', 'JPEG'], size_max_kb: 200, required: true, document_category: 'photograph', document_subtype: 'Postcard Photo', seeds_document_subtypes: ['Postcard Photo'] },
      { doc_id: 'signature', label: 'Signature', allowed_formats: ['JPG', 'JPEG'], size_max_kb: 30, required: true, document_category: 'signature', document_subtype: 'Personal Signature' },
      { doc_id: 'left_thumb_impression', label: 'Left Hand Thumb Impression', allowed_formats: ['JPG', 'JPEG'], size_max_kb: 200, required: true },
      { doc_id: 'right_thumb_and_finger_impressions', label: 'Right Thumb and Finger Impressions', allowed_formats: ['JPG', 'JPEG'], size_max_kb: 200, required: true },
      { doc_id: 'class_10_certificate', label: 'Class 10 Certificate / Marksheet', allowed_formats: ['PDF'], size_max_kb: 300, required: true, document_category: 'academic', document_subtype: 'Class 10 Marksheet', seeds_document_subtypes: ['Class 10 Marksheet'] },
      { doc_id: 'class_12_certificate', label: 'Class 12 Certificate / Marksheet', allowed_formats: ['PDF'], size_max_kb: 300, required: true, document_category: 'academic', document_subtype: 'Class 12 Marksheet', seeds_document_subtypes: ['Class 12 Marksheet'] },
      { doc_id: 'id_proof', label: 'Valid Government-issued Photo ID', allowed_formats: ['PDF'], size_max_kb: 300, required: true, document_category: 'identity' },
      { doc_id: 'category_certificate', label: 'Category Certificate', allowed_formats: ['PDF'], size_max_kb: 300, required: false, required_if: 'category != General', document_category: 'certificate', document_subtype: 'Category Certificate', seeds_document_subtypes: ['Category Certificate'] },
      { doc_id: 'pwd_medical_certificate', label: 'PwD / PwBD Medical Certificate', allowed_formats: ['PDF'], size_max_kb: 300, required: false, required_if: 'pwd_pwbd_status == true', document_category: 'certificate', document_subtype: 'PwD Medical Certificate', seeds_document_subtypes: ['PwD Medical Certificate'] },
      { doc_id: 'scribe_documents', label: 'Scribe Documents', allowed_formats: ['PDF'], size_max_kb: 500, required: false, required_if: 'scribe_opted == true', document_category: 'other', document_subtype: 'Scribe Document', seeds_document_subtypes: ['Scribe Document'] },
    ],
  },
];

export const formSchemasApi = {
  async list(): Promise<FormSchema[]> {
    try {
      const response = await apiRequest<{ schemas: FormSchema[] }>('/form-schemas');
      if (!response?.schemas?.length) {
        console.log('[formSchemasApi] API returned empty, using mock schemas');
        return MOCK_FORM_SCHEMAS;
      }
      return response.schemas;
    } catch (error) {
      console.log('[formSchemasApi] API error, using mock schemas:', error);
      return MOCK_FORM_SCHEMAS;
    }
  },
};

// =============================================================================
// Portals API  (canonical parent — aggregates all schema types per portal)
// =============================================================================

export interface Portal {
  id: string;                  // stable slug, e.g. "nta_neet"
  display_name: string;        // e.g. "NTA NEET"
  short_name: string;          // e.g. "NEET"
  category: string;            // e.g. "medical_entrance"
  country?: string;
  official_website?: string;
  has_form_schema: boolean;
  has_image_specs: boolean;
  form_schemas: FormSchema[];  // sorted newest-first by applicable_year
}

const MOCK_PORTALS: Portal[] = [
  {
    id: 'nta_neet',
    display_name: 'NTA NEET',
    short_name: 'NEET',
    category: 'medical_entrance',
    has_form_schema: true,
    has_image_specs: true,
    form_schemas: MOCK_FORM_SCHEMAS,
  },
];

export const portalsApi = {
  async list(): Promise<Portal[]> {
    try {
      const response = await apiRequest<{ portals: Portal[] }>('/portals');
      if (!response?.portals?.length) {
        console.log('[portalsApi] API returned empty, using mock portals');
        return MOCK_PORTALS;
      }
      return response.portals;
    } catch (error) {
      console.log('[portalsApi] API error, using mock portals:', error);
      return MOCK_PORTALS;
    }
  },
};

/**
 * Mock portal schemas for development/testing
 * These match the portal_schemas.json structure
 */
const MOCK_PORTAL_SCHEMAS: PortalSchema[] = [
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

/**
 * Maps a portal_schemas row name (e.g. "neet_photo") to a display portal name
 * and document type. Keeps the mapping in one place so the UI stays consistent.
 */
function inferPortalFromName(name: string): { portal: string; document_type: 'photo' | 'signature' } {
  const lower = name.toLowerCase();
  const document_type: 'photo' | 'signature' = lower.includes('signature') ? 'signature' : 'photo';
  let portal = name;
  if (lower.startsWith('neet'))     portal = 'NTA NEET';
  else if (lower.startsWith('jee')) portal = 'NTA JEE';
  else if (lower.startsWith('upsc')) portal = 'UPSC';
  else if (lower.startsWith('ssc'))  portal = 'SSC';
  else if (lower.startsWith('ibps')) portal = 'IBPS';
  else if (lower.startsWith('rrb'))  portal = 'RRB';
  else if (lower.startsWith('passport')) portal = 'Passport Seva';
  return { portal, document_type };
}

/**
 * Converts the flat requirements_summary from the DB
 * ({target_width, target_height, target_dpi, max_kb, output_format})
 * into the nested requirements object the app UI expects.
 */
function buildRequirements(
  reqSummary: Record<string, any> | null | undefined,
  document_type: 'photo' | 'signature',
): PortalSchema['requirements'] {
  if (!reqSummary) return undefined;
  const spec = {
    dimensions: [reqSummary.target_width, reqSummary.target_height] as [number, number],
    dpi: reqSummary.target_dpi,
    max_kb: reqSummary.max_kb,
    format: reqSummary.output_format || 'jpeg',
  };
  return document_type === 'signature' ? { signature: spec } : { photo: spec };
}

export const schemasApi = {
  /**
   * List available portal schemas from the API.
   * Falls back to mock data if the API is unavailable or returns nothing.
   */
  async list(): Promise<PortalSchema[]> {
    try {
      const response = await apiRequest<{ schemas: any[] }>('/portal-schemas');
      if (!response?.schemas?.length) {
        console.log('[schemasApi] API returned empty, using mock schemas');
        return MOCK_PORTAL_SCHEMAS;
      }
      return response.schemas.map(s => {
        const { portal, document_type } = inferPortalFromName(s.name);
        return {
          id: s.id,
          name: s.name,
          portal,
          document_type,
          version: s.version,
          requirements: buildRequirements(s.requirements_summary, document_type),
          requirements_summary: s.requirements_summary,
        };
      });
    } catch (error) {
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
  formSchemas: formSchemasApi,
  portals: portalsApi,
  isDevSandboxMode,
};
