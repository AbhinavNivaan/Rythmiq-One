# OCR Compatibility Fix Summary

## Issue
PaddleOCR initialization failed on Camber BASE with:
```
Unknown argument: show_log
```

## Root Cause
- **PaddleOCR 3.x** (released June 2025) removed several constructor parameters:
  - `show_log` → replaced by new logging system
  - `use_gpu` → replaced by `device` parameter
  - `enable_mkldnn` → auto-detected
  - Various model configuration params → use config files

- **Camber BASE** installs the latest version at runtime (currently 3.3.3+)
- Our code was using PaddleOCR 2.x API

## Fix Applied

### 1. Version-Aware Parameter Building (`worker/processors/ocr.py`)
- Added `_detect_paddleocr_version()` to detect installed version
- Added `_build_ocr_kwargs()` to build compatible kwargs:
  - **2.x**: Uses `show_log=False`, `use_gpu=False`, `enable_mkldnn=True`, etc.
  - **3.x**: Uses `lang='en'`, `use_doc_orientation_classify=False`, etc.

### 2. Defensive Initialization
- Fallback to minimal config if kwargs fail with TypeError
- Cache init errors to avoid repeated failures
- Structured error logging

### 3. Version-Aware OCR Inference
- Added `_run_ocr_inference()` to handle API differences:
  - **2.x**: `ocr.ocr(img, cls=True)`
  - **3.x**: `ocr.ocr(img)` (no cls param) or `ocr.predict(img)`

### 4. Requirements Update
- Removed upper bound on PaddleOCR version
- Code now supports both 2.x and 3.x APIs

## Files Changed
1. `worker/processors/ocr.py` - Main OCR module
2. `worker/requirements.txt` - Removed version ceiling
3. `scripts/validate_ocr_init.py` - New validation script

## Local Validation
```bash
python scripts/validate_ocr_init.py
```

Note: Full runtime validation requires Linux x86_64 (PaddlePaddle doesn't support Apple Silicon).

---

## Camber Re-Test Plan

### Prerequisites
1. Push changes to repo
2. Ensure Camber has access to updated code

### Test Steps

1. **Create a new Camber job** using the same payload that failed:
   ```bash
   # Use your existing test payload or create new one
   camber submit --image camber/base:latest \
     --script worker.py \
     --payload test-job-payload.json
   ```

2. **Monitor logs** for these success indicators:
   ```
   INFO - Initializing PaddleOCR with kwargs: ['lang', ...]
   # Should NOT see 'show_log' or 'use_gpu' in kwargs for 3.x
   ```

3. **Expected new behavior**:
   - No "Unknown argument: show_log" error
   - OCR engine initializes successfully
   - Text extraction completes

4. **Verify output**:
   - Job should complete with status "success" or "partial_success"
   - OCR results should be present in output

### Rollback Plan
If issues persist:
1. Pin PaddleOCR to 2.x in requirements: `paddleocr>=2.7.0,<3.0.0`
2. Also pin paddlepaddle: `paddlepaddle>=2.6.0,<3.0.0`

---

## Technical Details

### PaddleOCR 2.x vs 3.x API Differences

| Feature | 2.x | 3.x |
|---------|-----|-----|
| Log control | `show_log=False` | Logging module |
| GPU/CPU | `use_gpu=False` | `device='cpu'` |
| MKLDNN | `enable_mkldnn=True` | Auto-detected |
| OCR call | `ocr.ocr(img, cls=True)` | `ocr.ocr(img)` |
| Result format | `[[[box, (text, conf)], ...]]` | Result objects |

### References
- [PaddleOCR 3.x Upgrade Notes](https://www.paddleocr.ai/latest/en/update/upgrade_notes.html)
- [GitHub Issue #15751](https://github.com/PaddlePaddle/PaddleOCR/issues/15751) - show_log parameter deprecated
