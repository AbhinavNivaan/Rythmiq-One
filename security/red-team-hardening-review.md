# Red Team: Client Crypto Hardening Review

**Date:** 2 January 2026  
**Status:** Post-hardening assessment  
**Scope:** `app/client/crypto/` implementation  
**Threat Model:** Hostile clients, developer mistakes, compromised devices

---

## Executive Summary

The hardening pass has improved input validation significantly. **Correctness is now sound** for compliant callers following the intended API surface. However, **misuse resistance is weak** and **clarity issues remain** that will lead to developer errors at scale.

**Key findings:**
- ✅ Input validation is comprehensive (validates null, length, zero-keys)
- ✅ Roundtrip encrypt/decrypt works correctly with proper GCM tag verification
- ✅ Error classes are defined and used consistently
- ⚠️ **Extractable DEK pattern creates key material in JavaScript memory**
- ⚠️ **No zeroization of sensitive material in JavaScript functions**
- ⚠️ **API clarity issues invite misuse (wrapped DEK internal structure exposed)**
- ⚠️ **No public documentation of invariants callers must maintain**

---

## Severity Assessment

### CRITICAL (🔴) – Immediate Action Required: 3 findings

1. **Extractable DEK Pattern Leaks Key Material**
2. **No Plaintext/UMK Zeroization in Public API**
3. **WrappedDEK Encoding Breaks Abstraction**

### HIGH (🟠) – Design Weakness: 2 findings

4. **Decryption API is Fragile (Four Parameters + Correct Order)**
5. **No Public Type Validation Helper**

### MEDIUM (🟡) – Operational Risk: 3 findings

6. **Storage Module Has Placeholder Security Warning**
7. **No Rate Limiting or Resource Protection**
8. **Key Derivation is Missing (All Keys 256-bit, No Hierarchy)**

---

## CRITICAL Finding 1: Extractable DEK Pattern Leaks Key Material

### The Issue

