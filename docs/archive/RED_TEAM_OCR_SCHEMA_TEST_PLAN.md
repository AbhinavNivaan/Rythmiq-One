# RED TEAM TEST PLAN: OCR + SCHEMA PIPELINE

**Objective:** Validate that BLOCKER fixes are effective and regressions are prevented.

---

## TEST SUITE 1: Error Code System (B-1, B-3)

### TC-1.1: OCR Throws ProcessingError with Correct Code
```typescript
it('should throw ProcessingError with OCR_UNSUPPORTED_FORMAT code', async () => {
  const invalidPDF = Buffer.from([0x00, 0x01, 0x02]);  // Not a valid PDF
  
  try {
    await extractText(invalidPDF);
    fail('Should have thrown ProcessingError');
  } catch (error) {
    expect(error).toBeInstanceOf(ProcessingError);
    expect(error.code).toBe('OCR_UNSUPPORTED_FORMAT');
    expect(error.retryable).toBe(false);
  }
});
```

### TC-1.2: Worker Catches ProcessingError and Classifies Correctly
```typescript
it('should not retry on OCR_UNSUPPORTED_FORMAT', async () => {
  const worker = new CpuWorker({
    queue: mockQueue,
    processor: async () => {
      throw new ProcessingError('...', 'OCR_UNSUPPORTED_FORMAT', false);
    },
  });

  const result = await worker.runOnce();
  
  expect(result.state).toBe('FAILED');
  expect(result.failureReason).not.toContain('OCR_UNSUPPORTED_FORMAT');  // Code sanitized
  expect(mockQueue.markFailed).toHaveBeenCalled();
  expect(mockQueue.scheduleRetry).not.toHaveBeenCalled();
});
```

### TC-1.3: API Returns Error Code, Not Raw Message
```typescript
it('GET /jobs/:jobId should return error code, not plaintext', async () => {
  const job = await jobStore.createJob({...});
  await queue.markFailed(job.jobId, 'OCR_UNSUPPORTED_FORMAT');

  const response = await request(app).get(`/jobs/${job.jobId}`);
  
  expect(response.status).toBe(200);
  expect(response.body.error).toBe('OCR_UNSUPPORTED_FORMAT');
  expect(response.body.error).not.toContain('file format');  // No raw message
  expect(response.body.error).not.toContain('magic bytes');   // No debug info
});
```

### TC-1.4: Retry Policy Defaults to Non-Retryable
```typescript
it('should default unknown errors to non-retryable', () => {
  const policy = new RetryPolicy();
  const result = policy.classify(new Error('Unknown error'));
  
  expect(result.retryable).toBe(false);
});
```

### TC-1.5: HTTP 5xx Still Retried
```typescript
it('should retry HTTP 503', () => {
  const policy = new RetryPolicy();
  const error = new Error('Service unavailable');
  (error as any).status = 503;
  
  const result = policy.classify(error);
  expect(result.retryable).toBe(true);
});
```

---

## TEST SUITE 2: Transform Failure Handling (B-2)

### TC-2.1: Transform Error Marked as TRANSFORM_ERROR
```typescript
it('should mark transform function error as TRANSFORM_ERROR', () => {
  const schema: SchemaDefinition = {
    name: 'test',
    fields: {
      amount: {
        sourceFields: ['amount_text'],
        transform: (values) => parseInt(values[0]),  // Will throw on "123abc"
        required: true,
      },
    },
  };

  const transformer = new SchemaTransformer(schema);
  const normalized: NormalizedText = { amount_text: '123abc' };
  
  const result = transformer.transform(normalized);
  
  expect(result.success).toBe(false);
  expect(result.missing).toContain('amount');  // Required field missing
});
```

### TC-2.2: Worker Fails Job (Non-Retryable) on Transform Error
```typescript
it('should fail job (not retry) on schema transform error', async () => {
  const worker = new CpuWorker({
    queue: mockQueue,
    processor: async () => {
      // Transform crashes
      throw new ProcessingError('Amount transform failed', 'SCHEMA_TRANSFORM_ERROR', false);
    },
  });

  const result = await worker.runOnce();
  
  expect(result.state).toBe('FAILED');
  expect(mockQueue.scheduleRetry).not.toHaveBeenCalled();
  expect(mockQueue.markFailed).toHaveBeenCalledWith(
    expect.any(String),
    'SCHEMA_TRANSFORM_ERROR'  // Not raw error message
  );
});
```

