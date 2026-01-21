# Red Team Critical Findings

**Date:** 2 January 2026  
**Status:** Phase-1 Hardening Pass Complete; Critical Gaps Identified  
**Threat Model Version:** 1.0

---

## Executive Summary

This threat model contains **pervasive enforcement gaps disguised by carefully-worded disclaimers**. The central claim—"security properties are guarantees only when backed by explicit enforcement mechanisms"—is contradicted by extensive use of "best-effort," "intended," "designed to," and "mitigations" language that masks missing enforcement. A hostile administrator, compromised infrastructure, or clever attacker exploiting these gaps can silently violate core properties without detection.

---

## Critical Finding 1: Zero-Knowledge Claim is Conditional on Compliant Clients, But Enforcement is Missing

### The Gap
- **Claim:** "Zero-knowledge for storage, backups, logs, and operators **only for compliant (honest) clients**"
- **Reality:** The system has NO mechanism to detect, enforce, or reject non-compliant (plaintext) uploads
- **Enforcement Missing:** No cryptographic validation of ciphertext; no rejection of plaintext; no kill-switch; no detection

### Why This Breaks the Guarantee
The threat model states:
> "The API Gateway and storage layer treat uploads as opaque blobs; hostile uploads will be stored and processed as provided."

This means:
1. A hostile client uploads plaintext instead of ciphertext
2. API Gateway cannot distinguish plaintext from ciphertext (no keys, no validation)
3. Plaintext is stored, backed up, and logged
4. Zero-knowledge property is SILENTLY violated
5. No detection, no audit trail of the violation, no alert

### Attack Path
```
Hostile Client → Uploads plaintext labeled as "encrypted" envelope
                ↓
API Gateway    → Structural check passes (size/version/format valid)
                ↓
Processing     → Processes plaintext as-is
                ↓
Storage        → Stores plaintext in encrypted storage infrastructure
                ↓
Backups        → Plaintext now in backup systems
                ↓
Operators      → Can read plaintext if they access backups
                ↓
RESULT:        → Zero-knowledge claim violated silently; claim remains in threat model
```

### Red Team Assessment
**CRITICAL:** The zero-knowledge guarantee is conditional on something the system cannot verify or enforce. This is not a guarantee; it's a hope. Treat as unenforceable.

---

## Critical Finding 2: "Best-Effort" Appears 40+ Times; Describes Non-Existent Enforcement

### The Gap
Phrase pattern: "**X is best-effort only**; routing errors, misconfiguration, crashes, or GPU execution may violate this, and there is no Phase-1 detection, enforcement, or kill-switch."

Repeated for:
- RAM-only processing (Stage 4)
- Plaintext zeroization (multiple locations)
- Swap prevention (multiple locations)
- GPU containment (explicit admission: GPU provides no containment)
- Crash-induced plaintext leakage (acknowledged as possible, no mitigation)
- Key isolation (acknowledged as best-effort)
- Memory locking (acknowledged as not guaranteed)

### Why This is Critical
"Best-effort" means:
- No enforcement mechanism exists
- No detection if it fails
- No automatic remediation
- Silent failure is possible and expected

### Attack Path Example: GPU Plaintext Leakage
```
Processing engine routes job to GPU lane (intentionally, due to misconfiguration, or via attacker-triggered load)
                ↓
Plaintext decrypted inside GPU processing
                ↓
GPU driver buffers (outside process boundary, outside "locked memory" scope)
                ↓
GPU VRAM may be pageable or retained after process termination
                ↓
No Phase-1 detection: No mechanism to detect this happened
                ↓
No Phase-1 enforcement: No mechanism to prevent GPU routing
                ↓
No Phase-1 kill-switch: No automatic containment once plaintext is in VRAM
                ↓
RESULT: Plaintext persists in GPU driver buffers; system continues operating as if containment held
```

### Red Team Assessment
**CRITICAL:** "Best-effort" is explicitly acknowledged as unenforceable. This is a confession of missing controls, not a security property. Remove "best-effort" language and replace with honest assessment: "containment does not exist for GPU paths."

---

## Critical Finding 3: TLS Downgrade and Active MITM Are "Possible in Phase-1" (Not Prevented)

### The Gap
From threat model:
> "TLS is only assumed transport plumbing; downgrade and active MITM are possible in Phase-1"
> "Phase-1 does not enforce TLS version pinning or downgrade rejection"
> "Active downgrade and MITM remain possible in Phase-1"

### What This Means
1. Client→Server communication can be downgraded to SSLv3 or TLS 1.0
2. Man-in-the-middle attacker can inject themselves into connection
3. Authentication tokens are NOT protected by TLS (explicitly stated: "TLS provides no confidentiality or integrity guarantee for authentication tokens")
4. Application-layer encryption only

