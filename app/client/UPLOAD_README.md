# Client Upload Module

## Overview

The client upload module handles serialization and transmission of encrypted payloads to the API Gateway. It provides:

- **Serialization**: Convert `EncryptedPayload` objects to raw binary format
- **Upload**: Send encrypted payloads via POST /upload with proper headers
- **Retry logic**: Exponential backoff for transient failures
- **Idempotency**: Client-driven deduplication via `clientRequestId`
- **Error handling**: Graceful handling of all failure modes

## SECURITY NOTICE

**The server CANNOT verify encryption.** A misconfigured or hostile client can upload plaintext without server detection.

The server treats all uploads as opaque bytes only. Encryption verification happens exclusively at the processing engine with the User Master Key (UMK).

### Do NOT claim:
- ❌ "Server verified encryption"
- ❌ "Server-verified data integrity"
- ❌ "Server-encrypted backups"

### Always state:
- ✅ "Client-encrypted with AES-256-GCM"
- ✅ "Server has no access to plaintext or UMK"
- ✅ "Encryption verification at processing stage only"

## Usage

### Basic Upload

```typescript
import { encryptDocument, zeroArray } from "./crypto/encryptDocument";
import { generateUMK } from "./crypto/umk";
import {
  uploadEncryptedPayload,
  generateClientRequestId,
} from "./upload";

// Encrypt plaintext
const umk = generateUMK();
const plaintext = new TextEncoder().encode("secret data");
const encrypted = await encryptDocument(plaintext, umk);

// Clean up plaintext (best-effort)
zeroArray(plaintext);

// Upload with unique request ID
const clientRequestId = generateClientRequestId();
const result = await uploadEncryptedPayload(encrypted, clientRequestId);

if (result.success) {
  console.log("Upload succeeded, blobId:", result.response.blobId);
} else {
  console.error("Upload failed:", result.error.message);
}

// Clean up UMK (best-effort)
zeroArray(umk);
```

### With Custom Configuration

```typescript
const result = await uploadEncryptedPayload(encrypted, clientRequestId, {
  baseUrl: "https://gateway.example.com",
  maxRetries: 5,
  retryDelayMs: 500,
});
```

### Idempotent Uploads

Use the same `clientRequestId` for retries to ensure idempotency:

```typescript
const clientRequestId = generateClientRequestId();

// Initial upload
let result = await uploadEncryptedPayload(encrypted, clientRequestId);

// If network fails, retry with same clientRequestId
if (!result.success) {
  result = await uploadEncryptedPayload(encrypted, clientRequestId);
  // Gateway will deduplicate by clientRequestId
}
```

## Serialization Format

### EncryptedPayload → Bytes

```
[0:1]                  - version (uint8)
[1:2]                  - wrappedDEK.version (uint8)
[2:6]                  - wrappedDEK.algorithm length (uint32 BE)
[6:6+len]              - wrappedDEK.algorithm (UTF-8 string)
[...:...+4]            - wrappedDEK.wrappedKey length (uint32 BE)
[...:...:+len]         - wrappedDEK.wrappedKey (bytes)
[...:...:+12]          - nonce (12 bytes, fixed)
[...:...:+4]           - ciphertext length (uint32 BE)
[...:...:+len]         - ciphertext (bytes)
[...:...:+16]          - tag (16 bytes, fixed)
```

### Example

```typescript
const payload: EncryptedPayload = {
  version: 1,
  wrappedDEK: {
    version: 1,
    algorithm: "AES-KW",
    wrappedKey: Uint8Array([0x01, 0x02, ...]),
  },
  nonce: Uint8Array([0x11, 0x12, ...]),           // 12 bytes
  ciphertext: Uint8Array([0x21, 0x22, ...]),      // variable length
  tag: Uint8Array([0x31, 0x32, ...]),             // 16 bytes
};

const serialized = serializeEncryptedPayload(payload);
// serialized is now raw binary suitable for upload
```

## API Reference

### `uploadEncryptedPayload()`

```typescript
async function uploadEncryptedPayload(
  encryptedPayload: EncryptedPayload,
  clientRequestId: string,
  options?: {
    baseUrl?: string;
    maxRetries?: number;
    retryDelayMs?: number;
  }
): Promise<UploadResult>
```

**Parameters:**

- `encryptedPayload`: Validated `EncryptedPayload` object from `encryptDocument()`
- `clientRequestId`: Unique request identifier (UUID v4 recommended)
- `options.baseUrl`: Gateway base URL (default: `http://localhost:3001`)
- `options.maxRetries`: Maximum retry attempts for transient errors (default: 3)
- `options.retryDelayMs`: Initial retry delay in ms (default: 1000); exponential backoff applied

**Returns:**

```typescript
type UploadResult =
  | { success: true; response: UploadSuccessResponse }
  | { success: false; error: GatewayErrorResponse };

interface UploadSuccessResponse {
  blobId: string;
  clientRequestId: string;
  uploadedBytes: number;
}

interface GatewayErrorResponse {
  error?: string;
  message?: string;
  status: number;
  details?: Record<string, unknown>;
}
```

**Error Handling:**

```typescript
const result = await uploadEncryptedPayload(encrypted, clientRequestId);

if (result.success) {
  // Handle success
  const { blobId, uploadedBytes } = result.response;
} else {
  // Handle error
  const { status, error, message } = result.error;

  if (status === 400) {
    // Client error (bad request, invalid format, etc.)
    // Do not retry
  } else if (status === 413) {
    // Payload too large
    // Do not retry
  } else if (status >= 500) {
    // Server error
    // May retry with same clientRequestId
  } else if (status === 0) {
    // Network error
    // May retry with same clientRequestId
  }
}
```

