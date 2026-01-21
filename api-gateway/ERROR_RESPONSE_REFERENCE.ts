/**
 * SANITIZED ERROR RESPONSE REFERENCE
 * Quick lookup for all error scenarios
 * 
 * ============================================================================
 * VALIDATION ERRORS (HTTP 400)
 * ============================================================================
 */

// All validation errors return same response:
const VALIDATION_ERROR_RESPONSE = {
  statusCode: 400,
  body: { errorCode: 'INVALID_REQUEST' },
};

/**
 * Scenarios:
 * - Invalid Content-Type
 * - Invalid Content-Length
 * - Missing Content-Length
 * - Content exceeds size limit
 * - Missing required header
 * - Invalid header value
 * - Malformed JSON
 * - Empty request body
 * - Invalid query parameter
 * - Missing required field
 * 
 * SERVER LOG:
 *   [VALIDATION_ERROR] Invalid Content-Type: expected 'application/octet-stream', got 'text/plain'
 *   [VALIDATION_ERROR] Missing Content-Length header
 *   [VALIDATION_ERROR] Content-Length 999999999 exceeds maximum size of 104857600
 *   [VALIDATION_ERROR] Missing required header: x-client-request-id
 *   [VALIDATION_ERROR] Invalid x-client-request-id: must be non-empty string
 *   [FRAMEWORK_ERROR] entity.parse.failed
 *   [FRAMEWORK_ERROR] Unexpected token } in JSON at position 42
 */

/**
 * ============================================================================
 * AUTHENTICATION ERRORS (HTTP 401)
 * ============================================================================
 */

// All auth errors return same response:
const AUTH_ERROR_RESPONSE = {
  statusCode: 401,
  body: { errorCode: 'UNAUTHORIZED' },
};

/**
 * Scenarios:
 * - Missing Authorization header
 * - Malformed Authorization header (not "Bearer ...")
 * - Empty token
 * - Token signature invalid
 * - Token expired
 * - Token claims missing
 * - Token claims invalid
 * 
 * SERVER LOG:
 *   [AUTH_ERROR] Missing or malformed authorization header
 *   [AUTH_ERROR] Empty authorization token
 *   [AUTH_ERROR] Invalid token signature
 *   [AUTH_ERROR] Token has expired
 *   [AUTH_ERROR] Invalid token: missing subject claim
 */

/**
 * ============================================================================
 * BUSINESS LOGIC ERRORS (HTTP 4xx)
 * ============================================================================
 */

// Job not found, not authorized, or not ready:
const JOB_NOT_FOUND_RESPONSE = {
  statusCode: 404,
  body: { errorCode: 'JOB_NOT_AVAILABLE' },
};

/**
 * Server error (unexpected):
 */
const SERVER_ERROR_RESPONSE = {
  statusCode: 500,
  body: { errorCode: 'INTERNAL_ERROR' },
};

/**
 * SERVER LOG:
 *   [GLOBAL_ERROR_HANDLER] {
 *     message: "Cannot read property 'jobId' of undefined",
 *     stack: "TypeError: Cannot read property...\n    at upload.ts:42:15\n...",
 *     type: "TypeError"
 *   }
 */

/**
 * ============================================================================
 * REQUEST/RESPONSE EXAMPLES
 * ============================================================================
 */

// ──────────────────────────────────────────────────────────────────────────
// EXAMPLE 1: Invalid Content-Type
// ──────────────────────────────────────────────────────────────────────────

const example1_request = {
  method: 'POST',
  path: '/upload',
  headers: {
    'Content-Type': 'text/plain', // ❌ Wrong
    'x-client-request-id': 'abc-123',
    'Authorization': 'Bearer token...',
  },
  body: '...encrypted payload...',
};

const example1_response = {
  statusCode: 400,
  headers: { 'Content-Type': 'application/json' },
  body: {
    errorCode: 'INVALID_REQUEST',
  },
};

const example1_server_log = `[VALIDATION_ERROR] Invalid Content-Type: expected 'application/octet-stream', got 'text/plain'`;

// ──────────────────────────────────────────────────────────────────────────
// EXAMPLE 2: Content-Length Exceeds Limit
// ──────────────────────────────────────────────────────────────────────────

const example2_request = {
  method: 'POST',
  path: '/upload',
  headers: {
    'Content-Type': 'application/octet-stream',
    'Content-Length': '999999999', // ❌ Too large (100MB limit)
    'x-client-request-id': 'abc-123',
    'Authorization': 'Bearer token...',
  },
};

