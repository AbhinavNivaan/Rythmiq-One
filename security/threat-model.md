# Threat Model: Rythmiq One

**Version:** 1.0  
**Date:** 2 January 2026  
**Status:** Active

---

## 1. Enforcement Philosophy (Phase-1)

Security properties in this document are guarantees only when backed by explicit enforcement mechanisms. Invariants without enforcement are treated as non-existent.

**Enforcement Requirement:** A security claim is valid if and only if an enforcement mechanism exists.

**Allowed Enforcement Categories:**

1. **OS / Process Isolation**  
   Operating system boundaries, process separation, container isolation.

2. **Runtime Memory Controls**  
   Memory zeroing, swap prevention, memory access restrictions.

3. **Infrastructure-Level Access Controls**  
   Network segmentation, authentication layers, privilege restrictions.

4. **Explicit Protocol Rejection**  
   Rejection of non-compliant requests (unauthenticated payloads). TLS is only assumed transport plumbing; downgrade and active MITM are possible in Phase-1, and TLS provides no confidentiality or integrity guarantee for authentication tokens.

Claims without enforcement from these categories are excluded from this threat model.

---

## 2. System Overview

Rythmiq One is a zero-knowledge document processing system where zero-knowledge is scoped to storage, backups, logs, and operators **only for compliant (honest) clients**, and containment is best-effort only. Documents are expected to be encrypted using user-controlled keys before transmission to the server infrastructure. Storage and operators are intended not to possess or persist decryption keys or plaintext for compliant clients, but routing errors or GPU usage may violate containment and there is no Phase-1 detection, enforcement, or kill-switch. Cryptographic correctness of uploads cannot be verified by the server without keys; hostile or modified clients can upload plaintext that will be stored and processed as-is. For document transformation, the server performs best-effort ephemeral, in-memory decryption inside isolated workers; plaintext is intended to exist only transiently in RAM and be zeroed promptly, but routing errors, GPU execution, and crashes can retain plaintext with no Phase-1 detection, enforcement, or kill-switch.

The architecture consists of client-side components (browser-based encryption engine), API gateway (authentication and routing), processing engines (CPU and GPU lanes with per-job ephemeral in-memory decryption), and storage infrastructure. All components interact through well-defined trust boundaries: the server infrastructure is intended not to persist or expose decryption keys or plaintext to storage, backups, logs, or operators; transient plaintext is intended to exist only inside isolated worker memory during processing on a best-effort basis, and routing errors, GPU execution, or crashes may violate this with no Phase-1 detection, enforcement, or kill-switch.

---

## 3. Trust Boundaries

### Client Trust Domain
- **Trusts:** User's device hardware, browser sandbox, client-side JavaScript execution environment, user's key management practices
- **Trusted by:** Nothing external; the client is the root of trust
- **Boundary enforcement:** All encryption/decryption operations occur within this boundary

### API Gateway
- **Trusts:** Assumed platform TLS termination (downgrade/MITM possible; transport-only plumbing), authentication tokens, envelope structure (size/version)
- **Trusted by:** Client (for routing only), Processing engines (for job orchestration)
- **Boundary enforcement:** Performs structural envelope validation only (format/size/version); holds no keys and does not validate ciphertext correctness

### Processing Engines (CPU/GPU)
- **Trusts:** API Gateway for authorization, envelope structure, and routing
- **Trusted by:** API Gateway for job completion signals
- **Boundary enforcement (best-effort):** CPU workers aim to use per-job isolated processes with locked, non-pageable memory; routing errors, misconfiguration, or GPU paths can bypass containment, and plaintext may reside in GPU-controlled memory. Plaintext is intended to be transient and zeroed on teardown for compliant clients, but GPU lanes and failures can retain plaintext. No Phase-1 detection, enforcement, or kill-switch exists for routing mistakes or GPU leakage.

### Storage Infrastructure
- **Trusts:** Infrastructure-level ownership isolation, encrypted data integrity
- **Trusted by:** All components for persistence
- **Boundary enforcement:** Stores only encrypted blobs; no semantic understanding of content
- **Phase-1 Access Control:** Infrastructure controls are mitigations, not guarantees. Per-user storage ownership is enforced at the infrastructure layer (filesystem permissions, database row-level security) for honest operators, but a compromised administrator can bypass isolation. The application layer is NOT trusted for cross-user access prevention.

### Network Layer
- **Trusts:** Platform-provided TLS/HTTPS infrastructure and certificate authorities as deployment assumptions (downgradeable in Phase-1; active MITM viable)
- **Trusted by:** All components for transport only; confidentiality/integrity claims (including authentication tokens) do not rely on TLS
- **Boundary enforcement:** Assumed TLS may reduce passive risk when negotiated, but downgrade and active MITM are possible in Phase-1. TLS does not prevent server from seeing encrypted payloads or from receiving plaintext from hostile clients masquerading as ciphertext.

### Warning: Hostile Client Plaintext Uploads (Phase-1)
- The system does not and cannot protect against malicious or modified clients uploading plaintext instead of ciphertext; cryptographic correctness of uploads cannot be verified without keys.
- Zero-knowledge guarantees (no plaintext in storage, backups, logs, or operators) apply only to compliant clients. Hostile clients may cause storage, logging, and backups to contain plaintext they submit.
- The API Gateway and storage layer treat uploads as opaque blobs; hostile uploads will be stored and processed as provided.

---

## 4. Data Classification

### Plaintext
**Permitted locations (best-effort containment):**
- User's client device (browser memory, local storage with user consent)
- User's clipboard (temporarily, during copy operations)
- Client-side processing threads
- Server processing workers on CPU lanes intend to keep plaintext in per-job RAM only with locked, non-pageable allocations and immediate zeroing; this is best-effort and can be violated by routing errors, misconfiguration, or GPU execution paths (which may retain plaintext in driver/VRAM buffers). No Phase-1 detection, enforcement, or kill-switch exists for these failures.

**Prohibited locations (compliant clients; best-effort only):**
- Server memory outside per-job isolated workers (API gateway, shared services, schedulers) is not intended to hold plaintext, but routing errors or misconfiguration may violate this.
- Server storage (databases, file systems, caches) is not intended to hold plaintext; hostile clients and misconfiguration can place plaintext there.
- Server logs or monitoring systems are not intended to capture plaintext; logging mistakes or misrouting can violate this.
- Network transit in plaintext form is not intended; hostile clients can still send plaintext.
- Containment is best-effort only; routing errors or GPU usage may violate it, and there is no Phase-1 detection, enforcement, or kill-switch to stop or scrub such exposures.

