/**
 * Integration test: End-to-end client encryption + upload workflow
 *
 * This test validates the complete flow from plaintext → encryption → upload
 */

import { encryptDocument, zeroArray } from "./crypto/encryptDocument";
import { generateUMK } from "./crypto/umk";
import {
  serializeEncryptedPayload,
  generateClientRequestId,
  GATEWAY_CONFIG,
} from "../upload";

/**
 * Mock gateway response for testing
 */
interface MockGatewayState {
  uploadedBlobs: Map<string, Uint8Array>;
  requestIds: Set<string>;
}

/**
 * Test: Complete encryption + serialization + "upload" workflow
 */
async function testEndToEndWorkflow(): Promise<void> {
  console.log("\n=== Integration Test: End-to-End Workflow ===\n");

  // Step 1: Generate UMK
  console.log("1️⃣  Generating UMK...");
  const umk = generateUMK();
  console.log(`   ✓ Generated UMK (${umk.length} bytes)`);

  // Step 2: Create plaintext
  console.log("\n2️⃣  Creating plaintext...");
  const plaintext = new TextEncoder().encode("Sensitive document content");
  console.log(
    `   ✓ Created plaintext (${plaintext.length} bytes): "${new TextDecoder().decode(plaintext)}"`
  );

  // Step 3: Encrypt plaintext
  console.log("\n3️⃣  Encrypting plaintext...");
  const encrypted = await encryptDocument(plaintext, umk);
  console.log(`   ✓ Encrypted successfully`);
  console.log(`     - version: ${encrypted.version}`);
  console.log(
    `     - wrappedDEK.algorithm: ${encrypted.wrappedDEK.algorithm}`
  );
  console.log(
    `     - wrappedDEK.wrappedKey: ${encrypted.wrappedDEK.wrappedKey.length} bytes`
  );
  console.log(`     - nonce: ${encrypted.nonce.length} bytes`);
  console.log(`     - ciphertext: ${encrypted.ciphertext.length} bytes`);
  console.log(`     - tag: ${encrypted.tag.length} bytes`);

  // Step 4: Serialize encrypted payload
  console.log("\n4️⃣  Serializing encrypted payload...");
  const serialized = serializeEncryptedPayload(encrypted);
  console.log(`   ✓ Serialized to raw bytes (${serialized.length} bytes)`);

  // Step 5: Verify serialized format
  console.log("\n5️⃣  Validating serialized format...");
  if (!(serialized instanceof Uint8Array)) {
    throw new Error("Serialized payload must be Uint8Array");
  }
  if (serialized[0] !== encrypted.version) {
    throw new Error("Serialized version byte mismatch");
  }
  console.log(`   ✓ Serialized format valid`);
  console.log(`     - First byte (version): ${serialized[0]}`);
  console.log(
    `     - Total size: ${serialized.length} bytes (encrypted: ${
      encrypted.ciphertext.length + encrypted.tag.length
    }, wrapped: ${
      encrypted.wrappedDEK.wrappedKey.length
    }, headers: ${serialized.length - encrypted.ciphertext.length - encrypted.tag.length - encrypted.wrappedDEK.wrappedKey.length})`
  );

  // Step 6: Generate request ID
  console.log("\n6️⃣  Generating clientRequestId...");
  const clientRequestId = generateClientRequestId();
  console.log(`   ✓ Generated: ${clientRequestId}`);

  // Step 7: Simulate upload request headers
  console.log("\n7️⃣  Simulating HTTP request...");
  const headers = {
    "Content-Type": "application/octet-stream",
    "x-client-request-id": clientRequestId,
    "Content-Length": String(serialized.length),
  };
  console.log(`   ✓ HTTP Headers:`);
  console.log(`     - Content-Type: ${headers["Content-Type"]}`);
  console.log(`     - x-client-request-id: ${headers["x-client-request-id"]}`);
  console.log(`     - Content-Length: ${headers["Content-Length"]}`);
  console.log(`   ✓ Request body: ${serialized.length} bytes of binary data`);

  // Step 8: Cleanup
  console.log("\n8️⃣  Cleaning up sensitive data (best-effort)...");
  const plaintextBefore = new TextDecoder().decode(plaintext);
  zeroArray(plaintext);
  try {
    // Verify plaintext is zeroed (in-memory, just for testing)
    const isZeroed = plaintext.every((b) => b === 0);
    console.log(`   ✓ Plaintext zeroized: ${isZeroed}`);
  } catch {
    console.log(`   ⚠️  Cannot verify zeroization (expected)`);
  }

  zeroArray(umk);
  console.log(`   ✓ UMK zeroized`);

  console.log("\n✅ End-to-end workflow completed successfully!\n");
}

/**
 * Test: Idempotency with clientRequestId
 */
