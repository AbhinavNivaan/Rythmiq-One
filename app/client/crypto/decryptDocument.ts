import {
  InvalidInputError,
  UnsupportedVersionError,
  CryptoOperationError,
} from "./errors";
import { WrappedDEK, EncryptedPayload } from "./encryptDocument";

const SUPPORTED_VERSION = 1;

export interface DecryptedPayload {
  plaintext: Uint8Array;
}

function validateInput(
  input: Uint8Array | null | undefined,
  name: string
): Uint8Array {
  if (input === null || input === undefined) {
    throw new InvalidInputError(`${name} must not be null or undefined`);
  }
  if (!(input instanceof Uint8Array)) {
    throw new InvalidInputError(`${name} must be a Uint8Array`);
  }
  return input;
}

function validateKeySize(key: Uint8Array, expectedBits: number): void {
  if (key.byteLength !== expectedBits / 8) {
    throw new InvalidInputError(
      `Key must be exactly ${expectedBits} bits (${expectedBits / 8} bytes), got ${key.byteLength} bytes`
    );
  }
}

function validateNonZeroKey(key: Uint8Array): void {
  const isAllZero = key.every((byte) => byte === 0);
  if (isAllZero) {
    throw new InvalidInputError("Key must not be all zeros");
  }
}

function validateWrappedDEKLength(wrappedDEK: Uint8Array): void {
  const expectedLength = 40;
  if (wrappedDEK.byteLength !== expectedLength) {
    throw new InvalidInputError(
      `Wrapped DEK must be exactly ${expectedLength} bytes (AES-KW output), got ${wrappedDEK.byteLength} bytes`
    );
  }
}

function validateNonceLength(nonce: Uint8Array): void {
  if (nonce.byteLength !== 12) {
    throw new InvalidInputError(
      `Nonce must be exactly 12 bytes, got ${nonce.byteLength} bytes`
    );
  }
}

function validateTagLength(tag: Uint8Array): void {
  if (tag.byteLength !== 16) {
    throw new InvalidInputError(
      `Tag must be exactly 16 bytes, got ${tag.byteLength} bytes`
    );
  }
}

function validateCiphertextNotEmpty(ciphertext: Uint8Array): void {
  if (ciphertext.byteLength === 0) {
    throw new InvalidInputError("Ciphertext must not be empty");
  }
}

async function unwrapDEK(
  wrappedDEK: WrappedDEK,
  umk: Uint8Array
): Promise<CryptoKey> {
  validateInput(umk, "UMK");
  validateKeySize(umk, 256);
  validateNonZeroKey(umk);

  if (wrappedDEK === null || wrappedDEK === undefined) {
    throw new InvalidInputError("Wrapped DEK must not be null or undefined");
  }
  if (typeof wrappedDEK !== "object") {
    throw new InvalidInputError("Wrapped DEK must be an object");
  }
  if (!(wrappedDEK.wrappedKey instanceof Uint8Array)) {
    throw new InvalidInputError("Wrapped DEK key must be a Uint8Array");
  }

  validateWrappedDEKLength(wrappedDEK.wrappedKey);

  try {
    const umkKey = await crypto.subtle.importKey(
      "raw",
      umk,
      { name: "AES-KW", length: 256 },
      false,
      ["unwrapKey"]
    );

    const dek = await crypto.subtle.unwrapKey(
      "raw",
      wrappedDEK.wrappedKey,
      umkKey,
      { name: "AES-KW" },
      { name: "AES-GCM", length: 256 },
      false,
      ["decrypt"]
    );

    return dek;
  } catch (error) {
    if (
      error instanceof InvalidInputError ||
      error instanceof CryptoOperationError
    ) {
      throw error;
    }
    throw new CryptoOperationError(
      `Failed to unwrap DEK: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}

async function decryptWithDEK(
  ciphertext: Uint8Array,
  nonce: Uint8Array,
  tag: Uint8Array,
  dek: CryptoKey
): Promise<Uint8Array> {
  validateInput(ciphertext, "Ciphertext");
  validateCiphertextNotEmpty(ciphertext);
  validateInput(nonce, "Nonce");
  validateNonceLength(nonce);
  validateInput(tag, "Tag");
  validateTagLength(tag);

  try {
    const combined = new Uint8Array([...ciphertext, ...tag]);
    const plaintext = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: nonce, tagLength: 128 },
      dek,
      combined
    );

    return new Uint8Array(plaintext);
  } catch (error) {
    if (
      error instanceof InvalidInputError ||
      error instanceof CryptoOperationError
    ) {
      throw error;
    }
    throw new CryptoOperationError(
      `Failed to decrypt with DEK: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}

/**
 * Decrypts a document using envelope decryption (unwrap DEK with UMK).
 *
 * ZEROIZATION RESPONSIBILITY:
 * Callers own the plaintext lifecycle. The plaintext returned by this function
 * remains in memory until explicitly cleared. This module provides zeroArray()
 * as a best-effort helper, but JavaScript cannot guarantee memory zeroization due
 * to GC copies, optimizations, and runtime behavior. Do not rely on zeroArray()
 * for security-critical guarantees.
 *
 * CALLER RESPONSIBILITY:
 * - Plaintext lifecycle management (this function does not zero output)
 * - UMK lifecycle management (this function does not zero input)
 * - Secure disposal of decrypted plaintext after use
 *
 * USAGE EXAMPLE:
 * ```typescript
 * import { decryptDocument } from './decryptDocument';
 * import { zeroArray } from './encryptDocument';
 *
 * const plaintext = await decryptDocument(encrypted, umk);
 * // Use plaintext...
 * zeroArray(plaintext); // Best-effort cleanup (not guaranteed)
 * // plaintext should not be accessed after this point
 * ```
 *
 * @param payload - Encrypted payload containing wrapped DEK, nonce, ciphertext, and tag
 * @param umk - User Master Key for unwrapping DEK (caller must manage lifecycle)
 * @returns Decrypted plaintext (caller owns lifecycle and must zero after use)
 */
export async function decryptDocument(
  payload: EncryptedPayload,
  umk: Uint8Array
): Promise<Uint8Array> {
  if (payload === null || payload === undefined) {
    throw new InvalidInputError("Encrypted payload must not be null or undefined");
  }
  if (typeof payload !== "object") {
    throw new InvalidInputError("Encrypted payload must be an object");
  }

  if (payload.version !== SUPPORTED_VERSION) {
    throw new UnsupportedVersionError(
      `Unsupported payload version: ${payload.version}. This client only supports version ${SUPPORTED_VERSION}. ` +
      `Please update the client to handle this payload version or regenerate the payload with a supported version.`
    );
  }

  validateInput(payload.nonce, "Nonce");
  validateNonceLength(payload.nonce);
  validateInput(payload.ciphertext, "Ciphertext");
  validateCiphertextNotEmpty(payload.ciphertext);
  validateInput(payload.tag, "Tag");
  validateTagLength(payload.tag);
  validateInput(umk, "UMK");
  validateKeySize(umk, 256);
  validateNonZeroKey(umk);

  try {
    const dek = await unwrapDEK(payload.wrappedDEK, umk);
    const plaintext = await decryptWithDEK(
      payload.ciphertext,
      payload.nonce,
      payload.tag,
      dek
    );
    return plaintext;
  } catch (error) {
    if (
      error instanceof InvalidInputError ||
      error instanceof CryptoOperationError
    ) {
      throw error;
    }
    throw new CryptoOperationError(
      `Failed to decrypt document: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}
