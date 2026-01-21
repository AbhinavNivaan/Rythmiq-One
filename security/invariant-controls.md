# Invariant Controls Assessment

**Date:** 2 January 2026  
**Scope:** Phase-1 Enforcement Analysis  
**Assessment:** Which stated invariants have actual enforcement mechanisms?

---

## Overview

This document identifies which "invariants" in the threat model have binding enforcement mechanisms vs. which are aspirational statements with no enforcement.

---

## Invariant 1: Master Key Server Prohibition

**Stated:** "No master key or key material with decryption capability shall ever be transmitted to, stored on, or reconstructed by any server component."

### Enforcement Mechanisms Claimed
- Client-side key derivation (Argon2id)
- Key never transmitted
- Key never stored server-side

### Enforcement Mechanisms That Actually Exist
✅ **Key not transmitted:** Architecture does not have a "send key to server" API  
⚠️ **Key not stored:** Depends on honest server code (can be modified)  
❌ **Key not reconstructed:** No mechanism to prevent reconstruction  

### Attack Surface
- **Compromised server code:** Server code can be modified to send key to external server (no detection)
- **Compromised infrastructure:** Admin can modify code without audit trail (logs not tamper-evident)
- **Malicious client:** Client can be modified to send key to attacker's server
- **Memory dumps:** Server memory containing user's key (if somehow obtained) can be exfiltrated

### Red Team Assessment
**Status: WEAK** - Enforcement is architectural (no send-key API), not cryptographic or technical. Hostile code changes can violate this invariant silently.

---

## Invariant 2: Irreversible Master Key Loss

**Stated:** "Loss of the user's master key must result in permanent, irreversible data loss with no server-side recovery mechanism."

### Enforcement Mechanisms Claimed
- No server-side key escrow
- Recovery codes are single-use, high-entropy
- Recovery codes do not enable key recovery, only account recovery

### Enforcement Mechanisms That Actually Exist
❌ **No key escrow:** Depends on code not being modified  
✅ **Recovery codes exist:** Generated and stored (but mechanism has gaps)  
⚠️ **Recovery codes are claimed to be single-use:** Server-side policy (can be bypassed)

### Attack Surface
- **Modified server code:** Code can be changed to add key escrow without user knowledge
- **Hostile admin:** Admin can bypass single-use policy on recovery codes (see Critical Finding 11)
- **Recovery code tampering:** Admin can reset "used" flag or reissue codes (no cryptographic integrity)

### Red Team Assessment
**Status: WEAK** - Irreversibility depends on operational policy (recovery code single-use) that can be changed. No cryptographic enforcement.

---

## Invariant 3: Client-Side Encryption Enforcement (Scoped to Compliant Clients)

**Stated:** "For compliant (honest) clients, all document encryption must occur on the client device before any transmission to server infrastructure."

### Enforcement Mechanisms Claimed
- Encryption happens in JavaScript/native code before transmission
- Server has no encryption API for plaintext
- Server treats uploads as opaque blobs

### Enforcement Mechanisms That Actually Exist
❌ **Client encryption required:** No enforcement; hostile clients can skip encryption  
❌ **Server has no plaintext encryption:** Architecturally true, but code can be modified  
✅ **Server treats uploads as opaque:** Correct; server cannot verify what was encrypted

### Attack Surface
- **Hostile client:** Client can be modified to upload plaintext instead of ciphertext (cannot be detected)
- **Client supply chain attack:** Modified client binary skips encryption (no detection)
- **Modified server code:** Code can be changed to encrypt plaintext before storage (silent violation)

### Red Team Assessment
**Status: BROKEN** - "Compliant clients" are undefined and undetectable. Hostile clients can upload plaintext without detection. The invariant has no binding enforcement.

---

## Invariant 4: Metadata Minimization (No Plaintext in Logs)

**Stated:** "Logs and telemetry do not record document content or plaintext."

### Enforcement Mechanisms Claimed
- Operational policy against logging content
- Logging mistakes can reintroduce plaintext, but this is best-effort avoidance

### Enforcement Mechanisms That Actually Exist
❌ **No plaintext in logs:** Depends on code discipline (can be violated)  
❌ **No monitoring of log content:** No automated check for plaintext in logs  
❌ **No prevention of logging:** Code can be modified to log plaintext without detection

