# Quick Reference: Client Upload Module

## One-Minute Overview

The client upload module handles encrypted payload serialization and transmission to the API Gateway.

```typescript
// 1. Encrypt plaintext
const umk = generateUMK();
const plaintext = new TextEncoder().encode("secret");
const encrypted = await encryptDocument(plaintext, umk);

// 2. Upload to gateway
const clientRequestId = generateClientRequestId();
const result = await uploadEncryptedPayload(encrypted, clientRequestId);

// 3. Handle result
if (result.success) {
  console.log("Uploaded! blobId:", result.response.blobId);
} else {
  console.error("Failed:", result.error.message);
}
```

---

## API Cheat Sheet

### Upload Function
```typescript
uploadEncryptedPayload(
  payload: EncryptedPayload,
  clientRequestId: string,
  options?: {
    baseUrl?: string;           // default: http://localhost:3001
    maxRetries?: number;        // default: 3
    retryDelayMs?: number;      // default: 1000
  }
): Promise<UploadResult>
```

**Returns:** `{ success: true, response } | { success: false, error }`

### Helper Functions
```typescript
generateClientRequestId(): string          // UUID v4
serializeEncryptedPayload(payload): Uint8Array
isUploadSuccess(result): boolean
isUploadError(result): boolean
isRetryableError(error): boolean
formatGatewayError(error): string
```

---

## HTTP Request Format

```http
POST /upload
Content-Type: application/octet-stream
x-client-request-id: 550e8400-e29b-41d4-a716-446655440000
Content-Length: 1024

<binary_payload>
```

---

## Error Handling

### Don't Retry (Client Errors)
```typescript
if (result.error.status === 400) {
  console.error("Bad request - validation failed");
  // Don't retry
}

if (result.error.status === 413) {
  console.error("Payload too large");
  // Don't retry
}
```

### Do Retry (Server Errors)
```typescript
if (result.error.status >= 500) {
  console.error("Server error - retrying is safe");
  // Safe to retry with same clientRequestId
  result = await uploadEncryptedPayload(encrypted, clientRequestId);
}

if (result.error.status === 0) {
  console.error("Network error - retrying is safe");
  // Safe to retry with same clientRequestId
}
```

---

## Configuration

### Environment Variables
```bash
export REACT_APP_GATEWAY_URL="https://gateway.example.com"
```

### In Code
```typescript
const result = await uploadEncryptedPayload(encrypted, clientRequestId, {
  baseUrl: "https://gateway.example.com",
  maxRetries: 5,
  retryDelayMs: 500,
});
```

### Constants
```typescript
GATEWAY_CONFIG.maxUploadSizeBytes    // 100 MB
GATEWAY_CONFIG.uploadEndpoint        // "/upload"
```

---

## Serialization Format

Binary format (length-prefixed):

```
[uint8]           version
[uint8]           wrappedDEK.version
[uint32 BE]       algorithm length
[bytes]           algorithm (UTF-8)
[uint32 BE]       wrappedKey length
[bytes]           wrappedKey
[12 bytes]        nonce (fixed)
[uint32 BE]       ciphertext length
[bytes]           ciphertext
[16 bytes]        tag (fixed)
```

---

## Type Definitions

### Success
```typescript
interface UploadSuccessResponse {
  blobId: string;           // Server-assigned UUID
  clientRequestId: string;  // Echo of your request ID
  uploadedBytes: number;    // Bytes stored
}
```

### Error
```typescript
interface GatewayErrorResponse {
  status: number;           // HTTP status (0 = network error)
  error?: string;           // Error type
  message?: string;         // Human-readable message
  details?: Record<...>;    // Additional details
}
```

---

## Security Notes

⚠️ **Server CANNOT verify encryption**

- Server treats payloads as opaque bytes
- Encryption verified at processing engine only
- Hostile clients can upload plaintext undetected
- Always use client-side encryption before upload

✅ **Safe to retry with same clientRequestId**

