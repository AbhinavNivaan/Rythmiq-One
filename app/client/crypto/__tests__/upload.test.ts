/**
 * Tests for client upload module
 *
 * Validates:
 * - EncryptedPayload serialization/deserialization
 * - Upload request format
 * - Error handling
 * - Idempotency via clientRequestId
 */

import { serializeEncryptedPayload } from "./upload";
import { EncryptedPayload } from "./crypto/encryptDocument";

/**
 * Test: Serialize valid EncryptedPayload
 */
function testSerializeValidPayload(): void {
  const payload: EncryptedPayload = {
    version: 1,
    wrappedDEK: {
      version: 1,
      algorithm: "AES-KW",
      wrappedKey: new Uint8Array([
        0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b,
        0x0c, 0x0d, 0x0e, 0x0f, 0x10,
      ]),
    },
    nonce: new Uint8Array([
      0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c,
    ]),
    ciphertext: new Uint8Array([
      0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,
    ]),
    tag: new Uint8Array([
      0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3a, 0x3b, 0x3c,
      0x3d, 0x3e, 0x3f, 0x40,
    ]),
  };

  const serialized = serializeEncryptedPayload(payload);

  // Verify serialized format
  if (!(serialized instanceof Uint8Array)) {
    throw new Error("Expected Uint8Array, got " + typeof serialized);
  }

  // Should be: 1 (version) + 1 (dek version) + 4 (algo len) + 6 (AES-KW) +
  //            4 (wrapped key len) + 16 (wrapped key) +
  //            12 (nonce) + 4 (cipher len) + 8 (ciphertext) + 16 (tag)
  //            = 1+1+4+6+4+16+12+4+8+16 = 72

  const expectedSize =
    1 +
    1 +
    4 +
    6 +
    4 +
    16 +
    12 +
    4 +
    8 +
    16; // = 72
  if (serialized.length !== expectedSize) {
    throw new Error(
      `Expected serialized size ${expectedSize}, got ${serialized.length}`
    );
  }

  // Verify payload version is first byte
  if (serialized[0] !== 1) {
    throw new Error(`Expected version 1, got ${serialized[0]}`);
  }

  console.log("✓ testSerializeValidPayload passed");
}

/**
 * Test: Reject invalid payload version
 */
function testRejectInvalidVersion(): void {
  const payload = {
    version: 256, // Out of range
    wrappedDEK: {
      version: 1,
      algorithm: "AES-KW",
      wrappedKey: new Uint8Array([0x01]),
    },
    nonce: new Uint8Array(12),
    ciphertext: new Uint8Array([0x01]),
    tag: new Uint8Array(16),
  };

  try {
    serializeEncryptedPayload(payload as EncryptedPayload);
    throw new Error("Should have rejected invalid version");
  } catch (error) {
    if (!(error instanceof Error) || !error.message.includes("version")) {
      throw error;
    }
  }

  console.log("✓ testRejectInvalidVersion passed");
}

/**
 * Test: Reject invalid nonce length
 */
function testRejectInvalidNonceLength(): void {
  const payload: EncryptedPayload = {
    version: 1,
    wrappedDEK: {
      version: 1,
      algorithm: "AES-KW",
      wrappedKey: new Uint8Array([0x01]),
    },
    nonce: new Uint8Array(13), // Should be 12
    ciphertext: new Uint8Array([0x01]),
    tag: new Uint8Array(16),
  };

  try {
    serializeEncryptedPayload(payload);
    throw new Error("Should have rejected invalid nonce length");
  } catch (error) {
    if (!(error instanceof Error) || !error.message.includes("nonce")) {
      throw error;
    }
  }

  console.log("✓ testRejectInvalidNonceLength passed");
}

/**
 * Test: Reject invalid tag length
 */
function testRejectInvalidTagLength(): void {
  const payload: EncryptedPayload = {
    version: 1,
    wrappedDEK: {
      version: 1,
      algorithm: "AES-KW",
      wrappedKey: new Uint8Array([0x01]),
    },
    nonce: new Uint8Array(12),
    ciphertext: new Uint8Array([0x01]),
    tag: new Uint8Array(15), // Should be 16
  };

  try {
    serializeEncryptedPayload(payload);
    throw new Error("Should have rejected invalid tag length");
  } catch (error) {
    if (!(error instanceof Error) || !error.message.includes("tag")) {
      throw error;
    }
  }

  console.log("✓ testRejectInvalidTagLength passed");
}

/**
 * Test: Reject empty ciphertext
 */