### Attack Path: Token Interception
```
User logs in → Authentication token generated
               ↓
Token transmitted over TLS
               ↓
Attacker performs active MITM (possible in Phase-1)
               ↓
TLS is downgraded to insecure version
               ↓
Token is plaintext on network (application layer has no token encryption)
               ↓
Attacker captures token
               ↓
Attacker uses token to access user's documents
               ↓
RESULT: Zero-knowledge violated; attacker accesses plaintext decryption via stolen token
```

### Why This is Critical
The threat model says "no confidentiality or integrity guarantee (including for authentication tokens) in this document depends on TLS properties."

This means:
- Authentication tokens must be encrypted application-layer
- OR authentication must not depend on token confidentiality
- The threat model does NOT specify what IS done about tokens

### Red Team Assessment
**CRITICAL:** The threat model acknowledges MITM is possible but provides no mechanism to prevent token interception. Tokens are either unencrypted at application layer (critical vulnerability) or this gap is unstated. Demand: What is the token format? Is it encrypted? How is integrity protected?

---

## Critical Finding 4: API Gateway Cannot Detect Plaintext Uploads (Stated Twice, But No Mitigation)

### The Gap
From threat model (stated explicitly twice):
> "The server cannot verify cryptographic correctness of uploads without keys; hostile or modified clients can upload plaintext that will be stored and processed as-is."

and:

> "cryptographic correctness of uploads cannot be verified by the server without keys"

### Why This is a Confession, Not a Guarantee
The system has no way to:
1. Verify AES-256-GCM tag validity
2. Reject plaintext masquerading as ciphertext
3. Detect when a client intentionally disables encryption
4. Alert when plaintext enters the system

### Attack Path: Silent Plaintext Storage
```
Attacker modifies their client code to disable encryption
                ↓
Attacker uploads "document" (actually plaintext) with valid envelope structure
                ↓
API Gateway checks envelope (size/version/format) ✓
                ↓
API Gateway skips GCM tag verification (cannot do so without keys)
                ↓
Plaintext routed to processing engine
                ↓
Processing engine decrypts... plaintext (decryption of plaintext is identity operation, no error)
                ↓
Plaintext processed, stored, backed up
                ↓
Zero-knowledge claim: VIOLATED SILENTLY
                ↓
System continues operating as if no violation occurred
```

### Red Team Assessment
**CRITICAL:** The system is explicitly incapable of detecting plaintext uploads. The claim "zero-knowledge for compliant clients" is unverifiable. Treat as: **System stores whatever clients upload; clients control whether that's ciphertext or plaintext.**

---

## Critical Finding 5: TTL Enforcement is "Policy Only" – Hostile Infrastructure Can Disable It

### The Gap
From threat model:
> "TTL enforcement is a data lifecycle policy on primary read paths and can be bypassed by hostile infrastructure, code changes, or configuration drift."

and:

> "A compromised administrator can bypass isolation."

and:

> "Application layer is NOT trusted for access control; enforcement relies on OS/database boundaries that hostile infra operators can override."

### What This Means
1. TTL enforcement is a code/config policy, not enforced by the OS or database
2. A malicious admin can:
   - Delete TTL checks from code
   - Disable TTL validation via config
   - Modify timestamps to extend TTL
   - Copy data before deletion and hide it
3. Secondary systems (replicas, caches, CDNs, backups) may ignore TTL entirely
4. No monitoring alert is guaranteed (hostile operators can disable monitoring)

### Attack Path: Persistent Access Beyond TTL
```
Processing result generated with 30-day TTL
                ↓
(30 days pass)
                ↓
Malicious admin wants to retain access to this data
                ↓
Admin modifies TTL enforcement code: removes TTL check before read
                ↓
Admin disables monitoring/alerting that would detect expired-but-readable docs
                ↓
Primary storage now serves the document indefinitely
                ↓
Replicas/caches/backups already copied the plaintext (if hostile client uploaded plaintext)
                ↓
RESULT: TTL is unenforceable against hostile infrastructure; data persists indefinitely
```

### Red Team Assessment
**CRITICAL:** TTL is not a deletion guarantee; it's a configuration setting that hostile operators can change. Treat as: **Documents marked with TTL may remain in storage and accessible indefinitely if infrastructure is compromised.**

---

## Critical Finding 6: Audit Logs Are "Not Tamper-Evident" – Hostile Admins Can Erase Evidence

### The Gap
From threat model:
> "Audit logs are operational tools, not security guarantees. Logs are not tamper-evident in Phase-1, and a hostile administrator can modify or delete logs without detection."

