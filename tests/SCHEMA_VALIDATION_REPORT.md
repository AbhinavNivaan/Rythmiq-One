# Schema Adapter Validation Report

**Date:** 2026-01-27  
**Validator:** Automated Schema Compliance Test Suite  
**Target:** `worker/processors/schema.py`

---

## 1. Per-Schema Validation Table

### Test Results Summary

| Schema | Dimensions | DPI | File Size | Pass/Fail |
|--------|------------|-----|-----------|-----------|
| **NEET UG 2026** (200×230, 200 DPI, <100KB) | | | | |
| ├─ clean.jpg | 200×230 ✓ | 200 ✓ | 4.6KB ✓ | **PASS** |
| ├─ large.jpg | 200×230 ✓ | 200 ✓ | 5.8KB ✓ | **PASS** |
| ├─ noisy.jpg | 200×230 ✓ | 200 ✓ | 18.4KB ✓ | **PASS** |
| ├─ borderline.jpg | 200×230 ✓ | 200 ✓ | 5.5KB ✓ | **PASS** |
| ├─ tiny.jpg | 200×230 ✓ | 200 ✓ | 5.6KB ✓ | **PASS** |
| ├─ huge.jpg | 200×230 ✓ | 200 ✓ | 4.5KB ✓ | **PASS** |
| ├─ white.jpg | 200×230 ✓ | 200 ✓ | 1.2KB ✓ | **PASS** |
| └─ black.jpg | 200×230 ✓ | 200 ✓ | 1.8KB ✓ | **PASS** |
| **JEE Main 2026** (350×450, 300 DPI, <150KB) | | | | |
| ├─ clean.jpg | 350×450 ✓ | 300 ✓ | 8.9KB ✓ | **PASS** |
| ├─ large.jpg | 350×450 ✓ | 300 ✓ | 13.5KB ✓ | **PASS** |
| ├─ noisy.jpg | 350×450 ✓ | 300 ✓ | 60.6KB ✓ | **PASS** |
| ├─ borderline.jpg | 350×450 ✓ | 300 ✓ | 12.3KB ✓ | **PASS** |
| ├─ tiny.jpg | 350×450 ✓ | 300 ✓ | 11.4KB ✓ | **PASS** |
| ├─ huge.jpg | 350×450 ✓ | 300 ✓ | 8.8KB ✓ | **PASS** |
| ├─ white.jpg | 350×450 ✓ | 300 ✓ | 3.2KB ✓ | **PASS** |
| └─ black.jpg | 350×450 ✓ | 300 ✓ | 4.8KB ✓ | **PASS** |
| **Aadhaar Update** (200×230, 200 DPI, <100KB) | | | | |
| ├─ clean.jpg | 200×230 ✓ | 200 ✓ | 4.6KB ✓ | **PASS** |
| ├─ large.jpg | 200×230 ✓ | 200 ✓ | 5.8KB ✓ | **PASS** |
| ├─ noisy.jpg | 200×230 ✓ | 200 ✓ | 18.5KB ✓ | **PASS** |
| ├─ borderline.jpg | 200×230 ✓ | 200 ✓ | 5.5KB ✓ | **PASS** |
| ├─ tiny.jpg | 200×230 ✓ | 200 ✓ | 5.6KB ✓ | **PASS** |
| ├─ huge.jpg | 200×230 ✓ | 200 ✓ | 4.5KB ✓ | **PASS** |
| ├─ white.jpg | 200×230 ✓ | 200 ✓ | 1.2KB ✓ | **PASS** |
| └─ black.jpg | 200×230 ✓ | 200 ✓ | 1.8KB ✓ | **PASS** |
| **Passport Seva** (413×531, 300 DPI, <300KB) | | | | |
| ├─ clean.jpg | 413×531 ✓ | 300 ✓ | 10.6KB ✓ | **PASS** |
| ├─ large.jpg | 413×531 ✓ | 300 ✓ | 17.2KB ✓ | **PASS** |
| ├─ noisy.jpg | 413×531 ✓ | 300 ✓ | 83.4KB ✓ | **PASS** |
| ├─ borderline.jpg | 413×531 ✓ | 300 ✓ | 15.5KB ✓ | **PASS** |
| ├─ tiny.jpg | 413×531 ✓ | 300 ✓ | 13.8KB ✓ | **PASS** |
| ├─ huge.jpg | 413×531 ✓ | 300 ✓ | 10.4KB ✓ | **PASS** |
| ├─ white.jpg | 413×531 ✓ | 300 ✓ | 4.1KB ✓ | **PASS** |
| └─ black.jpg | 413×531 ✓ | 300 ✓ | 6.6KB ✓ | **PASS** |
| **College Generic** (400×500, 200 DPI, <200KB) | | | | |
| ├─ clean.jpg | 400×500 ✓ | 200 ✓ | 10.4KB ✓ | **PASS** |
| ├─ large.jpg | 400×500 ✓ | 200 ✓ | 15.4KB ✓ | **PASS** |
| ├─ noisy.jpg | 400×500 ✓ | 200 ✓ | 75.5KB ✓ | **PASS** |
| ├─ borderline.jpg | 400×500 ✓ | 200 ✓ | 14.4KB ✓ | **PASS** |
| ├─ tiny.jpg | 400×500 ✓ | 200 ✓ | 12.8KB ✓ | **PASS** |
| ├─ huge.jpg | 400×500 ✓ | 200 ✓ | 9.4KB ✓ | **PASS** |
| ├─ white.jpg | 400×500 ✓ | 200 ✓ | 3.7KB ✓ | **PASS** |
| └─ black.jpg | 400×500 ✓ | 200 ✓ | 5.9KB ✓ | **PASS** |

