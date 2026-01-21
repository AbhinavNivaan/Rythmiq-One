/**
 * E2E Test Script - Stage-2 OCR Validation
 * 
 * This script:
 * 1. Creates a job from the test invoice image
 * 2. Runs the CPU worker to process it with real Tesseract OCR
 * 3. Outputs the results
 */

import * as fs from 'fs';
import * as path from 'path';
import { cpuWorker } from '../engine/cpu/worker';
import { blobStore } from '../engine/storage/blobStore';
import { jobStore } from '../engine/jobs/jobStore';

async function runE2ETest() {
    console.log('=== Stage-2 OCR E2E Test ===\n');

    // 1. Load test invoice image
    const testImagePath = path.join(__dirname, 'test_invoice.png');
    if (!fs.existsSync(testImagePath)) {
        console.error('ERROR: Test invoice not found at:', testImagePath);
        process.exit(1);
    }

    const imageBytes = fs.readFileSync(testImagePath);
    console.log(`✓ Loaded test invoice (${imageBytes.length} bytes)`);

    // 2. Store the image in blob store
    const blobId = blobStore.put(imageBytes, {
        size: imageBytes.length,
        userId: 'test-user',
        timestamp: Date.now(),
    });
    console.log(`✓ Stored blob: ${blobId}`);

    // 3. Create job via jobStore (handles both queue and store registration)
    const jobResult = await jobStore.createJob({
        blobId,
        userId: 'test-user',
        clientRequestId: `e2e-test-${Date.now()}`,
        schemaId: 'invoice',
        schemaVersion: 'v1',
    });
    console.log(`✓ Created job: ${jobResult.jobId} (new: ${jobResult.isNewJob})`);

    // 4. Run worker to process the job
    console.log('\n--- Running OCR + Schema Transform ---\n');
    const startTime = Date.now();

    const result = await cpuWorker.runOnce();

    const processingTime = Date.now() - startTime;
    console.log(`\n--- Processing completed in ${processingTime}ms ---\n`);

    if (!result) {
        console.error('ERROR: No job was processed');
        process.exit(1);
    }

    // 5. Display results
    console.log('Job State:', result.state);

    if (result.state === 'SUCCEEDED') {
        console.log('\n✓ SUCCESS! OCR and schema transform completed.\n');
        console.log('Quality Score:', result.qualityScore);
        console.log('OCR Artifact ID:', result.ocrArtifactId);
        console.log('Schema Artifact ID:', result.schemaArtifactId);

        // Retrieve schema output
        if (result.schemaArtifactId) {
            const schemaArtifact = blobStore.get(result.schemaArtifactId);
            if (schemaArtifact) {
                const schemaOutput = JSON.parse(schemaArtifact.toString());
                console.log('\n--- Extracted Data ---');
                console.log(JSON.stringify(schemaOutput, null, 2));
            }
        }
    } else if (result.state === 'FAILED') {
        console.log('\n✗ FAILED');
        console.log('Error Code:', result.errorCode);
        console.log('Retryable:', result.retryable);
    } else {
        console.log('Unexpected state:', result.state);
    }

    console.log('\n=== Test Complete ===');
}

runE2ETest().catch(err => {
    console.error('Test failed with error:', err);
    process.exit(1);
});