const example2_response = {
  statusCode: 400,
  headers: { 'Content-Type': 'application/json' },
  body: {
    errorCode: 'INVALID_REQUEST',
  },
};

const example2_server_log = `[VALIDATION_ERROR] Content-Length 999999999 exceeds maximum size of 104857600`;

// ──────────────────────────────────────────────────────────────────────────
// EXAMPLE 3: Missing Required Header
// ──────────────────────────────────────────────────────────────────────────

const example3_request = {
  method: 'POST',
  path: '/upload',
  headers: {
    'Content-Type': 'application/octet-stream',
    'Content-Length': '1024',
    // ❌ Missing: 'x-client-request-id'
    'Authorization': 'Bearer token...',
  },
};

const example3_response = {
  statusCode: 400,
  headers: { 'Content-Type': 'application/json' },
  body: {
    errorCode: 'INVALID_REQUEST',
  },
};

const example3_server_log = `[VALIDATION_ERROR] Missing required header: x-client-request-id`;

// ──────────────────────────────────────────────────────────────────────────
// EXAMPLE 4: Invalid Authorization Token (Expired)
// ──────────────────────────────────────────────────────────────────────────

const example4_request = {
  method: 'GET',
  path: '/jobs/job-123',
  headers: {
    'Authorization': 'Bearer eyJhbGc...', // ❌ Expired
  },
};

const example4_response = {
  statusCode: 401,
  headers: { 'Content-Type': 'application/json' },
  body: {
    errorCode: 'UNAUTHORIZED',
  },
};

const example4_server_log = `[AUTH_ERROR] Token has expired`;

// ──────────────────────────────────────────────────────────────────────────
// EXAMPLE 5: Invalid Authorization Token (Bad Signature)
// ──────────────────────────────────────────────────────────────────────────

const example5_request = {
  method: 'GET',
  path: '/jobs/job-123',
  headers: {
    'Authorization': 'Bearer badbadbad...', // ❌ Invalid signature
  },
};

const example5_response = {
  statusCode: 401,
  headers: { 'Content-Type': 'application/json' },
  body: {
    errorCode: 'UNAUTHORIZED',
  },
};

const example5_server_log = `[AUTH_ERROR] Invalid token signature`;

// ──────────────────────────────────────────────────────────────────────────
// EXAMPLE 6: Missing Authorization Header
// ──────────────────────────────────────────────────────────────────────────

const example6_request = {
  method: 'GET',
  path: '/jobs/job-123',
  headers: {
    // ❌ Missing: 'Authorization'
  },
};

const example6_response = {
  statusCode: 401,
  headers: { 'Content-Type': 'application/json' },
  body: {
    errorCode: 'UNAUTHORIZED',
  },
};

const example6_server_log = `[AUTH_ERROR] Missing or malformed authorization header`;

// ──────────────────────────────────────────────────────────────────────────
// EXAMPLE 7: Unhandled Exception (Database Error)
// ──────────────────────────────────────────────────────────────────────────

const example7_request = {
  method: 'GET',
  path: '/jobs/job-123',
  headers: {
    'Authorization': 'Bearer valid-token...',
  },
};

// Internal error in route handler:
// const job = await db.getJob(jobId);  // ← Throws database connection error

const example7_response = {
  statusCode: 500,
  headers: { 'Content-Type': 'application/json' },
  body: {
    errorCode: 'INTERNAL_ERROR',
  },
};

const example7_server_log = `[GLOBAL_ERROR_HANDLER] {
  message: "ECONNREFUSED: Connection refused at 127.0.0.1:5432",
  stack: "Error: ECONNREFUSED...\n    at Connection.connect (pg.js:100:15)\n    at jobStore.ts:42:10\n    at routes/jobs.ts:15:5",
  type: "Error"
}`;

// ──────────────────────────────────────────────────────────────────────────
// EXAMPLE 8: Successful Request
// ──────────────────────────────────────────────────────────────────────────

const example8_request = {
  method: 'POST',
  path: '/upload',
  headers: {
    'Content-Type': 'application/octet-stream',
    'Content-Length': '1024',
    'x-client-request-id': 'abc-123-def',
    'Authorization': 'Bearer valid-token...',
  },
  body: '...encrypted payload...',
};

const example8_response = {
  statusCode: 201,
  headers: { 'Content-Type': 'application/json' },
  body: {
    blobId: 'blob-uuid-abc123',
    jobId: 'job-uuid-xyz789',
    clientRequestId: 'abc-123-def',
    uploadedBytes: 1024,
  },
};

