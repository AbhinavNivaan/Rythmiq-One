# Upload Envelope Specification

## Overview

The Upload Envelope defines the structure for submitting opaque payloads to a crypto-blind server. The server cannot verify encryption, decrypt payloads, or validate their contents.

## Envelope Structure

```
{
  "version": <int>,
  "contentLength": <int>,
  "contentType": "application/octet-stream",
  "clientRequestId": <string>,
  "payload": <bytes>
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | integer | Yes | Envelope format version. Current: 1 |
| `contentLength` | integer | Yes | Byte length of payload. Must equal payload size. |
| `contentType` | string | Yes | Fixed value: `application/octet-stream`. No alternatives permitted. |
| `clientRequestId` | string | Yes | Unique identifier for idempotency. Client-generated. Format: UUID v4 recommended. |
| `payload` | bytes | Yes | Opaque binary data. Server makes no assumptions about content or encoding. |

## Semantics

### Server Behavior

- The server **treats payload as opaque binary data**
- The server **does not verify, decrypt, or validate** payload contents
- The server **does not inspect or enforce** payload structure
- The server **does not extract, process, or log** payload bytes
- The server **does not make cryptographic assumptions** about the payload

### Client Responsibility

- Clients are responsible for all encryption, validation, and integrity protection
- The server provides **no cryptographic services** for upload payloads

### Idempotency

- `clientRequestId` enables client-driven idempotency
- Clients MUST generate unique IDs per logical request
- Server MUST deduplicate by `clientRequestId` on retry

## Threat Model Acceptance

This specification explicitly accepts the following:

- **Plaintext uploads**: Hostile or misconfigured clients may upload unencrypted payloads. The server cannot and will not detect or prevent this.
- **No encryption enforcement**: The server does not verify, require, or assume encryption.
- **No payload validation**: The server does not validate payload authenticity, integrity, or format.
- **Opaque handling**: The server's inability to inspect payloads is a feature, not a limitation.

Clients relying on encryption MUST implement encryption before upload. The server's crypto-blindness is by design.

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1 | 2026-01-04 | Initial specification |
