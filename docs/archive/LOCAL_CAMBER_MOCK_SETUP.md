# Local Camber Mock Setup Guide

**Status**: ✅ Implemented  
**Environment**: `EXECUTION_BACKEND=local` or `SERVICE_ENV=dev`  
**Purpose**: Deterministic E2E testing without real Camber calls

---

## Architecture Overview

### In-Process Mock (Recommended)

```
┌─────────────────────────────────────────────────────┐
│ FastAPI API Server (uvicorn)                        │
├─────────────────────────────────────────────────────┤
│                                                     │
│  POST /jobs                                         │
│    ├─ Validate input                                │
│    ├─ Create job record (status=pending)            │
│    └─ Call get_camber_service()                     │
│           │                                         │
│           ├─ Check EXECUTION_BACKEND=local?         │
│           │     YES → return MockCamberClient       │
│           │     NO  → return real CamberService     │
│           │                                         │
│           └─ submit_job() [RETURNS IMMEDIATELY]    │
│                 │                                   │
│                 └─ Background task spawned          │
│                      │                              │
│                      ├─ Load job payload            │
│                      ├─ Mock worker execution       │
│                      │   (FETCH→OCR→NORMALIZE)     │
│                      │                              │
│                      └─ POST /internal/webhooks/    │
│                         camber (with signature)     │
│                         │                           │
│                         └─ webhook_camber()         │
│                            ├─ Verify signature      │
│                            ├─ Update job state      │
│                            ├─ Package artifacts     │
│                            └─ Return 200 OK         │
│                                                     │
└─────────────────────────────────────────────────────┘

Key benefits over external HTTP server:
- No network latency (deterministic)
- Runs in same Python process
- Easy to inspect/mock for testing
- No separate container/service
- Full control over timing & failure modes
```

**Why NOT an external mock HTTP server?**

| Aspect | External Server | In-Process Mock |
|--------|-----------------|-----------------|
| **Startup** | Slow, extra Docker container | Instant with API |
| **Latency** | 10-50ms network overhead | <1ms |
| **Flakiness** | Network timeouts, port conflicts | Zero network deps |
| **Debugging** | Hard to inspect internal state | Direct access to objects |
| **Parallelism** | Hard to run tests concurrently | Full async/await support |
| **Test isolation** | Shared state across tests | Per-test instance |
| **Production parity** | No (extra network layer) | Yes (exact same code paths) |

---

## Files Added/Modified

### NEW: MockCamberClient

**File**: `app/api/services/mock_camber_client.py`

Implements `submit_job()` and `get_job_status()` interface (same as real `CamberService`).

**Key methods**:
- `submit_job(job_id, payload)` → returns mock camber_job_id (instant, non-blocking)
- `_process_job_async()` → background task that simulates processing
- `_generate_success_result()` → mock worker output (structured data)
- `_generate_failure_result()` → mock error response
- `_send_webhook()` → POST back to `/internal/webhooks/camber` with signature

**Gating**:
```python
# Only activated when:
if settings.execution_backend.lower() == "local":
    client = MockCamberClient(settings)
else:
    client = CamberService(settings)  # Real Camber
```

### MODIFIED: CamberService Factory

**File**: `app/api/services/camber.py`

Updated `get_camber_service()` to check `EXECUTION_BACKEND`:

```python
def get_camber_service() -> CamberService:
    """
    Factory: Get singleton instance.
    
    IF EXECUTION_BACKEND == "local":
        return MockCamberClient  # In-process mock
    ELSE:
        return CamberService     # Real Camber API
    """
    if settings.execution_backend.lower() == "local":
        from app.api.services.mock_camber_client import MockCamberClient
        return MockCamberClient(settings)
    else:
        return CamberService(settings)
```

**Why a factory?**
- NO scattered conditionals throughout code
- ONE clean entry point
- Both classes implement same interface
- Easy to swap implementations
- Backwards compatible with real Camber

### NEW: End-to-End Test Suite

**File**: `tests/test_e2e_pipeline.py`

