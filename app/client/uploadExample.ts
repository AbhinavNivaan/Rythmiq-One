/**
 * Example: Client-side encryption and upload workflow
 *
 * SECURITY NOTICE:
 * The server treats uploads as opaque bytes and CANNOT verify encryption.
 * Encryption verification happens only at the processing engine with UMK.
 */

import { encryptDocument, zeroArray } from "./crypto/encryptDocument";
import { generateUMK } from "./crypto/umk";
import {
  uploadEncryptedPayload,
  generateClientRequestId,
} from "./upload";

/**
 * Example workflow: Encrypt plaintext and upload to gateway
 */
export async function encryptAndUpload(plaintext: Uint8Array): Promise<void> {
  let umk: Uint8Array | null = null;

  try {
    // Step 1: Generate UMK (user must store this securely)
    umk = generateUMK();
    console.log("Generated UMK (32 bytes)");

    // Step 2: Encrypt plaintext with UMK
    const encrypted = await encryptDocument(plaintext, umk);
    console.log("Encrypted payload:", {
      version: encrypted.version,
      wrappedDEK: {
        version: encrypted.wrappedDEK.version,
        algorithm: encrypted.wrappedDEK.algorithm,
        wrappedKeyLength: encrypted.wrappedDEK.wrappedKey.length,
      },
      nonceLength: encrypted.nonce.length,
      ciphertextLength: encrypted.ciphertext.length,
      tagLength: encrypted.tag.length,
    });

    // Step 3: Generate unique request ID for idempotency
    const clientRequestId = generateClientRequestId();
    console.log("Generated clientRequestId:", clientRequestId);

    // Step 4: Upload encrypted payload to gateway
    const uploadResult = await uploadEncryptedPayload(
      encrypted,
      clientRequestId
    );

    if (uploadResult.success) {
      console.log("Upload successful:", {
        blobId: uploadResult.response.blobId,
        uploadedBytes: uploadResult.response.uploadedBytes,
      });
    } else {
      console.error("Upload failed:", uploadResult.error);
    }
  } finally {
    // Step 5: Securely dispose of UMK
    // Note: This is best-effort; JavaScript cannot guarantee memory zeroization
    if (umk) {
      zeroArray(umk);
      console.log("Zeroized UMK (best-effort)");
    }

    // Step 6: Securely dispose of plaintext
    // Note: This is best-effort; JavaScript cannot guarantee memory zeroization
    zeroArray(plaintext);
    console.log("Zeroized plaintext (best-effort)");
  }
}

/**
 * Example: Handle upload with custom configuration and retry policy
 */
export async function uploadWithCustomConfig(
  plaintext: Uint8Array
): Promise<void> {
  let umk: Uint8Array | null = null;

  try {
    umk = generateUMK();
    const encrypted = await encryptDocument(plaintext, umk);

    // Generate unique request ID (for idempotency)
    const clientRequestId = generateClientRequestId();

    // Custom gateway configuration
    const uploadResult = await uploadEncryptedPayload(
      encrypted,
      clientRequestId,
      {
        baseUrl: "https://gateway.example.com",
        maxRetries: 5,
        retryDelayMs: 500,
      }
    );

    if (!uploadResult.success) {
      // Handle specific error types
      if (uploadResult.error.status === 413) {
        console.error("Payload too large");
      } else if (uploadResult.error.status === 400) {
        console.error("Invalid payload:", uploadResult.error.message);
      } else if (uploadResult.error.status >= 500) {
        console.error("Server error (may retry):", uploadResult.error.message);
      } else if (uploadResult.error.status === 0) {
        console.error("Network error:", uploadResult.error.message);
      } else {
        console.error("Upload error:", uploadResult.error);
      }
    }
  } finally {
    if (umk) {
      zeroArray(umk);
    }
    zeroArray(plaintext);
  }
}

/**
 * Example: Idempotent upload with client-side request tracking
 */
export async function idempotentUpload(
  plaintext: Uint8Array,
  requestIdStorage: Map<string, boolean>
): Promise<string | null> {
  let umk: Uint8Array | null = null;

  try {
    umk = generateUMK();
    const encrypted = await encryptDocument(plaintext, umk);

    // Check if we've already attempted this upload
    const clientRequestId = generateClientRequestId();

    // Only proceed if we haven't tried this request ID before
    if (requestIdStorage.has(clientRequestId)) {
      console.log("Request already in flight, skipping upload");
      return null;
    }

    requestIdStorage.set(clientRequestId, true);

    const uploadResult = await uploadEncryptedPayload(
      encrypted,
      clientRequestId
    );

    if (uploadResult.success) {
      console.log("Upload successful, blobId:", uploadResult.response.blobId);
      return uploadResult.response.blobId;
    } else {
      // Log error but return null
      console.error("Upload failed:", uploadResult.error);
      return null;
    }
  } finally {
    if (umk) {
      zeroArray(umk);
    }
    zeroArray(plaintext);
  }
}