### What This Means
1. An admin who breaches the system and exfiltrates plaintext can:
   - Delete the audit log entries for their access
   - Modify timestamps to hide when access occurred
   - Remove evidence of the breach
2. No cryptographic integrity protection on logs
3. No immutable audit trail
4. No detection of log tampering

### Attack Path: Breach + Cover-Up
```
Malicious admin accesses plaintext in storage (via compromised code or misrouting)
                ↓
Admin exfiltrates plaintext to external server
                ↓
Audit log records: "Admin accessed document X at timestamp T"
                ↓
Admin deletes/modifies audit log entry
                ↓
No detection of tampering (logs not tamper-evident)
                ↓
Post-incident investigation: Log shows no suspicious access
                ↓
RESULT: Crime is undetectable; attacker leaves no evidence
```

### Red Team Assessment
**CRITICAL:** Audit logs provide no forensic protection against malicious administrators. They are operational visibility only. Treat as: **Hostile operators can breach the system and eliminate evidence of their actions.**

---

## Critical Finding 7: "Hostile Client Plaintext Uploads" Admittedly Bypass Zero-Knowledge

### The Gap
From threat model (Section 3, Trust Boundaries):
> "Warning: Hostile Client Plaintext Uploads (Phase-1)"
> "The system does not and cannot protect against malicious or modified clients uploading plaintext instead of ciphertext"

This is stated clearly but then immediately used to justify unenforceable guarantees like:
> "Zero-knowledge guarantees (no plaintext in storage, backups, logs, or operators) apply only to compliant clients."

### The Problem
"Compliant clients" is undefined and unenforced:
- No client authentication (only user authentication)
- No code integrity checks on client before upload
- No behavioral analysis to detect non-compliance
- No envelope authentication that proves the client encrypted it
- No rejection of plaintext uploads

Therefore:
- **Practically speaking:** All clients are potentially hostile
- **Technically speaking:** The zero-knowledge guarantee applies to zero clients in practice
- **Legally speaking:** Users cannot be assured their data is not stored as plaintext

### Attack Path: "Compliant" Client Becomes Hostile
```
User downloads official client software
                ↓
Attacker intercepts or modifies client binary (supply chain attack, repo compromise, MITM download)
                ↓
Modified client disables encryption
                ↓
User uploads "document" (actually plaintext)
                ↓
System cannot detect that client is now hostile
                ↓
Plaintext stored, backed up, accessible to operators
                ↓
Zero-knowledge claim: NOT APPLICABLE (client is hostile)
                ↓
User believes data is encrypted per threat model
                ↓
RESULT: Silent plaintext storage; user has no way to know
```

### Red Team Assessment
**CRITICAL:** There is no enforcement mechanism to distinguish "compliant" from "hostile" clients. The zero-knowledge guarantee is therefore a hope, not a guarantee. Reframe as: **The system cannot prevent plaintext uploads; zero-knowledge does not exist in practice.**

---

## Critical Finding 8: GPU Plaintext Containment is Explicitly Admitted as Non-Existent

### The Gap
From threat model (Section 9, Stage 4):
> "GPU lanes are selectable and not cryptographically prevented; any GPU routing (intentional, accidental, or due to misconfiguration) can leak plaintext beyond the CPU containment boundary."

and:

> "GPU workers are not contained; driver/VRAM buffers may be pageable or retained beyond process lifetime."

and:

> "(GPU provides no containment)"

### Why This is Critical
1. Documents can be routed to GPU for processing
2. GPU driver buffers are outside OS memory management
3. Plaintext may persist in VRAM after processing completes
4. No zeroization guarantee on GPU memory
5. **No mechanism to prevent GPU routing**
6. **No mechanism to detect if GPU routing occurred**

### Attack Path: GPU-Assisted Plaintext Exfiltration
```
Attacker (or misconfiguration) routes document processing to GPU
                ↓
Plaintext decrypted into GPU VRAM
                ↓
GPU driver buffers plaintext (beyond process boundary; not zeroized)
                ↓
Processing completes; process terminates
                ↓
Plaintext remains in VRAM (driver manages memory, not OS)
                ↓
Attacker accesses GPU memory directly (DMA, GPU kernel module, etc.)
                ↓
Plaintext exfiltrated from VRAM
                ↓
RESULT: Containment completely bypassed; plaintext leaked despite encryption
```

### Red Team Assessment
**CRITICAL:** GPU routing is selectable, not prevented, and will leak plaintext. Document does not protect against this. Treat as: **GPU processing exposes plaintext; do not route sensitive documents to GPU lanes.**

---

## Critical Finding 9: Key Derivation Argon2id Parameters Are "Intended" But Not "Enforced"

### The Gap
From threat model (Section 5):
> "Derived from user password via Argon2id (minimum: 128 MB memory, 3 iterations, parallelism 4)"

