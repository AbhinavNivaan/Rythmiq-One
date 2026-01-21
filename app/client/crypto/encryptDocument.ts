/**
 * Document encryption module.
 *
 * SECURITY NOTICE: Plaintext Lifecycle Responsibility
 * ====================================================
 * Callers are responsible for the lifecycle of all plaintext data.
 * This module does NOT guarantee zeroization of plaintext or key material.
 * JavaScript's garbage collector provides no memory zeroization guarantees.
 *
 * Best-effort helper functions are provided (e.g., zeroArray) but cannot
 * guarantee secure erasure from memory due to language and runtime limitations.
 */

import {
  InvalidInputError,
  UnsupportedVersionError,
  CryptoOperationError,
} from "./errors";

export interface WrappedDEK {
  version: number;
  algorithm: string;
  wrappedKey: Uint8Array;
}

export interface EncryptedPayload {
  version: number;
  wrappedDEK: WrappedDEK;
  nonce: Uint8Array;
  ciphertext: Uint8Array;
  tag: Uint8Array;
}

export { InvalidInputError, UnsupportedVersionError, CryptoOperationError };

/**
 * Overwrites array contents with zeros as a best-effort cleanup.
 *
 * IMPORTANT: This does NOT guarantee secure memory erasure.
 * JavaScript runtimes may create copies during GC or optimization.
 * Callers remain responsible for plaintext lifecycle management.
 *
 * @param buf - Array to overwrite with zeros
 */
export function zeroArray(buf: Uint8Array): void {
  for (let i = 0; i < buf.length; i++) {
    buf[i] = 0;
  }
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

function validatePlaintext(plaintext: Uint8Array): void {
  if (plaintext.byteLength === 0) {
    throw new InvalidInputError("Plaintext must not be empty");
  }
}

async function generateDEK(): Promise<CryptoKey> {
  try {
    return await crypto.subtle.generateKey(
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"]
    );
  } catch (error) {
    throw new CryptoOperationError(
      `Failed to generate DEK: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}

async function wrapDEK(dek: CryptoKey, umk: Uint8Array): Promise<WrappedDEK> {
  validateInput(umk, "UMK");
  validateKeySize(umk, 256);
  validateNonZeroKey(umk);

  try {
    const umkKey = await crypto.subtle.importKey(
      "raw",
      umk,
      { name: "AES-KW", length: 256 },
      false,
      ["wrapKey"]
    );

    const wrapped = await crypto.subtle.wrapKey(
      "raw",
      dek,
      umkKey,
      { name: "AES-KW" }
    );

    return {
      version: 1,
      algorithm: "AES-KW",
      wrappedKey: new Uint8Array(wrapped),
    };
  } catch (error) {
    if (
      error instanceof InvalidInputError ||
      error instanceof CryptoOperationError
    ) {
      throw error;
    }
    throw new CryptoOperationError(
      `Failed to wrap DEK: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}

async function encryptWithDEK(
  plaintext: Uint8Array,
  dek: CryptoKey
): Promise<{
  nonce: Uint8Array;
  ciphertext: Uint8Array;
  tag: Uint8Array;
}> {
  validateInput(plaintext, "Plaintext");
  validatePlaintext(plaintext);

  try {
    const nonce = crypto.getRandomValues(new Uint8Array(12));
    const encrypted = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv: nonce, tagLength: 128 },
      dek,
      plaintext
    );

    const encryptedArray = new Uint8Array(encrypted);
    const ciphertext = encryptedArray.slice(0, -16);
    const tag = encryptedArray.slice(-16);

    return { nonce, ciphertext, tag };
  } catch (error) {
    if (
      error instanceof InvalidInputError ||
      error instanceof CryptoOperationError
    ) {
      throw error;
    }
    throw new CryptoOperationError(
      `Failed to encrypt with DEK: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}

/**
 * Encrypts a document using envelope encryption (DEK wrapped by UMK).
 *
 * ZEROIZATION RESPONSIBILITY:
 * Callers own the plaintext lifecycle. After encryption, the caller is responsible
 * for securely disposing of the plaintext buffer. This module provides zeroArray()
 * as a best-effort helper, but JavaScript cannot guarantee memory zeroization due
 * to GC copies, optimizations, and runtime behavior. Do not rely on zeroArray()
 * for security-critical guarantees.
 *
 * CALLER RESPONSIBILITY:
 * - Plaintext lifecycle management (this function does not zero input)
 * - UMK lifecycle management (this function does not zero input)
 * - Secure disposal of sensitive data after use
 *
 * USAGE EXAMPLE:
 * ```typescript
 * const plaintext = new TextEncoder().encode("secret data");
 * const umk = await generateUMK();
 * const encrypted = await encryptDocument(plaintext, umk);
 * zeroArray(plaintext); // Best-effort cleanup (not guaranteed)
 * // plaintext should not be accessed after this point
 * ```
 *
 * @param plaintext - Document to encrypt (caller must manage lifecycle)
 * @param umk - User Master Key for wrapping DEK (caller must manage lifecycle)
 * @returns Encrypted payload containing wrapped DEK, nonce, ciphertext, and tag
 */
export async function encryptDocument(
  plaintext: Uint8Array,
  umk: Uint8Array
): Promise<EncryptedPayload> {
  validateInput(plaintext, "Plaintext");
  validatePlaintext(plaintext);
  validateInput(umk, "UMK");
  validateKeySize(umk, 256);
  validateNonZeroKey(umk);

  try {
    const dek = await generateDEK();
    const { nonce, ciphertext, tag } = await encryptWithDEK(plaintext, dek);
    const wrappedDEK = await wrapDEK(dek, umk);

    return {
      version: 1,
      wrappedDEK,
      nonce,
      ciphertext,
      tag,
    };
  } catch (error) {
    if (
      error instanceof InvalidInputError ||
      error instanceof CryptoOperationError
    ) {
      throw error;
    }
    throw new CryptoOperationError(
      `Failed to encrypt document: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}