### `serializeEncryptedPayload()`

```typescript
function serializeEncryptedPayload(
  payload: EncryptedPayload
): Uint8Array
```

Converts `EncryptedPayload` to raw bytes. Called automatically by `uploadEncryptedPayload()`.

**Validation:**

- `payload.version`: 0-255
- `payload.wrappedDEK.version`: 0-255
- `payload.wrappedDEK.algorithm`: non-empty string
- `payload.wrappedDEK.wrappedKey`: Uint8Array (non-empty)
- `payload.nonce`: exactly 12 bytes
- `payload.ciphertext`: non-empty Uint8Array
- `payload.tag`: exactly 16 bytes

**Throws:** `Error` with descriptive message if validation fails

### `generateClientRequestId()`

```typescript
function generateClientRequestId(): string
```

Generates a UUID v4 string suitable for `clientRequestId`. Uses `crypto.randomUUID()` if available, otherwise polyfill.

## Gateway Interaction

### Request Format

```http
POST /upload HTTP/1.1
Content-Type: application/octet-stream
Content-Length: <binary_size>
x-client-request-id: <uuid-v4>

<binary_payload>
```

### Response Format (Success)

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "blobId": "550e8400-e29b-41d4-a716-446655440000",
  "clientRequestId": "client-request-uuid",
  "uploadedBytes": 1024
}
```

### Response Format (Error)

```http
HTTP/1.1 <4xx|5xx> <Status>
Content-Type: application/json

{
  "error": "Error Type",
  "message": "Human-readable error description"
}
```

## Retry Logic

The module implements exponential backoff for transient failures:

1. **Initial delay**: `retryDelayMs` (default: 1000ms)
2. **Subsequent delays**: `delay * 2^attempt`
3. **Max retries**: `maxRetries` (default: 3)

**Total maximum delay**: ~7 seconds (1s + 2s + 4s + final attempt)

**Do NOT retry:**
- 400-499: Client errors (validation, format, authorization)
- Serialization errors
- Payloads exceeding size limits

**Safe to retry (same clientRequestId):**
- 500-599: Server errors
- Network timeouts
- Connection failures

## Plaintext Lifecycle Management

Per `encryptDocument()` contract, plaintext is NOT zeroized by the crypto module.

```typescript
const plaintext = readFile("sensitive.txt");
const umk = generateUMK();

try {
  const encrypted = await encryptDocument(plaintext, umk);
  await uploadEncryptedPayload(encrypted, generateClientRequestId());
} finally {
  // Best-effort zeroization (not guaranteed)
  zeroArray(plaintext);
  zeroArray(umk);
  // IMPORTANT: plaintext must not be accessed after this
}
```

## Configuration

### Environment Variables

```bash
# Gateway base URL
REACT_APP_GATEWAY_URL=https://gateway.example.com

# Or override in code
uploadEncryptedPayload(encrypted, clientRequestId, {
  baseUrl: "https://gateway.example.com",
})
```

### Constants

```typescript
GATEWAY_CONFIG = {
  baseUrl: process.env.REACT_APP_GATEWAY_URL || "http://localhost:3001",
  uploadEndpoint: "/upload",
  maxRetries: 3,
  retryDelayMs: 1000,
  maxUploadSizeBytes: 100 * 1024 * 1024, // 100 MB
};
```

## Testing

Run tests with:

```bash
# Node.js
node -r ts-node/register app/client/crypto/__tests__/upload.test.ts

# Jest or similar
npm test app/client/crypto/__tests__/upload.test.ts
```

Test coverage:
- ✅ Serialization of valid payloads
- ✅ Validation of payload structure
- ✅ Rejection of invalid versions, sizes, lengths
- ✅ Large ciphertext handling (1MB+)
- ✅ Different algorithm names
- ✅ Round-trip serialization

## Constraints

1. **No crypto changes**: This module ONLY serializes and uploads; crypto code is untouched
2. **No server verification claims**: Server is crypto-blind; cannot verify encryption
3. **Best-effort zeroization**: JavaScript cannot guarantee memory erasure
4. **Size limits**: 100 MB per upload (configurable)
5. **Format rigidity**: Version field enables future evolution without breaking existing payloads

## Error Messages

| Error | Cause | Retry? |
|-------|-------|--------|
| `Invalid Input` | clientRequestId invalid | No |
| `Serialization Error` | Invalid EncryptedPayload structure | No |
| `Payload Too Large` | Exceeds 100 MB limit | No |
| `Invalid Content-Type` | Server rejects non-`application/octet-stream` | No |
| `Missing Header` | clientRequestId header missing | No |
| `Server Error` | HTTP 5xx | Yes |
| `Network Error` | Connection failure | Yes |

## Future Enhancements

- [ ] Progress callback for large uploads
- [ ] Stream-based upload for memory efficiency
- [ ] Checksum validation (e.g., SHA-256 of plaintext)
- [ ] Multi-part upload for >100 MB
- [ ] Compression before encryption (client-side)
- [ ] Resumable uploads with range requests

## See Also

- [encryptDocument.ts](encryptDocument.ts) - Encryption API
- [decryptDocument.ts](decryptDocument.ts) - Decryption API
- [upload-envelope.md](../../security/upload-envelope.md) - Gateway envelope specification
- [threat-model.md](../../security/threat-model.md) - System threat model