### Attack Surface
- **Code mistakes:** Logging plaintext due to incomplete redaction (caught in testing, but not prevented)
- **Malicious code change:** Intentional log inclusion of plaintext (no audit trail due to non-tamper-evident logs)
- **Configuration drift:** Logging level changed to DEBUG, exposing plaintext (no alert)

### Red Team Assessment
**Status: MISSING** - No enforcement mechanism. Logging is a code discipline issue. Hostile code changes can be applied to capture plaintext in logs without detection.

---

## Invariant 5: Cryptographic Primitives (AES-256-GCM, Argon2id, HKDF-SHA256)

**Stated:** "Server-controlled components must implement AES-256-GCM, Argon2id (min 128 MB, 3 iterations, parallelism 4), HKDF-SHA256."

### Enforcement Mechanisms Claimed
- Implementation standard (code review during development)
- Security patches (infrastructure maintains correct crypto library versions)

### Enforcement Mechanisms That Actually Exist
⚠️ **Server implements AES-256-GCM:** Code can be modified to use weaker cipher  
⚠️ **Argon2id parameters:** Code can use lower parameters (server doesn't validate client parameters)  
❌ **HKDF-SHA256:** Can be replaced with weaker function (no verification)  
❌ **No cryptographic verification:** No way to verify what cipher was used in any given ciphertext

### Attack Surface
- **Code modification:** Cipher algorithm changed to AES-128 or XOR (no audit trail)
- **Library downgrade:** Cryptographic library replaced with weaker one (requires infra compromise)
- **Client-side parameters:** Argon2id can use fewer iterations/memory (server cannot detect)

### Red Team Assessment
**Status: WEAK** - Implementation is assumed, but no runtime verification. Code changes can weaken cryptography without detection. Client-side parameters are not validated.

---

## Invariant 6: User Password UX-Only Composition Prompts

**Stated:** "Password strength prompts are client-side UX safeguards; server cannot enforce or validate password composition."

### Enforcement Mechanisms Claimed
- Client-side prompts (UX only)
- Argon2id parameters mitigate weak passwords
- No server-side validation (by design)

### Enforcement Mechanisms That Actually Exist
✅ **Client prompts exist:** User sees password strength feedback  
⚠️ **Argon2id parameters:** Slow KDF mitigates weak passwords (assuming Argon2id is actually used)  
❌ **No server validation:** Cannot enforce minimum strength

### Attack Surface
- **Hostile client:** Client modified to skip prompts (password security unknown)
- **Weak password:** User ignores prompts; Argon2id is only mitigation (marginal)
- **Modified server:** Could accept weak passwords (no enforcement anyway)

### Red Team Assessment
**Status: WEAK** - UX prompts and KDF cost are only mitigations. A hostile client can reduce password entropy, and the system cannot detect this. Effective password strength is unknown.

---

## Invariant 7: Session Key Ephemeral Lifetime (Best-Effort)

**Stated:** "Session keys receive best-effort memory hygiene; only process termination is relied upon."

### Enforcement Mechanisms Claimed
- Process-per-job model
- Memory zeroization on teardown (best-effort)
- Session timeout (operational setting)

### Enforcement Mechanisms That Actually Exist
⚠️ **Process termination:** Kills memory (but memory dumps may survive)  
❌ **Zeroization:** Best-effort only; crashes prevent zeroization  
❌ **Session timeout:** Configuration setting (can be increased by admin)

### Attack Surface
- **Memory dump on crash:** Session keys remain in crash dump
- **GC prevents zeroization:** Browser GC may prevent memory from being freed before zeroization
- **Admin disables timeout:** Session timeout increased indefinitely (no alert)
- **Malware captures key:** Session key stolen from memory (device compromise)

### Red Team Assessment
**Status: MISSING** - No enforcement of ephemeral lifetime. Session keys can be extracted via memory dumps, GC prevention, or malware. Session timeout is not cryptographically enforced.

---

## Invariant 8: Authentication Timing (Deferred Verification)

**Stated:** "Clarification: Authentication may occur after decryption; no guarantee unauthenticated inputs are rejected before decryption."

### Enforcement Mechanisms Claimed
- Processing engine performs GCM tag verification after decryption
- Forged ciphertext is decrypted and then rejected

### Enforcement Mechanisms That Actually Exist
❌ **Tag verification is mandatory:** Code can skip verification without detection  
❌ **Forged ciphertext rejected:** Code change can remove rejection  
❌ **No monitoring of verification:** No audit of whether verification occurred

### Attack Surface
- **Code modification:** Verification code removed (silent failure)
- **Conditional verification:** Code skips verification in "debug" or "test" mode
- **Forged ciphertext processing:** Attacker sends ciphertext with wrong tag (server decrypts to garbage, but doesn't reject)

### Red Team Assessment
**Status: WEAK** - GCM tag verification is a code implementation detail, not an enforced invariant. Hostile code changes can skip verification without detection.

---

## Invariant 9: No Implicit Persistence (Data Lifecycle)

**Stated:** "Every data artifact must declare TTL or explicit deletion; TTL enforced on primary systems only as policy."

### Enforcement Mechanisms Claimed
- TTL database column on artifacts
- TTL validation on read paths (code check)
- Background deletion job (scheduled)

### Enforcement Mechanisms That Actually Exist
✅ **TTL column exists:** Stored with artifact  
⚠️ **TTL validation on reads:** Code check (can be removed or bypassed)  
❌ **No enforcement on secondary systems:** Replicas/caches/CDNs ignore TTL  
❌ **Physical deletion timing:** Best-effort; no SLA or enforcement

### Attack Surface
- **Code modification:** TTL check removed from read path (no alert)
- **Admin disables validation:** Configuration change bypasses TTL enforcement
- **Replica stale data:** Old replicas serve documents after TTL expiry (no consistency guarantee)
- **Backup retention:** Backups may retain data indefinitely (separate TTL policy)
- **Cache staleness:** CDN may serve stale data beyond TTL (no cache invalidation guarantee)

### Red Team Assessment
**Status: WEAK** - TTL is a policy, not an enforced invariant. Primary-path enforcement can be disabled. Secondary systems have no TTL awareness.

---

## Invariant 10: Plaintext Isolation (Best-Effort)

**Stated:** "Plaintext intended to stay on client devices; server-side plaintext in logs, memory, cache is best-effort avoidance goal."

### Enforcement Mechanisms Claimed
- Client-side encryption before transmission
- Ephemeral per-job worker memory
- Zeroization on teardown

### Enforcement Mechanisms That Actually Exist
❌ **Plaintext not transmitted:** Honest clients don't, but hostile clients can  
⚠️ **Worker isolation:** Process-per-job (can be bypassed by routing or misconfiguration)  
❌ **Zeroization:** Best-effort only; crashes violate this

### Attack Surface
- **Hostile client:** Sends plaintext instead of ciphertext (cannot be detected)
- **Routing error:** Job sent to non-isolated worker (no detection/prevention)
- **GPU routing:** Plaintext placed in GPU VRAM (admitted as possible; no prevention)
- **Crash during processing:** Plaintext remains in memory dump (no zeroization on crash)

### Red Team Assessment
**Status: BROKEN** - Plaintext isolation is aspirational, not enforced. Hostile clients can upload plaintext, and routing errors can expose plaintext beyond isolated workers.

---

## Invariant 11: RAM-Only Processing (Best-Effort)

**Stated:** "Raw uploads to processing engines remain in RAM-only buffers; disk writes not intended except for encrypted results."

### Enforcement Mechanisms Claimed
- In-memory job processing
- No intermediate spilling to disk
- Results only written when encrypted

### Enforcement Mechanisms That Actually Exist
❌ **In-memory processing:** No mechanism to prevent disk writes  
❌ **No spilling to disk:** Depends on code discipline and OS (swap cannot be fully disabled)  
⚠️ **Results encrypted before write:** Intended, but best-effort only (zeroization not enforced)

### Attack Surface
- **Swap enabled:** OS pages processing buffers to swap file (no prevention)
- **Memory pressure:** Kernel decides to spill to disk (system setting; admin can enable swap)
- **Temporary files:** Processing code writes intermediates to /tmp (no enforcement against this)
- **Crash dump:** Process crash creates memory dump on disk

### Red Team Assessment
**Status: MISSING** - RAM-only processing is not enforced. OS-level swap and crash dumps can result in plaintext on disk. No mechanism to prevent this.

---

## Invariant 12: Key Isolation

**Stated:** "No lifecycle stage involves transmission, storage, or processing of master keys."

### Enforcement Mechanisms Claimed
- Architectural (no send-key API)
- Keys derived on client; derivations done per-document

### Enforcement Mechanisms That Actually Exist
✅ **No send-key API:** No explicit key transmission function  
⚠️ **Key derivation on client:** Depends on client code (can be modified)  
❌ **Key storage:** Keys exist in memory during decryption; can be captured

### Attack Surface
- **Client modification:** Modified client sends key to attacker's server (no detection)
- **Memory capture:** Malware extracts key from memory (device compromise)
- **Key logged:** Code logging key material to disk (mistake or intentional; not prevented)
- **Key in crash dump:** Process crash containing key (not wiped)

### Red Team Assessment
**Status: WEAK** - Key isolation is architectural, not cryptographically enforced. Hostile code can violate this. Memory-based key capture is undetectable.

---

## Invariant Summary Table

| Invariant | Type | Enforcement | Status |
|-----------|------|-----------|--------|
| Master Key Server Prohibition | Cryptographic | Architectural + Code Discipline | WEAK |
| Irreversible Key Loss | Data Lifecycle | Operational Policy | WEAK |
| Client-Side Encryption Enforcement | Security Property | None (undetectable) | BROKEN |
| Metadata Minimization | Code Discipline | Code Review | MISSING |
| Cryptographic Primitives | Implementation | Code Review | WEAK |
| Password Strength UX Prompts | UX + KDF | Best-Effort KDF | WEAK |
| Session Key Ephemeral Lifetime | Memory Management | Process Termination | MISSING |
| Authentication Timing | Verification Order | Code Implementation | WEAK |
| No Implicit Persistence | Data Lifecycle | Policy + Scheduled Job | WEAK |
| Plaintext Isolation | Operational Containment | Best-Effort Worker Isolation | BROKEN |
| RAM-Only Processing | Operational Constraint | No Enforcement | MISSING |
| Key Isolation | Architectural | Architectural + Code Discipline | WEAK |

---

## Red Team Position on Invariants

### Categories of Failure

**BROKEN (0 enforcement mechanisms):**
- Client-Side Encryption Enforcement: Cannot verify compliant clients; hostile uploads undetectable
- Plaintext Isolation: Hostile clients can upload plaintext; routing errors can expose plaintext

**MISSING (aspirational; no real mechanism):**
- Metadata Minimization: Logging is code discipline; no automated prevention of plaintext in logs
- Session Key Ephemeral Lifetime: Best-effort only; crashes expose keys; timeout not enforced
- RAM-Only Processing: No mechanism; swap/disk can contain plaintext; no prevention

**WEAK (enforcement exists but is bypassable):**
- Master Key Server Prohibition: Code can be modified to send key; no audit trail
- Irreversible Key Loss: Recovery codes bypass single-use policy (admin can change); no cryptographic binding
- Cryptographic Primitives: Can be downgraded; no runtime verification
- Password Strength: Argon2id can use fewer iterations; server cannot validate
- Authentication Timing: GCM verification is code; can be skipped without detection
- No Implicit Persistence: TTL is policy; can be disabled or ignored by replicas
- Key Isolation: Hostile code can send keys; no detection

### Conclusion

**Only 2 of 12 invariants have any meaningful enforcement:**
1. **No send-key API** (Master Key Server Prohibition) - Architectural, but can be modified
2. **TTL column exists** (No Implicit Persistence) - But enforcement is policy-based and bypassable

**The remaining 10 invariants rely on:**
- Code discipline (best-effort)
- Operational policy (configuration)
- Honest operators (assumption)
- Best-effort memory management (aspirational)

**None of these are cryptographically enforced or automatically verified.**

---

## Recommendations

### For Binding Invariants

Each invariant should be checked against:
1. **Does enforcement exist today?** If no, reclassify as non-binding.
2. **Is enforcement cryptographic or OS-level?** If it's code discipline or policy, admit it can be bypassed.
3. **Is there detection if enforcement fails?** If no, add monitoring or alert.
4. **Can hostile operators bypass enforcement?** If yes, state this explicitly.

### For Phase-2

Enforce invariants cryptographically:
- **Master Key Server Prohibition:** Client-side attestation; verify server does not possess keys
- **Plaintext Isolation:** Server-side encryption verification; reject unhashed uploads
- **No Implicit Persistence:** Immutable TTL enforcement (distributed ledger or external audit)
- **Authentication Timing:** GCM verification before processing; reject forged ciphertext immediately
- **Metadata Minimization:** Encrypted audit logs with external verification

---

*End of Invariant Assessment*