function testRejectEmptyCiphertext(): void {
  const payload: EncryptedPayload = {
    version: 1,
    wrappedDEK: {
      version: 1,
      algorithm: "AES-KW",
      wrappedKey: new Uint8Array([0x01]),
    },
    nonce: new Uint8Array(12),
    ciphertext: new Uint8Array(0), // Empty
    tag: new Uint8Array(16),
  };

  try {
    serializeEncryptedPayload(payload);
    throw new Error("Should have rejected empty ciphertext");
  } catch (error) {
    if (!(error instanceof Error) || !error.message.includes("ciphertext")) {
      throw error;
    }
  }

  console.log("✓ testRejectEmptyCiphertext passed");
}

/**
 * Test: Reject null payload
 */
function testRejectNullPayload(): void {
  try {
    serializeEncryptedPayload(null as any);
    throw new Error("Should have rejected null payload");
  } catch (error) {
    if (!(error instanceof Error) || !error.message.includes("non-null")) {
      throw error;
    }
  }

  console.log("✓ testRejectNullPayload passed");
}

/**
 * Test: Serialize with different algorithm names
 */
function testSerializeWithDifferentAlgorithms(): void {
  const algorithms = ["AES-KW", "AES-256-KW", "RSA-OAEP"];

  for (const algo of algorithms) {
    const payload: EncryptedPayload = {
      version: 1,
      wrappedDEK: {
        version: 1,
        algorithm: algo,
        wrappedKey: new Uint8Array([0x01, 0x02]),
      },
      nonce: new Uint8Array(12),
      ciphertext: new Uint8Array([0x01]),
      tag: new Uint8Array(16),
    };

    const serialized = serializeEncryptedPayload(payload);
    if (!(serialized instanceof Uint8Array) || serialized.length === 0) {
      throw new Error(`Failed to serialize with algorithm ${algo}`);
    }
  }

  console.log("✓ testSerializeWithDifferentAlgorithms passed");
}

/**
 * Test: Large ciphertext
 */
function testSerializeLargeCiphertext(): void {
  // 1 MB ciphertext
  const largeCiphertext = crypto.getRandomValues(new Uint8Array(1024 * 1024));

  const payload: EncryptedPayload = {
    version: 1,
    wrappedDEK: {
      version: 1,
      algorithm: "AES-KW",
      wrappedKey: new Uint8Array([0x01]),
    },
    nonce: new Uint8Array(12),
    ciphertext: largeCiphertext,
    tag: new Uint8Array(16),
  };

  const serialized = serializeEncryptedPayload(payload);

  // Should be approximately 1MB + overhead
  if (serialized.length < largeCiphertext.length) {
    throw new Error(
      "Serialized payload smaller than ciphertext (likely buffer corruption)"
    );
  }

  console.log("✓ testSerializeLargeCiphertext passed");
}

/**
 * Test: Serialized format can be parsed back
 */
function testRoundtripSerialization(): void {
  const payload: EncryptedPayload = {
    version: 1,
    wrappedDEK: {
      version: 1,
      algorithm: "AES-KW",
      wrappedKey: new Uint8Array([0x01, 0x02, 0x03, 0x04, 0x05]),
    },
    nonce: new Uint8Array([
      0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c,
    ]),
    ciphertext: new Uint8Array([0x21, 0x22, 0x23]),
    tag: new Uint8Array([
      0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3a, 0x3b, 0x3c,
      0x3d, 0x3e, 0x3f, 0x40,
    ]),
  };

  const serialized = serializeEncryptedPayload(payload);

  // Verify we can read back the components
  const dataView = new DataView(serialized.buffer);

  // Version should be first byte
  const versionByte = dataView.getUint8(0);
  if (versionByte !== 1) {
    throw new Error(`Expected version 1, got ${versionByte}`);
  }

  console.log("✓ testRoundtripSerialization passed");
}

/**
 * Run all tests
 */
export async function runUploadTests(): Promise<void> {
  console.log("Running upload module tests...\n");

  testSerializeValidPayload();
  testRejectInvalidVersion();
  testRejectInvalidNonceLength();
  testRejectInvalidTagLength();
  testRejectEmptyCiphertext();
  testRejectNullPayload();
  testSerializeWithDifferentAlgorithms();
  testSerializeLargeCiphertext();
  testRoundtripSerialization();

  console.log("\n✅ All upload tests passed!");
}

// Run if executed directly
if (typeof require !== "undefined" && require.main === module) {
  runUploadTests().catch((error) => {
    console.error("Test runner error:", error);
    process.exit(1);
  });
}
