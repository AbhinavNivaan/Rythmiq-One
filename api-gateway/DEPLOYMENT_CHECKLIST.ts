/**
 * ============================================================================
 * DEPLOYMENT CHECKLIST & VERIFICATION
 * ============================================================================
 * 
 * Use this checklist to verify the sanitization is correctly implemented
 * and deployed to your environment.
 * 
 * ============================================================================
 * PHASE 1: CODE REVIEW (Before Deployment)
 * ============================================================================
 */

const PHASE_1_CHECKLIST = [
  {
    item: 'api-gateway/errors/validationErrors.ts created',
    verify: 'File exists with sendValidationError and sendAuthError exports',
  },
  {
    item: 'api-gateway/errors/errorHandler.ts created',
    verify: 'File exists with globalErrorHandler and asyncHandler exports',
  },
  {
    item: 'api-gateway/routes/upload.ts modified',
    verify: 'Uses sendValidationError for all validation errors',
  },
  {
    item: 'api-gateway/auth/middleware.ts modified',
    verify: 'Uses sendAuthError for all auth errors',
  },
  {
    item: 'api-gateway/errors/apiError.ts enhanced',
    verify: 'Has security documentation',
  },
  {
    item: 'No error messages expose limits',
    verify: 'Search: no "100" or "104857600" in error responses',
  },
  {
    item: 'No error messages expose header names',
    verify: 'Search: no "x-client-request-id" in error responses',
  },
  {
    item: 'No error messages expose formats',
    verify: 'Search: no "application/octet-stream" in error responses',
  },
  {
    item: 'Import statements correct',
    verify: 'sendValidationError imported in upload.ts',
  },
  {
    item: 'Import statements correct',
    verify: 'sendAuthError imported in auth/middleware.ts',
  },
];

/**
 * ============================================================================
 * PHASE 2: INTEGRATION (Before Running Tests)
 * ============================================================================
 */

const PHASE_2_CHECKLIST = [
  {
    item: 'Update server.ts',
    task: 'Import sanitizationErrorHandler and globalErrorHandler',
    code: `import { sanitizationErrorHandler, globalErrorHandler } from './errors/errorHandler';`,
  },
  {
    item: 'Register sanitizationErrorHandler',
    task: 'Add BEFORE routes',
    code: `app.use(sanitizationErrorHandler);`,
    order: 'After body parsers, BEFORE routes',
  },
  {
    item: 'Register globalErrorHandler',
    task: 'Add AFTER all routes (MUST be last)',
    code: `app.use(globalErrorHandler);`,
    order: 'LAST in middleware chain',
  },
  {
    item: 'Compile TypeScript',
    task: 'Run: npm run build or tsc',
    verify: 'No compilation errors',
  },
  {
    item: 'Verify no breaking changes',
    task: 'Check that routes still function',
    verify: 'Valid requests still succeed',
  },
];

/**
 * ============================================================================
 * PHASE 3: TESTING (Verification)
 * ============================================================================
 */

const PHASE_3_CHECKLIST = [
  {
    name: 'Invalid Content-Type',
    request: {
      method: 'POST',
      path: '/upload',
      headers: {
        'Content-Type': 'text/plain',
        'x-client-request-id': 'test-123',
        'Authorization': 'Bearer token...',
      },
    },
    expectedStatus: 400,
    expectedBody: { errorCode: 'INVALID_REQUEST' },
    shouldNOTContain: ['application/octet-stream', 'text/plain', 'Content-Type'],
  },
  {
    name: 'Content-Length Exceeds Limit',
    request: {
      method: 'POST',
      path: '/upload',
      headers: {
        'Content-Type': 'application/octet-stream',
        'Content-Length': '104857601',
        'x-client-request-id': 'test-123',
        'Authorization': 'Bearer token...',
      },
    },
    expectedStatus: 400,
    expectedBody: { errorCode: 'INVALID_REQUEST' },
    shouldNOTContain: ['104857600', '100', 'MB', 'bytes', 'maximum'],
  },
  {
    name: 'Missing Required Header',
    request: {
      method: 'POST',
      path: '/upload',
      headers: {
        'Content-Type': 'application/octet-stream',
        'Content-Length': '1024',
        'Authorization': 'Bearer token...',
      },
    },
    expectedStatus: 400,
    expectedBody: { errorCode: 'INVALID_REQUEST' },
    shouldNOTContain: ['x-client-request-id', 'header', 'required'],
  },
  {
    name: 'Invalid Authorization (Expired Token)',
    request: {
      method: 'GET',
      path: '/jobs/job-123',
      headers: {
        'Authorization': 'Bearer expired-token...',
      },
    },
    expectedStatus: 401,
    expectedBody: { errorCode: 'UNAUTHORIZED' },
    shouldNOTContain: ['expired', 'token', 'claims', 'signature'],
  },
  {
    name: 'Invalid Authorization (Bad Token)',
    request: {
      method: 'GET',
      path: '/jobs/job-123',
      headers: {
        'Authorization': 'Bearer invalid-token...',
      },
    },
    expectedStatus: 401,
    expectedBody: { errorCode: 'UNAUTHORIZED' },
    shouldNOTContain: ['invalid', 'signature', 'JWT', 'verify'],
  },
  {
    name: 'Missing Authorization Header',
    request: {
      method: 'GET',
      path: '/jobs/job-123',
      headers: {},
    },
    expectedStatus: 401,
    expectedBody: { errorCode: 'UNAUTHORIZED' },
    shouldNOTContain: ['missing', 'authorization', 'required'],
  },
  {
    name: 'Valid Request (Success)',
    request: {
      method: 'POST',
      path: '/upload',
      headers: {
        'Content-Type': 'application/octet-stream',
        'Content-Length': '1024',
        'x-client-request-id': 'test-123',
        'Authorization': 'Bearer valid-token...',
      },
    },
    expectedStatus: '201 or 200 (if idempotent)',
    expectedBody: {
      containsKey: 'blobId',
    },
    shouldNOTContain: ['error', 'errorCode', 'INVALID_REQUEST'],
  },
];

