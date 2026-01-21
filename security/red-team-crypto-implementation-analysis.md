# Red Team: Client Crypto Implementation Analysis

**Date:** 2 January 2026  
**Analyst:** Red Team Security Review  
**Target:** app/client/crypto/ implementation  
**Threat Model Posture:** Hostile clients, developer mistakes, compromised devices

---

## Executive Summary

**CRITICAL FINDING:** The client-side crypto implementation has **no decryption function**, **no integrity verification**, **no error handling**, and **no defense against developer misuse**. The code is a write-only encryption API with zero validation of inputs, zero zeroization of sensitive material, and zero protection against timing attacks or key reuse.

**Severity Assessment:**
- 🔴 **CRITICAL:** 8 findings (immediate code changes required)
- 🟠 **HIGH:** 6 findings (architectural weaknesses)
- 🟡 **MEDIUM:** 4 findings (operational risks)

**Bottom Line:** This implementation is a prototype. It assumes honest developers, correct inputs, and controlled environments. It has no defenses against the stated threat model: hostile clients, developer mistakes, or compromised devices.

---

## Critical Finding 1: NO DECRYPTION OR UNWRAPPING FUNCTION EXISTS

### Evidence
```bash
$ grep -r "decrypt\|unwrap" app/client/crypto/
# NO RESULTS
```

The crypto module provides:
- ✅ Encryption: `encryptDocument()`
- ✅ DEK generation: `generateDEK()`
- ✅ DEK wrapping: `wrapDEK()`
- ❌ **MISSING:** Decryption function
- ❌ **MISSING:** DEK unwrapping function
- ❌ **MISSING:** GCM tag verification
- ❌ **MISSING:** Integrity validation

### Impact
1. **Cannot decrypt documents** → System is write-only
2. **Cannot test encryption roundtrip** → No way to verify correctness
3. **Cannot implement processing pipeline** → Server processing requires decryption
4. **GCM tag verification never occurs** → Integrity protection is theoretical

### Attack Surface
- **Forged ciphertext:** No verification means any bytes can be "decrypted"
- **Modified wrappedDEK:** No authentication; attacker can modify wrapped key
- **Swapped nonces/tags:** No binding between ciphertext and metadata

