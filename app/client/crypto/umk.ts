import { InvalidInputError, CryptoOperationError } from "./errors";

export function generateUMK(): Uint8Array {
  try {
    const umk = new Uint8Array(32);
    crypto.getRandomValues(umk);

    const isAllZero = umk.every((byte) => byte === 0);
    if (isAllZero) {
      throw new InvalidInputError("Generated UMK must not be all zeros");
    }

    return umk;
  } catch (error) {
    if (error instanceof InvalidInputError) {
      throw error;
    }
    throw new CryptoOperationError(
      `Failed to generate UMK: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}

export function importUMKAsNonExtractable(
  umk: Uint8Array
): Promise<CryptoKey> {
  if (umk === null || umk === undefined) {
    throw new InvalidInputError("UMK must not be null or undefined");
  }
  if (!(umk instanceof Uint8Array)) {
    throw new InvalidInputError("UMK must be a Uint8Array");
  }
  if (umk.byteLength !== 32) {
    throw new InvalidInputError(
      `UMK must be exactly 256 bits (32 bytes), got ${umk.byteLength} bytes`
    );
  }

  const isAllZero = umk.every((byte) => byte === 0);
  if (isAllZero) {
    throw new InvalidInputError("UMK must not be all zeros");
  }

  try {
    return crypto.subtle.importKey(
      "raw",
      umk,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"]
    );
  } catch (error) {
    throw new CryptoOperationError(
      `Failed to import UMK as non-extractable key: ${error instanceof Error ? error.message : String(error)}`
    );
  }
}