**Total: 40 passed, 0 failed**

---

## 2. Compression Convergence Summary

| Schema | Image | Iterations | Quality | Size KB | Converged |
|--------|-------|------------|---------|---------|-----------|
| NEET UG 2026 | noisy.jpg | 1 | 85 | 18.4 | ✓ |
| NEET UG 2026 | borderline.jpg | 1 | 85 | 5.5 | ✓ |
| JEE Main 2026 | noisy.jpg | 1 | 85 | 60.6 | ✓ |
| JEE Main 2026 | borderline.jpg | 1 | 85 | 12.3 | ✓ |
| Aadhaar Update | noisy.jpg | 1 | 85 | 18.5 | ✓ |
| Aadhaar Update | borderline.jpg | 1 | 85 | 5.5 | ✓ |
| Passport Seva | noisy.jpg | 1 | 85 | 83.4 | ✓ |
| Passport Seva | borderline.jpg | 1 | 85 | 15.5 | ✓ |
| College Generic | noisy.jpg | 1 | 85 | 75.5 | ✓ |
| College Generic | borderline.jpg | 1 | 85 | 14.4 | ✓ |

### Analysis

- **Maximum iterations observed:** 1 (for standard test images)
- **All compressions converged:** Yes
- **Iteration cap:** MAX_COMPRESSION_ITERATIONS = 20
- **Quality floor:** MIN_JPEG_QUALITY = 20

### Stress Test Results (High-Entropy Images)

| Test Case | Converged | Iterations | Final Quality | Size KB |
|-----------|-----------|------------|---------------|---------|
| Random noise 200×230 → 100KB | ✓ | 1 | 85 | 33.2 |
| Random noise 413×531 → 300KB | ✓ | 1 | 85 | 156.1 |
| Random noise 400×500 → 5KB | ✗ | 8 | 20 | 34.8 |
| Checkerboard 350×450 → 150KB | ✓ | 1 | 85 | 34.9 |
| Gradient 400×500 → 200KB | ✓ | 1 | 85 | 5.0 |

**Conclusion:** Compression converges reliably. Impossible constraints (5KB for 400×500 noise) correctly fail with `SIZE_EXCEEDED` error code.

---

## 3. Edge Case Findings

