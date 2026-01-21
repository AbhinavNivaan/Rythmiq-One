# Client Crypto Module

## What This Does

Encrypts and decrypts documents using AES-256-GCM with ephemeral per-document keys (DEKs) wrapped by a user master key (UMK).

- `encryptDocument()`: Generates a random DEK, encrypts plaintext, wraps DEK with UMK
- `decryptDocument()`: Unwraps DEK with UMK, decrypts ciphertext
- `generateUMK()`: Creates a random 256-bit UMK

**Cryptographic primitives only. No key management, no persistence, no protocol, no server.**

## What This Does NOT Do

- Key storage or recovery
- Key rotation
- Authentication
- Integrity verification of envelope structure
- Enforcement of encryption at protocol level
- Protection against malicious clients
- Server-side key validation
- Backup or export of keys

## Threat Model

**Hostile clients are allowed.**

The server cannot verify that uploaded payloads are encrypted. A modified or malicious client can upload plaintext. The server will store and process whatever you send.

**Zero-knowledge applies only to compliant clients.** If you don't use this module, or use it incorrectly, your plaintext is visible to the server, operators, storage, backups, and logs.

The server trusts nothing about client behavior.

## Key Loss is Irreversible

**If you lose the UMK, the data is gone. Permanently.**

There is no recovery mechanism, no backup key, no password reset, no account recovery. This is not a bug. It is the security model.

The server never has your UMK. It cannot help you.

## Non-Goals

- **No key escrow**: Server never sees UMK
- **No recovery**: Lose the key, lose the data
- **No enforcement**: Server cannot verify encryption compliance
- **No audit**: Server cannot detect plaintext uploads from hostile clients

## Plaintext Zeroization

**JavaScript cannot guarantee memory zeroization.** This module provides `zeroArray()` as a best-effort cleanup utility, but it cannot protect against:
- Garbage collector copies
- JIT compilation optimizations
- Runtime memory snapshots
- GC heap fragmentation

**Use `zeroArray()` only for reducing the window of plaintext visibility, not as a security guarantee.**

## Usage

```typescript
import { encryptDocument, zeroArray } from './encryptDocument';
import { decryptDocument } from './decryptDocument';
import { generateUMK } from './umk';

// Generate UMK (user must store this)
const umk = generateUMK(); // 32 bytes

// Encrypt
const plaintext = new TextEncoder().encode("secret data");
const encrypted = await encryptDocument(plaintext, umk);
// encrypted = { wrappedDEK, nonce, ciphertext, tag }

// IMPORTANT: Caller owns plaintext lifecycle
zeroArray(plaintext); // Best-effort cleanup (not guaranteed)
// plaintext should not be accessed after this point

// Decrypt
const decrypted = await decryptDocument(encrypted, umk);
// decrypted = Uint8Array("secret data")

// IMPORTANT: Caller owns plaintext lifecycle
zeroArray(decrypted); // Best-effort cleanup (not guaranteed)
// decrypted should not be accessed after this point
```

## DO NOT

- **DO NOT** persist UMK to disk, localStorage, sessionStorage, or cookies without additional protection
- **DO NOT** log plaintext, UMK, or DEK
- **DO NOT** send UMK to the server
- **DO NOT** assume the server will reject plaintext
- **DO NOT** assume the server will validate encryption
- **DO NOT** assume storage.ts is secure (it's a non-persistent in-memory Map for testing only)
- **DO NOT** expect key recovery