const example8_server_log = `[INFO] Upload successful: blobId=blob-uuid-abc123, jobId=job-uuid-xyz789`;

/**
 * ============================================================================
 * ERROR CODE REFERENCE (ALL POSSIBLE CODES)
 * ============================================================================
 */

const ERROR_CODES = {
  // Validation errors (400)
  INVALID_REQUEST: {
    statusCode: 400,
    usage: 'Request validation failed (any validation error)',
    examples: [
      'Invalid Content-Type',
      'Missing required header',
      'Invalid header value',
      'Content exceeds size limit',
      'Malformed JSON',
    ],
  },

  // Authentication errors (401)
  UNAUTHORIZED: {
    statusCode: 401,
    usage: 'Authentication failed (missing or invalid token)',
    examples: [
      'Missing Authorization header',
      'Invalid token signature',
      'Token expired',
      'Missing token claims',
    ],
  },

  // Business logic errors (404)
  JOB_NOT_AVAILABLE: {
    statusCode: 404,
    usage: 'Job not found, not authorized, or not ready',
    examples: [
      'Job ID does not exist',
      'Job belongs to different user',
      'Job not in SUCCEEDED state',
    ],
  },

  // Server errors (500)
  INTERNAL_ERROR: {
    statusCode: 500,
    usage: 'Unexpected server error',
    examples: [
      'Database connection error',
      'Null pointer exception',
      'Timeout',
      'Out of memory',
    ],
  },

  // Server config errors (500)
  SERVER_ERROR: {
    statusCode: 500,
    usage: 'Server configuration missing',
    examples: [
      'JWT_SECRET environment variable not set',
      'Database URL not configured',
    ],
  },

  // Not found (404) - optional
  NOT_FOUND: {
    statusCode: 404,
    usage: 'Endpoint does not exist',
    examples: ['POST /unknown/path'],
  },
};

/**
 * ============================================================================
 * TESTING MATRIX
 * ============================================================================
 */

const testingMatrix = `
┌─────────────────────────────┬──────────────┬──────────────────────────┐
│ Test Case                   │ Status Code  │ Error Code               │
├─────────────────────────────┼──────────────┼──────────────────────────┤
│ Invalid Content-Type        │ 400          │ INVALID_REQUEST          │
│ Content-Length zero         │ 400          │ INVALID_REQUEST          │
│ Content-Length too large    │ 400          │ INVALID_REQUEST          │
│ Missing x-client-request-id │ 400          │ INVALID_REQUEST          │
│ Invalid x-client-request-id │ 400          │ INVALID_REQUEST          │
│ Malformed JSON              │ 400          │ INVALID_REQUEST          │
│ Missing Authorization       │ 401          │ UNAUTHORIZED             │
│ Invalid token               │ 401          │ UNAUTHORIZED             │
│ Expired token               │ 401          │ UNAUTHORIZED             │
│ Job not found               │ 404          │ JOB_NOT_AVAILABLE        │
│ Database error              │ 500          │ INTERNAL_ERROR           │
│ Configuration missing       │ 500          │ SERVER_ERROR             │
│ Valid request               │ 200/201      │ (success - no error code)│
└─────────────────────────────┴──────────────┴──────────────────────────┘
`;

console.log(testingMatrix);

/**
 * ============================================================================
 * CURL EXAMPLES FOR TESTING
 * ============================================================================
 */

const curlExamples = `
# Invalid Content-Type
curl -X POST http://localhost:3000/upload \\
  -H "Content-Type: text/plain" \\
  -H "x-client-request-id: test-123" \\
  -H "Authorization: Bearer token..." \\
  --data-binary @file.bin

# Missing required header
curl -X POST http://localhost:3000/upload \\
  -H "Content-Type: application/octet-stream" \\
  -H "Authorization: Bearer token..." \\
  --data-binary @file.bin

# Invalid authorization token
curl -X GET http://localhost:3000/jobs/job-123 \\
  -H "Authorization: Bearer invalid"

# Missing authorization
curl -X GET http://localhost:3000/jobs/job-123

# Valid request
curl -X POST http://localhost:3000/upload \\
  -H "Content-Type: application/octet-stream" \\
  -H "x-client-request-id: test-123" \\
  -H "Authorization: Bearer $(cat token.txt)" \\
  --data-binary @file.bin
`;