### TC-2.3: Missing vs. Ambiguous vs. Transform Errors Distinct
```typescript
it('should distinguish MISSING, AMBIGUOUS, and TRANSFORM_ERROR', () => {
  const schema: SchemaDefinition = {
    name: 'test',
    fields: {
      required_field: {
        sourceFields: ['missing_source'],
        required: true,
      },
      ambiguous_field: {
        sourceFields: ['field_a', 'field_b'],
        // No transform: will be ambiguous if both present
      },
      transform_field: {
        sourceFields: ['bad_data'],
        transform: (v) => { throw new Error('Invalid'); },
        required: true,
      },
    },
  };

  const transformer = new SchemaTransformer(schema);
  const normalized = { field_a: 'value_a', field_b: 'value_b', bad_data: 'x' };
  
  const result = transformer.transform(normalized);
  
  expect(result.missing).toContain('required_field');  // MISSING
  expect(result.ambiguous).toContain('ambiguous_field');  // AMBIGUOUS
  expect(result.success).toBe(false);  // TRANSFORM_ERROR causes failure
});
```

---

## TEST SUITE 3: Determinism & Silent Failures

### TC-3.1: Identical Input Produces Identical Output
```typescript
it('should produce deterministic OCR output', async () => {
  const pdf = Buffer.from([...]);  // Valid PDF
  
  const result1 = await extractText(pdf);
  const result2 = await extractText(pdf);
  
  expect(JSON.stringify(result1)).toBe(JSON.stringify(result2));
});
```

### TC-3.2: No Plaintext in Logs
```typescript
it('should not log plaintext content', async () => {
  const consoleSpy = jest.spyOn(console, 'info');
  
  const worker = new CpuWorker({...});
  await worker.runOnce();  // Process document
  
  const logs = consoleSpy.mock.calls.map(c => JSON.stringify(c[0]));
  
  // Logs should contain jobId, timestamps, codes—not document content
  logs.forEach(log => {
    expect(log).not.toMatch(/invoice|amount|total/i);  // No domain words
    expect(log).toMatch(/jobId|timestamp|event/);  // Only metadata
  });
});
```

### TC-3.3: Silent Success Path Verified
```typescript
it('should fail fast on corrupt data, not silently accept', async () => {
  const processor = async (bytes) => {
    if (bytes.length < 10) {
      throw new ProcessingError('Corrupt data', 'OCR_CORRUPT_DATA', false);
    }
    return { /* ... */ };
  };

  const worker = new CpuWorker({ queue: mockQueue, processor });
  const result = await worker.runOnce();
  
  expect(result.state).toBe('FAILED');
  expect(result.failureReason).toBe('OCR_CORRUPT_DATA');
  expect(mockQueue.scheduleRetry).not.toHaveBeenCalled();
});
```

---

## TEST SUITE 4: Retry Safety

### TC-4.1: Retryable vs Non-Retryable Classification
```typescript
it('should classify errors correctly', () => {
  const policy = new RetryPolicy();
  
  // Non-retryable
  const formats = ['OCR_UNSUPPORTED_FORMAT', 'OCR_CORRUPT_DATA'];
  formats.forEach(code => {
    const err = new ProcessingError('...', code, false);
    expect(policy.classify(err).retryable).toBe(false);
  });

  // Retryable
  const err503 = new Error('Service unavailable');
  (err503 as any).status = 503;
  expect(policy.classify(err503).retryable).toBe(true);
});
```

### TC-4.2: Retry Limit Enforced
```typescript
it('should not retry after maxRetries exceeded', async () => {
  const policy = new RetryPolicy({ maxRetries: 2 });
  
  const decision3 = policy.decide(3, new Error('Transient error'));
  expect(decision3.shouldRetry).toBe(false);
  expect(decision3.terminal).toBe(true);
});
```

### TC-4.3: Idempotency Key Prevents Duplicate Jobs
```typescript
it('should prevent duplicate jobs with same idempotency key', async () => {
  const key = { userId: 'user1', clientRequestId: 'req-001' };
  
  const result1 = await jobStore.createJob({ blobId: 'blob1', ...key });
  const result2 = await jobStore.createJob({ blobId: 'blob2', ...key });
  
  expect(result1.jobId).toBe(result2.jobId);
  expect(result1.isNewJob).toBe(true);
  expect(result2.isNewJob).toBe(false);
});
```

---

## TEST SUITE 5: End-to-End Happy Paths

### TC-5.1: Valid Document Succeeds
```typescript
it('should process valid PDF to completion', async () => {
  const validPDF = createValidPDF();
  await blobStore.put(validPDF);
  
  const job = await jobStore.createJob({ blobId, userId });
  expect(job.isNewJob).toBe(true);

  const worker = new CpuWorker({ queue: inMemoryJobQueue });
  const result = await worker.runOnce();

  expect(result.state).toBe('SUCCEEDED');
  expect(result.ocrArtifactId).toBeDefined();
  expect(result.schemaArtifactId).toBeDefined();
  expect(result.qualityScore).toBeGreaterThan(0);
});
```

### TC-5.2: Invalid Document Fails Without Retry
```typescript
it('should fail unsupported format without retry', async () => {
  const invalidData = Buffer.from([0x00, 0x01, 0x02]);
  await blobStore.put(invalidData, { userId });

  const job = await jobStore.createJob({ blobId, userId });
  const worker = new CpuWorker({ queue: inMemoryJobQueue });
  
  const result = await worker.runOnce();

  expect(result.state).toBe('FAILED');
  expect(result.retries).toBe(0);  // No retries attempted
});
```

