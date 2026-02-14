/**
 * Utility functions for Rythmiq app
 */

/**
 * Format file size in human readable format
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

/**
 * Format date to relative time (e.g., "2 hours ago")
 */
export function formatRelativeTime(date: string | Date): string {
  const now = new Date();
  const then = new Date(date);
  const diffMs = now.getTime() - then.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);
  
  if (diffSec < 60) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHour < 24) return `${diffHour}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  
  return then.toLocaleDateString();
}

/**
 * Format quality score as percentage with label
 */
export function formatQualityScore(score: number): { label: string; color: string; percentage: string } {
  const percentage = Math.round(score * 100);
  
  if (score >= 0.8) {
    return { label: 'Excellent', color: '#22c55e', percentage: `${percentage}%` };
  }
  if (score >= 0.5) {
    return { label: 'Good', color: '#eab308', percentage: `${percentage}%` };
  }
  return { label: 'Poor', color: '#ef4444', percentage: `${percentage}%` };
}

/**
 * Get document type display name
 */
export function getDocumentTypeName(type: string): string {
  const names: Record<string, string> = {
    voter_id: 'Voter ID',
    aadhaar: 'Aadhaar Card',
    pan: 'PAN Card',
    photo: 'Photo',
    signature: 'Signature',
    marksheet: 'Marksheet',
    other: 'Other Document',
  };
  return names[type] || type;
}

/**
 * Get status display info
 */
export function getStatusInfo(status: string): { label: string; color: string } {
  const statusMap: Record<string, { label: string; color: string }> = {
    uploading: { label: 'Uploading', color: '#6b7280' },
    uploaded: { label: 'Uploaded', color: '#6b7280' },
    processing: { label: 'Processing', color: '#eab308' },
    ready: { label: 'Ready', color: '#22c55e' },
    failed: { label: 'Failed', color: '#ef4444' },
  };
  return statusMap[status] || { label: status, color: '#6b7280' };
}

/**
 * Validate email format
 */
export function isValidEmail(email: string): boolean {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
}

/**
 * Validate password strength
 */
export function validatePassword(password: string): { valid: boolean; message: string } {
  if (password.length < 8) {
    return { valid: false, message: 'Password must be at least 8 characters' };
  }
  if (!/[A-Z]/.test(password)) {
    return { valid: false, message: 'Password must contain an uppercase letter' };
  }
  if (!/[a-z]/.test(password)) {
    return { valid: false, message: 'Password must contain a lowercase letter' };
  }
  if (!/[0-9]/.test(password)) {
    return { valid: false, message: 'Password must contain a number' };
  }
  return { valid: true, message: '' };
}

/**
 * Generate unique ID (for local use only)
 */
export function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Debounce function
 */
export function debounce<T extends (...args: unknown[]) => unknown>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout | null = null;
  
  return (...args: Parameters<T>) => {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}

/**
 * Sleep for specified milliseconds
 */
export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}