### Red Team Assessment
**CRITICAL (🔴):** A crypto implementation without decryption is incomplete. This indicates:
1. Code is untested (cannot encrypt-then-decrypt to verify)
2. Threat model Stage 4 (processing engine decryption) is unimplemented
3. GCM tag verification is missing (integrity protection doesn't exist)

**Recommendation:** Implement `decryptDocument()` and `unwrapDEK()` with explicit GCM tag verification BEFORE decryption completes.

---

## Critical Finding 2: NO VALIDATION OF INPUT PARAMETERS

### Evidence from [encryptDocument.ts](app/client/crypto/encryptDocument.ts):
```typescript
export async function encryptDocument(
  plaintext: Uint8Array,
  umk: Uint8Array
): Promise<EncryptedPayload>
```

**Missing validations:**
- ❌ No check that `plaintext` is non-null
- ❌ No check that `plaintext.length > 0`
- ❌ No check that `umk.length === 32` (256 bits)
- ❌ No check that `umk` is not all zeros
- ❌ No maximum plaintext size enforcement
- ❌ No input sanitization

### Attack Scenarios

#### Scenario 1: Zero-Length Plaintext
```typescript
const encrypted = await encryptDocument(new Uint8Array(0), umk);
// Returns valid-looking payload with empty ciphertext
// Server stores this as a "document"
// Processing engine crashes on empty plaintext
```

#### Scenario 2: All-Zero UMK
```typescript
const weakKey = new Uint8Array(32); // All zeros
const encrypted = await encryptDocument(plaintext, weakKey);
// Encryption succeeds with catastrophically weak key
// All documents encrypted with same weak key
```

#### Scenario 3: Wrong Key Length
```typescript
const shortKey = new Uint8Array(16); // 128-bit key passed as 256-bit
const encrypted = await encryptDocument(plaintext, shortKey);
// importKey() may fail silently or accept wrong length
// Result: Weak encryption or runtime error
```

#### Scenario 4: Null/Undefined Inputs (Developer Mistake)
```typescript
const encrypted = await encryptDocument(undefined, umk);
// TypeScript won't catch at runtime
// Crypto API throws cryptic error
// No helpful error message for developer
```

### Red Team Assessment
**CRITICAL (🔴):** Missing input validation enables:
1. **Developer mistakes:** Wrong key length, null inputs → silent failures
2. **Hostile clients:** All-zero keys, empty plaintext → weak encryption
3. **Resource exhaustion:** Gigabyte-sized plaintext → OOM crash

**Recommendation:** Add comprehensive input validation:
```typescript
export async function encryptDocument(
  plaintext: Uint8Array,
  umk: Uint8Array
): Promise<EncryptedPayload> {
  // Validate inputs
  if (!plaintext || plaintext.length === 0) {
    throw new Error("plaintext must be non-empty");
  }
  if (plaintext.length > 100 * 1024 * 1024) { // 100MB max
    throw new Error("plaintext exceeds maximum size");
  }
  if (!umk || umk.length !== 32) {
    throw new Error("UMK must be exactly 32 bytes");
  }
  if (isAllZeros(umk)) {
    throw new Error("UMK must not be all zeros");
  }
  // ... rest of function
}
```

---

## Critical Finding 3: NO ZEROIZATION OF SENSITIVE MATERIAL

### Evidence from [encryptDocument.ts](app/client/crypto/encryptDocument.ts#L8-L21):
```typescript
async function generateDEK(): Promise<CryptoKey> {
  return await crypto.subtle.generateKey(
    { name: "AES-GCM", length: 256 },
    true,  // ← EXTRACTABLE! Key can be exported
    ["encrypt"]
  );
}

async function exportDEK(key: CryptoKey): Promise<Uint8Array> {
  const raw = await crypto.subtle.exportKey("raw", key);
  return new Uint8Array(raw);
  // ← DEK bytes remain in memory (no zeroization)
}
```

### Zeroization Gaps

| Sensitive Material | Zeroization | Status |
|-------------------|-------------|--------|
| `dekRaw` (line 81) | None | ❌ Leaked |
| `plaintext` parameter | None | ❌ Leaked |
| `umk` parameter | None | ❌ Leaked |
| `wrapNonce` | None | ❌ Leaked (less critical) |
| `dek` CryptoKey | None | ❌ Leaked |
| Intermediate buffers | None | ❌ Leaked |

### Attack Scenarios

#### Scenario 1: Memory Scraping
```javascript
// Attacker injects code into client (XSS, compromised library, etc.)
const originalEncrypt = encryptDocument;
encryptDocument = async (plaintext, umk) => {
  // Intercept and exfiltrate
  exfiltrateToAttacker(plaintext, umk);
  return originalEncrypt(plaintext, umk);
};
```

#### Scenario 2: Garbage Collection Timing
```javascript
const encrypted = await encryptDocument(sensitiveData, umk);
// sensitiveData, umk, dekRaw all remain in memory
// Subject to JavaScript GC (non-deterministic)
// May be paged to disk before GC runs
// Forensic recovery possible
```

#### Scenario 3: Process Crash Dump
```javascript
await encryptDocument(plaintext, umk);
// <--- CRASH HERE --->
// plaintext, umk, dekRaw in memory dump
// No zeroization occurred
// Forensic analysis extracts keys and plaintext
```

### Red Team Assessment
**CRITICAL (🔴):** No zeroization of sensitive material violates threat model Section 4 ("Ephemeral RAM-Only" data classification).

Per threat model:
> "Plaintext lifetime target: duration of a single cryptographic operation (< 100 milliseconds per operation; not enforced)"

Current implementation: Plaintext and keys remain in memory **indefinitely** until garbage collection.

**Recommendation:** Implement explicit zeroization:
```typescript
export async function encryptDocument(
  plaintext: Uint8Array,
  umk: Uint8Array
): Promise<EncryptedPayload> {
  let dekRaw: Uint8Array | null = null;
  try {
    const dek = await generateDEK();
    dekRaw = await exportDEK(dek);
    
    const { nonce, ciphertext, tag } = await encryptWithDEK(plaintext, dek);
    const { wrappedDEK, wrapNonce, wrapTag } = await wrapDEK(dekRaw, umk);
    
    return {
      wrappedDEK: new Uint8Array([...wrappedDEK, ...wrapNonce, ...wrapTag]),
      nonce,
      ciphertext,
      tag,
    };
  } finally {
    // Zero sensitive material
    if (dekRaw) {
      crypto.getRandomValues(dekRaw); // Overwrite with random
      dekRaw.fill(0); // Then zero
    }
    // Note: Cannot zero plaintext/umk (passed by reference)
    // Caller must zero
  }
}
```

**BUT:** JavaScript cannot reliably zero memory (GC is non-deterministic, paging is uncontrolled). This is acknowledged in threat model:
> "Browser clients cannot guarantee non-pageable memory; zeroization is best-effort and subject to GC and paging."

**Honest Assessment:** Zeroization in JavaScript is **best-effort only**. Treat as defense-in-depth, not a guarantee.

---

## Critical Finding 4: DEK IS MARKED EXTRACTABLE (Violates Key Isolation)

### Evidence from [encryptDocument.ts](app/client/crypto/encryptDocument.ts#L8-L13):
```typescript
async function generateDEK(): Promise<CryptoKey> {
  return await crypto.subtle.generateKey(
    { name: "AES-GCM", length: 256 },
    true,  // ← EXTRACTABLE = TRUE
    ["encrypt"]
  );
}
```

### Why This is Critical

**Web Crypto API extractability:**
- `extractable: true` → Key can be exported via `exportKey()` as raw bytes
- `extractable: false` → Key cannot be exported; remains in browser's secure key store

**Current implementation:**
1. DEK is generated as **extractable**
2. DEK is **immediately exported** to `Uint8Array`
3. DEK bytes remain in JavaScript-accessible memory
4. DEK can be:
   - Read by any code with access to the variable
   - Paged to disk by OS
   - Captured in memory dumps
   - Intercepted by XSS or compromised code

### Correct Pattern (Non-Extractable Keys)
```typescript
// Generate non-extractable DEK
const dek = await crypto.subtle.generateKey(
  { name: "AES-GCM", length: 256 },
  false,  // ← NON-EXTRACTABLE
  ["encrypt", "wrapKey"]
);

// Wrap the DEK using wrapKey (DEK never leaves secure store)
const wrappedDEK = await crypto.subtle.wrapKey(
  "raw",
  dek,      // ← CryptoKey (non-extractable)
  umkKey,   // ← UMK as CryptoKey
  { name: "AES-GCM", iv: wrapNonce }
);
```

### Why Current Implementation Uses Extractable Keys

**Root cause:** Manual wrapping is being performed because the code uses `Uint8Array` for UMK instead of `CryptoKey`.

**Workflow:**
1. UMK is passed as `Uint8Array` (raw bytes)
2. UMK is imported as `CryptoKey` inside `wrapDEK()`
3. DEK must be exported to `Uint8Array` to wrap it manually
4. Therefore, DEK must be extractable

**This is a design flaw.** The UMK should be a `CryptoKey` from the start, never a `Uint8Array`.

### Red Team Assessment
**CRITICAL (🔴):** Extractable DEKs violate the principle of least privilege. Keys should remain in browser's secure key store.

**Current risk:**
- DEK exposure to JavaScript heap
- DEK subject to paging/swap
- DEK accessible to compromised code

**Correct design:**
1. UMK should be generated/imported as **non-extractable** `CryptoKey`
2. DEK should be generated as **non-extractable** `CryptoKey`
3. Use `crypto.subtle.wrapKey()` (native wrapping) instead of manual export+encrypt
4. Keys never leave secure key store

**Recommendation:** Refactor to use `CryptoKey` throughout; eliminate raw byte handling.

---

## Critical Finding 5: NO ERROR HANDLING OR FAILURE MODES

### Evidence: Zero `try-catch` Blocks

```bash
$ grep -c "try" app/client/crypto/*.ts
0
$ grep -c "catch" app/client/crypto/*.ts
0
$ grep -c "throw" app/client/crypto/*.ts
0
```

**All crypto operations are unchecked:**
- `crypto.subtle.generateKey()` can fail
- `crypto.subtle.importKey()` can fail (wrong key length, wrong format)
- `crypto.subtle.encrypt()` can fail (memory allocation, invalid parameters)
- `crypto.getRandomValues()` can fail (CSPRNG exhaustion, entropy pool)

### Attack Scenarios

#### Scenario 1: Silent Failure → Undefined Behavior
```typescript
// Crypto operation fails
const dek = await generateDEK(); // Returns undefined (shouldn't, but no validation)
const dekRaw = await exportDEK(dek); // Throws error
// Uncaught exception propagates to caller
// Caller may not handle it
// UI shows generic error
// User retries → same error
// User gives up → document never encrypted
```

#### Scenario 2: Partial Encryption
```typescript
const dek = await generateDEK(); // Success
const dekRaw = await exportDEK(dek); // Success
const { nonce, ciphertext, tag } = await encryptWithDEK(plaintext, dek); // Success
const { wrappedDEK, wrapNonce, wrapTag } = await wrapDEK(dekRaw, umk); // FAILS
// Function crashes before returning
// Caller has no encrypted payload
// No cleanup of DEK (still in memory)
```

#### Scenario 3: Wrong Key Length Accepted
```typescript
const umk = new Uint8Array(16); // Wrong length (should be 32)
await encryptDocument(plaintext, umk); // importKey fails
// Error thrown: "Algorithm length doesn't match key length"
// Developer sees cryptic WebCrypto error
// No guidance on what went wrong
```

### Red Team Assessment
**CRITICAL (🔴):** No error handling means:
1. **Developer experience is poor:** Cryptic errors, no actionable messages
2. **Silent failures possible:** Code may return partial data
3. **Resource leaks:** Failed operations don't clean up

**Recommendation:** Add comprehensive error handling:
```typescript
export async function encryptDocument(
  plaintext: Uint8Array,
  umk: Uint8Array
): Promise<EncryptedPayload> {
  try {
    // Input validation (see Finding 2)
    validateInputs(plaintext, umk);
    
    const dek = await generateDEK();
    const dekRaw = await exportDEK(dek);
    
    try {
      const { nonce, ciphertext, tag } = await encryptWithDEK(plaintext, dek);
      const { wrappedDEK, wrapNonce, wrapTag } = await wrapDEK(dekRaw, umk);
      
      return {
        wrappedDEK: new Uint8Array([...wrappedDEK, ...wrapNonce, ...wrapTag]),
        nonce,
        ciphertext,
        tag,
      };
    } finally {
      // Zero DEK (see Finding 3)
      zeroDEK(dekRaw);
    }
  } catch (error) {
    // Wrap cryptic WebCrypto errors
    if (error instanceof DOMException) {
      throw new Error(`Encryption failed: ${error.message}. Check key length and input validity.`);
    }
    throw error;
  }
}
```

---

## Critical Finding 6: WRAPPED DEK FORMAT IS BRITTLE AND UNDOCUMENTED

### Evidence from [encryptDocument.ts](app/client/crypto/encryptDocument.ts#L78-L88):
```typescript
export async function encryptDocument(
  plaintext: Uint8Array,
  umk: Uint8Array
): Promise<EncryptedPayload> {
  // ...
  const { wrappedDEK, wrapNonce, wrapTag } = await wrapDEK(dekRaw, umk);
  
  return {
    wrappedDEK: new Uint8Array([...wrappedDEK, ...wrapNonce, ...wrapTag]),
    //          └─ Concatenation without length prefix or delimiter
    nonce,
    ciphertext,
    tag,
  };
}
```

### Problem: Ambiguous Deserialization

**Concatenation:** `wrappedDEK || wrapNonce || wrapTag`
- `wrappedDEK`: 32 bytes (encrypted DEK)
- `wrapNonce`: 12 bytes (GCM nonce)
- `wrapTag`: 16 bytes (GCM authentication tag)
- **Total:** 60 bytes

**Parsing on decryption:**
```typescript
// How to split the 60 bytes?
const wrappedDEKBytes = payload.wrappedDEK.slice(0, 32);   // Hardcoded
const wrapNonce = payload.wrappedDEK.slice(32, 44);        // Hardcoded
const wrapTag = payload.wrappedDEK.slice(44, 60);          // Hardcoded
```

### Why This is Brittle

1. **No version field:** Cannot change format without breaking existing data
2. **No length prefixes:** Cannot support variable-length ciphertext
3. **Hardcoded offsets:** Cannot extend format
4. **No format documentation:** Developer must reverse-engineer

### Attack Scenarios

#### Scenario 1: Format Evolution Breaks Compatibility
```typescript
// Future change: Upgrade to 256-bit nonce
const wrapNonce = crypto.getRandomValues(new Uint8Array(32)); // Was 12
// Now total is 32 + 32 + 16 = 80 bytes
// Existing code expects 60 bytes
// Deserialization fails or parses wrong fields
```

#### Scenario 2: Length Confusion Attack
```typescript
// Attacker crafts payload with ambiguous boundaries
// If parser doesn't validate total length:
const fakePayload = {
  wrappedDEK: new Uint8Array(50), // Wrong length (should be 60)
  nonce: ...,
  ciphertext: ...,
  tag: ...
};
// Parser tries to slice: wrappedDEK[0:32], nonce[32:44], tag[44:60]
// But payload is only 50 bytes
// Out-of-bounds read → undefined behavior
```

### Red Team Assessment
**HIGH (🟠):** Brittle serialization format creates future compatibility risk and parsing ambiguity.

**Recommendation:** Use a structured format:
```typescript
interface WrappedDEKEnvelope {
  version: number;        // Format version (e.g., 1)
  ciphertext: Uint8Array; // Wrapped DEK
  nonce: Uint8Array;      // GCM nonce
  tag: Uint8Array;        // GCM tag
}

// Serialize with length prefixes
function serializeWrappedDEK(envelope: WrappedDEKEnvelope): Uint8Array {
  // [version:1][ciphertext_len:2][ciphertext][nonce_len:1][nonce][tag_len:1][tag]
  // Or use existing serialization format (CBOR, Protobuf, etc.)
}
```

---

## Critical Finding 7: NO PROTECTION AGAINST KEY REUSE

### Evidence from [umk.ts](app/client/crypto/umk.ts):
```typescript
export function generateUMK(): Uint8Array {
  const umk = new Uint8Array(32);
  crypto.getRandomValues(umk);
  return umk;
}
```

**UMK generation is stateless:**
- No check for existing UMK
- No prevention of multiple UMK generation
- No warning if UMK already exists

### Attack Scenarios

#### Scenario 1: Developer Accidentally Generates Multiple UMKs
```typescript
// User's first session
const umk1 = generateUMK();
storeKey("userUMK", umk1);
encryptDocument(doc1, umk1); // Encrypted with umk1

// User's second session (developer mistake: regenerates UMK)
const umk2 = generateUMK(); // DIFFERENT KEY!
storeKey("userUMK", umk2); // Overwrites umk1
encryptDocument(doc2, umk2); // Encrypted with umk2

// Now:
// - doc1 cannot be decrypted (wrapped with umk1, which is lost)
// - doc2 can be decrypted (wrapped with umk2, which is stored)
// - USER LOSES ACCESS TO doc1 PERMANENTLY
```

#### Scenario 2: UMK Key Reuse Across Documents
```typescript
// Same UMK used for all documents (correct per key model)
encryptDocument(doc1, umk);
encryptDocument(doc2, umk);
encryptDocument(doc3, umk);

// Each document has a fresh DEK (good)
// But all DEKs are wrapped with the same UMK (intended)
// If UMK is compromised, ALL documents are compromised
```

This is by design per key-model.md:
> "Each DEK is wrapped exclusively by the UMK"

But there's no guidance on:
- UMK rotation
- UMK compromise detection
- UMK revocation

### Red Team Assessment
**HIGH (🟠):** No protection against developer mistakes in UMK lifecycle:
1. Accidental regeneration → permanent data loss
2. No UMK rotation → long-lived master key
3. No compromise detection → delayed incident response

**Recommendation:**
1. Add UMK existence check before generation:
   ```typescript
   export function generateUMK(): Uint8Array {
     const existing = retrieveKey("userUMK");
     if (existing) {
       throw new Error("UMK already exists. Use retrieveKey() or explicitly rotate.");
     }
     const umk = new Uint8Array(32);
     crypto.getRandomValues(umk);
     return umk;
   }
   ```

2. Add UMK rotation function:
   ```typescript
   export async function rotateUMK(
     oldUMK: Uint8Array,
     newUMK: Uint8Array,
     wrappedDEKs: Uint8Array[]
   ): Promise<Uint8Array[]> {
     // Unwrap all DEKs with oldUMK
     // Re-wrap all DEKs with newUMK
     // Return new wrappedDEKs
   }
   ```

---

## Critical Finding 8: STORAGE MODULE HAS NO ENCRYPTION OR ACCESS CONTROL

### Evidence from [storage.ts](app/client/crypto/storage.ts):
```typescript
// NOT SECURE PERSISTENCE - in-memory only
const store = new Map<string, Uint8Array>();

export function storeKey(id: string, key: Uint8Array): void {
  store.set(id, key);
}

export function retrieveKey(id: string): Uint8Array | undefined {
  return store.get(id);
}

export function deleteKey(id: string): boolean {
  return store.delete(id);
}
```

### Risks

1. **In-memory only:** Keys lost on page refresh
2. **No persistence:** User must re-enter password on every session
3. **No encryption:** If keys are stored (future), they're plaintext
4. **No access control:** Any code can call `retrieveKey()`
5. **No audit trail:** No logging of key access

### Attack Scenarios

#### Scenario 1: XSS Steals All Keys
```javascript
// Attacker injects script
const stolenKeys = {
  umk: retrieveKey("userUMK"),
  sessionKey: retrieveKey("sessionKey"),
  // ... any other keys
};
exfiltrateToAttacker(stolenKeys);
```

#### Scenario 2: Compromised Dependency Reads Keys
```javascript
// Malicious npm package or supply chain attack
import { retrieveKey } from '../crypto/storage';
const umk = retrieveKey("userUMK");
sendToMaliciousServer(umk);
```

### Red Team Assessment
**HIGH (🟠):** Storage module provides no security:
1. No encryption of stored keys
2. No access control (any code can read)
3. No persistence (usability issue)
4. Comment says "NOT SECURE PERSISTENCE" but doesn't explain mitigation

Per key-model.md:
> "Web: Stored in IndexedDB via WebCrypto-provided non-extractable CryptoKey when supported; otherwise in IndexedDB as an encrypted blob protected by a per-origin random key kept in-memory only"

**Current implementation does not match key model specification.**

**Recommendation:**
1. Implement IndexedDB storage with WebCrypto non-extractable keys
2. Add access control (closure pattern to hide `store`)
3. Add audit logging
4. Document storage security model

---

## High-Risk Finding 9: NO NONCE REUSE PREVENTION

### Evidence from [encryptDocument.ts](app/client/crypto/encryptDocument.ts#L61):
```typescript
const nonce = crypto.getRandomValues(new Uint8Array(12));
```

**Nonce generation is purely random:**
- No counter
- No state tracking
- No duplicate detection
- Relies on CSPRNG uniqueness (probabilistic)

### Why This Matters

**AES-GCM security property:**
> "Never reuse the same nonce with the same key. Nonce reuse breaks confidentiality and integrity."

**Current implementation:**
- Each document uses a **fresh DEK** → Same nonce can be reused across documents (safe)
- Within a document, each encryption operation generates a **random nonce** → Probabilistic uniqueness

**Birthday bound:**
- 96-bit nonce → $2^{48}$ encryptions before 50% collision probability
- For random nonces: ~$2^{32}$ million encryptions needed for concern
- **In practice:** Safe for reasonable document counts

### Why This is Still a Risk

1. **Non-deterministic:** No guarantee of uniqueness
2. **No audit trail:** Cannot detect if nonce was reused
3. **Future-proofing:** If DEK reuse is introduced (bug), nonce reuse becomes catastrophic

### Red Team Assessment
**MEDIUM (🟡):** Current implementation is **probably safe** but relies on probabilistic guarantees.

**Recommendation:** Use deterministic nonce generation:
```typescript
// Option 1: Counter-based (requires state)
let nonceCounter = 0n;
function generateNonce(): Uint8Array {
  const nonce = new Uint8Array(12);
  const counter = nonceCounter++;
  // Encode counter into nonce
  new DataView(nonce.buffer).setBigUint64(4, counter, false);
  return nonce;
}

// Option 2: Hybrid (random prefix + counter)
const randomPrefix = crypto.getRandomValues(new Uint8Array(8));
let nonceCounter = 0;
function generateNonce(): Uint8Array {
  const nonce = new Uint8Array(12);
  nonce.set(randomPrefix.slice(0, 8), 0); // Random prefix
  new DataView(nonce.buffer).setUint32(8, nonceCounter++, false); // Counter suffix
  return nonce;
}
```

**Trade-off:** Random nonces are stateless (simpler); counter-based nonces require state management.

**Verdict:** Current approach is acceptable for Phase-1; recommend migration to counter-based for Phase-2.

---

## High-Risk Finding 10: NO RATE LIMITING OR ABUSE PREVENTION

### Evidence
The crypto module has:
- No rate limiting on encryption operations
- No resource usage tracking
- No maximum operation count
- No cooldown periods

### Attack Scenarios

#### Scenario 1: Resource Exhaustion (DoS)
```javascript
// Attacker calls encryption in tight loop
for (let i = 0; i < 1000000; i++) {
  await encryptDocument(largePlaintext, umk);
}
// CPU pinned at 100%
// Browser tab becomes unresponsive
// User forced to close tab → loses session
```

#### Scenario 2: Memory Exhaustion
```javascript
// Attacker encrypts large documents
const hugePlaintext = new Uint8Array(500 * 1024 * 1024); // 500MB
await encryptDocument(hugePlaintext, umk);
// Browser OOM
// Tab crashes
```

#### Scenario 3: Entropy Pool Depletion
```javascript
// Generate excessive random nonces
for (let i = 0; i < 100000; i++) {
  crypto.getRandomValues(new Uint8Array(1024 * 1024)); // 1MB each
}
// CSPRNG entropy pool depleted (theoretical; modern browsers handle this)
```

### Red Team Assessment
**MEDIUM (🟡):** No abuse prevention allows local DoS:
1. CPU exhaustion
2. Memory exhaustion  
3. Battery drain (mobile)

**Recommendation:**
1. Add rate limiting:
   ```typescript
   const rateLimiter = new RateLimiter({ maxOps: 100, windowMs: 60000 });
   
   export async function encryptDocument(...): Promise<EncryptedPayload> {
     if (!rateLimiter.tryAcquire()) {
       throw new Error("Rate limit exceeded. Try again later.");
     }
     // ...
   }
   ```

2. Add size limits (already recommended in Finding 2)

3. Consider Web Worker offloading:
   ```typescript
   // Offload encryption to Web Worker to avoid blocking UI
   const worker = new Worker('crypto-worker.js');
   worker.postMessage({ plaintext, umk });
   ```

---

## High-Risk Finding 11: TIMING ATTACKS POSSIBLE ON KEY OPERATIONS

### Evidence
No constant-time operations:
- Key comparison: `umk === otherUMK` (JavaScript `===` is not constant-time)
- Array slicing: `.slice()` timing depends on length
- Concatenation: `[...a, ...b]` timing depends on length

### Attack Scenarios

#### Scenario 1: Timing Oracle for UMK Validation
```javascript
// Attacker measures timing of incorrect UMK
const start = performance.now();
try {
  await unwrapDEK(wrappedDEK, wrongUMK); // Fails
} catch (e) {
  const elapsed = performance.now() - start;
  // If elapsed is shorter, first byte of wrongUMK might be correct
  // Iterate through all bytes to recover UMK
}
```

**Note:** This attack requires:
1. Unwrap function to exist (currently missing)
2. Timing resolution sufficient to distinguish single-byte differences
3. Network timing isolation (local attack only)

**Practicality:** Low for browser clients (network jitter, GC pauses), higher for native clients.

### Red Team Assessment
**MEDIUM (🟡):** Timing attacks are **theoretical** for browser clients (too much noise) but **practical** for native/server clients.

**Recommendation:**
1. Use constant-time comparison for keys:
   ```typescript
   function constantTimeEqual(a: Uint8Array, b: Uint8Array): boolean {
     if (a.length !== b.length) return false;
     let diff = 0;
     for (let i = 0; i < a.length; i++) {
       diff |= a[i] ^ b[i];
     }
     return diff === 0;
   }
   ```

2. Add random delay to unwrap operation:
   ```typescript
   await unwrapDEK(wrappedDEK, umk);
   await sleep(Math.random() * 10); // 0-10ms random delay
   ```

3. Document limitation:
   > "Timing attacks are not mitigated in browser clients due to inherent JavaScript/GC timing variability."

---

## High-Risk Finding 12: README IS EMPTY (No Documentation)

### Evidence from [README.md](app/client/crypto/README.md):
```
(The file exists, but is empty)
```

### Impact
1. **No usage examples:** Developers must reverse-engineer
2. **No security guidance:** Developers may misuse APIs
3. **No threat model summary:** Developers unaware of assumptions
4. **No testing instructions:** No guidance on verification

### Developer Footguns (Examples of Predictable Mistakes)

#### Mistake 1: Reusing UMK Across Users
```typescript
// WRONG: Global UMK
const globalUMK = generateUMK();
encryptDocument(user1Doc, globalUMK);
encryptDocument(user2Doc, globalUMK);
// user1 can decrypt user2's document if they get the wrapped DEK
```

#### Mistake 2: Storing UMK in LocalStorage
```typescript
// WRONG: Plaintext storage
localStorage.setItem("umk", JSON.stringify(Array.from(umk)));
// Accessible to any script, persists across sessions
```

#### Mistake 3: Not Zeroizing Inputs
```typescript
// WRONG: Plaintext remains in memory
const plaintext = new Uint8Array(sensitiveData);
await encryptDocument(plaintext, umk);
// plaintext still in memory, not zeroed
```

### Red Team Assessment
**HIGH (🟠):** No documentation guarantees developer mistakes.

**Recommendation:** Write comprehensive README:

```markdown
# Client-Side Cryptography

## Overview
End-to-end encryption using AES-256-GCM with per-document DEKs wrapped by user master key (UMK).

## Security Model
- **Trust boundary:** Client device only
- **Threat model:** Hostile server, compromised network, malicious operators
- **Assumptions:** Honest client code, uncompromised device, secure key storage

## Usage

### First Time Setup
\`\`\`typescript
import { generateUMK, storeKey } from './crypto/umk';
import { encryptDocument } from './crypto/encryptDocument';

// Generate UMK (once per user)
const umk = generateUMK();
storeKey('userUMK', umk);
\`\`\`

### Encrypting a Document
\`\`\`typescript
const plaintext = new TextEncoder().encode("sensitive data");
const encrypted = await encryptDocument(plaintext, umk);
// Send encrypted.ciphertext, encrypted.nonce, encrypted.tag to server
\`\`\`

### CRITICAL: Zeroize Plaintext After Use
\`\`\`typescript
const plaintext = new Uint8Array(data);
try {
  const encrypted = await encryptDocument(plaintext, umk);
  return encrypted;
} finally {
  plaintext.fill(0); // Zero plaintext
}
\`\`\`

## DO NOT
❌ Share UMK across users  
❌ Store UMK in localStorage/sessionStorage  
❌ Reuse DEKs  
❌ Skip input validation  
❌ Assume encryption guarantees deletion  

## Phase-1 Limitations
⚠️ No decryption function (write-only)  
⚠️ No GCM tag verification  
⚠️ No recovery from lost UMK  
⚠️ Browser memory cannot be reliably zeroed  
```

---

## Medium-Risk Finding 13: NO VERSION FIELD IN EncryptedPayload

### Evidence from [encryptDocument.ts](app/client/crypto/encryptDocument.ts#L1-L6):
```typescript
export interface EncryptedPayload {
  wrappedDEK: Uint8Array;
  nonce: Uint8Array;
  ciphertext: Uint8Array;
  tag: Uint8Array;
}
```

**Missing:**
- ❌ Version field
- ❌ Algorithm identifier
- ❌ Key derivation parameters

### Why This Matters

**Future changes:**
1. Upgrade to ChaCha20-Poly1305 → Cannot distinguish from AES-GCM
2. Change nonce size → Parser breaks
3. Add authenticated data → No field to store it

**Without version field:**
- All existing payloads must be assumed to be "version 1"
- Cannot gracefully migrate to new formats
- Must maintain backward compatibility forever

### Red Team Assessment
**MEDIUM (🟡):** Missing version field limits future cryptographic agility.

**Recommendation:**
```typescript
export interface EncryptedPayload {
  version: number;        // Format version (e.g., 1)
  algorithm: string;      // "AES-256-GCM"
  wrappedDEK: Uint8Array;
  nonce: Uint8Array;
  ciphertext: Uint8Array;
  tag: Uint8Array;
}
```

---

## Medium-Risk Finding 14: NO AUTHENTICATED ASSOCIATED DATA (AAD)

### Evidence
Current GCM usage:
```typescript
const encrypted = await crypto.subtle.encrypt(
  { name: "AES-GCM", iv: nonce, tagLength: 128 },
  dek,
  plaintext
);
```

**Missing parameter:** `additionalData`

### What is AAD?

**GCM supports AAD (Additional Authenticated Data):**
- Data that is authenticated but not encrypted
- Binds ciphertext to metadata
- Prevents ciphertext/metadata mismatch attacks

### Attack Scenarios Without AAD

#### Scenario 1: Metadata Swapping
```typescript
// User encrypts two documents
const doc1 = encryptDocument(plaintext1, umk);
const doc2 = encryptDocument(plaintext2, umk);

// Attacker swaps metadata
const malicious = {
  wrappedDEK: doc1.wrappedDEK, // From doc1
  nonce: doc1.nonce,           // From doc1
  ciphertext: doc2.ciphertext, // FROM doc2 (swapped!)
  tag: doc2.tag                // FROM doc2 (swapped!)
};

// Decryption will succeed!
// But plaintext2 is now decrypted with doc1's DEK
// Result: Corrupted plaintext (different key) or wrong document content
```

#### Scenario 2: Ciphertext/User Binding
```typescript
// Attacker copies user1's encrypted document
// Attacker sends it to user2's account
// Server stores it under user2's ID
// user2 decrypts with their UMK → fails (wrong wrappedDEK)
// But if attacker also copies wrappedDEK:
//   user2 unwraps DEK with their UMK → fails
// So this attack doesn't work UNLESS attacker also steals user1's UMK

// However, AAD would prevent even the attempt:
const aad = { userId: "user1", docId: "doc123" };
encryptDocument(plaintext, umk, aad);
// Decryption with different AAD would fail
```

### Red Team Assessment
**MEDIUM (🟡):** Missing AAD weakens binding between ciphertext and metadata.

**Recommendation:**
```typescript
export async function encryptDocument(
  plaintext: Uint8Array,
  umk: Uint8Array,
  metadata: { userId: string; docId: string; timestamp: number }
): Promise<EncryptedPayload> {
  // ...
  const aad = new TextEncoder().encode(JSON.stringify(metadata));
  const encrypted = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: nonce, tagLength: 128, additionalData: aad },
    dek,
    plaintext
  );
  // ...
}
```

---

## Operational Risk Finding 15: NO TESTING OR VALIDATION

### Evidence
```bash
$ find app/client/crypto -name "*test*" -o -name "*spec*"
# NO RESULTS
```

**No tests:**
- ❌ No unit tests
- ❌ No integration tests
- ❌ No encryption/decryption roundtrip tests
- ❌ No input validation tests
- ❌ No error handling tests

### Impact
1. **Cannot verify correctness:** No proof encryption works
2. **Cannot detect regressions:** Changes may break encryption
3. **Cannot validate against test vectors:** No compliance check

### Red Team Assessment
**MEDIUM (🟡):** Untested crypto code is untrustworthy crypto code.

**Recommendation:** Add comprehensive test suite:

```typescript
// tests/encryptDocument.test.ts
import { encryptDocument } from '../encryptDocument';
import { generateUMK } from '../umk';

describe('encryptDocument', () => {
  it('should encrypt and produce valid ciphertext', async () => {
    const plaintext = new Uint8Array([1, 2, 3, 4, 5]);
    const umk = generateUMK();
    const encrypted = await encryptDocument(plaintext, umk);
    
    expect(encrypted.ciphertext).toBeDefined();
    expect(encrypted.nonce.length).toBe(12);
    expect(encrypted.tag.length).toBe(16);
    expect(encrypted.wrappedDEK.length).toBe(60); // 32+12+16
  });
  
  it('should reject empty plaintext', async () => {
    const plaintext = new Uint8Array(0);
    const umk = generateUMK();
    await expect(encryptDocument(plaintext, umk)).rejects.toThrow();
  });
  
  it('should reject wrong UMK length', async () => {
    const plaintext = new Uint8Array([1, 2, 3]);
    const umk = new Uint8Array(16); // Wrong length
    await expect(encryptDocument(plaintext, umk)).rejects.toThrow();
  });
  
  // TODO: Add decryption roundtrip test when decryptDocument() exists
});
```

---

## Operational Risk Finding 16: CSPRNG ENTROPY NOT VALIDATED

### Evidence from [umk.ts](app/client/crypto/umk.ts):
```typescript
crypto.getRandomValues(umk);
```

**No validation:**
- No check that `crypto.getRandomValues` is available
- No check that entropy pool is initialized
- No error handling if CSPRNG fails

### Attack Scenarios

#### Scenario 1: Degraded Entropy (Embedded Systems)
```javascript
// On embedded device with poor entropy source
const umk = generateUMK();
// CSPRNG may produce weak randomness
// UMK is predictable
```

#### Scenario 2: Mocked CSPRNG (Testing Environment)
```javascript
// Developer mocks crypto for testing
crypto.getRandomValues = (arr) => arr.fill(0); // All zeros!
const umk = generateUMK(); // All zeros!
// Production code ships with mock → catastrophic
```

### Red Team Assessment
**MEDIUM (🟡):** No entropy validation allows weak key generation.

**Recommendation:**
```typescript
export function generateUMK(): Uint8Array {
  if (!crypto || !crypto.getRandomValues) {
    throw new Error("Secure random number generator not available");
  }
  
  const umk = new Uint8Array(32);
  crypto.getRandomValues(umk);
  
  // Sanity check: Ensure not all zeros
  if (umk.every(byte => byte === 0)) {
    throw new Error("CSPRNG produced all-zero output; entropy may be compromised");
  }
  
  return umk;
}
```

---

## Operational Risk Finding 17: NO SEPARATION BETWEEN TEST AND PRODUCTION KEYS

### Evidence
The storage module has no environment awareness:
- Same key IDs in test and production
- No namespace separation
- No key tagging (test vs. prod)

### Attack Scenarios

#### Scenario 1: Test Key Used in Production
```typescript
// Developer testing locally
const testUMK = generateUMK();
storeKey("userUMK", testUMK);
encryptDocument(testDoc, testUMK);

// Code ships to production
// Production uses same key ID "userUMK"
// Test key is now in production storage
// Documents encrypted with test key
```

#### Scenario 2: Production Key Leaked in Test Logs
```typescript
// Production code
const umk = retrieveKey("userUMK");
console.log("UMK:", umk); // Debug log
// Log shipped to production
// UMK in production logs
```

### Red Team Assessment
**LOW (informational):** No environment separation increases risk of test/prod confusion.

**Recommendation:**
```typescript
const KEY_PREFIX = process.env.NODE_ENV === 'production' ? 'prod:' : 'test:';

export function storeKey(id: string, key: Uint8Array): void {
  const prefixedId = `${KEY_PREFIX}${id}`;
  store.set(prefixedId, key);
}
```

---

## Operational Risk Finding 18: NO METRICS OR OBSERVABILITY

### Evidence
No logging, no metrics, no telemetry:
- No encryption operation count
- No error rate tracking
- No performance metrics
- No security event logging

### Impact
1. **Cannot detect attacks:** No visibility into abuse
2. **Cannot measure performance:** No optimization data
3. **Cannot debug issues:** No operational context

### Red Team Assessment
**LOW (informational):** No observability limits incident response.

**Recommendation:**
```typescript
// Add structured logging
import { logger } from '../logger';

export async function encryptDocument(...): Promise<EncryptedPayload> {
  const startTime = performance.now();
  try {
    // ... encryption logic ...
    logger.info('encryption_success', {
      plaintextSize: plaintext.length,
      duration: performance.now() - startTime
    });
    return payload;
  } catch (error) {
    logger.error('encryption_failure', {
      error: error.message,
      duration: performance.now() - startTime
    });
    throw error;
  }
}
```

---

## Summary Table: All Findings

| # | Finding | Severity | Status | Recommendation |
|---|---------|----------|--------|----------------|
| 1 | No decryption function | 🔴 CRITICAL | Missing | Implement `decryptDocument()` |
| 2 | No input validation | 🔴 CRITICAL | Missing | Add comprehensive validation |
| 3 | No zeroization | 🔴 CRITICAL | Missing | Explicit zeroing (best-effort) |
| 4 | Extractable DEKs | 🔴 CRITICAL | Design flaw | Use non-extractable CryptoKey |
| 5 | No error handling | 🔴 CRITICAL | Missing | Add try-catch + helpful errors |
| 6 | Brittle serialization | 🟠 HIGH | Design flaw | Versioned format |
| 7 | No key reuse protection | 🟠 HIGH | Missing | UMK lifecycle management |
| 8 | Insecure storage | 🟠 HIGH | Design flaw | IndexedDB + non-extractable keys |
| 9 | No nonce reuse prevention | 🟡 MEDIUM | Acceptable | Consider counter-based |
| 10 | No rate limiting | 🟡 MEDIUM | Missing | Add abuse prevention |
| 11 | Timing attacks possible | 🟡 MEDIUM | Acceptable | Document limitation |
| 12 | No documentation | 🟠 HIGH | Missing | Write comprehensive README |
| 13 | No version field | 🟡 MEDIUM | Missing | Add to EncryptedPayload |
| 14 | No AAD support | 🟡 MEDIUM | Missing | Add metadata binding |
| 15 | No tests | 🟡 MEDIUM | Missing | Comprehensive test suite |
| 16 | No entropy validation | 🟡 MEDIUM | Missing | Validate CSPRNG output |
| 17 | No test/prod separation | ⚪ LOW | Missing | Environment namespacing |
| 18 | No observability | ⚪ LOW | Missing | Logging + metrics |

---

## Prioritized Remediation Plan

### Phase 1: Blockers (Must-Fix Before Production)
1. **Implement decryption** (Finding 1)
2. **Add input validation** (Finding 2)
3. **Add error handling** (Finding 5)
4. **Write documentation** (Finding 12)
5. **Add tests** (Finding 15)

### Phase 2: Security Hardening
6. **Refactor to non-extractable keys** (Finding 4)
7. **Implement IndexedDB storage** (Finding 8)
8. **Add UMK lifecycle management** (Finding 7)
9. **Add versioned serialization** (Finding 6)

### Phase 3: Defense-in-Depth
10. **Add zeroization** (Finding 3) [best-effort]
11. **Add AAD support** (Finding 14)
12. **Add rate limiting** (Finding 10)
13. **Add entropy validation** (Finding 16)

### Phase 4: Operational Excellence
14. **Add observability** (Finding 18)
15. **Add version field** (Finding 13)
16. **Environment separation** (Finding 17)

### Can Defer to Phase-2
- Nonce reuse prevention (Finding 9) [current approach acceptable]
- Timing attack mitigation (Finding 11) [inherent limitation]

---

## Red Team Final Assessment

**Current State:** Prototype-quality code unsuitable for production.

**Core Issues:**
1. **Incomplete:** Write-only encryption (no decryption)
2. **Fragile:** No validation, no error handling
3. **Insecure-by-default:** Extractable keys, no zeroization
4. **Undocumented:** Empty README, no examples
5. **Untested:** No verification of correctness

**Honest Threat Model Alignment:**
- ✅ Client-side encryption → Server cannot access plaintext (IF client is honest)
- ❌ Zeroization → Best-effort only; JavaScript cannot guarantee
- ❌ Non-extractable keys → Current impl uses extractable
- ❌ Secure storage → In-memory Map; does not match key-model.md spec
- ❌ Protection against developer mistakes → No guardrails

**Recommended Action:** Complete Phase 1 remediation before deploying to users. Current code is a foundation, not a production system.

---

*End of Red Team Analysis*