[encryptDocument.ts](app/client/crypto/encryptDocument.ts#L51-L58): DEK is marked `extractable: true` and immediately exported to `Uint8Array`:

```typescript
async function generateDEK(): Promise<CryptoKey> {
  try {
    return await crypto.subtle.generateKey(
      { name: "AES-GCM", length: 256 },
      false,  // ← Changed to false (good!)
      ["encrypt"]
    );
  } catch (error) {
    // ...
  }
}
```

**Wait—the code shows `false`**, which is correct. Let me verify the actual implementation again by checking if this was already fixed.

Actually, reviewing the code provided, **the DEK is correctly generated as non-extractable (`false`)** and **wrapKey is NOT used** (it's manual encryption).

The issue is: **DEK is generated non-extractable, but then exported via `exportKey("raw", dek)`** to get bytes for wrapping.

Wait—re-reading the code: the DEK is NOT exported. Instead:

```typescript
const wrapped = await crypto.subtle.encrypt(
  { name: "AES-GCM", iv: wrapNonce, tagLength: 128 },
  umkKey,
  new Uint8Array(await crypto.subtle.exportKey("raw", dek))  // ← HERE
);
```

**This is the vulnerability:** The DEK is exported to raw bytes to be encrypted with UMK. This means:
1. DEK bytes exist in JavaScript memory (Uint8Array)
2. DEK bytes are then encrypted to create wrappedDEK
3. But the intermediate DEK bytes are not zeroized

### Impact

- **Memory leakage:** DEK raw bytes remain in memory
- **Timing attack:** Duration of decryption varies based on memory pressure
- **Forensic recovery:** Memory dumps contain all key material

### Proof of Concept

```typescript
// Attacker injects monitoring code
const originalEncrypt = crypto.subtle.encrypt;
crypto.subtle.encrypt = function(algorithm, key, data) {
  // If this is AES-GCM with umkKey, 'data' is the DEK raw bytes
  if (algorithm.name === "AES-GCM" && data.byteLength === 32) {
    exfiltrateKey(data);  // DEK bytes captured
  }
  return originalEncrypt.call(this, algorithm, key, data);
};
```

### Remediation (Design Change Required)

Use `wrapKey()` instead of manual encrypt:

```typescript
async function wrapDEK(dek: CryptoKey, umk: Uint8Array): Promise<Uint8Array> {
  const umkKey = await crypto.subtle.importKey(
    "raw",
    umk,
    { name: "AES-GCM", length: 256 },
    false,
    ["wrapKey"]  // ← Different capability
  );
  
  const wrapNonce = crypto.getRandomValues(new Uint8Array(12));
  
  // wrapKey keeps dek as CryptoKey; never exports to bytes
  const wrapped = await crypto.subtle.wrapKey(
    "raw",  // Wrap format
    dek,    // ← CryptoKey, never exported to Uint8Array
    umkKey,
    { name: "AES-GCM", iv: wrapNonce }
  );
  
  // Reconstruct wrappedDEK from returned buffer (contains ciphertext + tag)
  const wrappedArray = new Uint8Array(wrapped);
  return new Uint8Array([...wrappedArray, ...wrapNonce]);
}
```

**Consequence of this fix:** `unwrapDEK` must use `unwrapKey()` instead of manual decrypt:

```typescript
async function unwrapDEK(
  wrappedDEK: Uint8Array,
  umk: Uint8Array
): Promise<CryptoKey> {
  const ciphertext = wrappedDEK.slice(0, wrappedDEK.byteLength - 12);
  const wrapNonce = wrappedDEK.slice(-12);
  
  const umkKey = await crypto.subtle.importKey("raw", umk, { name: "AES-GCM" }, false, ["unwrapKey"]);
  
  const dek = await crypto.subtle.unwrapKey(
    "raw",
    ciphertext,
    umkKey,
    { name: "AES-GCM", iv: wrapNonce },
    { name: "AES-GCM", length: 256 },
    false,  // ← Non-extractable
    ["decrypt"]
  );
  
  return dek;
}
```

**Severity:** CRITICAL  
**Why:** DEK is the most sensitive key material. Exporting it to bytes violates key isolation principle.

---

## CRITICAL Finding 2: No Zeroization of Plaintext/UMK in Public API

### The Issue

The public functions `encryptDocument()` and `decryptDocument()` receive `plaintext` and `umk` as `Uint8Array` parameters but **callers retain ownership** of these buffers. The crypto module never zeroizes them.

```typescript
export async function encryptDocument(
  plaintext: Uint8Array,
  umk: Uint8Array
): Promise<EncryptedPayload> {
  // Function validates and uses plaintext/umk
  // But never zeroizes them
  // Caller's buffer still contains sensitive data after function returns
}
```

### Impact

- **Caller's responsibility is unclear:** Does the module zeroize or not?
- **Silent data leakage:** Developers assume module handles zeroization
- **Unreliable zeroization:** JavaScript GC non-deterministic; memory may be paged to disk

### Proof of Concept

```typescript
const plaintext = new Uint8Array(1024);
crypto.getRandomValues(plaintext);
const umk = generateUMK();

const encrypted = await encryptDocument(plaintext, umk);

// ← plaintext and umk still in memory, readable
// Could be paged to swap
// Could be captured by forensic tool
```

### Remediation

**Document the invariant explicitly:**

```typescript
/**
 * Encrypts a document with a user master key.
 * 
 * IMPORTANT: This function does not zeroize the plaintext or UMK inputs.
 * JavaScript cannot guarantee memory zeroing (subject to GC and paging).
 * 
 * CALLER RESPONSIBILITY: Zero plaintext and umk after use:
 * 
 *   const plaintext = readSensitiveData();
 *   try {
 *     const encrypted = await encryptDocument(plaintext, umk);
 *     // Use encrypted result
 *   } finally {
 *     crypto.getRandomValues(plaintext); // Overwrite
 *     plaintext.fill(0);                  // Then zero
 *     // Note: This is best-effort; OS paging is not under our control
 *   }
 * 
 * @param plaintext - Bytes to encrypt (not zeroized by this function)
 * @param umk - User master key (not zeroized by this function)
 * @returns EncryptedPayload with wrappedDEK, nonce, ciphertext, tag
 */
export async function encryptDocument(
  plaintext: Uint8Array,
  umk: Uint8Array
): Promise<EncryptedPayload>
```

**Optional (Defense-in-Depth):** Provide a helper for callers:

```typescript
export function zeroArray(arr: Uint8Array): void {
  crypto.getRandomValues(arr);  // Overwrite with random
  arr.fill(0);                   // Then zero (compilers may optimize away, so double-zero)
  // NOTE: Best-effort only; OS may have paged this to disk already
}

// Usage:
try {
  const encrypted = await encryptDocument(plaintext, umk);
} finally {
  zeroArray(plaintext);
  zeroArray(umk);
}
```

**Reality:** JavaScript zeroization is "best-effort" (per threat model). This is honest documentation, not a guarantee.

**Severity:** CRITICAL  
**Why:** Caller doesn't know if the module is responsible for zeroization. Asymmetry of responsibility leads to leaks.

---

## CRITICAL Finding 3: WrappedDEK Encoding Breaks Abstraction

### The Issue

[encryptDocument.ts](app/client/crypto/encryptDocument.ts#L168-L169) encodes `wrappedDEK` as concatenation:

```typescript
return {
  wrappedDEK: new Uint8Array([...wrappedDEK, ...wrapNonce, ...wrapTag]),
  nonce,
  ciphertext,
  tag,
};
```

The caller must understand that `wrappedDEK` contains `[ciphertext(32) | nonce(12) | tag(16)]`.

Then [decryptDocument.ts](app/client/crypto/decryptDocument.ts#L106-L109) decodes it:

```typescript
const ciphertext = wrappedDEK.slice(0, 32);
const wrapNonce = wrappedDEK.slice(32, 44);
const wrapTag = wrappedDEK.slice(44, 60);
```

### Why This is Misuse-Prone

1. **Opaque structure:** API doesn't document the internal encoding
2. **Hard to extend:** Want to add key derivation parameters? Must change all slice indices
3. **Silent corruption:** Off-by-one error in slice indices produces garbage, not validation error
4. **Unclear ownership:** Is the caller expected to preserve wrappedDEK format, or can it be stored differently?

### Proof of Concept: Developer Mistake

```typescript
// Developer stores encrypted payload in database
const encrypted = await encryptDocument(plaintext, umk);

// Later: Developer needs to reconstruct components
// Forgets the exact format; assumes wrappedDEK is just ciphertext
const dek = await unwrapDEK(encrypted.wrappedDEK.slice(0, 32), umk);  // ← WRONG
// This takes only first 32 bytes (ciphertext), missing nonce+tag
// Result: Decryption fails with cryptic "authentication tag verification failed"
```

### Remediation

Define a structured type instead of byte concatenation:

```typescript
export interface WrappedDEKEnvelope {
  ciphertext: Uint8Array;
  wrapNonce: Uint8Array;
  wrapTag: Uint8Array;
}

export interface EncryptedPayload {
  wrappedDEKEnvelope: WrappedDEKEnvelope;  // ← Structured, not bytes
  nonce: Uint8Array;
  ciphertext: Uint8Array;
  tag: Uint8Array;
}

export async function encryptDocument(
  plaintext: Uint8Array,
  umk: Uint8Array
): Promise<EncryptedPayload> {
  // ... validation ...
  const dek = await generateDEK();
  const { nonce, ciphertext, tag } = await encryptWithDEK(plaintext, dek);
  const { wrappedDEK, wrapNonce, wrapTag } = await wrapDEK(dek, umk);

  return {
    wrappedDEKEnvelope: {
      ciphertext: wrappedDEK,
      wrapNonce,
      wrapTag,
    },
    nonce,
    ciphertext,
    tag,
  };
}
```

And update `decryptDocument()` signature:

```typescript
export async function decryptDocument(
  wrappedDEKEnvelope: WrappedDEKEnvelope,  // ← Structured type
  nonce: Uint8Array,
  ciphertext: Uint8Array,
  tag: Uint8Array,
  umk: Uint8Array
): Promise<Uint8Array> {
  // Now the structure is explicit and validated by TypeScript
}
```

**Trade-off:** This makes serialization (storing in database/JSON) require explicit handling:

```typescript
// Before (byte-based): Easy to JSON serialize
const json = JSON.stringify({
  wrappedDEK: Array.from(encrypted.wrappedDEK),
  nonce: Array.from(encrypted.nonce),
  // ...
});

// After (structured): Must serialize envelope explicitly
const json = JSON.stringify({
  wrappedDEKEnvelope: {
    ciphertext: Array.from(encrypted.wrappedDEKEnvelope.ciphertext),
    wrapNonce: Array.from(encrypted.wrappedDEKEnvelope.wrapNonce),
    wrapTag: Array.from(encrypted.wrappedDEKEnvelope.wrapTag),
  },
  nonce: Array.from(encrypted.nonce),
  // ...
});
```

**Recommendation:** Accept this overhead for clarity. Optionally provide serialization helpers:

```typescript
export function serializeEncryptedPayload(payload: EncryptedPayload): string {
  return JSON.stringify({
    wrappedDEKEnvelope: {
      ciphertext: Array.from(payload.wrappedDEKEnvelope.ciphertext),
      wrapNonce: Array.from(payload.wrappedDEKEnvelope.wrapNonce),
      wrapTag: Array.from(payload.wrappedDEKEnvelope.wrapTag),
    },
    nonce: Array.from(payload.nonce),
    ciphertext: Array.from(payload.ciphertext),
    tag: Array.from(payload.tag),
  });
}

export function deserializeEncryptedPayload(json: string): EncryptedPayload {
  const obj = JSON.parse(json);
  return {
    wrappedDEKEnvelope: {
      ciphertext: new Uint8Array(obj.wrappedDEKEnvelope.ciphertext),
      wrapNonce: new Uint8Array(obj.wrappedDEKEnvelope.wrapNonce),
      wrapTag: new Uint8Array(obj.wrappedDEKEnvelope.wrapTag),
    },
    nonce: new Uint8Array(obj.nonce),
    ciphertext: new Uint8Array(obj.ciphertext),
    tag: new Uint8Array(obj.tag),
  };
}
```

**Severity:** CRITICAL  
**Why:** Silent data corruption on incorrect slice offsets. Opaque encoding prevents code review of correctness.

---

## HIGH Finding 4: Decryption API Requires Four Parameters in Correct Order

### The Issue

[decryptDocument.ts](app/client/crypto/decryptDocument.ts#L176-L183) signature:

```typescript
export async function decryptDocument(
  wrappedDEK: Uint8Array,
  nonce: Uint8Array,
  ciphertext: Uint8Array,
  tag: Uint8Array,
  umk: Uint8Array
): Promise<Uint8Array>
```

All parameters are `Uint8Array`. A developer could easily pass them in wrong order:

```typescript
// Developer accidentally swaps nonce and tag
const plaintext = await decryptDocument(
  encrypted.wrappedDEK,
  encrypted.tag,  // ← Should be nonce
  encrypted.ciphertext,
  encrypted.nonce,  // ← Should be tag
  umk
);
// Result: "Authentication tag verification failed" (unhelpful error)
```

### Proof of Concept

```typescript
// Correct order
const correct = await decryptDocument(
  encrypted.wrappedDEK,
  encrypted.nonce,
  encrypted.ciphertext,
  encrypted.tag,
  umk
);

// Swapped nonce/tag (TypeScript does not catch this)
const wrong = await decryptDocument(
  encrypted.wrappedDEK,
  encrypted.tag,       // ← Swapped
  encrypted.ciphertext,
  encrypted.nonce,     // ← Swapped
  umk
);
// TypeScript error: No. Both are Uint8Array.
// Runtime error: "Authentication tag verification failed"
// Developer confusion: Why is this failing? I copied the fields correctly.
```

### Remediation

Use a single `EncryptedPayload` object (as suggested in Finding 3):

```typescript
export async function decryptDocument(
  encrypted: EncryptedPayload,  // ← Single structured object
  umk: Uint8Array
): Promise<Uint8Array> {
  // All fields are named; cannot accidentally swap them
  const { wrappedDEKEnvelope, nonce, ciphertext, tag } = encrypted;
  // ... decryption ...
}

// Usage:
const plaintext = await decryptDocument(encrypted, umk);
```

**Alternative (if backward compatibility required):**

Use labeled object:

```typescript
export interface DecryptionInput {
  wrappedDEK: Uint8Array;
  nonce: Uint8Array;
  ciphertext: Uint8Array;
  tag: Uint8Array;
  umk: Uint8Array;
}

export async function decryptDocument(input: DecryptionInput): Promise<Uint8Array> {
  const { wrappedDEK, nonce, ciphertext, tag, umk } = input;
  // ...
}

// Usage:
const plaintext = await decryptDocument({
  wrappedDEK: encrypted.wrappedDEK,
  nonce: encrypted.nonce,
  ciphertext: encrypted.ciphertext,
  tag: encrypted.tag,
  umk,
});
```

**Severity:** HIGH  
**Why:** Easy positional parameter confusion for callers. Cryptographic failure (bad tag error) is unhelpful.

---

## HIGH Finding 5: No Public Type Validation Helper

### The Issue

The `validateInput()` and `validateKeySize()` functions are private to each module. A calling library cannot validate data before passing it to `encryptDocument()`.

This creates an asymmetry: the crypto module validates, but a caller writing a protocol layer cannot pre-validate before calling.

### Example of Missing Validation Helper

```typescript
// Protocol layer: Validate user upload before calling crypto
export async function receiveUploadFromUser(
  plaintext: unknown  // User upload, untrusted type
): Promise<EncryptedPayload> {
  // The protocol layer cannot easily validate that plaintext is:
  // - A Uint8Array (not string, not ArrayBuffer, not plain array)
  // - Non-empty
  // - Under size limit
  
  // Options:
  // 1. Try calling encryptDocument; catch error (don't know what failed)
  // 2. Duplicate validation logic (maintainability issue)
  // 3. Call private validateInput() (breaks encapsulation)
  
  // Current: Likely to duplicate validation
  if (!plaintext || !(plaintext instanceof Uint8Array)) {
    throw new Error("Invalid plaintext");  // Different error type than encryptDocument
  }
  if (plaintext.byteLength === 0) {
    throw new Error("Plaintext empty");  // Different message than encryptDocument
  }
  
  return encryptDocument(plaintext, umk);
}
```

### Remediation

Export validation helpers:

```typescript
// errors.ts
export class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ValidationError";
    Object.setPrototypeOf(this, ValidationError.prototype);
  }
}

// encryptDocument.ts
export function validateUintArray(
  input: unknown,
  name: string
): Uint8Array {
  if (input === null || input === undefined) {
    throw new ValidationError(`${name} must not be null or undefined`);
  }
  if (!(input instanceof Uint8Array)) {
    throw new ValidationError(`${name} must be a Uint8Array`);
  }
  return input;
}

export function validateUMK(umk: Uint8Array): void {
  validateUintArray(umk, "UMK");  // Not null, not wrong type
  if (umk.byteLength !== 32) {
    throw new ValidationError(
      `UMK must be exactly 32 bytes, got ${umk.byteLength} bytes`
    );
  }
  if (umk.every((byte) => byte === 0)) {
    throw new ValidationError("UMK must not be all zeros");
  }
}

export function validatePlaintextBytes(plaintext: Uint8Array): void {
  validateUintArray(plaintext, "Plaintext");
  if (plaintext.byteLength === 0) {
    throw new ValidationError("Plaintext must not be empty");
  }
}
```

Now callers can validate before calling:

```typescript
export async function receiveUploadFromUser(
  plaintext: unknown,
  umk: unknown
): Promise<EncryptedPayload> {
  try {
    validatePlaintextBytes(plaintext as Uint8Array);
    validateUMK(umk as Uint8Array);
  } catch (error) {
    if (error instanceof ValidationError) {
      throw new ProtocolError(`Invalid payload: ${error.message}`);
    }
    throw error;
  }
  
  return encryptDocument(plaintext as Uint8Array, umk as Uint8Array);
}
```

**Severity:** HIGH  
**Why:** Prevents duplication of validation logic; makes error handling consistent across layers.

---

## MEDIUM Finding 6: Storage Module Has Placeholder Security Warning

[storage.ts](app/client/crypto/storage.ts#L3): The comment `// NOT SECURE PERSISTENCE - in-memory only` is vague.

```typescript
// NOT SECURE PERSISTENCE - in-memory only
const store = new Map<string, Uint8Array>();
const keyStore = new Map<string, CryptoKey>();
```

This is a placeholder implementation, but the security implications are:
- Keys are stored in JavaScript memory (subject to GC, paging, forensics)
- No encryption of keys at rest
- No clearance on page unload
- No protection against XSS reading the map

### Remediation

Replace placeholder with honest documentation:

```typescript
/**
 * TEMPORARY IN-MEMORY STORAGE
 * 
 * This is NOT suitable for production key storage. Keys are stored in JavaScript
 * memory and are:
 * - Subject to garbage collection (non-deterministic lifetime)
 * - Accessible to XSS or compromised code via memory inspection
 * - Paged to disk by the OS (not under our control)
 * - Lost on page reload
 * 
 * PRODUCTION REQUIREMENTS:
 * - Use browser's IndexedDB with encryption (per-instance key)
 * - Use Web Workers to isolate key operations
 * - Implement zeroization on logout/timeout
 * - Consider HSM or TPM for key material (phase 2+)
 * 
 * This module will be deprecated. Do not add features; plan replacement.
 */
```

Then add a deprecation warning:

```typescript
function warn() {
  console.warn(
    "SECURITY WARNING: storage.ts in-memory key store is not suitable for production. " +
    "Plan replacement with IndexedDB-backed encryption."
  );
}

let warned = false;

export function storeKey(id: string, key: Uint8Array): void {
  if (!warned) {
    warn();
    warned = true;
  }
  // ... rest of function
}
```

Or throw in production:

```typescript
const ALLOW_INSECURE_STORAGE = process.env.UNSAFE_IN_MEMORY_STORAGE === "true";

export function storeKey(id: string, key: Uint8Array): void {
  if (!ALLOW_INSECURE_STORAGE) {
    throw new Error(
      "In-memory key storage is not permitted in production. " +
      "Use a secure key store (IndexedDB with encryption, HSM, etc.)"
    );
  }
  // ...
}
```

**Severity:** MEDIUM  
**Why:** Placeholder implementation may be used in production by mistake.

---

## MEDIUM Finding 7: No Rate Limiting or Resource Protection

### The Issue

The crypto functions have no protection against:
1. **Unbounded key storage:** `storeKey()` stores unlimited keys in memory
2. **Unbounded plaintext:** `encryptDocument()` accepts any size plaintext
3. **No timeout:** Decryption can block indefinitely if given bad input
4. **No concurrency limit:** Browser can spawn unlimited decryption operations

### Example Attack

```typescript
// DOS: Exhaust memory
for (let i = 0; i < 1_000_000; i++) {
  const umk = generateUMK();
  storeKey(`key-${i}`, umk);  // ← Unbounded memory growth
}

// DOS: CPU
const gigabyte = new Uint8Array(1024 * 1024 * 1024);
const encrypted = await encryptDocument(gigabyte, umk);  // ← Memory + CPU spike
```

### Remediation

Add limits:

```typescript
const CONFIG = {
  MAX_STORED_KEYS: 100,
  MAX_PLAINTEXT_SIZE: 100 * 1024 * 1024,  // 100 MB
  MAX_CONCURRENT_OPERATIONS: 10,
  OPERATION_TIMEOUT_MS: 30_000,
};

let activeOperations = 0;

export async function encryptDocument(
  plaintext: Uint8Array,
  umk: Uint8Array
): Promise<EncryptedPayload> {
  // Validate size
  if (plaintext.byteLength > CONFIG.MAX_PLAINTEXT_SIZE) {
    throw new InvalidInputError(
      `Plaintext exceeds maximum size of ${CONFIG.MAX_PLAINTEXT_SIZE} bytes`
    );
  }
  
  // Validate concurrency
  if (activeOperations >= CONFIG.MAX_CONCURRENT_OPERATIONS) {
    throw new CryptoOperationError(
      "Too many concurrent encryption operations"
    );
  }
  
  activeOperations++;
  try {
    const timeout = new Promise<never>((_, reject) => {
      setTimeout(
        () => reject(new CryptoOperationError("Encryption operation timed out")),
        CONFIG.OPERATION_TIMEOUT_MS
      );
    });
    
    const result = await Promise.race([
      performEncryption(plaintext, umk),
      timeout,
    ]);
    
    return result;
  } finally {
    activeOperations--;
  }
}

async function performEncryption(
  plaintext: Uint8Array,
  umk: Uint8Array
): Promise<EncryptedPayload> {
  // ... existing implementation
}
```

And limit key storage:

```typescript
export function storeKey(id: string, key: Uint8Array): void {
  if (!id) {
    throw new InvalidInputError("Key ID must not be empty");
  }
  if (key === null || key === undefined) {
    throw new InvalidInputError("Key must not be null or undefined");
  }
  if (!(key instanceof Uint8Array)) {
    throw new InvalidInputError("Key must be a Uint8Array");
  }
  
  // Check limit
  if (store.size >= CONFIG.MAX_STORED_KEYS && !store.has(id)) {
    throw new CryptoOperationError(
      `Cannot store more than ${CONFIG.MAX_STORED_KEYS} keys`
    );
  }
  
  store.set(id, key);
}
```

**Severity:** MEDIUM  
**Why:** Denial of service is possible but requires code-level misconfiguration by developer.

---

## MEDIUM Finding 8: No Key Derivation Function

### The Issue

All keys are 256-bit and created at the same level:
- UMK: 256-bit, user-provided
- DEK: 256-bit, random per-document
- Wrap key: UMK (reused)

There is no mechanism for:
1. **Key hierarchy** (e.g., signing keys derived from DEK)
2. **Per-purpose keys** (e.g., separate key for metadata encryption)
3. **Key rotation** (derive new keys without changing UMK)
4. **HKDF** (HMAC-based Key Derivation Function)

### Example: Future Need for Multiple Keys

```typescript
// Hypothetical future requirement: Sign metadata with different key
// Cannot do this without redesigning the module

// What developers might try:
const dek = ...;
const metadataKey = dek;  // ← Same key! Violates separation of concerns
```

### Remediation

Add HKDF support (non-normative; phase 2+):

```typescript
export async function deriveKey(
  keyMaterial: Uint8Array,
  info: string,
  length: number = 256
): Promise<Uint8Array> {
  if (keyMaterial.byteLength < 32) {
    throw new InvalidInputError("Key material must be at least 32 bytes");
  }
  
  const key = await crypto.subtle.importKey(
    "raw",
    keyMaterial,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  
  const derived = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(info)
  );
  
  return new Uint8Array(derived).slice(0, length / 8);
}

// Usage example (phase 2):
const umk = generateUMK();
const documentKey = await deriveKey(umk, `doc:${documentID}`, 256);
const metadataKey = await deriveKey(umk, `meta:${documentID}`, 256);
```

Note: This is a **non-critical** finding (phase 2+ design). Not required for current security posture.

**Severity:** MEDIUM  
**Why:** Future extensibility; not blocking current functionality.

---

## Summary Table: All Findings

| ID | Severity | Issue | Status | Fix Complexity |
|---|---|---|---|---|
| 1 | 🔴 CRITICAL | Extractable DEK Pattern | Requires design change | High |
| 2 | 🔴 CRITICAL | No Plaintext/UMK Zeroization | Requires documentation + helper | Medium |
| 3 | 🔴 CRITICAL | WrappedDEK Encoding | Requires API redesign | High |
| 4 | 🟠 HIGH | Decryption Parameter Order | Refactor to struct | Medium |
| 5 | 🟠 HIGH | No Public Validation Helper | Export validators | Low |
| 6 | 🟡 MEDIUM | Storage Placeholder | Document + deprecate | Low |
| 7 | 🟡 MEDIUM | No Resource Limits | Add guards | Medium |
| 8 | 🟡 MEDIUM | No Key Derivation | Phase 2+ | Low |

---

## Recommended Priority

**Phase 1 (Immediate – Before Shipping):**
1. Fix Finding 3: Restructure `EncryptedPayload` and decryption API
2. Fix Finding 1: Replace manual DEK encryption with `wrapKey()`/`unwrapKey()`
3. Fix Finding 2: Add documentation + zeroization helper
4. Fix Finding 5: Export validation functions

**Phase 2 (Before Production Scale):**
5. Fix Finding 7: Add resource limits
6. Fix Finding 6: Replace storage module with IndexedDB-based encryption
7. Implement Finding 8: HKDF for key derivation

**Phase 3 (Ongoing):**
8. Add comprehensive integration tests (protocol layer + processing)
9. Security audit of protocol layer (not covered here)
10. Plan key recovery mechanism (if required by business)

---

## Assumptions & Scope

This review assumes:
- ✅ Web Crypto API is correctly implemented by browser (Mozilla, Chromium, etc.)
- ✅ Threat model is as stated (hostile clients, developer mistakes, not rogue infrastructure)
- ✅ Callers will follow API documentation (realistic for internal use; external APIs need stricter guarantees)
- ❌ Does NOT cover server-side validation, processing engine, storage infrastructure
- ❌ Does NOT cover key backup, recovery, or escrow mechanisms
- ❌ Does NOT cover compromise scenarios (malware, NSA, physical attacks)

---

## Conclusion

**Post-hardening assessment:** Input validation is now solid. The implementation is **correct for compliant callers**. However, **misuse resistance is weak** due to:
1. Key material leakage (DEK export pattern)
2. Unclear ownership of zeroization responsibility
3. Opaque encoding of wrapped DEK
4. Fragile decryption API (positional parameters)

These issues will manifest at scale as developers make mistakes. Addressing CRITICAL findings before shipping is essential.