/**
 * ============================================================================
 * PHASE 4: SERVER LOG VERIFICATION
 * ============================================================================
 */

const PHASE_4_CHECKLIST = [
  {
    testCase: 'Invalid Content-Type',
    expectedLogPattern: `/\\[VALIDATION_ERROR\\].* Invalid Content-Type/`,
    shouldContain: 'application/octet-stream',
  },
  {
    testCase: 'Content-Length Exceeds',
    expectedLogPattern: `/\\[VALIDATION_ERROR\\].* exceeds maximum size/`,
    shouldContain: '104857600',
  },
  {
    testCase: 'Missing Header',
    expectedLogPattern: `/\\[VALIDATION_ERROR\\].* Missing required header/`,
    shouldContain: 'x-client-request-id',
  },
  {
    testCase: 'Invalid Token',
    expectedLogPattern: `/\\[AUTH_ERROR\\]/`,
    shouldContain: 'Token verification failed or similar',
  },
  {
    testCase: 'Unhandled Exception',
    expectedLogPattern: `/\\[GLOBAL_ERROR_HANDLER\\]/`,
    shouldContain: 'stack trace with file paths',
  },
];

/**
 * ============================================================================
 * PHASE 5: SECURITY VERIFICATION
 * ============================================================================
 */

const PHASE_5_CHECKLIST = [
  {
    name: 'No size limits in responses',
    command: 'grep -r "104857600\|100.*MB\|maximum.*size" api-gateway/routes api-gateway/auth',
    expectResult: 'No matches (limits only in server logs)',
  },
  {
    name: 'No header names in error responses',
    command: 'grep -r "x-client-request-id\|x-.*header" api-gateway/routes api-gateway/auth',
    expectResult: 'No matches in error responses (only in internal code)',
  },
  {
    name: 'No format specifications in responses',
    command: 'grep -r "application/octet-stream\|Content-Type.*:" api-gateway/routes/upload.ts',
    expectResult: 'No matches in sendValidationError calls',
  },
  {
    name: 'No stack traces in route responses',
    command: 'grep -r "stack\|stack trace\|at.*:" api-gateway/routes api-gateway/auth',
    expectResult: 'No matches (only in error handler logs)',
  },
  {
    name: 'All validation errors use sendValidationError',
    command: 'grep -r "res.status.*json.*error:" api-gateway/routes',
    expectResult: 'No matches (all use sendValidationError or throwApiError)',
  },
  {
    name: 'All auth errors use sendAuthError',
    command: 'grep -r "res.status.*json.*error:" api-gateway/auth',
    expectResult: 'No matches (all use sendAuthError)',
  },
];

/**
 * ============================================================================
 * PHASE 6: PERFORMANCE VERIFICATION
 * ============================================================================
 */

const PHASE_6_CHECKLIST = [
  {
    metric: 'Response time for valid requests',
    baseline: '< 50ms (without I/O)',
    verify: 'No significant change from before',
  },
  {
    metric: 'Response time for validation errors',
    baseline: '< 5ms',
    verify: 'Fast rejection',
  },
  {
    metric: 'Server log file growth',
    baseline: 'Expected with full error context',
    verify: 'Monitor log disk usage',
  },
  {
    metric: 'Memory usage',
    baseline: 'No significant increase',
    verify: 'Console.warn and console.error calls are lightweight',
  },
];

/**
 * ============================================================================
 * MANUAL TEST SCRIPT
 * ============================================================================
 */

