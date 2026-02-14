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

// API Configuration
const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

// Dev sandbox mode - set via environment variable
const DEV_SANDBOX_MODE = process.env.EXPO_PUBLIC_DEV_SANDBOX === 'true';

// Token storage keys
const AUTH_TOKEN_KEY = 'rythmiq_auth_token';
const REFRESH_TOKEN_KEY = 'rythmiq_refresh_token';

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
    return await SecureStore.getItemAsync(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

/**
 * Store auth token securely
 */
export async function setAuthToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(AUTH_TOKEN_KEY, token);
}

/**
 * Clear auth tokens (logout)
 */
export async function clearAuthTokens(): Promise<void> {
  await SecureStore.deleteItemAsync(AUTH_TOKEN_KEY);
  await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
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
  
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });
  
  const data = await response.json();
  
  if (!response.ok) {
    throw new ApiError(
      response.status,
      data.code || 'UNKNOWN_ERROR',
      data.message || 'An error occurred',
      data.details
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
    created_at: string;
  };
  access_token: string;
  refresh_token: string;
}

export interface SessionResponse {
  user: {
    id: string;
    email: string;
  } | null;
  valid: boolean;
}

export const authApi = {
  /**
   * Sign up with email and password
   */
  async signup(email: string, password: string): Promise<AuthResponse> {
    const response = await apiRequest<AuthResponse>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    
    // Store tokens
    await setAuthToken(response.access_token);
    if (response.refresh_token) {
      await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, response.refresh_token);
    }
    
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
    
    // Store tokens
    await setAuthToken(response.access_token);
    if (response.refresh_token) {
      await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, response.refresh_token);
    }
    
    return response;
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
  quality_score?: number;
  created_at?: string;
  updated_at?: string;
  output_file_path?: string;
  error?: {
    code: string;
    message: string;
  };
}

// Default schema used for master documents (Scan flow)
// In production, this should be a generic "master" schema that does quality enhancement
// without specific portal constraints.
const MASTER_DOCUMENT_SCHEMA = 'passport_photo';

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
    // Use the generic master schema - this will be enhanced without strict constraints
    // The backend doesn't support job_type: 'master' yet, so we use legacy API
    return apiRequest<{ job_id: string; upload_url: string; expires_at: string }>('/jobs', {
      method: 'POST',
      body: JSON.stringify({
        portal_schema_name: MASTER_DOCUMENT_SCHEMA,
        filename,
        mime_type: mimeType,
        file_size_bytes: fileSizeBytes,
      }),
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
    return apiRequest<JobStatus>(`/jobs/${jobId}/status`);
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