But also:
> "Password handling in the browser cannot guarantee zeroization or confinement; garbage collection is non-deterministic, memory may be paged"

And earlier:
> "The server cannot and does not enforce password composition or minimum strength."

### Why This is Critical
1. The spec says Argon2id parameters are MINIMUM
2. Browser clients are best-effort (GC, paging, no guarantees)
3. Server does NOT validate these parameters
4. Hostile or modified client can use Argon2id(1 iteration, 1 MB, parallelism 1)
5. Server accepts any password-derived key without validation
6. Resulting key is still usable but may be weak

### Attack Path: Weak Derivation Bypass
```
Attacker modifies client to use Argon2id(1 iteration, 8 MB, parallelism 1)
                ↓
Reduced computational cost for password cracking (1000x faster)
                ↓
Server has no way to validate Argon2id parameters
                ↓
Attacker-controlled key derivation is accepted
                ↓
User's password is effectively 1000x weaker than intended
                ↓
RESULT: Password entropy guarantee is violated; attacker can brute-force master key
```

### Red Team Assessment
**CRITICAL:** Server does not enforce or validate key derivation parameters. Clients control entropy of master key. Treat as: **Password security depends on client not being hostile; if client is compromised or modified, Argon2id provides no guarantees.**

---

## Critical Finding 10: Session Timeout is "Operational Protection, Not Cryptographic Guarantee"

### The Gap
From threat model (Section 5, Scenario 4):
> "**Phase-1 Mitigation:** Session timeout (operational protection, not cryptographic guarantee)"

This means:
1. Session timeout is a configuration setting
2. Hostile admin can increase timeout to indefinite
3. No cryptographic mechanism to enforce timeout
4. No automatic re-authentication
5. Malware on device persists across session (acknowledged in threat model)

### Attack Path: Persistent Session After Malware Compromise
```
Attacker achieves malware on user device
                ↓
User has active session with authentication token
                ↓
Malware captures session token/cookie
                ↓
Session timeout configured as 1 hour (operational setting)
                ↓
Malware uses stolen token to access documents indefinitely
                ↓
If admin wants to cover up breach, can:
   - Increase session timeout to 30 days (configuration change)
   - Disable session timeout entirely (configuration change)
   - No audit trail of this change (logs not tamper-evident)
                ↓
RESULT: Session timeout provides no protection against compromise
```

### Red Team Assessment
**CRITICAL:** Session timeout is a configuration setting with no cryptographic enforcement. Hostile operators or malware can bypass it. Treat as: **Session timeout is not a security boundary; assume sessions can persist indefinitely.**

---

## Critical Finding 11: Recovery Codes Have No Attestation – Can Be Replayed or Tampered With

### The Gap
From threat model (Section 5, Scenario 1):
> "Phase-1 Limitation: These controls do not protect against hostile infrastructure or administrators; a malicious operator can bypass rate limits, replay or reissue codes, or tamper with redemption state."

This means:
1. Recovery code rate limiting is server-side policy (no crypto enforcement)
2. Hostile admin can:
   - Remove rate limiting
   - Reissue a single-use code multiple times
   - Replay a consumed code
   - Modify which account the code unlocks
3. No cryptographic commitment to prevent tampering

### Attack Path: Unauthorized Account Recovery
```
User A has recovery codes (securely stored offline)
                ↓
Attacker gains admin access to infrastructure
                ↓
Attacker tampers with recovery code state:
   - Changes account binding: recovery_codes_for[User_A] → recovery_codes_for[Attacker_Account]
   - Or resets the "used" flag on a consumed code
   - Or disables rate limiting
                ↓
Attacker uses User A's recovery code to unlock Attacker's account
                ↓
Attacker gains Attacker's master key (which has Attacker's documents)
                ↓
Wait, this doesn't gain access to User A's data directly...
                ↓
Better attack: Admin reissues a recovered code, authenticates as User A
                ↓
RESULT: Admin can unlock any account using recovery codes without user knowledge
```

### Red Team Assessment
**CRITICAL:** Recovery codes are not cryptographically bound to accounts or users. Hostile operators can tamper with them. Treat as: **Recovery codes provide no protection against infrastructure compromise; admin can unlock any account.**

---

## Critical Finding 12: "Contained in CPU Memory" is Best-Effort; Crashes Leak Plaintext

### The Gap
From threat model (Section 9, Stage 4):
> "Plaintext intermediates are intended to remain in locked, non-pageable memory within that worker; this is best-effort and can be violated by routing errors, misconfiguration, crashes, or GPU execution paths"

and:

> "No Phase-1 detection, enforcement, or kill-switch exists for these failures."