const manualTestScript = `
#!/bin/bash
# Save as: test-sanitization.sh
# Run: chmod +x test-sanitization.sh && ./test-sanitization.sh

set -e

API_URL="http://localhost:3000"
VALID_TOKEN="<your-valid-jwt-token>"
INVALID_TOKEN="invalid.token.here"

echo "Running validation error tests..."
echo ""

# Test 1: Invalid Content-Type
echo "Test 1: Invalid Content-Type"
curl -s -X POST "$API_URL/upload" \\
  -H "Content-Type: text/plain" \\
  -H "x-client-request-id: test-123" \\
  -H "Authorization: Bearer $VALID_TOKEN" \\
  --data "test" | jq .

echo "Expected: { errorCode: 'INVALID_REQUEST' }"
echo ""

# Test 2: Missing x-client-request-id
echo "Test 2: Missing x-client-request-id"
curl -s -X POST "$API_URL/upload" \\
  -H "Content-Type: application/octet-stream" \\
  -H "Authorization: Bearer $VALID_TOKEN" \\
  --data-binary @file.bin | jq .

echo "Expected: { errorCode: 'INVALID_REQUEST' }"
echo ""

# Test 3: Invalid token
echo "Test 3: Invalid Authorization Token"
curl -s -X GET "$API_URL/jobs/job-123" \\
  -H "Authorization: Bearer $INVALID_TOKEN" | jq .

echo "Expected: { errorCode: 'UNAUTHORIZED' }"
echo ""

# Test 4: Missing Authorization
echo "Test 4: Missing Authorization Header"
curl -s -X GET "$API_URL/jobs/job-123" | jq .

echo "Expected: { errorCode: 'UNAUTHORIZED' }"
echo ""

# Test 5: Valid request
echo "Test 5: Valid Upload Request"
curl -s -X POST "$API_URL/upload" \\
  -H "Content-Type: application/octet-stream" \\
  -H "x-client-request-id: test-123" \\
  -H "Authorization: Bearer $VALID_TOKEN" \\
  --data-binary @file.bin | jq .

echo "Expected: { blobId, jobId, clientRequestId, uploadedBytes }"
echo ""

echo "All tests completed!"
`;

/**
 * ============================================================================
 * ROLLBACK PLAN
 * ============================================================================
 */

const rollbackPlan = `
If errors occur after deployment:

1. IMMEDIATE (Within 1 minute)
   - Revert api-gateway/ to previous commit
   - git checkout HEAD~1 -- api-gateway/
   - Rebuild and restart services
   - Monitor logs for errors

2. SHORT TERM (1-10 minutes)
   - Check server logs for [VALIDATION_ERROR], [AUTH_ERROR], [GLOBAL_ERROR_HANDLER]
   - Look for any patterns in failures
   - Check if specific endpoints are affected
   
3. DIAGNOSIS
   - Enable debug logging: DEBUG=* npm start
   - Check for missing imports
   - Verify middleware registration order
   - Test with curl commands from manual test script
   
4. RECOVERY
   - Fix issues in development environment first
   - Re-run tests (PHASE 3)
   - Re-deploy

Emergency contacts:
- Security team: security@example.com
- DevOps: devops@example.com
`;

/**
 * ============================================================================
 * POST-DEPLOYMENT MONITORING
 * ============================================================================
 */

const monitoringSetup = `
Monitor these metrics after deployment:

1. Error Rate by Code
   - INVALID_REQUEST: Should match validation failure rate (typically 5-10%)
   - UNAUTHORIZED: Should match auth failure rate (typically 1-3%)
   - INTERNAL_ERROR: Should be very low (< 0.1%)

2. Server Log Volume
   - [VALIDATION_ERROR]: Expected for invalid requests
   - [AUTH_ERROR]: Expected for invalid tokens
   - [GLOBAL_ERROR_HANDLER]: Should be rare (< 100/hour)

3. Response Times
   - Validation errors: Should be < 5ms
   - Auth errors: Should be < 10ms
   - Valid requests: No significant change

4. Alerts to Set
   - Alert if [GLOBAL_ERROR_HANDLER] errors > 100/hour
   - Alert if INTERNAL_ERROR responses > 10/minute
   - Alert if server logs not appearing (logging misconfiguration)

5. Security Audit
   - Verify no error messages contain size limits
   - Verify no error messages contain header names
   - Verify no error messages contain format specs
   - Check weekly for log entries
`;

/**
 * ============================================================================
 * SIGN-OFF CHECKLIST
 * ============================================================================
 */

const signoff = `
Security Review Sign-Off:

Before considering this deployment complete, confirm:

☐ All PHASE 1 code review items completed
☐ All PHASE 2 integration items completed
☐ All PHASE 3 test cases passing
☐ All PHASE 4 server logs verified
☐ All PHASE 5 security checks passed
☐ PHASE 6 performance acceptable
☐ Manual test script successful
☐ Rollback plan documented and tested
☐ Monitoring alerts configured
☐ Team notified of changes
☐ Documentation updated

Deployment approved by:
- Security Lead: _______________  Date: _______
- DevOps Lead: _______________  Date: _______
- Backend Lead: _______________  Date: _______

Deployment date: _______________
Expected completion: _______________
`;

export { PHASE_1_CHECKLIST, PHASE_2_CHECKLIST, PHASE_3_CHECKLIST, PHASE_4_CHECKLIST, PHASE_5_CHECKLIST, PHASE_6_CHECKLIST, manualTestScript, rollbackPlan, monitoringSetup, signoff };
