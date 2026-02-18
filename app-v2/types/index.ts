/**
 * TypeScript type definitions for Rythmiq Phase 1
 */

// =============================================================================
// User & Auth Types
// =============================================================================

export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

// =============================================================================
// Document Types
// =============================================================================

export type DocumentType = 
  | 'voter_id'
  | 'aadhaar'
  | 'pan'
  | 'photo'
  | 'signature'
  | 'marksheet'
  | 'other';

export type DocumentStatus = 
  | 'uploading'
  | 'uploaded'
  | 'processing'
  | 'ready'
  | 'failed';

export interface Document {
  id: string;
  user_id: string;
  type: DocumentType;
  filename: string;
  status: DocumentStatus;
  quality_score?: number;
  quality_breakdown?: QualityBreakdown;
  thumbnail_url?: string;
  created_at: string;
  updated_at: string;
}

export interface QualityBreakdown {
  sharpness: number;
  exposure: number;
  noise: number;
  edge_density: number;
}

// =============================================================================
// Job Types
// =============================================================================

export type JobStatus = 
  | 'pending'
  | 'processing'
  | 'completed'
  | 'failed';

export interface Job {
  id: string;
  document_id: string;
  status: JobStatus;
  progress?: number;
  quality_score?: number;
  error?: JobError;
  created_at: string;
  completed_at?: string;
}

export interface JobError {
  code: string;
  message: string;
  retryable: boolean;
}

// =============================================================================
// Schema Types
// =============================================================================

export interface SchemaRequirement {
  dimensions: [number, number]; // [width, height]
  dpi: number;
  max_kb: number;
  format: 'jpg' | 'png';
}

export interface PortalSchema {
  id: string;
  name: string;
  version: number;
  requirements: {
    photo?: SchemaRequirement;
    signature?: SchemaRequirement;
    [key: string]: SchemaRequirement | undefined;
  };
  active: boolean;
  created_at: string;
  updated_at: string;
}

// =============================================================================
// Adaptation Types
// =============================================================================

export interface AdaptationJob {
  id: string;
  document_id: string;
  portal_id: string;
  status: JobStatus;
  zip_url?: string;
  expires_at?: string;
  created_at: string;
}

// =============================================================================
// Transparency Log Types
// =============================================================================

export type AuditEventType =
  | 'uploaded'
  | 'encrypted'
  | 'processing_started'
  | 'processing_completed'
  | 'adapted'
  | 'downloaded'
  | 'deleted';

export interface AuditEvent {
  id: string;
  document_id: string;
  event_type: AuditEventType;
  details?: Record<string, unknown>;
  timestamp: string;
}

// =============================================================================
// API Response Types
// =============================================================================

export interface ApiResponse<T> {
  data: T;
  success: boolean;
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  has_more: boolean;
}