### What This Means
1. Process crash during plaintext processing → plaintext remains in memory dump
2. Memory dump may be stored for post-mortem analysis
3. No automatic deletion of memory dumps (best-effort only)
4. No encryption of memory dumps
5. Admin can access plaintext via memory dump

### Attack Path: Plaintext Exfiltration via Crash Dump
```
Processing engine decrypts plaintext for OCR
                ↓
Attacker (or misconfiguration) triggers crash during processing
                ↓
Crash dump is generated (contains plaintext in memory)
                ↓
Crash dump is stored for debugging purposes
                ↓
Zeroization is best-effort (does not occur if process crashes)
                ↓
Admin extracts crash dumps for analysis
                ↓
Admin reads plaintext from crash dump
                ↓
RESULT: Plaintext exfiltrated via crash dump; no detection
```

### Red Team Assessment
**CRITICAL:** Crashes leak plaintext to memory dumps; no protection against this. Treat as: **Any document passed to processing engines can leak plaintext via crash dumps if system crashes during processing.**

---

## Critical Finding 13: Infrastructure-Level Access Control is "Mitigations, Not Guarantees"

### The Gap
From threat model (Section 11, Storage Access Control):
> "Infrastructure-layer controls (filesystem permissions, database row-level security) provide isolation for honest operators but are not guarantees against malicious administrators."

and:

> "Application layer is NOT trusted for access control; enforcement relies on OS/database boundaries that hostile infra operators can override."

This explicitly states:
1. Filesystem permissions can be changed by root
2. Database privileges can be elevated by DBA
3. Row-level security can be disabled
4. There is no protection against malicious admins

### Attack Path: Cross-User Data Access
```
Malicious DBA wants to access User B's documents
                ↓
DBA uses administrative access to modify database row-level security
                ↓
DBA removes the filter that enforces user isolation
                ↓
DBA queries User B's encrypted blobs directly
                ↓
Encrypted blobs are still encrypted (protection: AES-256-GCM still holds)
                ↓
But DBA accesses blobs User B thought were isolated
                ↓
This violates the stated assumption: "cross-user access denied by default"
                ↓
RESULT: Cross-user isolation is unenforceable against malicious infrastructure
```

### Red Team Assessment
**CRITICAL:** The threat model admits access control cannot protect against malicious operators. Therefore, the only protection against data exfiltration is client-side encryption. If client-side encryption is bypassed (hostile client, compromised client, plaintext upload), there is no second layer of defense.

---

## Critical Finding 14: "Intended," "Designed To," and "Expect" Appear 50+ Times – These Are Not Enforcement

### The Gap
Phrase patterns that appear frequently:
- "is **intended** to use platform secure memory" (no guarantee)
- "**Designed to** prevent…" (no enforcement mechanism)
- "We **expect** operators will…" (assumption, not guarantee)
- "must be **intended** not to persist" (policy statement, not technical control)
- "shall **receive** best-effort memory hygiene" (acknowledged as best-effort)

### Why This Matters
According to the threat model's own stated philosophy:
> "Security properties in this document are guarantees only when backed by explicit enforcement mechanisms."

Yet the threat model is full of statements like:
> "plaintext is **intended** to exist only transiently in RAM and **be zeroed promptly**"

"Intended to be zeroed" is NOT "is zeroed." It's a design goal, not a guarantee. Under the threat model's own standard, this should not be stated as a security property.

### Examples of Non-Enforced "Intentions"
| Claim | Enforcement |
|-------|------------|
| Plaintext is intended to be ephemeral | None; best-effort only |
| Plaintext is intended to be zeroed | None; crashes violate this |
| Swap is intended to be disabled | OS configuration; admin can enable |
| Non-pageable memory is intended | OS/allocator decision; no enforcement |
| Plaintext is intended not to be logged | No audit of what's logged; mistakes happen |
| GPU lanes are intended for non-sensitive data only | No mechanism to prevent GPU routing |
| Recovery codes are intended to be single-use | Server-side policy; admin can change |

### Red Team Assessment
**CRITICAL:** The threat model uses "intended," "designed to," and "expected" as if they are enforcement mechanisms. They are not. Replace with honest language: "There is no mechanism to enforce this property; it is aspirational only."

---

## Critical Finding 15: No Enforcement of "Locked, Non-Pageable Memory" on CPU Workers

### The Gap
From threat model (Section 9, Stage 4):
> "CPU workers aim to use per-job isolated processes with locked, non-pageable memory"

and:

> "locked, non-pageable memory with swap disabled and to zero buffers immediately after use"