Tests include:
- ✅ Mock client returns immediately (non-blocking)
- ✅ Webhook payload generation (required fields, structure)
- ✅ Factory gating (local vs. camber backend selection)
- ✅ Job state transitions (pending → processing → completed)
- ✅ Idempotency (webhook replay safety)
- ✅ Error propagation (failure webhooks)
- ✅ Concurrent job handling (multiple jobs in parallel)
- ✅ Performance (< 100ms job execution)

---

## Environment Variables

### Required for Local Mock

```bash
# Enable local mock instead of real Camber
EXECUTION_BACKEND=local

# Mock still needs these (for webhook signature generation)
WEBHOOK_SECRET=your-test-secret-here

# Not used by mock, but required for app startup
CAMBER_API_KEY=mock-key-unused
CAMBER_API_ENDPOINT=https://api.mock.local
CAMBER_APP_NAME=mock-app

# Service environment
SERVICE_ENV=dev
```

### Switching to Real Camber

```bash
EXECUTION_BACKEND=camber
CAMBER_API_KEY=<your-real-camber-key>
CAMBER_API_ENDPOINT=https://api.camber.cloud
CAMBER_APP_NAME=<your-real-app-name>
```

---

## Webhook Callback Format

### Example Success Webhook (Auto-Generated by Mock)

```json
POST /internal/webhooks/camber
X-Webhook-Secret: <hmac-sha256-signature>

{
  "camber_job_id": "mock-550e8400",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "success",
  "timestamp": "2026-01-26T10:30:45.123456",
  "result": {
    "status": "SUCCESS",
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "result": {
      "structured": {
        "field_1": "mock_value_1",
        "field_2": "mock_value_2"
      },
      "confidence": {
        "field_1": 0.95,
        "field_2": 0.87
      },
      "quality_score": 0.92,
      "page_count": 1,
      "processing_time_ms": 150
    }
  }
}
```

### Example Failure Webhook

```json
{
  "camber_job_id": "mock-550e8400",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "timestamp": "2026-01-26T10:30:45.123456",
  "result": {
    "status": "FAILED",
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "error": {
      "code": "OCR_FAILURE",
      "stage": "OCR",
      "details": {
        "reason": "No text detected in image"
      }
    }
  }
}
```

### Signature Verification

Webhook signature is computed:
```python
import hmac
import hashlib

secret = settings.webhook_secret.encode()
payload_json = json.dumps(webhook_payload, separators=(",", ":"))
signature = hmac.new(secret, payload_json.encode(), hashlib.sha256).hexdigest()
```

Verify using constant-time comparison:
```python
if not hmac.compare_digest(received_signature, expected_signature):
    raise WebhookAuthException("Invalid webhook signature")
```

---

## Usage: Running Tests

### All Mock Tests

```bash
pytest tests/test_e2e_pipeline.py -v
```

### Specific Test

```bash
pytest tests/test_e2e_pipeline.py::test_mock_client_submit_returns_immediately -v
```

### With Logging

```bash
pytest tests/test_e2e_pipeline.py -v --log-cli-level=DEBUG
```

### With Coverage

```bash
pytest tests/test_e2e_pipeline.py --cov=app/api/services --cov-report=html
```

---

## Usage: Development Server

### Start API with Local Mock

```bash
export EXECUTION_BACKEND=local
export WEBHOOK_SECRET=dev-secret-12345
export SERVICE_ENV=dev

uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload
```

### Create a Job (Manual)

```bash
# 1. Create job
curl -X POST http://127.0.0.1:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "portal_schema_name": "invoice",
    "filename": "test.pdf",
    "mime_type": "application/pdf",
    "file_size_bytes": 50000
  }'

# Response:
# {
#   "job_id": "550e8400-e29b-41d4-a716-446655440000",
#   "status": "pending",
#   "upload_url": "s3://signed-url..."
# }

# 2. Wait ~1 second for mock webhook
sleep 1

# 3. Check job status
curl http://127.0.0.1:8000/jobs/550e8400-e29b-41d4-a716-446655440000

# Response:
# {
#   "job_id": "550e8400-e29b-41d4-a716-446655440000",
#   "status": "completed",
#   "result": {...}
# }
```

