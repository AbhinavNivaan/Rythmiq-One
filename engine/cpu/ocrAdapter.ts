/**
 * CPU-only OCR Adapter
 * 
 * Processes raw document bytes and returns extracted text with page metadata.
 * Uses Tesseract.js for real OCR processing.
 */

import Tesseract from 'tesseract.js';

// ============================================================================
// Types
// ============================================================================

export enum OCRErrorCode {
  UNSUPPORTED_FORMAT = 'UNSUPPORTED_FORMAT',
  CORRUPT_DATA = 'CORRUPT_DATA',
  OCR_FAILURE = 'OCR_FAILURE',
  TIMEOUT = 'TIMEOUT',
  SIZE_EXCEEDED = 'SIZE_EXCEEDED',
}

export interface OCRError {
  code: OCRErrorCode;
  message: string;
}

export interface PageMetadata {
  number: number;
  text: string;
  confidence?: number;
  dimensions?: {
    width: number;
    height: number;
  };
  metadata?: Record<string, unknown>;
}

export interface OCRSuccessResult {
  status: 'success';
  pages: PageMetadata[];
  totalPages: number;
  processingTime: number; // milliseconds
}

export interface OCRErrorResult {
  status: 'error';
  error: OCRError;
  pages: [];
}

export type OCRResult = OCRSuccessResult | OCRErrorResult;

// ============================================================================
// Configuration
// ============================================================================

interface OCRConfig {
  maxFileSizeBytes: number;
  pageTimeoutMs: number;
  supportedMimeTypes: Set<string>;
  language: string;
}

const DEFAULT_CONFIG: OCRConfig = {
  maxFileSizeBytes: 50 * 1024 * 1024, // 50 MB
  pageTimeoutMs: 60000, // 60 seconds per page (Tesseract needs more time)
  supportedMimeTypes: new Set([
    'image/png',
    'image/jpeg',
    'image/tiff',
    'image/tif',
    // PDF not supported directly by Tesseract.js - will return clear error
  ]),
  language: 'eng', // English by default
};

// ============================================================================
// Error Utilities
// ============================================================================

function createErrorResult(code: OCRErrorCode, message: string): OCRErrorResult {
  return {
    status: 'error',
    error: { code, message },
    pages: [],
  };
}

// ============================================================================
// Format Detection
// ============================================================================

/**
 * Detect document format from file signature (magic bytes).
 * Returns MIME type or null if unrecognized.
 */
function detectFormat(data: Buffer): string | null {
  if (data.length < 4) {
    return null;
  }

  // PDF: %PDF - not supported by Tesseract.js directly
  if (
    data[0] === 0x25 &&
    data[1] === 0x50 &&
    data[2] === 0x44 &&
    data[3] === 0x46
  ) {
    return 'application/pdf';
  }

  // PNG: 89 50 4E 47
  if (
    data[0] === 0x89 &&
    data[1] === 0x50 &&
    data[2] === 0x4e &&
    data[3] === 0x47
  ) {
    return 'image/png';
  }

  // JPEG: FF D8 FF
  if (data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff) {
    return 'image/jpeg';
  }

  // TIFF: 49 49 2A 00 (little-endian) or 4D 4D 00 2A (big-endian)
  if (
    (data[0] === 0x49 &&
      data[1] === 0x49 &&
      data[2] === 0x2a &&
      data[3] === 0x00) ||
    (data[0] === 0x4d &&
      data[1] === 0x4d &&
      data[2] === 0x00 &&
      data[3] === 0x2a)
  ) {
    return 'image/tiff';
  }

  return null;
}

// ============================================================================
// Validation
// ============================================================================