### Why This is Critical
1. **"Aim to use"** = "attempt but don't guarantee"
2. **Memory locking requires OS support:** Different on Linux (mlock), macOS (mlock), Windows (VirtualLock)
3. **Swap disabling is system-wide or per-process:** Admin can enable swap globally
4. **No mechanism to verify locking succeeded:** Code can call mlock() and fail silently; locked flag may be false
5. **No monitoring of actual memory state:** No periodic verification that locked memory is actually locked

### Attack Path: Plaintext Swapped to Disk
```
Processing worker intends to allocate locked, non-pageable memory
                ↓
Worker calls mlock(ptr, size) to lock memory
                ↓
mlock() call fails due to RLIMIT_MEMLOCK limit (admin can set to 0)
                ↓
Memory allocation remains but is NOT locked
                ↓
No error is thrown; code continues as if lock succeeded
                ↓
Swap is enabled on system
                ↓
Under memory pressure, OS pages locked-but-not-really memory to disk
                ↓
Plaintext is now in swap file (unencrypted)
                ↓
Admin can read swap file
                ↓
RESULT: Plaintext leaked to disk; system does not detect failure
```

### Red Team Assessment
**CRITICAL:** Memory locking is a best-effort OS feature; there is no guarantee it succeeds. No monitoring of actual lock status. Treat as: **Plaintext can be swapped to disk; this is possible and undetected.**

---

## Critical Finding 16: "Browser Cannot Guarantee Non-Pageable Memory" – Zero-Knowledge is Impossible for Web Clients

### The Gap
From threat model (Section 4, Ephemeral data):
> "Browser clients cannot guarantee non-pageable memory; zeroization is best-effort and subject to GC and paging."

### Why This Invalidates the Zero-Knowledge Guarantee
For browser clients:
1. Master key decryption occurs in JavaScript
2. JavaScript execution environment has non-deterministic GC
3. Memory may be paged to disk by the OS
4. Browser has no API to lock memory
5. Page files on user's device are unencrypted (or encrypted with OS key)
6. Therefore, master key MAY be paged to disk in plaintext

### Attack Path: Master Key in Page File
```
User accesses Rythmiq One in browser
                ↓
Master key derived from password (Argon2id)
                ↓
Master key stored in JavaScript variable in memory
                ↓
Browser runs garbage collection (non-deterministic timing)
                ↓
Master key is not in a local scope that GC can collect (global or closure)
                ↓
OS pages memory containing master key to disk (page file)
                ↓
Page file is unencrypted or encrypted with OS login password only
                ↓
Attacker with physical access can read page file
                ↓
Master key extracted from page file
                ↓
Attacker can decrypt all user's documents
                ↓
RESULT: Zero-knowledge is impossible for browser clients (master key is paged to disk)
```

### Red Team Assessment
**CRITICAL:** Zero-knowledge is technically impossible for browser clients due to OS paging. The threat model acknowledges this ("subject to paging") but still claims zero-knowledge applies. This is false. Either:
1. Withdraw zero-knowledge claim for browser clients, OR
2. Provide mechanism to prevent paging (not currently done)

---

## Critical Finding 17: Monitoring and Alerting Depend on Admin Not Disabling It

### The Gap
From threat model (Section 11):
> "Monitoring is configured to alert on expired-but-readable blobs on primaries, but hostile operators can disable or alter monitoring."

and:

> "Monitoring detects and alerts on expired-but-not-blocked documents on primaries"

### Why This is Critical
1. Alerting is an operational best practice, not a security control
2. If admin disables monitoring, violations go undetected
3. No cryptographic commitment to monitoring state
4. No external auditor ensuring monitoring is active
5. No alerting on monitoring being disabled

### Attack Path: Silent TTL Bypass
```
Admin wants to access expired processing results
                ↓
Admin disables TTL enforcement code
                ↓
Admin disables monitoring/alerting for expired-but-readable documents
                ↓
Admin accesses expired data (no alert)
                ↓
Admin re-enables monitoring (if they remember)
                ↓
No alert for monitoring being disabled
                ↓
RESULT: TTL violation is completely undetected
```

### Red Team Assessment
**CRITICAL:** Monitoring provides no protection against malicious operators. It's an operational visibility tool for honest infrastructure. Treat as: **Assume monitoring is disabled or tampered with; rely only on cryptographic controls.**

---

## Critical Finding 18: GCM Tag Verification Can Be Deferred or Skipped

### The Gap
From threat model (Section 9, Stage 3):
> "Cryptographic authenticity (AES-256-GCM tag verification) is performed only at the processing engine after decryption"

and:

> "Processing engine verifies authentication after decryption"

### Why This is Critical
1. **Deferred verification:** Tag checked AFTER decryption, not before
2. **Decryption of forged ciphertext is allowed:** Malformed GCM tags can be decrypted
3. **No guarantee tag verification occurs:** Processing engine can skip verification
4. **No audit trail if verification is skipped:** Code change is undetected