- Gateway deduplicates by clientRequestId
- No double-processing risk
- Idempotent retry mechanism

✅ **Best-effort plaintext cleanup**

```typescript
try {
  const encrypted = await encryptDocument(plaintext, umk);
  // ... upload ...
} finally {
  zeroArray(plaintext);  // Best-effort (not guaranteed)
  zeroArray(umk);        // Best-effort (not guaranteed)
}
```

---

## Testing

### Unit Tests
```bash
ts-node app/client/crypto/__tests__/upload.test.ts
```

### Integration Tests
```bash
ts-node app/client/crypto/__tests__/integration.test.ts
```

### Coverage
- 9 unit tests
- 4 integration test scenarios
- Edge cases and error paths
- Large payload handling (1MB+)

---

## Common Patterns

### Pattern 1: Basic Upload
```typescript
const clientRequestId = generateClientRequestId();
const result = await uploadEncryptedPayload(encrypted, clientRequestId);
if (!result.success) console.error(result.error.message);
```

### Pattern 2: With Error Handling
```typescript
const result = await uploadEncryptedPayload(encrypted, clientRequestId);
if (result.success) {
  console.log("Success:", result.response.blobId);
} else if (isRetryableError(result.error)) {
  // Retry with exponential backoff
} else {
  // Don't retry
  console.error("Non-retryable error:", result.error);
}
```

### Pattern 3: Idempotent Uploads
```typescript
const clientRequestId = generateClientRequestId();
// First attempt
let result = await uploadEncryptedPayload(encrypted, clientRequestId);
// If network fails, retry with same clientRequestId
if (!result.success && isRetryableError(result.error)) {
  result = await uploadEncryptedPayload(encrypted, clientRequestId);
}
```

### Pattern 4: Custom Configuration
```typescript
const result = await uploadEncryptedPayload(
  encrypted,
  clientRequestId,
  {
    baseUrl: "https://production-gateway.com",
    maxRetries: 10,
    retryDelayMs: 2000,
  }
);
```

---

## Files Created

| File | Purpose | Lines |
|------|---------|-------|
| `upload.ts` | Core module | 467 |
| `uploadTypes.ts` | Type definitions | 200+ |
| `uploadExample.ts` | Usage examples | 98 |
| `upload.test.ts` | Unit tests | 234 |
| `integration.test.ts` | Integration tests | 260 |
| `UPLOAD_README.md` | Documentation | 500+ |
| `IMPLEMENTATION_SUMMARY.ts` | Summary | 300+ |
| `DELIVERABLES.ts` | Deliverables list | 400+ |
| `IMPLEMENTATION_CHECKLIST.md` | Checklist | 300+ |

---

## Troubleshooting

### Serialization Error
```
Error: Serialization error in ciphertext: ciphertext must not be empty
```
→ EncryptedPayload structure is invalid. Check payload fields.

### 413 Payload Too Large
```
Error: Payload size 105000000 bytes exceeds maximum 104857600 bytes
```
→ Payload exceeds 100 MB. Need to compress or split.

### Network Error
```
Error: Network error: Connection refused
```
→ Gateway unreachable. Check baseUrl and network connectivity. Safe to retry.

### 400 Bad Request
```
Error: Invalid Content-Type
```
→ Wrong header format. Check serialization and headers. Don't retry.

---

## See Also

- [UPLOAD_README.md](UPLOAD_README.md) - Complete documentation
- [uploadExample.ts](uploadExample.ts) - Code examples
- [upload.test.ts](crypto/__tests__/upload.test.ts) - Test cases
- [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md) - Verification

---

## Status

✅ **Production Ready**

All requirements fulfilled:
- ✅ Serialization to raw bytes
- ✅ POST /upload with headers
- ✅ Error handling
- ✅ Retry logic with clientRequestId
- ✅ No crypto changes
- ✅ 100% TypeScript
- ✅ Comprehensive tests
- ✅ Complete documentation