### Encrypted-at-Rest
**Data types:**
- User documents (encrypted with user's master key)
- Processing results (encrypted with same or derived keys)
- Metadata envelopes (may contain encrypted indexes)

**Storage locations:**
- Server storage infrastructure
- Backup systems
- Content delivery networks (if applicable)

**Encryption standard:** AES-256-GCM minimum (expected for compliant clients; the server cannot verify cryptographic correctness of uploads without keys, and hostile clients may store plaintext that does not meet this standard)

### Encrypted-in-Transit
**Posture:**
- TLS is an assumed transport mechanism provided by the deployment platform. Phase-1 does not enforce TLS version pinning or downgrade rejection; active downgrade and MITM remain possible. When strong TLS is negotiated, it only reduces passive risk; no confidentiality or integrity guarantee (including for authentication tokens) in this document depends on TLS properties.
- Perfect Forward Secrecy (PFS) is opportunistic only when the negotiated TLS version supports it; not enforced.
- Certificate pinning is recommended for native clients; browsers lack enforceable pinning in this model.

**Scope:**
- All API calls between client and API gateway
- Internal service-to-service communication
- Database connections

### Ephemeral (RAM-Only)
**Data types:**
- Decrypted documents during client-side processing
- User's master key during active session
- Derived keys for specific operations
- Plaintext OCR results before re-encryption

**Constraints (environment-specific, best-effort only):**
- Plaintext lifetime target: duration of a single cryptographic operation (< 100 milliseconds per operation; not enforced)
- Server processing workers on CPU lanes intend to keep plaintext in locked, non-pageable memory with swap disabled and to zero buffers immediately after use; routing errors, misconfiguration, or GPU execution paths can violate this, and GPU/driver buffers may retain plaintext.
- Native mobile/desktop clients attempt to use platform secure memory/OS key APIs; swap/pagefile control may not be available or reliable.
- Browser clients cannot guarantee non-pageable memory; zeroization is best-effort and subject to GC and paging.
- Zeroization on completion and on error paths is intended but best-effort only; misrouting, crashes, or GPU execution may leave plaintext resident.
- Cleared on session termination or timeout (best-effort)
- No swap/page file persistence is an operational intent for server processing workers; clients are best-effort where OS allows.

---

## 4. Key Management Model

### Key Creation
**Master Key:**
- Generated client-side using Web Crypto API or equivalent
- Derived from user password via Argon2id (minimum: 128 MB memory, 3 iterations, parallelism 4)
- Entropy source: CSPRNG (Cryptographically Secure Pseudo-Random Number Generator)
- Key length: 256 bits minimum

**Password Handling (Phase-1):**
- Browser clients: best-effort only. Password handling in the browser cannot guarantee zeroization or confinement; garbage collection is non-deterministic, memory may be paged, and isolation depends on the browser runtime. Workers and input isolation reduce exposure but are not guarantees.
- Native or server-controlled environments (where applicable): stronger handling applies only when using platform credential APIs/secure input paths and isolated processes without shared memory; passwords are intended to be zeroed immediately after derivation, but crashes or misconfiguration can defeat this.
- Password input is intended to use platform dialogs/password managers or isolated workers with no DOM/main-thread access; hostile infrastructure or client modifications can bypass this intent.
- Password buffers are intended to be zeroed after Argon2id derivation; browsers cannot guarantee zeroization due to GC and paging. No password caching or persistence across sessions unless explicitly encrypted with a derived key.

**Derived Keys:**
- Document-specific keys generated via HKDF-SHA256
- Separate keys for different document operations (storage, processing, sharing)
- Context binding: includes document ID, operation type, timestamp

### Storage
**Client-Side:**
- Master key encrypted with password-derived key (stored in browser IndexedDB with user consent)
- Alternative: hardware security module (HSM) or platform keychain if available
- Session keys kept only in volatile memory

**Server-Side:**
- No master keys stored under any circumstance
- No derived keys with decryption capability stored
- Encrypted key recovery blobs (optional, encrypted with user's recovery key) stored for account recovery

### Key Loss Scenarios

**Scenario 1: User forgets password**
- **Result:** Permanent data loss unless recovery codes are used
- **Phase-1 User Safety Feature (policy only):** User-controlled recovery codes generated at account creation; hostile infrastructure or configuration changes can bypass, replay, or tamper with them.
   - **Posture (user safety feature):** Codes are generated with high entropy (CSPRNG) and intended to be single-use with rate limiting, but hostile infrastructure or configuration changes can bypass, replay, or tamper with them.
  - **Phase-1 Limitation:** Screenshot prevention NOT enforced (user responsible for secure storage)
  - **Phase-1 Limitation:** No mandatory rotation schedule (user may retain codes indefinitely)
   - **Phase-1 Limitation:** These controls do not protect against hostile infrastructure or administrators; a malicious operator can bypass rate limits, replay or reissue codes, or tamper with redemption state.
- **Design position:** No server-side password reset; no key escrow; recovery codes are availability conveniences, not cryptographic security boundaries and are bypassable by hostile infrastructure

**Scenario 2: Device compromise before key export**
- **Result:** User cannot access documents from new device
- **Mitigation:** Multiple device enrollment during setup; explicit key export workflow
- **Design position:** Usability burden on user; no server-side backup

**Scenario 3: Recovery code loss**
- **Result:** Permanent data loss if password also forgotten (recovery codes are sole account recovery mechanism)
- **Mitigation:** Explicit warnings during account creation; multi-device redundancy; user responsible for secure offline storage
- **Design position:** Security over availability; user bears responsibility; recovery codes are weaker than primary authentication

**Scenario 4: Malware captures key**
- **Result:** Attacker gains access to user's documents
- **Phase-1 Mitigation:** Session timeout (operational protection, not cryptographic guarantee)
- **Phase-1 Limitation:** No automatic key rotation mechanism; user must manually re-encrypt documents with new key after suspected compromise
- **Phase-1 Reality:** Compromised client devices may leak plaintext locally. Once a client device is compromised, the zero-knowledge property breaks for that user's session, and no server-side mechanism can prevent local plaintext disclosure.
- **Future Mitigations (Phase-2, Non-Enforced):** Anomaly detection on key usage patterns and server-side device integrity checks may be added to reduce compromise window detection time, but will not prevent plaintext leakage if device is truly compromised.
- **Design position:** Client-side security is user's responsibility; we provide tools but cannot prevent client-side compromise

---

## 6. Adversary Models

### Adversary 1: Curious Server
**Profile:** System administrator, cloud provider employee, or attacker with server infrastructure access

**Capabilities:**
- Read all encrypted data in storage
- Inspect all encrypted payloads in transit (server-side)
- Read server logs, memory dumps, database contents
- Observe traffic patterns, document sizes, upload frequencies

**Limitations:**
- Cannot break AES-256-GCM
- Cannot extract keys from client-side code
- Cannot force client to transmit keys

**Mitigations:**
- All document content encrypted client-side before transmission
- Metadata minimization (avoid leaking document type, structure)
- No logging of payload internals
- Traffic padding: not implemented in Phase-1 (deferred mitigation for Phase-2)

**Residual risks:**
- Traffic analysis reveals usage patterns
- Document size may leak information category
- Upload frequency correlates with user activity

### Adversary 2: Malicious User
**Profile:** Legitimate user attempting to abuse system, exfiltrate data, or disrupt service

**Capabilities:**
- Access own encrypted documents
- Submit crafted payloads to processing engines
- Attempt resource exhaustion attacks
- Share maliciously encrypted documents with others

**Limitations:**
- Cannot decrypt other users' documents
- Cannot bypass authentication without valid credentials
- Cannot access server infrastructure directly

**Mitigations:**
- Rate limiting on API endpoints
- Resource quotas per user
- Input validation on encrypted payload structure (size, format)
- Isolation between user workloads

**Residual risks:**
- Malicious content encrypted within valid documents
- Social engineering attacks on other users
- Denial-of-service through resource exhaustion

### Adversary 3: Compromised Client Device
**Profile:** Malware, keylogger, or physical attacker with access to user's device

**Capabilities:**
- Capture keys from browser memory
- Intercept plaintext before encryption
- Modify client-side code execution
- Exfiltrate decrypted documents
- Capture user password during login

**Limitations:**
- Cannot compromise other users' devices
- Cannot force server to decrypt data

**Mitigations (Client-Side):**
- Sub-resource integrity (SRI) for client code (detects tampering but does not prevent execution of malware)
- Content Security Policy (CSP) (restricts script origins but does not prevent compromised client from sending correct requests)
- Session timeout and re-authentication (mitigates persistence but does not prevent per-session compromise)
- Hardware-backed key storage (platform-dependent; unavailable on many browsers)

**Mitigations (Server-Side):**
- **Server enforces upload envelope structure only:** API Gateway checks envelope format, size limits, and versioning; it does not validate AES-256-GCM correctness and cannot detect plaintext masquerading as ciphertext.
- **GUARANTEE:** API Gateway performs structural envelope validation (format, size, version) before routing; cryptographic authenticity is verified only by the processing engine after decryption.

**Residual risks:**
- **Critical Risk (Phase-1 Reality):** Compromised client devices may leak plaintext locally. Once a device is compromised by malware or an attacker with access, there is no server-side mechanism that can prevent plaintext leakage or key extraction from the compromised client.
- **High risk:** Once device is compromised, zero-knowledge property breaks for that user
- Client-side security fundamentally depends on device integrity
- Malware can persist across sessions
- SRI and CSP do not prevent malware from operating within compromised client; they only detect or constrain some attack vectors
- Compromised client can generate valid encrypted envelopes that server cannot distinguish from legitimate requests

### Adversary 4: Network Attacker
**Profile:** Passive eavesdropper or active man-in-the-middle on network path

**Capabilities (Passive):**
- Observe encrypted traffic patterns
- Analyze packet sizes, timing, frequency
- Correlate network activity with users

**Capabilities (Active):**
- Attempt TLS downgrade or active MITM (feasible in Phase-1; no enforced rejection)
- Certificate substitution (if CA compromised)
- Connection hijacking

**Limitations:**
- When strong TLS is successfully negotiated, passive decryption is less likely; Phase-1 allows downgrade and MITM, so this is not relied on as a guarantee.
- Application-layer AEAD remains required for confidentiality and integrity (including authentication tokens); TLS is not a trusted control.
- Certificate pinning prevents MITM only on native clients; browsers have no pinning guarantee.

**Mitigations/Assumptions:**
- TLS is assumed transport provided by the platform; Phase-1 does not enforce version floor or downgrade rejection and permits MITM.
- HSTS is deployed but does not stop downgrade or active MITM on compromised paths.
- Certificate pinning applies only to native applications; browsers lack enforceable pinning.
- Confidentiality and integrity depend on application-layer AEAD; TLS contributes only when strong versions are negotiated and is not trusted for authentication token protection.

**Residual risks:**
- Traffic patterns leak metadata
- Compromised CA enables MITM (on browser clients without pinning)
- Endpoint identification via network analysis

### Adversary 5: Compromised Certificate Authority
**Profile:** Certificate Authority compromised through breach, coercion, or intentional misissuance

**Capabilities:**
- Issue fraudulent TLS certificates for Rythmiq One domains
- Perform man-in-the-middle attacks on encrypted payloads
- Intercept authentication tokens and session credentials
- Capture encrypted documents in transit

**Limitations (Native Clients):**
- Cannot bypass certificate pinning enforcement
- Cannot force native client to accept fraudulent certificates

**Limitations (Browser Clients):**
- Cannot bypass browser CA trust model enforcement
- Browser trusts CA by design; fraudulent certificates are valid in browser context

**Phase-1 Guarantees (Native Clients):**
- **Certificate pinning is mandatory** (enforcement: hardcoded pins in application code)
- **Pins are bundled with the application** (enforcement: build-time inclusion in APK/binary)
- **Pin rotation requires application update** (enforcement: no runtime pin modification)
- **Scope:** Pinning constrains native clients only; the underlying network transport is not a system guarantee, and downgrade or active MITM on non-pinned paths remain possible.

**Phase-1 Guarantees (Browser Clients):**
- **No certificate pinning guarantee** (enforcement limitation: browser does not expose pinning APIs to web applications)
- **Network transport is treated as deployment plumbing under standard CA assumptions; no confidentiality or integrity guarantees (including for authentication tokens) rely on it. Downgrade and fraudulent-certificate MITM remain possible in Phase-1.**

**Design Position:**
- Native clients receive cryptographic protection against CA compromise through pinning
- Browser clients accept the risk of CA compromise as inherent to the web trust model
- Browser clients are recommended only for non-sensitive document types or organizations with strong CA monitoring practices

---

## 7. Assumptions

We explicitly assume the following to be true:

1. **Client Execution Environment Integrity**
   - User's browser correctly implements Web Crypto API
   - JavaScript execution environment is not compromised at load time
   - Browser sandbox provides isolation from other processes

2. **Cryptographic Primitive Security**
   - AES-256-GCM provides semantic security
   - Argon2id with specified parameters resists brute-force attacks
   - TLS is an assumed transport mechanism provided by deployment platforms; Phase-1 allows downgrade and active MITM and does not rely on TLS properties for confidentiality or integrity (including authentication)
   - CSPRNG outputs are indistinguishable from random

3. **User Behavior**
   - Users are prompted client-side to choose stronger passwords (e.g., ≥14 characters, mixed classes), but this is a UX safeguard only; the server cannot and does not enforce password composition, and under hostile clients password entropy cannot be guaranteed
   - Users do not intentionally share master keys with third parties
   - Users understand that key loss means permanent data loss

4. **Infrastructure Security**
   - Server infrastructure prevents unauthorized physical access (mitigation, not a guarantee under malicious admins)
   - Infrastructure-level access controls are mitigations only; a compromised administrator can bypass filesystem or database isolation, and the threat model does not protect against malicious infra operators
   - Security patches applied within 30 days of disclosure

5. **Network Security**
   - Certificate Authority infrastructure is trustworthy (assumption only)
   - TLS certificate validation is assumed when TLS is used; downgrade and active MITM remain possible in Phase-1 and no guarantees rely on TLS
   - DNS is not permanently hijacked (short-term attacks acceptable)

6. **Legal and Organizational**
   - No legal compulsion to implement backdoors
   - Organization does not intentionally weaken cryptographic implementations
   - Audit logging is partial in Phase-1 (see Section 11 for details)

7. **Operational**
   - Server integrity is not enforced in Phase-1; the server may be modified to perform plaintext operations without guaranteed detection
   - Server enforces envelope structure only; it cannot verify cryptographic validity without keys, and malicious clients may upload plaintext disguised as ciphertext. Zero-knowledge guarantees apply only to compliant clients; hostile clients can bypass client-side encryption by design.
   - Key compromise is not actively detected in Phase-1; detection is user-initiated only and compromise may remain silent indefinitely. No automatic monitoring or notification exists.

**Critical assumption:** The weakest link is client device security. A compromised client nullifies all server-side security measures.

---

## 8. Security Invariants (Non-Negotiable)

The following invariants are binding constraints that must hold at all times. Violation of any invariant constitutes a critical security failure requiring immediate remediation.

### Operational Clarification: API Gateway Plaintext Handling (Best-Effort Only)
- **POSTURE:** For compliant (honest) clients whose uploads are correctly encrypted, the API Gateway is intended not to observe, store, log, or process plaintext document bytes. Cryptographic correctness cannot be verified at the gateway without keys; hostile or modified clients may send plaintext that will be routed, stored, and processed as provided.
- **LIMITATION:** This is best-effort only; routing errors or misconfiguration may introduce plaintext to the gateway path, and there is no Phase-1 detection, enforcement, or kill-switch to stop or scrub such exposure.

### Invariant 2: Master Key Server Prohibition
- **INVARIANT:** No master key or key material with decryption capability shall ever be transmitted to, stored on, or reconstructed by any server component.
- **RATIONALE:** The server must remain unable to decrypt user data even under complete infrastructure compromise or legal compulsion.
- **FAILURE CONSEQUENCE:** Users lose exclusive key control. Server compromise becomes equivalent to total user data exposure. Account recovery mechanisms become backdoors for unauthorized decryption.

### Invariant 3: Irreversible Master Key Loss
- **INVARIANT:** Loss of the user's master key must result in permanent, irreversible data loss with no server-side recovery mechanism.
- **RATIONALE:** Availability of server-side recovery mechanisms introduces key escrow, which contradicts zero-knowledge architecture and creates vulnerability to compulsion attacks.
- **FAILURE CONSEQUENCE:** Attackers can exploit recovery mechanisms to access data. Users cannot maintain exclusive control over data accessibility.

### Invariant 4: Client-Side Encryption Enforcement (Scoped to Compliant Clients)
- **INVARIANT:** For compliant (honest) clients, all document encryption must occur on the client device before any transmission to server infrastructure; no server-side encryption of user-provided plaintext is permitted. The server cannot verify cryptographic correctness without keys; hostile or modified clients may bypass encryption and upload plaintext that will be stored and processed as-is.
- **RATIONALE:** Server-side encryption implies server has plaintext access, violating the zero-knowledge property for compliant clients and creating administrative backdoors. Hostile clients are outside enforcement scope because the server cannot distinguish plaintext masquerading as ciphertext.
- **FAILURE CONSEQUENCE:** For compliant clients, documents become accessible to server administrators during encryption process. Metadata about content is exposed through plaintext handling. Hostile clients can already expose plaintext by uploading it directly; zero-knowledge does not apply to them.

### Operational Posture: CPU Routing Plaintext Containment (Best-Effort Only)
- **POSTURE:** CPU plaintext containment is best-effort and holds only when routing policy successfully forces CPU-only execution. Routing errors, misconfiguration, or GPU routing may violate containment and retain plaintext in VRAM/driver buffers.
- **SCOPE:** For compliant clients whose uploads are correctly encrypted, CPU-side decryption is intended to occur inside per-job isolated workers in locked, non-pageable memory with prompt zeroization; this is not enforced and can fail under routing errors or GPU use.
- **LIMITATION:** GPU lanes are selectable and not cryptographically prevented; any GPU routing (intentional, accidental, or due to misconfiguration) can leak plaintext beyond the CPU containment boundary. Hostile or modified clients may upload plaintext that will be processed and buffered as provided.
- **RATIONALE:** CPU containment is an operational mitigation only and should not be interpreted as enforced or automatic. No Phase-1 detection, enforcement, or kill-switch exists for routing mistakes or GPU leakage.

### Operational Posture (Non-Invariant): TLS Transport Assumption
- **SCOPE:** TLS is assumed transport provided by deployment platforms. Phase-1 does not enforce version pinning or downgrade rejection; browser and service clients may negotiate weaker protocols, and active MITM remains possible. This is an operational assumption, not a security guarantee.
- **IMPACT:** Active downgrade and MITM remain feasible in Phase-1. No invariants depend on TLS, and confidentiality/integrity (including for authentication tokens) must come from application-layer AEAD.
- **ACKNOWLEDGMENT:** Lower TLS versions may be accepted today; future enforcement is not guaranteed and is not relied upon.

### Invariant 5: Metadata Minimization Scope (Operational Only)
- **INVARIANT:** Logs and telemetry do not record document content or plaintext. Operational metadata (timestamps, user identifiers, operation types) is logged. Traffic analysis and access-pattern inference are not prevented in Phase-1; size, timing, and access patterns may be exposed.
- **RATIONALE:** Removing plaintext from logs prevents direct content disclosure, but operational metadata remains necessary for running the service. Without traffic shaping or padding, inference from size/timing/access patterns is possible and not mitigated in Phase-1.
- **FAILURE CONSEQUENCE:** If plaintext appears in logs, direct disclosure occurs. Even with plaintext excluded, adversaries can still infer behavior from operational metadata and traffic analysis in Phase-1.

### Development Standard (Intent): No Plaintext in Server Logs
- **INTENT:** Server application logs, system logs, and monitoring telemetry should not contain plaintext document content, decrypted metadata, or user passwords. Logs are plaintext and not tamper-evident in Phase-1.
- **RATIONALE:** Logs are often backed up, archived, and accessed by multiple parties (operations, security, vendors). Plaintext in logs violates data classification policy.
- **REALITY:** Logging mistakes can reintroduce plaintext, and Phase-1 provides no automatic prevention or tamper-evident detection.

### Implementation Standard (Server-Controlled Components Only): Cryptographic Primitives
- **STANDARD:** Server-controlled components must implement AES-256-GCM for symmetric encryption, Argon2id (minimum 128 MB, 3 iterations, parallelism 4) for key derivation, and HKDF-SHA256 for key expansion. These are implementation choices, not protocol guarantees. Hostile or modified clients can choose weaker or different primitives and are explicitly out of scope for enforcement.
- **RATIONALE:** These primitives underpin server-side cryptographic operations; weaker choices increase risk of cryptanalysis or brute-force success where the server performs cryptography.
- **IMPACT:** Compliance depends on server code/config; no universal enforcement exists against client-provided payloads or hostile clients.

### Invariant 8: User Password UX-Only Composition Prompts
- **INVARIANT:** Password strength prompts are purely client-side UX safeguards; the server cannot and does not enforce password composition or minimum strength. Under a hostile client model, password entropy cannot be guaranteed.
- **RATIONALE:** Composition prompts and Argon2id cost parameters are intended to nudge users toward stronger secrets, but any client can remove these prompts and submit low-entropy passwords that the server cannot detect.
- **FAILURE CONSEQUENCE:** Users (or malicious clients) can choose weak passwords, reducing effective security margin and making brute-force more feasible; no server-side control exists to prevent this.

### Best-Effort (Non-Invariant): Session Key Ephemeral Lifetime
- **POSTURE:** Session keys and ephemeral key material receive best-effort memory hygiene only; process termination is relied upon for memory reclamation. There are no guarantees against hostile code, deliberate memory dumps, advanced forensics, or GPU/driver buffer persistence.
- **RATIONALE:** Residual key material can be recovered via dumps, malware, or GPU/driver artifacts; without enforced zeroization, only opportunistic clearing and process teardown reduce exposure.
- **IMPACT:** This is not a binding guarantee; hostile or instrumented environments may retain key material.

### Clarification (Non-Invariant): Authentication Timing
- **POSTURE:** Authentication and cryptographic verification may occur after decryption inside processing workers. No guarantee is made that unauthenticated inputs are rejected prior to decryption.
- **RATIONALE:** Gateway performs only structural checks; processing lanes may defer tag verification until after decryption. Hostile or malformed payloads can be decrypted before authentication fails.
- **IMPACT:** Attackers can supply unauthenticated or plaintext payloads that may be decrypted before rejection; integrity and confidentiality rely on in-worker checks and fail-open risks remain if those checks are bypassed.

---

## 9. End-to-End Data Lifecycle

This section describes the complete lifecycle of a document from creation through deletion, specifying data state, location, and lifetime constraints at each stage. These constraints are binding operational requirements that enforce the zero-knowledge property and prevent implicit persistence.

### Stage 1: Capture on Device

**Description:** User selects or creates a document on their client device for processing.

**Data State:** Plaintext

**Location:** 
- User's local filesystem or application memory
- Browser file input or clipboard
- User's device only (not transmitted)

**Maximum Allowed Lifetime:** Unbounded while user retains original

**Security Properties:**
- No encryption applied yet
- No server involvement
- Responsibility for device security rests entirely with user

**Transition:** User initiates upload to processing system

---

### Stage 2: Encryption

**Description:** Document is encrypted client-side using user-held master/derived keys before any transmission to server infrastructure. Server-side workers may perform ephemeral encryption of derived artifacts (e.g., OCR output) during processing, but the server is never a long-term encryption authority or key holder.

**Data State:** Plaintext → Encrypted (AES-256-GCM)

**Location:** 
- Client device (browser, native application, or local processing engine)
- RAM during encryption operation only
- No persistence to disk during encryption

**Maximum Allowed Lifetime:** 
- Plaintext document: design target < 100 milliseconds during encryption operation; not cryptographically enforced (duration of encryption operation only)
- Plaintext key material: design target < 50 milliseconds during derivation and encryption; not cryptographically enforced (single key derivation, encryption, then immediate zeroing)
- Ciphertext: awaiting transmission

**Security Properties (expected for compliant clients; best-effort only):**
- Primary encryption occurs on the client with user-held keys before any network transmission; the server cannot verify this cryptographically without keys.
- Master key remains client-side; server never persists or controls master/derived keys.
- Derived keys used per-document
- Authenticated encryption (GCM authentication tags required)
- Plaintext is intended to be held in locked, non-pageable memory with swap disabled for CPU workers; this is best-effort and can be violated by routing errors, misconfiguration, crashes, or GPU execution paths that may retain plaintext in driver/VRAM buffers. No Phase-1 detection, enforcement, or kill-switch exists for these failures.

**Constraints (environment-specific; best-effort only):**
- Server does not provide long-term encryption services; server-side workers may perform ephemeral encryption of derived artifacts during processing but do not retain keys.
- No server-side encryption of user plaintext as a primary path
- No key material transmitted during encryption
- Plaintext buffers (document and key material) are intended to be zeroed from memory immediately upon encryption completion; zeroization is best-effort and can fail on crashes or misrouting to GPU.
- On encryption failure (exception, timeout, abort), plaintext zeroization is intended before control returns; this is best-effort only.
- Server processing workers (if encryption occurs there) intend to place plaintext in locked, non-pageable memory with swap disabled. GPU workers are not contained; driver/VRAM buffers may be pageable or retained beyond process lifetime. Hostile or modified clients may skip encryption entirely; the server will store and process whatever is uploaded.
- Native mobile/desktop clients attempt to use platform secure memory/OS key APIs; swap/pagefile control may not be available or guaranteed.
- Browser clients cannot guarantee non-pageable memory; zeroization is best-effort and subject to GC and paging.
- Avoiding page file or disk spillage on server workers is an operational intent only; misconfiguration or crashes may violate this. Clients are best-effort where OS allows.

**Transition:** Encrypted ciphertext prepared for upload

---

### Stage 3: Upload

**Description:** Encrypted document is transmitted from client to server infrastructure over a network channel where TLS is assumed transport plumbing but may be downgraded or intercepted (MITM) in Phase-1.

**Data State:** Encrypted (AES-256-GCM)

**Location:**
- Client device (originating)
- Network transit (TLS is assumed transport when negotiated; Phase-1 allows downgrade to weaker protocols and active MITM)
- Server infrastructure receiving (API Gateway)

**Maximum Allowed Lifetime:**
- Network transit: milliseconds to seconds (typical HTTP request duration)
- Server reception buffer: < 1 second (immediate handoff to processing or storage)

**Security Properties:**
- Application-layer AES-256-GCM provides confidentiality and integrity; transport properties are not relied upon. TLS is assumed transport when negotiated, but Phase-1 permits downgrade and active MITM and offers no guarantee.
- PFS on TLS is opportunistic when strong versions are negotiated; not enforced.
- Authentication tokens may transit over TLS, but their confidentiality/integrity must rely solely on application-layer protections; TLS is not trusted for authentication.

**Constraints:**
- **GUARANTEE:** API Gateway enforces envelope structure, size limits, and versioning only before routing; it cannot validate AES-256-GCM tags or ciphertext correctness and cannot detect plaintext masquerading as ciphertext (enforcement: schema/size/version checks at gateway). Cryptographic correctness of uploads cannot be verified at the gateway without keys.
- **GUARANTEE (scope: compliant clients only):** Cryptographic authenticity (AES-256-GCM tag verification) is performed only at the processing engine after decryption; the gateway does not and cannot perform this verification, and hostile or modified clients may supply plaintext that will be stored and processed as provided.
- API Gateway must not decrypt payload
- API Gateway must not inspect plaintext
- No plaintext logging at any layer
- Payload integrity is verified at the processing engine after decryption of the payload; transport integrity from TLS is not relied upon and MITM/downgrade remain possible.

**Transition:** Server receives encrypted payload and routes to processing or storage

---

### Stage 4: Processing

**Description:** Encrypted document is processed by CPU or GPU engines. CPU paths aim to decrypt inside per-job isolated workers in locked memory on a best-effort basis; routing errors, misconfiguration, or GPU paths can bypass this and place plaintext in driver/VRAM buffers. Plaintext is intended to be transient with prompt zeroization on CPU teardown, but this is best-effort and can fail; GPU lanes provide no containment or zeroization assurance. CPU-only containment depends on correct routing and can be violated by routing errors or misconfiguration.

**Data State:** 
- Ciphertext (primary)
- Plaintext OCR results or intermediate outputs (ephemeral only)

**Location:**
- Processing engine (CPU or GPU lane)
- Worker process RAM during computation
- No persistent storage of intermediates
- Scratch buffers for computation (ephemeral)

**Maximum Allowed Lifetime:**
- Encrypted input: duration of processing job (minutes to hours, user-dependent)
- Plaintext intermediates (if any): design target < 50 milliseconds during single operation; not cryptographically enforced (single operation window for OCR generation, re-encryption, then immediate zeroing)
- Results (encrypted): held until retrieved by client or TTL expiry

**Security Properties (best-effort):**
- Processing engine verifies authentication after decryption inside a per-job isolated worker for compliant clients whose uploads are actually encrypted.
- CPU decryption and plaintext intermediates are intended to remain in locked, non-pageable memory within that worker; this is best-effort and can be violated by routing errors, misconfiguration, crashes, or GPU routing that may place plaintext in driver/VRAM buffers.
- Plaintext intermediates (e.g., OCR output) are intended to be immediately re-encrypted for compliant clients; hostile uploads that arrive as plaintext remain plaintext unless the client encrypts them.
- Keys and plaintext are intended to stay within the worker boundary for compliant clients; hostile uploads may already be plaintext and will be handled as provided. Nothing is intended to be logged or persisted, but logging/misconfiguration errors can violate this.
- Worker isolation via process-per-job execution is operational only (separate OS user, no shared filesystem, no worker reuse); it does not prevent misrouting or GPU leakage, and no Phase-1 detection, enforcement, or kill-switch exists for such leakage.

- **Constraints (best-effort):**
- Raw uploads are intended to stay in RAM-only buffers and be passed to the worker without disk persistence; crashes or misconfiguration may violate this.
- Decryption is intended only inside the per-job isolated worker for the duration of the transformation; routing errors or misconfiguration may execute outside this boundary or on GPU.
- If plaintext intermediates are required (e.g., OCR processing), best-effort expectations for CPU workers only (GPU provides no containment):
   - Generated in dedicated process spawned per job (separate OS user, no shared resources, swap disabled where configured)
   - Held in locked, non-pageable memory for CPU workers on a best-effort basis; GPU lanes cannot guarantee non-pageable VRAM and carry residual leakage risk
   - Re-encrypted promptly after generation (design target < 50 milliseconds; not enforced); GPU lanes provide no containment or timing guarantee
   - Zeroization after re-encryption and on error paths is best-effort and may fail on crashes, routing errors, or GPU execution
   - Not intended to be written to disk; misconfiguration or crashes may violate this
   - Process termination after job completion is operational hygiene; it does not guarantee containment if routing or GPU usage occurred
- Processing engine zeroization of ephemeral buffers is best-effort only; crashes, misrouting, or GPU execution may leave plaintext resident, and there is no Phase-1 detection, enforcement, or kill-switch for these failures.

**Transition:** Encrypted results generated and prepared for storage or direct return

---

### Stage 5: Storage

**Description:** Encrypted documents and processing results are persisted to server storage infrastructure for later retrieval.

**Data State:** Encrypted (AES-256-GCM)

**Location:**
- Storage infrastructure (databases, file systems, cloud object stores)
- Backup systems
- Optionally: content delivery networks (if geographic distribution required)
- Server infrastructure only

**Maximum Allowed Lifetime:**
- Document storage: user-specified retention period or indefinite (user retains deletion control)
- Processing results: explicitly bounded TTL (see below)
- Backup retention: follow document retention; separate TTL policy for backup media

**Security Properties (scope: compliant clients; best-effort only):**
- All stored blobs are expected to remain encrypted; the server cannot verify cryptographic correctness without keys.
- No plaintext content at rest is expected for compliant clients, but hostile clients may store plaintext that will reside in storage, caches, and backups. Containment is best-effort only; routing errors or GPU usage upstream may have already exposed plaintext, and there is no Phase-1 detection, enforcement, or kill-switch for such exposures.
- Encryption keys remain client-side
- Storage layer cannot decrypt payloads and cannot distinguish ciphertext from plaintext provided by hostile clients
- Integrity protection maintained (GCM tags) for compliant clients

**Constraints:**
- Processing result artifacts must have explicit Time-To-Live (TTL):
  - Default TTL: 30 days from generation
  - User-configurable TTL: minimum 1 day, maximum 90 days
  - No implicit persistence; all artifacts must declare expiry
- No storage of plaintext metadata, document structure, or content hints
- Encryption at rest uses the same key derivation as the application-layer encryption used for transport payloads (not TLS)
- **Phase-1 Access Control:** Infrastructure-level per-user ownership enforced via filesystem permissions and database row-level security; cross-user access denied by default at infrastructure layer; application layer is NOT trusted for access enforcement

**Phase-1 TTL Enforcement (data lifecycle policy; logical vs physical):**
- **POLICY (Access Control Only, data lifecycle):** TTL checks are an access-control policy implemented in code/config on primary storage read paths; hostile infrastructure or code changes can disable or bypass these checks. No tamper-evident protection exists in Phase-1.
- **Scope:** Secondary systems (replicas, caches, CDNs, backups) may retain and serve data beyond TTL; there is no bounded staleness guarantee in Phase-1.
- **Expectation (policy only):** Storage primaries attempt TTL validation on reads; expired documents are intended to return access-denied on primary paths, but hostile infrastructure, code changes, or configuration drift can bypass or disable this.
- **Monitoring:** Alerts are configured to fire if expired documents remain readable on primaries, but hostile operators can disable or alter monitoring.
- **Limitation:** Physical deletion is best-effort via scheduled jobs; no precise schedule or completeness guarantee across replicas, caches, or backups (best-effort target within 7 days on primaries; backups may retain longer).
- **Limitation:** No replica lag or clock-skew guarantees; secondary systems may remain stale indefinitely in Phase-1.
- TTL provides access control, not assured data eradication. Plaintext uploaded by hostile clients follows the same TTL/deletion behavior; storage cannot distinguish plaintext from ciphertext without keys.

**Transition:** Client retrieves encrypted document or results; TTL expiry is an access-control policy on primaries only and may be absent or bypassed on other paths (replicas/caches/CDNs/backups may lag or ignore TTL, and hostile infrastructure can disable it).

---

### Stage 6: Export

**Description:** User retrieves encrypted document or processing results from server and decrypts on client device.

**Data State:** 
- Ciphertext (during transmission and server storage)
- Plaintext (during decryption on client)

**Location:**
- Server storage (retrieving ciphertext)
- Network transit (TLS assumed transport; Phase-1 allows downgrade to weaker protocols and active MITM)
- Client device (decryption and plaintext)

**Maximum Allowed Lifetime:**
- Ciphertext in transit: seconds (network latency)
- Plaintext on client after decryption: unbounded (user retains export)
- Plaintext in browser memory during viewing: session duration or until user clears

**Security Properties:**
- Application-layer AES-256-GCM provides confidentiality and integrity; TLS is assumed transport and may be downgraded or intercepted (MITM) in Phase-1 and is not trusted for authentication token protection.
- Export decryption occurs on the client; server stores and serves ciphertext only for export for compliant clients. Hostile clients may have stored plaintext, which will be served as provided.
- Any server-side plaintext during processing was intended to be confined to an isolated worker's RAM and zeroed post-transformation for compliant clients, but routing errors, GPU execution, or crashes may retain plaintext; no Phase-1 detection, enforcement, or kill-switch exists for such failures.
- Client must verify GCM authentication tag before decryption
- Session-scoped keys used for decryption

**Constraints:**
- Decryption exclusively on client device (browser or native app)
- Server must not cache plaintext exports; however, plaintext that a hostile client uploaded will remain stored and may be served as-is
- Client must clear plaintext from memory on application termination
- No download of plaintext to disk unless explicitly user-initiated
- Plaintext results from export must be treated as user-controlled data

**Transition:** User views plaintext; may re-encrypt for storage or share via external channels

---

### Stage 7: Expiry and Deletion

**Description:** Document or processing result hits TTL and primary access paths enforce denial as a data lifecycle policy; replicas/caches/CDNs may still serve stale data until propagation completes, hostile infrastructure can bypass enforcement, and physical deletion remains best-effort.

**Data State:** 
- Ciphertext (active, readable)
- Ciphertext (expired; primary paths blocked; secondary systems may lag)
- Void (physically deleted) ← best-effort

**Location:**
- Server storage (primary and replicas)
- Backup systems
- Transaction logs (zero if no decryption history to preserve)

**Maximum Allowed Lifetime:**
- **Phase-1 Distinction:** Primary-path blocking vs Deleted
-   - **Primary-path blocking (logical access control):** Expired documents are blocked on primary storage read paths at TTL expiry. Secondary systems (replicas/caches/CDNs/backups) may retain and serve data beyond TTL; no bounded staleness guarantee exists in Phase-1.
   - **Deleted (physical removal):** Physical deletion is a best-effort background job (target within 7 days on primaries); no guarantee of timely or complete removal across replicas, caches, or backups.
- User-initiated deletion: primary paths are blocked immediately; physical deletion best-effort within 24 hours; replicas/caches/backups may remain readable with no bounded staleness guarantee.
- Processing result TTL expiry: primary paths are blocked at expiry timestamp; physical deletion best-effort within 7 days; secondary systems may lag indefinitely.
- Backup retention: primary-path blocking propagates to backups as backup jobs run; physical deletion is best-effort (target within 90 days) and stale backup reads remain possible until propagation completes, with no bounded staleness guarantee.
- Transaction logs: no plaintext to delete; metadata logs kept per regulatory requirements.

**Phase-1 TTL Posture (policy, not security boundary):**
- TTL enforcement is a data lifecycle policy on primary read paths and can be bypassed by hostile infrastructure, code changes, or configuration drift.
- Replicas/caches/CDNs/backups may serve stale data indefinitely; there is no strict SLA or bounded staleness window in Phase-1.
- Monitoring/alerting for expired-but-readable items is configuration-dependent and can be disabled or bypassed; no assurance is provided.
- Access denial on primaries is best-effort policy, not a guarantee of unreadability or deletion. Secondary systems may still serve data, and physical artifacts may persist.
- TTL does not provide assured data eradication or containment; expired blobs may remain readable wherever enforcement is absent.

**Phase-1 Limitations:**
- Physical deletion timing is best-effort (no precise SLA).
- Replica lag and cache/CDN staleness are not eliminated; stale reads may occur until propagation/invalidation completes.
- No clock skew guarantees across distributed nodes.
- Expired documents may remain physically present for up to 7 days (primaries) and longer on backups (up to 90 days) even after primary-path blocking begins; stale secondary reads remain possible until propagation completes.

**Constraints:**
- Explicit deletion API required; no implicit garbage collection
- TTL-based expiry must be enforced at read time (mandatory storage layer check)
- Physical deletion (when it occurs) must remove:
  - Primary blob from storage
  - Encrypted backups (or mark as expired)
  - Temporary artifacts (processing intermediates)
  - Metadata records (if any plaintext metadata exists)
- Physical deletion must NOT attempt to destroy key material (no key material on server)
- Expiry and deletion logged in Phase-1 audit system (user ID hash, timestamp, operation result)
- After physical deletion, no server component can reconstruct or recover data

**Transition:** Primary paths block access at expiry; secondary systems may lag; physical deletion completes lifecycle on best-effort timing

---

## Data Lifecycle Integrity Rules

The following rules must hold across all lifecycle stages:

1. **No Implicit Persistence (Primary Enforcement Only, data lifecycle policy):** Every data artifact must declare a TTL or explicit deletion, and TTL is enforced on primary systems only as a policy control. Secondary systems (replicas, caches, CDNs, backups) may retain artifacts beyond TTL; hostile infrastructure can bypass enforcement and the system does not guarantee bounded lifetime across all copies in Phase-1. Floating artifacts without declared TTL or deletion remain a critical failure.

2. **Plaintext Isolation (compliant clients; best-effort):** Intended that plaintext stays on client devices. Server-side plaintext (logs, memory, cache, swap) is a best-effort avoidance goal and can be violated by routing errors, misconfiguration, crashes, or GPU execution. Hostile or modified clients may upload plaintext that will be stored and processed as provided; the system cannot prevent or cryptographically detect this, and there is no Phase-1 detection, enforcement, or kill-switch to contain such exposures.

3. **RAM-Only Processing (best-effort):** Raw uploads to processing engines are intended to remain in RAM-only buffers; routing errors, crashes, misconfiguration, or GPU execution may violate this. Disk writes of ciphertext/plaintext are not intended except for final encrypted results, but this is not enforced, and no Phase-1 detection, enforcement, or kill-switch exists if containment fails.

4. **TTL Enforcement (Phase-1, Primary-Only, Policy):** All server-generated artifacts (OCR output, processing results, temporary files) should declare TTL and rely on primary-path blocking at expiry as a policy control. TTL enforcement can be bypassed by hostile infrastructure or configuration drift; secondary systems (replicas, caches, CDNs, backups) may retain artifacts beyond TTL with no bounded lifetime guarantee in Phase-1. Physical deletion remains a best-effort background job (no precise SLA). Alerting is configuration-dependent and not assured. Manual TTL deferrals require explicit user action.

5. **Audit Trail (Phase-1 Partial):** Lifecycle transitions are partially logged in Phase-1:
   - User ID (hashed reference, not plaintext)
   - Operation type (upload, process, export, delete operations only; client-side operations not logged)
   - Timestamp
   - Result (success / failure for server operations)
   - **Phase-1 Limitation:** No encrypted log rotation; no complete forensic audit trail; logs stored in plaintext on server (operational data only, no document content)
   - No plaintext document content in audit logs

6. **Key-Isolation:** No lifecycle stage shall involve transmission, storage, or processing of master keys or key material (except on client during encryption/decryption).

---

## 10. Non-Goals

The system explicitly does **NOT** protect against:

1. **Client-Side Compromise**
   - Malware on user's device
   - Compromised browser or extensions
   - Physical access to unlocked device
   - Evil maid attacks on client hardware

2. **User-Initiated Key Disclosure**
   - User voluntarily sharing password or recovery codes
   - Social engineering attacks targeting users
   - Phishing attacks that extract credentials

3. **Traffic Analysis**
   - Correlation of upload patterns with user identity
   - Document size leakage
   - Timing attacks based on processing duration
   - Network-level activity correlation

4. **Availability During Key Loss**
   - Account recovery without user-held secrets
   - Data recovery after password loss without recovery codes
   - Emergency access by administrators

5. **Malicious Content**
   - Malware encrypted within documents
   - Exploitation of document processing vulnerabilities via crafted encrypted payloads
   - Detection of illegal content (system is content-blind)

6. **Side-Channel Attacks**
   - Power analysis on client device
   - Timing attacks on encryption operations
   - Cache-timing attacks in browser
   - Spectre/Meltdown class vulnerabilities on GPU processing lanes (residual risk accepted; no mitigation in Phase-1)

7. **Legal Compulsion**
   - Resistance to lawful intercept orders
   - Protection against state-level adversaries with legal authority
   - Anonymity of users (authentication required)

8. **Quantum Computing**
   - Post-quantum cryptographic resistance (not implemented in v1.0)
   - Forward secrecy against future quantum attacks

9. **Endpoint Security**
   - Hardening user's operating system
   - Securing user's network environment
   - Protecting against hardware keyloggers

10. **Service Abuse**
    - Preventing use for illegal content storage
    - Content moderation (system cannot inspect content)
    - Automated detection of policy violations

**Design Philosophy:** We prioritize strong cryptographic guarantees over operational convenience. The burden of key management and device security rests with the user. Data loss from key loss is an acceptable trade-off for zero-knowledge architecture.

---

## 11. Phase-1 Access Control and Audit Enforcement

### Storage Access Control (Phase-1)

**Infrastructure-Level Enforcement (Mitigations, Not Guarantees):**
- Infrastructure-layer controls (filesystem permissions, database row-level security) provide isolation for honest operators but are not guarantees against malicious administrators.
- Cross-user access is denied by default at the infrastructure layer, but a compromised admin can bypass these controls.
- Application layer is NOT trusted for access control; enforcement relies on OS/database boundaries that hostile infra operators can override.

**What This Means:**
- User A cannot read User B's encrypted blobs via application logic if infra operators remain honest and controls are intact.
- Storage isolation is provided by operating system user separation or database privilege separation as a mitigation.
- Application vulnerabilities (e.g., IDOR, authorization bypass) are blocked at the storage layer when infra controls are intact; hostile admins are out of scope.

**What This Does NOT Mean:**
- Protection from malicious administrators or compromised infrastructure; such actors can bypass isolation.
- Absolute guarantees of cross-user isolation under infra compromise.
- Encrypted blobs remain unreadable without keys, but access controls do not resist hostile infra operators.

### Audit Logging (Phase-1 Partial)

**Operational, Not Security Control:** Audit logs are operational tools, not security guarantees. Logs are not tamper-evident in Phase-1, and a hostile administrator can modify or delete logs without detection.

**Phase-1 Capabilities:**
- Server-side operations (upload, process, export, delete) are logged with user ID hash, timestamp, and result for operational visibility only; this logging does not provide integrity or anti-tamper guarantees.
- No plaintext document content is intended to appear in audit logs under any execution path; this is an operational hygiene target, not a tamper-resistant guarantee.
- Logs stored in plaintext operational database (metadata only)
- Logs retained for 90 days from generation

**Phase-1 Limitations (Explicitly Deferred):**
- **NO encrypted log rotation** (deferred to Phase-2)
- **NO complete forensic audit trail** for all lifecycle transitions; client-side operations (capture, encryption) are not logged
- **NO cryptographic log integrity verification** (deferred to Phase-2)
- **NO tamper-evident log storage** (deferred to Phase-2)
- **NO real-time anomaly detection** on audit events (deferred to Phase-2)

**What Phase-1 Audit Provides:**
- Operational visibility for debugging and incident response
- Basic accountability for server-side actions (who uploaded, processed, deleted what resources)
- Compliance with minimum logging requirements for infrastructure operations

**What Phase-1 Audit Does NOT Provide:**
- Forensic-grade audit trail suitable for legal evidence
- Protection against administrator log tampering (hostile administrators can modify or delete logs without detection)
- Comprehensive lifecycle tracking (client-side operations unlogged)
- Encrypted or anonymized audit records

**Design Position:**
Audit logging in Phase-1 is operational tooling, not a security guarantee. Logs are not tamper-evident, and malicious administrators can alter or remove them. Users requiring forensic auditability should defer deployment until Phase-2 encrypted audit implementation.

### TTL and Expiry Enforcement (Phase-1)

**Critical Distinction: Primary-Path Blocking vs Deleted**

Phase-1 enforces TTL on primary access paths; secondary systems are best-effort and may serve stale data until propagation completes. Physical deletion remains asynchronous.

**Phase-1 Policy (Access Control Only):**
- Primary storage TTL enforcement is a code/config policy on read paths; hostile infra or code changes can disable or bypass it. No tamper-evident protection exists in Phase-1.
- Storage primaries are expected to validate TTL on reads and return access-denied for expired documents; secondary systems may still serve stale data until propagation completes.
- Monitoring is configured to alert on expired-but-readable blobs on primaries, but hostile operators can disable or alter monitoring.

**Phase-1 Limitations (Explicitly Deferred):**
- **NO precise physical deletion SLA** (best-effort within 7 days for TTL expiry; 24 hours for user-initiated deletion)
- **NO replica lag handling** (replicas may serve stale TTL data during synchronization)
- **NO clock skew compensation** across distributed storage nodes (nodes use local clocks; skew up to 1 second tolerated)
- **NO immediate physical deletion** upon expiry (scheduled background job handles deletion)

**What Primary-Path Blocking Means:**
- Primary storage rejects read attempts with access-denied error
- Document remains physically present in storage and may still be served by lagging replicas/caches/CDNs until propagation completes
- Cryptographic keys remain client-side; server cannot decrypt even if physically present
- Monitoring detects and alerts on expired-but-not-blocked documents on primaries
- Physical deletion occurs asynchronously via scheduled job (best-effort timing)

**What "Deleted" Means:**
- Physical removal of ciphertext blob from storage infrastructure
- Removal from all replicas and backup systems (propagates over time)
- No recovery possible through any mechanism
- Occurs after primary-path blocking, on best-effort schedule

**Design Position:**
Phase-1 treats TTL as an access-control policy, not an immutable guarantee. Primary-path access denial is attempted via configurable checks; replicas/caches/CDNs may serve stale data until propagation completes. Physical deletion is a storage hygiene operation that occurs asynchronously. Users requiring tamper-evident enforcement, immediate physical deletion, or strict secondary consistency should defer deployment until Phase-2 synchronous deletion implementation.

### Client Compromise Monitoring (Phase-2, Non-Enforced)

**Future Mitigations (Explicitly Deferred from Phase-1):**

The following mechanisms may be added in Phase-2 to detect and mitigate device compromise, but are **NOT** enforced in Phase-1 and provide **NO SECURITY GUARANTEE** at this time:

- **Anomaly Detection on Key Usage:** Server-side monitoring of cryptographic operations per user to detect suspicious patterns (e.g., rapid re-encryption, unusual access frequencies, geographic anomalies). **Non-enforced in Phase-1:** Not deployed; cannot prevent plaintext leakage from compromised device.

- **Key-Usage Monitoring and Alerts:** Real-time notifications to user when master key is accessed from unusual devices, locations, or times. **Non-enforced in Phase-1:** Alerts are informational only and cannot prevent compromise in progress.

- **Device Integrity Attestation:** Verification that client device OS and firmware have not been modified before allowing key operations. **Non-enforced in Phase-1:** Not deployed; many platforms lack stable attestation APIs.

**Critical Caveat:** These future mitigations are **detection and response mechanisms only**. They cannot prevent plaintext leakage from an already-compromised device. A compromised client device will inevitably leak plaintext locally; these mechanisms only help users detect compromise faster.

**Design Position:** Phase-1 explicitly accepts that compromised clients leak plaintext. Detection mechanisms in Phase-2 will reduce time-to-detection but do not eliminate the fundamental risk. Users with high-value data requiring compromise prevention should deploy additional client-side hardening (endpoint detection and response, behavioral monitoring) outside Rythmiq One's scope.

### TTL and Expiry Enforcement (Phase-1)

### Account Recovery Mechanisms (Phase-1)

**Critical Distinction: Recovery Codes Are NOT Equivalent to Primary Authentication**

Recovery codes are user-facing safety features for availability after password loss. They do not strengthen cryptographic security and can be bypassed, replayed, or tampered with by hostile infrastructure or configuration changes.

**Phase-1 Posture (user-facing safety, not guarantee):**
- Codes are generated with high entropy (CSPRNG) and intended to be single-use and rate-limited, but these properties depend on cooperative infrastructure and can be disabled or modified by malicious operators.
- Recovery codes are intended only for master key recovery during password reset; enforcement relies on server policy that hostile admins can alter.
- Recovery codes are user-controlled (generated client-side, displayed once, never transmitted to server in plaintext) but provide no cryptographic strengthening.

**Phase-1 Limitations (Explicitly Deferred):**
- **NO screenshot prevention enforcement** (user responsible for secure offline storage; no technical prevention of screenshots, photos, or copying)
- **NO mandatory rotation schedule** (recovery codes may remain valid indefinitely until used or manually regenerated by user)
- **NO device binding** (recovery code can be used from any device; no attestation of device integrity)
- **NO biometric confirmation** for recovery code redemption (deferred to Phase-2)
- **NO server-side encrypted backup** of recovery codes (user solely responsible for storage)

**What Recovery Codes ARE:**
- Emergency account recovery mechanism for password loss scenarios
- Single-use, high-entropy secrets that enable master key re-derivation or recovery
- Weaker than primary authentication (represent controlled security/availability trade-off)
- User's responsibility to store securely offline (printed, password manager, hardware token)

**What Recovery Codes Are NOT:**
- Equivalent to password for security strength (no Argon2id key derivation; direct code validation)
- Suitable for regular authentication (single-use only; consumed on redemption)
- Protected from user-initiated disclosure (user can photograph, screenshot, or share codes)
- Automatically rotated or managed by system (user-initiated regeneration only)

**Design Position:**
Recovery codes are a pragmatic compromise between zero-knowledge security and user accessibility. Phase-1 enforces high entropy and single-use properties cryptographically, but cannot prevent user mishandling (screenshots, insecure storage, social engineering disclosure). Users requiring maximum security should disable recovery codes entirely and accept permanent data loss risk upon password loss.

---

## Threat Model Maintenance

**Review Frequency:** Quarterly or after significant architecture changes

**Ownership:** Security team (Blue Team)

**Update Triggers:**
- New attack vectors discovered
- Cryptographic standard changes
- Regulatory requirement changes
- Incident post-mortems

**Approval Required:** CTO and Security Lead

---

## Red Team Closure & Accepted Risks (Phase-1)

**Red Team Review Status:** Complete

The Red Team review for Phase-1 is complete. This section formalizes accepted risks, closes outstanding ambiguities, and establishes final boundaries for security guarantees. No further guarantees are implied beyond those explicitly stated in this document. The interpretation of terms "best-effort", "policy", and "design intent" is frozen as documented.

### Interpretation of Invariants

The term "Invariant" is used exclusively for properties that are enforced mechanically in the current implementation. Any property labeled "best-effort", "policy", "design intent", or "assumption" is not an invariant and carries no security guarantee. Readers must not infer security guarantees from documentation language, architectural descriptions, or stated intentions. Only explicitly enforced mechanisms constitute security boundaries.

**Scope of Zero-Knowledge Guarantees:**
Zero-knowledge properties apply only to compliant clients that properly encrypt data before transmission. The system cannot detect or prevent hostile clients from uploading plaintext. Cryptographic correctness of uploads cannot be verified by the server without possession of decryption keys. Hostile or modified clients may submit plaintext to storage, backups, and logs.

**Infrastructure Trust Boundaries:**
The system does not protect against malicious administrators or compromised infrastructure components. Administrators with sufficient privileges can bypass storage isolation, modify routing logic, disable memory protections, or extract data from backups. Infrastructure-level access controls are deployment mitigations, not cryptographic guarantees.

**Plaintext Containment Limits:**
GPU processing paths, browser execution environments, and distributed replica synchronization may violate plaintext containment. Plaintext may reside in GPU driver memory, VRAM buffers, browser heap allocations, or inter-node replication channels. Phase-1 has no detection, enforcement, or kill-switch mechanisms for these violations. Routing errors and misconfigurations can place plaintext in prohibited locations without triggering alerts or automatic remediation.

**Non-Guarantee Mechanisms:**
The following mechanisms are not security guarantees: TTL-based expiration policies, audit logging retention, account recovery procedures, and metadata minimization practices. These are operational policies subject to administrator override, infrastructure failure, or configuration drift. They provide no cryptographic enforcement.

**Phase-1 Design Priorities:**
Phase-1 prioritizes architectural clarity and honest documentation of security boundaries over completeness of enforcement mechanisms. Containment is best-effort. Detection and response capabilities are deferred to Phase-2. This posture accepts higher risk of undetected failures in exchange for transparent risk communication and rapid deployment.

### Phase-1 Scope Lock

This threat model reflects Phase-1 implementation reality only. Missing enforcement mechanisms represent accepted risks, not documentation oversights or temporary gaps to be closed through policy updates. Any strengthening of security guarantees requires architectural redesign and explicit enforcement implementation, not reinterpretation of existing documentation or addition of new documentation language.

No reader, auditor, or stakeholder should attempt to "tighten" guarantees through documentation updates, clarifications, or reinterpretation of intent. Phase-1 boundaries are fixed. Expansion of security properties beyond those explicitly enforced today requires Phase-2 architectural work and formal security review.

---

*End of Document*