### Attack Path: Forged Ciphertext Processing
```
Attacker creates forged AES-256-GCM ciphertext (wrong tag)
                ↓
Attacker sends to API Gateway
                ↓
API Gateway skips GCM verification (correct; it doesn't have keys)
                ↓
Processing engine receives forged ciphertext
                ↓
Processing engine decrypts (decryption is deterministic; forgery decrypts to garbage)
                ↓
Code is supposed to verify GCM tag AFTER decryption and reject if invalid
                ↓
But what if developer comment says "skip verification for debugging"?
                ↓
Processing engine now accepts any ciphertext (valid or forged)
                ↓
Attacker can craft ciphertext that decrypts to specific plaintext
                ↓
RESULT: Integrity checking can be bypassed by code change; no audit trail
```

### Red Team Assessment
**CRITICAL:** GCM tag verification is not performed before decryption, so forged ciphertext is decrypted. If tag verification code is removed or skipped, no alert occurs. Threat model should state: "Integrity cannot be verified until after decryption; forged ciphertext will be processed."

---

## Critical Finding 19: "Phase-1 Access Control" is Admitted as Less Than Ideal

### The Gap
From threat model (Section 3, Storage Infrastructure):
> "**Phase-1 Access Control:** Infrastructure controls are mitigations, not guarantees. Per-user storage ownership is enforced at the infrastructure layer (filesystem permissions, database row-level security) for honest operators, but a compromised administrator can bypass isolation."

### What This Means
The word "**Phase-1**" prefix on "Access Control" is a tacit admission:
1. These controls are temporary
2. Better controls are expected in Phase-2
3. Phase-1 controls are known to be weak
4. The team is aware of gaps

But the question is: **What protections EXIST today?** The threat model says:
- Mitigations: Filesystem permissions, DB row-level security
- Against: Honest operators only
- Weakness: Compromised admin bypasses

So today, there is no cryptographic enforcement of access control. Client-side encryption is the only defense, and it requires clients to be honest (see Critical Finding 7).

### Red Team Assessment
**CRITICAL:** "Phase-1" is a label, not an excuse. If Phase-1 controls are weak, state this explicitly in the executive summary. Do not bury weakness in detailed threat model sections. Current posture: **Access control relies on honest operators; no cryptographic enforcement.**

---

## Critical Finding 20: Encryption Standard is "Expected" Not "Enforced"

### The Gap
From threat model (Section 4, Data Classification):
> "AES-256-GCM minimum (**expected** for compliant clients; the server cannot verify cryptographic correctness of uploads without keys, and hostile clients may store plaintext that does not meet this standard)"

### Why This is Critical
1. **Expected ≠ Enforced**
2. Client can use AES-128-GCM (weaker)
3. Client can use XOR cipher (no security)
4. Client can upload plaintext with AES wrapper (fake encryption)
5. Server cannot detect any of this

### Attack Path: Weak Encryption
```
Attacker modifies client to use AES-128-GCM instead of AES-256-GCM
                ↓
Attacker uploads "document" with AES-128 ciphertext
                ↓
API Gateway accepts (structural check only)
                ↓
Processing engine decrypts with user's key (engine does not know client used weak cipher)
                ↓
Documents encrypted with weak cipher remain stored
                ↓
RESULT: System accepts weaker encryption without detection
```

### Red Team Assessment
**CRITICAL:** Encryption standard is not enforced. Server accepts whatever clients send. Threat model claims AES-256-GCM but cannot verify it. Treat as: **Effective encryption standard is unknown; assume weaker cipher may be in use.**

---

## Critical Finding 21: Session Token Format is Undefined

### The Gap
From threat model: The token format, encryption, and authentication mechanism are NOT specified.

Mentions of "authentication tokens":
- "TLS does not prevent server from...receiving plaintext from hostile clients"
- "no confidentiality or integrity guarantee (including for authentication tokens) in this document depends on TLS properties"
- "Network transport is treated as deployment plumbing under standard CA assumptions; no confidentiality or integrity guarantees (including for authentication tokens) rely on it."

### Why This is Critical
1. Token format not specified → Don't know what the token is
2. Token security not described → Don't know how it's protected
3. Token lifetime not specified → Don't know how long sessions last
4. Token binding not specified → Don't know if token is bound to device/IP
5. "no confidentiality guarantee for tokens" → Tokens may be plaintext

### Red Team Assessment
**CRITICAL:** Authentication token mechanism is completely unspecified in threat model. This is a critical gap. Demand: Token format, encryption, integrity protection, lifetime, binding, and revocation mechanism must be explicitly specified.

---

## Critical Finding 22: "Compliant Clients" are Undefined – How to Distinguish Honest from Hostile?