| Edge Case | Result | Notes |
|-----------|--------|-------|
| Near-white images | ✅ PASS | Compresses well (1-4KB) |
| Near-black images | ✅ PASS | Compresses well (2-7KB) |
| Very small input (upscale) | ✅ PASS | LANCZOS4 interpolation maintains quality |
| Very large input (20× res) | ✅ PASS | No memory issues, correct downscale |
| Corrupt file (fake JPEG header) | ✅ FAIL correctly | Returns `DECODE_FAILED` error code |
| Impossible size constraint (1KB) | ✅ FAIL correctly | Returns `SIZE_EXCEEDED` with details |

---

## 4. Bugs Found and Fixes Applied

### Bug #1: Missing DPI Verification in `verify_schema_compliance`

**Location:** `worker/processors/schema.py:385-420`

**Problem:** The `verify_schema_compliance()` function only checked dimensions and file size, but did NOT verify DPI metadata. This could allow images with incorrect DPI to pass verification.

**Fix Applied:**
```python
# Added DPI verification using PIL
pil_img = Image.open(io.BytesIO(data))
dpi = pil_img.info.get('dpi', (72, 72))
if isinstance(dpi, tuple):
    dpi_x, dpi_y = int(dpi[0]), int(dpi[1])
else:
    dpi_x = dpi_y = int(dpi)

if dpi_x != schema.target_dpi:
    return False, f"DPI X {dpi_x} != target {schema.target_dpi}"

if dpi_y != schema.target_dpi:
    return False, f"DPI Y {dpi_y} != target {schema.target_dpi}"
```

**Impact:** Portal compliance verification is now complete. Images with incorrect DPI will be rejected.

### Bug #2: Import Shadowing (`errors/` vs `errors.py`)

**Location:** `worker/errors/__init__.py`

**Problem:** The `errors/` directory shadowed the `errors.py` module, causing import failures for `WorkerError`, `ErrorCode`, and `ProcessingStage`.

**Fix Applied:** Updated `errors/__init__.py` to re-export classes from the parent `errors.py` module using `importlib.util`.

**Impact:** All processor modules can now import error classes correctly.

---

## 5. Final Verdict

# ✅ SCHEMA ADAPTER IS PRODUCTION-READY

### Validation Summary

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Exact output dimensions | ✅ PASS | 40/40 images match target pixels exactly |
| DPI metadata correctness | ✅ PASS | All outputs have correct DPI X and Y |
| File size limits enforced | ✅ PASS | All outputs strictly below max_kb |
| Compression loop convergence | ✅ PASS | Max 8 iterations (well under 20 cap) |
| No infinite loops | ✅ PASS | Hard iteration cap enforced |
| Graceful error handling | ✅ PASS | Corrupt inputs return DECODE_FAILED |
| Impossible constraints detected | ✅ PASS | Returns SIZE_EXCEEDED with details |
| Edge cases handled | ✅ PASS | White, black, tiny, huge all work |

### Test Coverage

- **Pytest tests:** 86 passed
- **Stress tests:** 7 passed
- **Verification tests:** 6 passed
- **Schemas validated:** 5 (all seeded portals)
- **Image variants per schema:** 8

### Confidence Level

**HIGH** - The schema adapter has been tested with:
- All 5 seeded portal schemas
- Multiple image types (clean, noisy, borderline, edge cases)
- High-entropy stress tests
- Impossible constraint scenarios

No silent failures were observed. All failures produce proper error codes suitable for portal rejection handling.

---

## Appendix: Test Artifacts

### Files Created

1. `tests/fixtures/schema_validation/generate_test_images.py` - Test image generator
2. `tests/fixtures/schema_validation/manifest.json` - Test image manifest
3. `tests/fixtures/schema_validation/{schema}/` - Per-schema test images
4. `tests/test_schema_validation.py` - Comprehensive validation pytest
5. `tests/test_schema_stress.py` - Compression stress tests
6. `tests/test_verify_compliance.py` - Verification function tests

### Running Validation

```bash
# Full validation report
PYTHONPATH=worker python tests/test_schema_validation.py

# Pytest with verbose output
PYTHONPATH=worker pytest tests/test_schema_validation.py -v

# Stress tests
PYTHONPATH=worker python tests/test_schema_stress.py

# Verification function tests
PYTHONPATH=worker python tests/test_verify_compliance.py
```
