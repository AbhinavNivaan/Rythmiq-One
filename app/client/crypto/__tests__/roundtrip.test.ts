import { generateUMK } from "../umk";
import { encryptDocument, EncryptedPayload } from "../encryptDocument";
import { decryptDocument } from "../decryptDocument";

/**
 * Minimal test harness for roundtrip encrypt/decrypt
 */

interface TestResult {
  name: string;
  passed: boolean;
  error?: string;
}

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

function bytesEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

async function testRoundtrip(): Promise<TestResult> {
  try {
    // Generate UMK
    const umk = generateUMK();
    assert(umk instanceof Uint8Array, "UMK should be Uint8Array");
    assert(umk.byteLength === 32, "UMK should be 32 bytes");

    // Create random plaintext
    const plaintext = new Uint8Array(256);
    crypto.getRandomValues(plaintext);

    // Encrypt
    const encrypted: EncryptedPayload = await encryptDocument(plaintext, umk);
    assert(encrypted.version !== undefined, "Payload should have version");
    assert(encrypted.wrappedDEK instanceof Object, "Wrapped DEK should be an object");
    assert(encrypted.wrappedDEK.version !== undefined, "Wrapped DEK should have version");
    assert(typeof encrypted.wrappedDEK.algorithm === "string", "Algorithm should be string");
    assert(encrypted.wrappedDEK.wrappedKey instanceof Uint8Array, "Wrapped key should be Uint8Array");
    assert(encrypted.nonce instanceof Uint8Array, "Nonce should be Uint8Array");
    assert(encrypted.ciphertext instanceof Uint8Array, "Ciphertext should be Uint8Array");
    assert(encrypted.tag instanceof Uint8Array, "Tag should be Uint8Array");

    // Decrypt
    const decrypted = await decryptDocument(encrypted, umk);

    // Assert byte equality
    assert(
      bytesEqual(plaintext, decrypted),
      "Decrypted plaintext should equal original plaintext"
    );

    return {
      name: "Roundtrip encrypt/decrypt with random bytes",
      passed: true,
    };
  } catch (error) {
    return {
      name: "Roundtrip encrypt/decrypt with random bytes",
      passed: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

async function runTests(): Promise<void> {
  console.log("Running crypto roundtrip tests...\n");

  const result = await testRoundtrip();

  if (result.passed) {
    console.log(`✓ ${result.name}`);
  } else {
    console.log(`✗ ${result.name}`);
    console.log(`  Error: ${result.error}`);
  }

  const allPassed = result.passed;
  console.log(`\n${allPassed ? "All tests passed" : "Tests failed"}`);
  process.exit(allPassed ? 0 : 1);
}

// Run tests if executed directly
runTests().catch((error) => {
  console.error("Test runner error:", error);
  process.exit(1);
});