### The Gap
The threat model uses "compliant clients" 10+ times but never defines:
1. What makes a client "compliant"?
2. How does the server detect non-compliance?
3. What happens if a client is detected as non-compliant?
4. Can a client become non-compliant after initial upload?
5. Is there a whitelist of known compliant clients?

### Why This is Critical
Without a definition, "compliant clients" is meaningless. The threat model could claim:
- "Compliant clients use AES-256" (but cannot verify)
- "Compliant clients enable zeroization" (but cannot verify)
- "Compliant clients do not leak keys" (but cannot verify)

Since the server cannot verify any of these, the term is useless.

### Red Team Assessment
**CRITICAL:** Define "compliant client" or remove the term. If definition requires client attestation, state that. If server cannot detect non-compliance, say so. Current state: Compliant client is undefined, making the associated guarantees unverifiable.

---

## Summary of Critical Gaps

| Finding | Enforcement | Status |
|---------|-----------|--------|
| Zero-knowledge for compliant clients | Cannot verify compliance | BROKEN |
| Best-effort plaintext containment | No detection, enforcement, or kill-switch | MISSING |
| TLS downgrade protection | Not enforced; MITM possible | MISSING |
| API Gateway plaintext detection | Explicitly impossible | MISSING |
| TTL enforcement | Policy only; can be disabled | WEAK |
| Audit log integrity | Tamper-evident protection missing | MISSING |
| Hostile client detection | No mechanism | MISSING |
| GPU containment | Explicitly absent | MISSING |
| Key derivation parameters | Server cannot validate | WEAK |
| Session timeout | Configuration setting; can be disabled | WEAK |
| Recovery code integrity | No cryptographic binding | WEAK |
| Crash plaintext containment | No zeroization on crash | MISSING |
| Access control (all levels) | Honest operators only; no cryptographic enforcement | WEAK |
| "Intended" / "designed to" statements | Not enforcement mechanisms | MISCLASSIFIED |
| Locked memory guarantees | Best-effort OS feature; no verification | WEAK |
| Browser memory containment | Impossible due to paging | IMPOSSIBLE |
| Monitoring effectiveness | Can be disabled by admin | WEAK |
| GCM tag verification timing | Deferred to post-decryption | WEAK |
| Encryption standard enforcement | Cannot verify client-side | WEAK |
| Session token security | Completely unspecified | MISSING |

---

## Recommendations for Red Team

### Immediate Actions (Treat as Vulnerabilities)

1. **Define enforcement mechanisms for all security claims.**
   - Replace "intended," "designed to," "expected" with actual mechanisms
   - OR explicitly state claim is non-binding

2. **Specify session token format and security.**
   - Token encryption algorithm
   - Token integrity protection mechanism
   - Token lifetime and binding policy

3. **Define "compliant client" or remove the term.**
   - If attestation required, specify mechanism
   - If undetectable, admit zero-knowledge applies to zero clients in practice

4. **Remove "best-effort" from binding guarantees.**
   - Either enforce or reclassify as non-binding
   - Add detection/kill-switch if possible

5. **Add cryptographic enforcement to TLS.**
   - Enforce minimum TLS version (TLS 1.3 only)
   - Implement certificate pinning even for browsers (via service worker)
   - OR admit MITM is possible and provide application-layer token encryption

### Phase-2 Requirements (If Deferred)

1. **Cryptographic audit logs** (tamper-evident, immutable)
2. **GPU containment** (isolation or rejection of GPU-routable jobs)
3. **Client attestation** (verify client code before accepting encryption)
4. **Synchronized deletion** (replicas/caches/backups respect TTL)
5. **Monitoring immutability** (cannot be disabled without cryptographic alert)
6. **Memory isolation verification** (periodic checks that locked memory is actually locked)

---

## Red Team Position

**The threat model is written as if many controls exist when they do not.** The extensive use of "best-effort," "intended," and "Phase-1 limitation" language obscures the reality that:

1. The system cannot detect plaintext uploads (hostile client uploads are undetectable)
2. The system cannot prevent TTL bypass (hostile admin can change TTL)
3. The system cannot prevent audit tampering (logs are not tamper-evident)
4. The system cannot prevent GPU routing (plaintext will leak to VRAM)
5. The system cannot enforce session timeout (tokens have no cryptographic expiry)
6. The system cannot verify client encryption (server cannot tell if plaintext was uploaded)

**The guarantee that should be made:** "Client-side encryption with key kept on client device prevents server from accessing plaintext, IF the client is honest and not compromised."

**The guarantee that should NOT be made:** "Zero-knowledge architecture prevents plaintext storage," because the system cannot enforce or detect compliance.

---

*End of Red Team Analysis*