### TC-5.3: Transient Error Retried
```typescript
it('should retry transient errors', async () => {
  let attempt = 0;
  const processor = async () => {
    attempt++;
    if (attempt < 2) {
      const err = new Error('Temporary issue');
      (err as any).status = 503;
      throw err;
    }
    return { /* success */ };
  };

  const worker = new CpuWorker({
    queue: inMemoryJobQueue,
    processor,
    retryPolicy: new RetryPolicy({ maxRetries: 3 }),
  });

  let result1 = await worker.runOnce();
  expect(result1.state).toBe('RETRYING');

  // Wait for retry window
  await new Promise(resolve => setTimeout(resolve, 1000));

  let result2 = await worker.runOnce();
  expect(result2.state).toBe('SUCCEEDED');
});
```

---

## INTEGRATION TEST: Full Pipeline

```typescript
describe('OCR + Schema Pipeline (End-to-End)', () => {
  it('should process complex invoice without plaintext leakage', async () => {
    // Create realistic invoice PDF
    const invoice = createInvoicePDF({
      invoiceNumber: 'INV-2026-001',
      date: '2026-01-04',
      total: '$1,234.56',
    });

    // Upload
    const blobId = await blobStore.put(invoice, { userId: 'user1' });
    const job = await jobStore.createJob({
      blobId,
      userId: 'user1',
      clientRequestId: 'req-001',
    });

    // Process
    const worker = new CpuWorker({ queue: inMemoryJobQueue });
    const result = await worker.runOnce();

    // Verify: No plaintext in job state
    const jobRecord = await jobStore.getJob(job.jobId);
    expect(jobRecord.failureReason).toBeUndefined();
    expect(JSON.stringify(jobRecord)).not.toContain('INV-2026-001');

    // Verify: No plaintext in API response
    const apiResponse = await request(app).get(`/jobs/${job.jobId}`);
    expect(JSON.stringify(apiResponse.body)).not.toContain('1234.56');

    // Verify: Artifacts stored separately, not in job state
    expect(result.ocrArtifactId).toBeDefined();
    expect(result.schemaArtifactId).toBeDefined();
    
    // Artifacts contain plaintext, but job state does not
    const ocrArtifact = await blobStore.get(result.ocrArtifactId);
    expect(ocrArtifact.toString()).toContain('INV-2026-001');
  });
});
```

---

## REGRESSION TESTS (Post-Fix)

```typescript
describe('Regression Prevention', () => {
  it('[B-1] Error messages never leak to API', async () => {
    // Any error code thrown by processors should sanitize before API return
  });

  it('[B-2] Transform errors fail job, not marked ambiguous', async () => {
    // Verify transform crashes always result in FAILED state, not partial success
  });

  it('[B-3] Unsupported formats not retried', async () => {
    // Verify OCR_UNSUPPORTED_FORMAT is terminal, 0 retries
  });

  it('[A-1] OCR output deterministic', async () => {
    // Identical input always produces identical output
  });

  it('[A-2] Offset maps consistent', async () => {
    // Offset tracking doesn't corrupt through transformations
  });
});
```

---

## COVERAGE MATRIX

| Test ID | BLOCKER | Category | Status |
|---------|---------|----------|--------|
| TC-1.1 | B-1 | Error Codes | ✗ Create |
| TC-1.2 | B-1, B-3 | Worker Classify | ✗ Create |
| TC-1.3 | B-1 | API Sanitization | ✗ Create |
| TC-1.4 | B-3 | Retry Default | ✗ Create |
| TC-1.5 | B-3 | Retry HTTP | ✗ Create |
| TC-2.1 | B-2 | Transform Error | ✗ Create |
| TC-2.2 | B-2 | Worker Failure | ✗ Create |
| TC-2.3 | B-2 | Failure Types | ✗ Create |
| TC-3.1 | A-1 | Determinism | ✓ Exists |
| TC-3.2 | B-1 | Log Leakage | ✗ Create |
| TC-3.3 | B-2 | Silent Failures | ✗ Create |
| TC-4.1 | B-3 | Classification | ✗ Create |
| TC-4.2 | B-3 | Retry Limit | ✗ Create |
| TC-4.3 | D-2 | Idempotency | ✓ Partial |
| TC-5.1 | All | Happy Path | ✗ Create |
| TC-5.2 | B-1, B-3 | Fail Fast | ✗ Create |
| TC-5.3 | B-3 | Retry Logic | ✗ Create |

---

## EXECUTION PLAN

1. **Phase 1:** Implement fixes for B-1, B-2, B-3
2. **Phase 2:** Run Test Suite 1-5 (all should pass)
3. **Phase 3:** Run Regression Tests (no regressions)
4. **Phase 4:** Merge to main with full coverage report

---