---

## Verification Checklist

- [ ] **Mock enabled**: `EXECUTION_BACKEND=local` in `.env`
- [ ] **Webhook secret set**: `WEBHOOK_SECRET=<value>` in `.env`
- [ ] **Imports work**: `from app.api.services.mock_camber_client import MockCamberClient`
- [ ] **Factory returns mock**: `get_camber_service()` returns `MockCamberClient` instance
- [ ] **API boots cleanly**: `uvicorn app.api.main:app --reload`
- [ ] **Job creation works**: `POST /jobs` returns `job_id` and `upload_url`
- [ ] **Webhook delivered**: Check logs for `[MOCK CAMBER] webhook delivered`
- [ ] **Job completes**: `GET /jobs/{job_id}` returns `status=completed`
- [ ] **Artifacts exist**: Output files are in artifact store
- [ ] **DB transitions work**: Job record shows state progression
- [ ] **Tests pass**: `pytest tests/test_e2e_pipeline.py -v`
- [ ] **Idempotency works**: Webhook can be replayed without side effects
- [ ] **Real Camber still works**: Switch `EXECUTION_BACKEND=camber` - no code changes needed

---

## Troubleshooting

### "MockCamberClient not found" import error

**Cause**: Import happening before factory check  
**Fix**: Use factory pattern (`get_camber_service()`) - don't import directly

### Webhook returns 404

**Cause**: API endpoint not running, or port mismatch  
**Fix**: Ensure API is running on `api_port` in settings (default: 8000)

### Webhook signature verification fails

**Cause**: `WEBHOOK_SECRET` doesn't match between mock and API  
**Fix**: Ensure same secret in both places:
```bash
# Set once globally
export WEBHOOK_SECRET=your-secret
# Both API and mock will use it
```

### Job never completes

**Cause**: Background task not awaited, event loop issue  
**Fix**: Mock spawns tasks using `asyncio.create_task()` - works inside uvicorn

### Real Camber calls when EXECUTION_BACKEND=local

**Cause**: Singleton caching - old instance not cleared  
**Fix**: Restart API:
```bash
# Kill and restart
kill %1  # or Ctrl+C
uvicorn app.api.main:app --reload
```

---

## Design Decisions

### 1. In-Process vs. External HTTP Server

**Decision**: In-process mock

**Rationale**:
- Deterministic (no network jitter)
- Fast (instant execution)
- Easy to test (direct object inspection)
- Simpler CI/CD (no extra containers)
- Same code path as real integration

### 2. Background Task Spawning

**Decision**: `asyncio.create_task()` in `submit_job()`

**Rationale**:
- Non-blocking (submit returns immediately)
- Runs inside FastAPI's event loop
- Properly integrated with uvicorn lifecycle
- Allows concurrent job execution

### 3. Webhook Signature Format

**Decision**: HMAC-SHA256 (same as real Camber)

**Rationale**:
- Reuses existing signature verification code
- No "mock-only" logic in webhook handler
- Ensures parity with production behavior
- Allows testing webhook auth paths

### 4. Factory Pattern

**Decision**: Single factory entry point (`get_camber_service()`)

**Rationale**:
- No scattered conditionals in business logic
- Both implementations have same interface
- Easy to extend to other backends
- Backwards compatible
- Single responsibility (client selection)

---

## Next Steps

1. **Database Integration**: Replace file-based mock with Supabase for state persistence
2. **Failure Simulation**: Add environment variables to trigger specific failure modes
3. **Metrics**: Track mock execution times, webhook latency
4. **Test Data**: Pre-populate with realistic OCR results
5. **CI/CD Integration**: Run full E2E suite in GitHub Actions

---

## References

- [FastAPI Testing](https://fastapi.tiangolo.com/advanced/testing-dependencies/)
- [AsyncIO Best Practices](https://docs.python.org/3/library/asyncio.html)
- [HMAC Signature Verification](https://en.wikipedia.org/wiki/HMAC)
- [Job Lifecycle Design](./docs/e2e-run.md)
- [Webhook Handler](./app/api/routes/webhooks.py)