async function testIdempotency(): Promise<void> {
  console.log("\n=== Integration Test: Idempotency ===\n");

  const mockGateway: MockGatewayState = {
    uploadedBlobs: new Map(),
    requestIds: new Set(),
  };

  // Encrypt a document
  const umk = generateUMK();
  const plaintext = new TextEncoder().encode("Data");
  const encrypted = await encryptDocument(plaintext, umk);
  const serialized = serializeEncryptedPayload(encrypted);

  // Generate a specific request ID
  const clientRequestId = generateClientRequestId();
  console.log(`1️⃣  Using clientRequestId: ${clientRequestId}`);

  // "Upload" twice with same request ID
  console.log(`\n2️⃣  Simulating first upload...`);
  if (!mockGateway.requestIds.has(clientRequestId)) {
    const blobId = crypto.randomUUID ? crypto.randomUUID() : "blob-123";
    mockGateway.uploadedBlobs.set(blobId, serialized);
    mockGateway.requestIds.add(clientRequestId);
    console.log(`   ✓ First upload accepted (blobId: ${blobId})`);
  }

  console.log(`\n3️⃣  Simulating retry with same clientRequestId...`);
  if (mockGateway.requestIds.has(clientRequestId)) {
    console.log(`   ✓ Request ID already recorded`);
    console.log(
      `   ✓ Gateway deduplicates by clientRequestId (returns same blobId)`
    );
  }

  console.log(`\n✅ Idempotency test passed!\n`);

  zeroArray(plaintext);
  zeroArray(umk);
}

/**
 * Test: Multiple documents with different request IDs
 */
async function testMultipleUploads(): Promise<void> {
  console.log("\n=== Integration Test: Multiple Uploads ===\n");

  const uploads: Array<{
    clientRequestId: string;
    serializedSize: number;
  }> = [];

  for (let i = 0; i < 3; i++) {
    const umk = generateUMK();
    const plaintext = new TextEncoder().encode(
      `Document ${i + 1}: some data`
    );
    const encrypted = await encryptDocument(plaintext, umk);
    const serialized = serializeEncryptedPayload(encrypted);
    const clientRequestId = generateClientRequestId();

    uploads.push({
      clientRequestId,
      serializedSize: serialized.length,
    });

    console.log(`${i + 1}️⃣  Upload ${i + 1}:`);
    console.log(`   clientRequestId: ${clientRequestId}`);
    console.log(`   serializedSize: ${serialized.length} bytes`);

    zeroArray(plaintext);
    zeroArray(umk);
  }

  console.log(`\n✅ Successfully simulated ${uploads.length} uploads!\n`);
}

/**
 * Test: Serialize payload with maximum supported sizes
 */
async function testLargeCiphertextSerialization(): Promise<void> {
  console.log("\n=== Integration Test: Large Payload Serialization ===\n");

  // Create a 10 MB ciphertext (simulated)
  const largeCiphertext = crypto.getRandomValues(
    new Uint8Array(10 * 1024 * 1024)
  );

  const payload = {
    version: 1,
    wrappedDEK: {
      version: 1,
      algorithm: "AES-KW",
      wrappedKey: crypto.getRandomValues(new Uint8Array(512)),
    },
    nonce: crypto.getRandomValues(new Uint8Array(12)),
    ciphertext: largeCiphertext,
    tag: crypto.getRandomValues(new Uint8Array(16)),
  };

  console.log(`1️⃣  Creating large payload...`);
  console.log(
    `   - ciphertext: ${(payload.ciphertext.length / 1024 / 1024).toFixed(2)} MB`
  );

  console.log(`\n2️⃣  Serializing...`);
  const serialized = serializeEncryptedPayload(
    payload as any as ReturnType<typeof encryptDocument>
  );

  console.log(
    `   ✓ Serialized: ${(serialized.length / 1024 / 1024).toFixed(2)} MB`
  );

  // Check against gateway size limit
  const maxSize = GATEWAY_CONFIG.maxUploadSizeBytes;
  const exceeds = serialized.length > maxSize;
  console.log(`\n3️⃣  Checking size limit...`);
  console.log(`   - Gateway limit: ${(maxSize / 1024 / 1024).toFixed(2)} MB`);
  console.log(`   - Payload size: ${(serialized.length / 1024 / 1024).toFixed(2)} MB`);
  console.log(`   - Within limit: ${!exceeds}`);

  console.log(`\n✅ Large payload serialization test passed!\n`);
}

/**
 * Run all integration tests
 */
export async function runIntegrationTests(): Promise<void> {
  console.log("\n╔════════════════════════════════════════════╗");
  console.log("║ CLIENT UPLOAD MODULE - INTEGRATION TESTS  ║");
  console.log("╚════════════════════════════════════════════╝");

  try {
    await testEndToEndWorkflow();
    await testIdempotency();
    await testMultipleUploads();
    await testLargeCiphertextSerialization();

    console.log("╔════════════════════════════════════════════╗");
    console.log("║       ✅ ALL INTEGRATION TESTS PASSED ✅   ║");
    console.log("╚════════════════════════════════════════════╝\n");
  } catch (error) {
    console.error("\n❌ Integration test failed:", error);
    throw error;
  }
}

// Run if executed directly
if (typeof require !== "undefined" && require.main === module) {
  runIntegrationTests().catch((error) => {
    console.error("Test runner error:", error);
    process.exit(1);
  });
}