function validateInput(
  data: Buffer,
  config: OCRConfig
): { valid: true } | { valid: false; error: OCRErrorResult } {
  if (!Buffer.isBuffer(data)) {
    return {
      valid: false,
      error: createErrorResult(
        OCRErrorCode.CORRUPT_DATA,
        'Input must be a valid Buffer'
      ),
    };
  }

  if (data.length === 0) {
    return {
      valid: false,
      error: createErrorResult(
        OCRErrorCode.CORRUPT_DATA,
        'Input buffer is empty'
      ),
    };
  }

  if (data.length > config.maxFileSizeBytes) {
    return {
      valid: false,
      error: createErrorResult(
        OCRErrorCode.SIZE_EXCEEDED,
        `File size ${data.length} exceeds limit ${config.maxFileSizeBytes}`
      ),
    };
  }

  const detectedFormat = detectFormat(data);
  if (!detectedFormat) {
    return {
      valid: false,
      error: createErrorResult(
        OCRErrorCode.UNSUPPORTED_FORMAT,
        'Unrecognized file format (magic bytes not recognized)'
      ),
    };
  }

  // Special handling for PDF - provide clear guidance
  if (detectedFormat === 'application/pdf') {
    return {
      valid: false,
      error: createErrorResult(
        OCRErrorCode.UNSUPPORTED_FORMAT,
        'PDF format is not currently supported. Please upload an image (PNG, JPEG, or TIFF) instead.'
      ),
    };
  }

  if (!config.supportedMimeTypes.has(detectedFormat)) {
    return {
      valid: false,
      error: createErrorResult(
        OCRErrorCode.UNSUPPORTED_FORMAT,
        `Format ${detectedFormat} is not supported. Please use PNG, JPEG, or TIFF.`
      ),
    };
  }

  return { valid: true };
}

// ============================================================================
// Real OCR Processing via Tesseract.js
// ============================================================================

/**
 * Process image data with Tesseract.js OCR engine.
 * 
 * @param data - Raw image bytes
 * @param config - OCR configuration
 * @returns OCR result with extracted text and metadata
 */
async function processOCR(
  data: Buffer,
  config: OCRConfig
): Promise<OCRResult> {
  const startTime = Date.now();

  // Validate input
  const validation = validateInput(data, config);
  if (validation.valid === false) {
    return validation.error;
  }

  try {
    // Create Tesseract worker
    const worker = await Tesseract.createWorker(config.language, 1, {
      // Suppress verbose logging - security consideration
      logger: () => { },
    });

    try {
      // Run OCR recognition on the image buffer
      const result = await worker.recognize(data);

      // Extract text and confidence
      const text = result.data.text || '';
      const confidence = result.data.confidence || 0;

      // Check if we got meaningful text
      if (!text.trim()) {
        await worker.terminate();
        return createErrorResult(
          OCRErrorCode.OCR_FAILURE,
          'No text could be extracted from the document'
        );
      }

      const processingTime = Date.now() - startTime;

      // Construct page metadata (Tesseract treats single image as one page)
      const page: PageMetadata = {
        number: 1,
        text: normalizeWhitespace(text),
        confidence: confidence / 100, // Convert to 0-1 scale
        dimensions: result.data.hocr ? undefined : undefined, // Dimensions not available in basic mode
        metadata: {
          extractionMethod: 'tesseract.js',
          language: config.language,
        },
      };

      await worker.terminate();

      return {
        status: 'success',
        pages: [page],
        totalPages: 1,
        processingTime,
      };
    } catch (err) {
      await worker.terminate();
      throw err;
    }
  } catch (err) {
    const message =
      err instanceof Error ? err.message : 'Unknown OCR processing error';

    // Don't log the actual error message in production - could contain file details
    return createErrorResult(OCRErrorCode.OCR_FAILURE, 'OCR processing failed');
  }
}

/**
 * Normalize whitespace: collapse consecutive spaces and newlines.
 * This is the only text transformation allowed per spec (no auto-correction).
 */
function normalizeWhitespace(text: string): string {
  return text
    .replace(/[ \t]+/g, ' ') // Collapse consecutive spaces/tabs to single space
    .replace(/\n\n+/g, '\n') // Collapse consecutive newlines to single newline
    .trim();
}

// ============================================================================
// Public API
// ============================================================================

/**
 * Main OCR adapter entry point.
 * 
 * @param data - Raw document bytes
 * @param config - Optional OCR configuration (uses defaults if not provided)
 * @returns OCRResult with status, pages, and error details (if applicable)
 */
export async function extractText(
  data: Buffer,
  config: Partial<OCRConfig> = {}
): Promise<OCRResult> {
  const finalConfig: OCRConfig = {
    ...DEFAULT_CONFIG,
    ...config,
  };

  return processOCR(data, finalConfig);
}

/**
 * Get default OCR configuration.
 */
export function getDefaultConfig(): OCRConfig {
  return { ...DEFAULT_CONFIG };
}

/**
 * Type guard: check if result is success.
 */
export function isOCRSuccess(result: OCRResult): result is OCRSuccessResult {
  return result.status === 'success';
}

/**
 * Type guard: check if result is error.
 */
export function isOCRError(result: OCRResult): result is OCRErrorResult {
  return result.status === 'error';
}
