# Client-Side Key Model

## 1. User Master Key (UMK)
- **Purpose:** Root key held only by the client to wrap/unwrap Document Encryption Keys (DEKs); never sent to the server; never derivable from server data.
- **Lifetime:** Created on first encryption use; persists until the user deletes local key material; no rotation is enforced by the server.
- **Storage location:**
  - macOS: Stored in the user Keychain (secure item, non-exportable flag where available) or an app-private encrypted file when Keychain storage is unavailable.
  - iOS/iPadOS: Stored in the Secure Enclave–backed Keychain class (device-bound, non-migrating); falls back to app-private encrypted file if Secure Enclave is unavailable.
  - Windows: Stored in DPAPI-protected user scope or an app-private encrypted file if DPAPI is unavailable.
  - Linux: Stored in a libsecret/gnome-keyring/KWallet item when available; otherwise in an app-private encrypted file with OS file permissions only.
  - Web: Stored in IndexedDB via WebCrypto-provided non-extractable CryptoKey when supported; otherwise in IndexedDB as an encrypted blob protected by a per-origin random key kept in-memory only; cleared with site data.
- **Loss event:** If the UMK is lost, all DEKs remain wrapped and permanently inaccessible; all client-encrypted documents become undecryptable; server cannot assist or recover.
- **Server inference:** Server observes only opaque ciphertext and wrapped DEKs; it cannot infer UMK existence, validity, or use; it can only observe whether uploads include wrapped DEKs.

## 2. Document Encryption Keys (DEK)
- **Generation:** Fresh random symmetric key per document (and per major re-encryption event) using a CSPRNG on the client.
- **Wrapping:** Each DEK is wrapped exclusively by the UMK (e.g., AEAD key wrap); wrapped DEKs stored alongside the document metadata client-side and optionally sent to the server as opaque blobs; no server-held unwrapped DEKs; no additional escrow keys.
- **Rotation:** On re-encryption, generate a new DEK and wrap with the current UMK; old DEK and ciphertext may be retained or discarded per client policy but remain inaccessible without the corresponding wrap.

## 3. Session Keys
- **Purpose:** Ephemeral keys derived on the client to encrypt transient data in memory or transport within a single app session; never persisted; not used to wrap DEKs.
- **Lifetime:** Created on demand; live only for the duration of the session or operation; destroyed immediately after use or when the session ends.
- **Disposal semantics:** Explicit zeroization in memory where supported; drop references to trigger runtime garbage collection; clear any cached CryptoKey handles; no persistence to disk.

## Explicit Statements
- UMK loss results in permanent loss of access to all wrapped DEKs and thus all client-encrypted documents; no recovery path exists.
- Server cannot infer client key state or verify encryption use; it only sees ciphertext and opaque wrapped DEKs; it cannot determine UMK presence, correctness, or disposal.
