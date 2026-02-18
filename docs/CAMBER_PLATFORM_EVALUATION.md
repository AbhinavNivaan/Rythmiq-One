# Camber Platform Evaluation Report

**Document Version:** 2.1  
**Date:** January 31, 2026  
**Author:** Rythmiq Engineering Team  
**Status:** ⚠️ EVALUATION COMPLETE - RESULTS CONCERNING

---

## Executive Summary

This document outlines the discovered limitations of the Camber Cloud platform for running Rythmiq's document processing worker, and defines a comprehensive test plan to evaluate whether Camber meets our production requirements. The evaluation will produce quantitative metrics to inform a **go/no-go decision** on continuing with Camber.

### ⚠️ CRITICAL FINDINGS (January 31, 2026)

| Component | Job Duration | Processing Time | Status |
|-----------|--------------|-----------------|--------|
| **Fast Path (Pillow) cold** | 30s | <1s | ✅ MEETS TARGET |
| **Fast Path (Pillow) warm** | 14-15s | <1s | ✅ MEETS TARGET |
| **OpenCV** | 20s | 0.26s | ✅ MEETS TARGET |
| **PyMuPDF** | 20s | 0.19s | ✅ MEETS TARGET |
| **img2pdf** | 19s | 0.01s | ✅ MEETS TARGET |
| **rembg (cold)** | 86s | 46s (41s import + 4s inference) | ❌ FAILS TARGET |
| **rembg (warm)** | 90s | 45s (model redownloaded!) | 🚫 BLOCKER |
| **PaddleOCR** | FAILED | N/A | 🚫 PLATFORM ERROR |

### Key Discovery: ML Models Re-Download Every Job

**rembg U2Net model (176MB) is downloaded on EVERY job** because:
1. Stash only caches pip packages, not `~/.u2net/` model directory
2. No Docker support = no way to pre-bake models
3. Even "warm" jobs take 90s due to model download

### Recommendation: ⚠️ CONDITIONAL GO

- ✅ **Paths A, B, D (Pillow, OpenCV, PyMuPDF)**: Viable on Camber
- ❌ **Path C (rembg)**: NOT viable - 90s/job is unacceptable
- ❌ **Path E (PaddleOCR)**: Platform error, needs investigation
- ⏳ **Path F (Google Vision)**: Not yet tested, likely viable

---

## Processing Stack Under Evaluation

```
Rythmiq Worker Processing Stack
├─ PaddleOCR (OCR)              - 44s init overhead [IMMUTABLE]
├─ Google Vision API (OCR)      - Cloud API, ~$45/month, ~1-2s/call
├─ OpenCV (auto-crop, enhancement)
├─ PyMuPDF (PDF processing)
├─ img2pdf (format conversion)
├─ rembg (background removal)   - ML model, init overhead TBD
└─ Pillow (DPI, compression)
```

### Cost Estimate: Google Vision API
- Free tier: 1,000 units/month
- Beyond free: $1.50 per 1,000 units
- Estimated usage: 30,000 docs/month = ~$45/month

---

## Part 1: Platform Limitations Discovered

### 1.1 Critical Limitation: No System Package Installation

**Issue:** Camber BASE engine does not allow `apt-get install` or any system-level package installation.

```
E: List directory /var/lib/apt/lists/partial is missing. - Acquire (13: Permission denied)
```

**Impact:**
- Cannot install `tesseract-ocr` system binary
- Cannot install `poppler-utils` for PDF processing
- Cannot install custom fonts or system libraries
- Limits us to pure Python solutions only

**Workaround Attempted:** Tesseract OCR backend (failed - requires system binary)

### 1.2 Critical Limitation: No Docker Support on BASE Engine

**Issue:** Camber BASE engine does not support custom Docker images.

**Impact:**
- Cannot pre-bake dependencies into container
- Cannot include system-level OCR tools (Tesseract, etc.)
- Cannot use optimized base images
- Every job starts from scratch (or Stash cache)

**Documentation Reference:** Camber support confirmed Docker is only available on higher-tier engines.

### 1.3 Significant Limitation: Python OCR Performance

**Tested OCR Solutions:**

| Solution | Init Time | Works on Camber? | Notes |
|----------|-----------|------------------|-------|
| **PaddleOCR** | ~44s | ✅ Yes | 22s import + 22s model load |
| **Tesseract** | ~0.2s | ❌ No | Requires `tesseract-ocr` binary |
| **EasyOCR** | ~40-50s | ⏳ Untested | Similar PyTorch overhead expected |
| **Google Vision** | ~1-2s | ✅ Yes | Cloud API, requires credentials |

**Root Cause:** Pure Python OCR libraries (PaddleOCR, EasyOCR) require loading large ML models into memory on every cold start. This is an inherent limitation, not a Camber-specific issue, but Camber's lack of Docker support prevents us from pre-loading models.

### 1.4 ML Model Init Overhead (Critical)

**Components with ML model loading:**

| Component | Purpose | Est. Init Time | Model Size |
|-----------|---------|----------------|------------|
| **PaddleOCR** | Text extraction | ~44s | ~150MB |
| **rembg (U2Net)** | Background removal | ~15-30s TBD | ~170MB |
| **OpenCV DNN** | If using DNN features | ~5-10s | Varies |

**Implication:** Any job requiring OCR + background removal could face ~60-75s init overhead.

### 1.6 Limitation: Stash Cache Persistence

**Issue:** Stash caching helps with pip packages but NOT with in-memory model state.

**What Stash CAN cache:**
- ✅ pip packages (~50s savings)
- ✅ Downloaded model files on disk
- ✅ Static configuration files

**What Stash CANNOT cache:**
- ❌ In-memory model state (must reload every job)
- ❌ Initialized Python objects
- ❌ Warm interpreter state

### 1.7 Limitation: Cold Start Overhead

**Observed cold start components:**

| Component | Time | Cacheable? |
|-----------|------|------------|
| Job scheduling/provisioning | ~10-15s | No |
| Stash restore | ~5-10s | N/A |
| pip install (without cache) | ~50-55s | Yes (Stash) |
| pip install (with cache) | ~0s | Yes |
| PaddleOCR import | ~22s | No |
| PaddleOCR model load | ~22s | No |
| **Total (worst case)** | **~120s** | - |
| **Total (with Stash)** | **~60-70s** | - |

### 1.8 Limitation: No Long-Running Workers

**Issue:** Camber jobs are ephemeral - each job is a fresh environment.

**Impact:**
- Cannot maintain warm model state between jobs
- Cannot implement connection pooling
- Cannot batch multiple documents in a single job (without custom logic)
- Every job pays the full initialization cost

---

## Part 2: Test Plan - Platform Suitability Evaluation

### 2.1 Test Objectives

1. **Quantify actual latency** for each processing path
2. **Measure cold start vs warm start** (sequential jobs)
3. **Evaluate concurrent job performance**
4. **Determine cost-effectiveness** (time × compute cost)
5. **Produce go/no-go recommendation** with data

### 2.2 Test Subjects

We will test the following processing paths using our actual stack:

#### Path A: Fast Path (Pillow + img2pdf only)
- Input: Clean, high-quality document image
- Processing: Quality check → DPI adjust → Compress → Convert
- Components: `Pillow`, `img2pdf`
- Expected: Fast (~15-20s with cache)

#### Path B: Enhancement Path (OpenCV + Pillow)
- Input: Document needing auto-crop/enhancement
- Processing: Auto-crop → Denoise → Enhance → Schema compliance
- Components: `OpenCV`, `Pillow`
- Expected: Moderate (~20-30s with cache)

#### Path C: Background Removal Path (rembg)
- Input: Document with background to remove
- Processing: Background removal → Enhancement → Schema compliance
- Components: `rembg` (U2Net model), `Pillow`
- Expected: Slow first call (~30-45s init), faster subsequent

#### Path D: PDF Processing Path (PyMuPDF)
- Input: PDF document
- Processing: Extract pages → Process → Reassemble
- Components: `PyMuPDF`, `Pillow`, `img2pdf`
- Expected: Moderate (~20-30s)

#### Path E: OCR Path - PaddleOCR
- Input: Document requiring text extraction
- Processing: Quality check → OCR → Extract text → Output
- Components: `PaddleOCR`
- Expected: Slow (~60s with 44s init overhead)

#### Path F: OCR Path - Google Vision (Critical Docs)
- Input: High-priority document requiring accurate OCR
- Processing: Quality check → Cloud OCR → Extract text → Output
- Components: `Google Vision API`
- Expected: Fast (~15-20s, ~$0.0015/doc)

---

## Part 3: Test Specifications

### Test 1: Component Init Time Baseline

**Objective:** Measure initialization time for each component in isolation.

**Procedure:**
1. For each component, run a job that only imports and initializes it
2. Measure import time and first-use time separately
3. Run on cold cache to get worst case

**Components to Test:**
| Component | Test Command |
|-----------|--------------|
| Pillow | `from PIL import Image; Image.new('RGB', (100,100))` |
| OpenCV | `import cv2; cv2.imread(...)` |
| PyMuPDF | `import fitz; fitz.open(...)` |
| img2pdf | `import img2pdf` |
| rembg | `from rembg import remove; remove(...)` |
| PaddleOCR | `from paddleocr import PaddleOCR; ocr = PaddleOCR()` |

**Metrics to Capture:**
- `T_import`: Time to import module
- `T_init`: Time for first operation
- `T_total`: Total initialization overhead

---

### Test 2: Fast Path (Pillow + img2pdf)

**Objective:** Measure best-case latency with minimal dependencies.

**Procedure:**
1. Submit job with only Pillow + img2pdf
2. Process: Load image → Resize → Adjust DPI → Compress → Convert to PDF
3. Run 5 sequential jobs

**Input:** 4000x3000 JPEG, 5MB

**Metrics to Capture:**
- Cold start time (first job)
- Warm time (subsequent jobs)
- Processing time only (excluding init)

---

### Test 3: Enhancement Path (OpenCV)

**Objective:** Measure OpenCV-based processing latency.

**Procedure:**
1. Submit job using OpenCV for auto-crop and enhancement
2. Process: Load → Auto-crop → Denoise → Sharpen → Output
3. Run 5 sequential jobs

**Metrics to Capture:**
- OpenCV init overhead
- Processing time per operation
- Total job latency

---

### Test 4: Background Removal (rembg)

**Objective:** Measure rembg U2Net model initialization overhead.

**Procedure:**
1. Submit job that uses rembg for background removal
2. First call will download/load U2Net model
3. Run 5 sequential jobs to measure warm vs cold

**Expected:** Similar to PaddleOCR - significant first-call overhead.

**Metrics to Capture:**
- Model download time (if not cached)
- Model load time
- Inference time
- Total job latency

---

### Test 5: PDF Processing (PyMuPDF)

**Objective:** Measure PDF processing latency.

**Procedure:**
1. Submit job using PyMuPDF
2. Process: Open PDF → Extract pages → Process → Reassemble
3. Run 5 sequential jobs

**Input:** 5-page PDF, 10MB

**Metrics to Capture:**
- PyMuPDF init time
- Page extraction time
- Reassembly time
- Total job latency

---

### Test 6: OCR Path - PaddleOCR

**Objective:** Confirm PaddleOCR 44s init overhead.

**Procedure:**
1. Submit 5 sequential OCR jobs using PaddleOCR
2. Each job: Load image → OCR → Extract text
3. Record init time vs inference time

**Metrics to Capture:**
- Import time (~22s expected)
- Model load time (~22s expected)
- Inference time (~2-5s expected)
- Total per-job latency

---

### Test 7: OCR Path - Google Vision API

**Objective:** Measure cloud OCR latency (for critical docs).

**Procedure:**
1. Submit 5 sequential jobs using Google Vision API
2. Each job: Load image → API call → Parse response
3. Requires GOOGLE_VISION_CREDENTIALS_JSON env var

**Metrics to Capture:**
- API call latency
- Response parsing time
- Total job latency
- Cost per call

---

### Test 8: Full Pipeline - Worst Case

**Objective:** Measure maximum latency scenario.

**Scenario:** Job requires ALL processing steps:
- Background removal (rembg)
- Enhancement (OpenCV)
- OCR (PaddleOCR)
- Schema compliance (Pillow)
- PDF conversion (img2pdf)

**Expected:** ~90-120s for cold start

**Metrics to Capture:**
- Total cold start time
- Breakdown by component
- Warm start time (if models cached in memory - N/A on Camber)

---

### Test 9: Concurrent Jobs - Same User

### Test 9: Concurrent Jobs - Same User

**Objective:** Simulate user uploading multiple documents simultaneously.

**Scenario:** User uploads 5 documents at once for processing (Fast Path).

**Procedure:**
1. Submit 5 jobs simultaneously (parallel)
2. All jobs use Fast Path (Pillow + img2pdf only)
3. Record start time, end time for each

**Metrics to Capture:**
- `T_first_complete`: When first job finishes
- `T_last_complete`: When last job finishes
- `T_spread`: Time between first and last
- Parallelization efficiency

---

### Test 10: Concurrent Jobs - Multiple Users

**Objective:** Simulate production load with multiple users.

**Scenario:** 3 users each submit 3 jobs = 9 concurrent jobs.

**Procedure:**
1. Submit 9 jobs simultaneously
2. Mix of Fast Path and Enhancement Path
3. Record all timings

**Metrics to Capture:**
- Per-user latency distribution
- Resource contention indicators
- Queue depth behavior
- Fair scheduling assessment

---

### Test 11: Sustained Load

**Objective:** Measure behavior under continuous load.

**Procedure:**
1. Submit 1 job every 30 seconds for 10 minutes
2. Total: 20 jobs
3. Mix of all paths (weighted by expected production distribution)

**Metrics to Capture:**
- Latency trend over time
- Any degradation patterns
- Cache persistence over time
- Platform stability

---

## Part 4: Success Criteria

### 4.1 Target Latency Requirements

| Path | Target | Acceptable | Unacceptable |
|------|--------|------------|--------------|
| Fast Path (Pillow/img2pdf) cold | <25s | <40s | >60s |
| Fast Path warm | <15s | <25s | >40s |
| Enhancement Path (OpenCV) cold | <35s | <50s | >75s |
| Enhancement Path warm | <20s | <35s | >50s |
| Background Removal (rembg) cold | <60s | <90s | >120s |
| Background Removal warm | <25s | <45s | >75s |
| PDF Processing cold | <30s | <45s | >70s |
| PDF Processing warm | <20s | <35s | >50s |
| OCR - PaddleOCR (any) | <70s | <90s | >120s |
| OCR - Google Vision cold | <25s | <40s | >60s |
| OCR - Google Vision warm | <20s | <30s | >45s |
| Full Pipeline (worst case) | <120s | <150s | >180s |
| Concurrent (5 jobs Fast Path) | <60s all | <90s | >120s |

### 4.2 Component Init Overhead Targets

| Component | Target Init | Acceptable | Blocker |
|-----------|-------------|------------|---------|
| Pillow | <1s | <3s | >5s |
| OpenCV | <2s | <5s | >10s |
| PyMuPDF | <1s | <3s | >5s |
| img2pdf | <1s | <2s | >5s |
| rembg | <30s | <45s | >60s |
| PaddleOCR | 44s [known] | N/A | N/A |
| Google Vision | <2s | <5s | >10s |

### 4.3 Decision Matrix

| Score | Criteria | Action |
|-------|----------|--------|
| **GREEN** | All targets met | Continue with Camber |
| **YELLOW** | Acceptable thresholds met, some targets missed | Evaluate optimizations, consider hybrid |
| **RED** | Unacceptable thresholds hit | Evaluate alternatives |

### 4.4 Path-Specific Recommendations

Based on test results, we may recommend:

| If... | Then... |
|-------|---------|
| Fast Path meets targets | Use Camber for schema compliance jobs |
| rembg init > 45s | Use Google Vision for background docs instead |
| PaddleOCR blocking | Use Google Vision for ALL OCR ($45/mo) |
| Concurrent jobs queue badly | Implement client-side batching |
| All paths RED | Migrate to alternative platform |

---

## Part 5: Alternative Platforms to Consider

If Camber evaluation results in RED status:

### 5.1 AWS Lambda + EFS
- **Pros:** Docker support, EFS for model caching, warm starts
- **Cons:** Cold start can be high, 15-min timeout

### 5.2 Google Cloud Run
- **Pros:** Docker support, min instances for warm, good scaling
- **Cons:** Cost for min instances, cold start ~5-10s

### 5.3 Modal Labs
- **Pros:** Designed for ML, persistent volumes, warm containers
- **Cons:** Newer platform, less enterprise features

### 5.4 AWS Fargate
- **Pros:** Full Docker, long-running tasks, no cold start
- **Cons:** Higher cost, more infrastructure management

### 5.5 Self-Hosted Kubernetes
- **Pros:** Full control, optimal warm pooling
- **Cons:** Operational overhead, scaling complexity

---

## Part 6: Test Execution Schedule

| Day | Test | Components | Duration |
|-----|------|------------|----------|
| Day 1 AM | Test 1: Component Init Baseline | All | 3 hours |
| Day 1 PM | Test 2: Fast Path | Pillow, img2pdf | 2 hours |
| Day 1 PM | Test 3: Enhancement Path | OpenCV | 2 hours |
| Day 2 AM | Test 4: Background Removal | rembg | 3 hours |
| Day 2 AM | Test 5: PDF Processing | PyMuPDF | 2 hours |
| Day 2 PM | Test 6: OCR - PaddleOCR | PaddleOCR | 2 hours |
| Day 2 PM | Test 7: OCR - Google Vision | Cloud API | 2 hours |
| Day 3 AM | Test 8: Full Pipeline | All | 3 hours |
| Day 3 PM | Test 9: Concurrent (Single User) | Fast Path | 2 hours |
| Day 3 PM | Test 10: Concurrent (Multi User) | Mixed | 2 hours |
| Day 4 | Test 11: Sustained Load | Mixed | 4 hours |
| Day 5 | Analysis & Recommendation | - | Full day |

---

## Part 7: Test Artifacts Required

### 7.1 Test Worker Code
- [x] `harness.py` - Timing instrumentation framework
- [x] `test_runner.py` - Test execution orchestrator
- [ ] `test_components.py` - Individual component init tests
- [ ] `test_fast_path.py` - Pillow + img2pdf processing
- [ ] `test_enhancement.py` - OpenCV processing
- [ ] `test_background_removal.py` - rembg processing
- [ ] `test_pdf.py` - PyMuPDF processing
- [ ] `test_ocr_paddle.py` - PaddleOCR processing
- [ ] `test_ocr_google.py` - Google Vision processing
- [ ] `test_full_pipeline.py` - All components combined

### 7.2 Requirements File
```
# requirements-eval.txt
Pillow>=10.2.0
opencv-python-headless>=4.9.0
PyMuPDF>=1.23.0
img2pdf>=0.5.1
rembg>=2.0.50
paddlepaddle>=2.6.0
paddleocr>=2.7.0
google-cloud-vision>=3.7.0
numpy>=1.26.0
```

### 7.3 Test Data
- [ ] Clean document images (5 samples, various sizes)
- [ ] Documents needing enhancement (5 samples)
- [ ] Documents with backgrounds to remove (5 samples)
- [ ] PDF documents (5 samples, 1-10 pages each)
- [ ] OCR test documents (5 samples with known text)

### 7.4 Reporting
- [ ] Raw timing data (JSON per test)
- [ ] Summary CSV for all tests
- [ ] Analysis notebook
- [ ] Final recommendation document

---

## Appendix A: Commands Reference

### Check Job Status
```bash
camber job get <JOB_ID> --api-key "$CAMBER_API_KEY"
```

### Get Job Logs
```bash
camber job logs <JOB_ID> --api-key "$CAMBER_API_KEY"
```

### Clear Stash Cache
```bash
camber stash rm -r stash://USER/test/ --api-key "$CAMBER_API_KEY"
```

### List Stash Contents
```bash
camber stash ls stash://USER/ --api-key "$CAMBER_API_KEY"
```

---

## Appendix B: Current Baseline Measurements

From previous testing sessions:

| Metric | Measured Value | Date |
|--------|----------------|------|
| pip install (no cache) | ~50-55s | Jan 30, 2026 |
| pip install (Stash cache) | ~0s | Jan 30, 2026 |
| PaddleOCR import | ~22s | Jan 30, 2026 |
| PaddleOCR model load | ~22s | Jan 30, 2026 |
| Total OCR path (cached) | ~60s | Jan 30, 2026 |
| Tesseract backend | N/A (not available) | Jan 31, 2026 |
| Job scheduling overhead | ~10-15s | Jan 30, 2026 |

---

## Appendix C: Detailed Test Results (January 31, 2026)

### Test 2: Fast Path (Pillow + img2pdf)

**Jobs:** 15381, 15382, 15383

| Run | Job Duration | Processing Time | Status |
|-----|--------------|-----------------|--------|
| Cold | 30s | <1s | ✅ |
| Warm 1 | 15s | <1s | ✅ |
| Warm 2 | 14s | <1s | ✅ |

**Analysis:** Fast path meets all targets. ~15s job overhead (scheduling + Stash).

### Test 3: OpenCV Enhancement Path

**Job:** 15384

| Metric | Value |
|--------|-------|
| Job Duration | 20s |
| Import Time | <1s |
| Resize Operation | 0.262s |
| Status | ✅ MEETS TARGET |

**Analysis:** OpenCV is lightweight. No ML models = fast init.

### Test 5: PDF Processing (PyMuPDF)

**Job:** 15385

| Metric | Value |
|--------|-------|
| Job Duration | 20s |
| Import Time | <1s |
| Open/Read PDF | 0.191s |
| Status | ✅ MEETS TARGET |

### Test: img2pdf

**Job:** 15386

| Metric | Value |
|--------|-------|
| Job Duration | 19s |
| Import Time | <0.1s |
| Conversion | 0.013s |
| Status | ✅ MEETS TARGET |

### Test 4: Background Removal (rembg) - CRITICAL

**Jobs:** 15387 (failed), 15388 (cold), 15391 (warm)

#### Cold Start (Job 15388)
| Metric | Value |
|--------|-------|
| Job Duration | 86s (1m26s) |
| Import Time | 41.033s |
| Model Download | 176MB @ ~80MB/s |
| First Inference | 4.199s |
| Second Inference | 1.596s |
| Total Processing | 46.840s |
| Status | ❌ FAILS TARGET (>60s cold) |

#### "Warm" Start (Job 15391) - CRITICAL FINDING
| Metric | Value |
|--------|-------|
| Job Duration | 90s (1m30s) |
| Import Time | 40.791s |
| Model Download | 176MB (REDOWNLOADED!) |
| First Inference | 4.285s |
| Total Processing | 45.089s |
| Status | 🚫 BLOCKER |

**Root Cause:** Stash does NOT cache `~/.u2net/` model directory.
Every job downloads the 176MB U2Net model from GitHub.

### Test 6: OCR - PaddleOCR - PLATFORM ERROR

**Jobs:** 15389 (API error), 15390 (runtime error)

| Metric | Value |
|--------|-------|
| Job Duration | 60s |
| Import Time | 7.222s |
| Init (model download) | ~50s |
| Status | 🚫 FAILED |

**Error:**
```
NotImplementedError: ConvertPirAttribute2RuntimeAttribute not support 
[pir::ArrayAttribute<pir::DoubleAttribute>]
(at onednn_instruction.cc:116)
```

**Analysis:** PaddlePaddle has a compatibility issue with Camber's CPU 
(OneDNN/MKL configuration). This may be fixable with environment variables.

---

## Appendix D: Job Reference

| Job ID | Test | Status | Duration | Key Finding |
|--------|------|--------|----------|-------------|
| 15381 | Fast Path (cold) | COMPLETED | 30s | Baseline |
| 15382 | Fast Path (warm) | COMPLETED | 15s | Good caching |
| 15383 | Fast Path (warm) | COMPLETED | 14s | Consistent |
| 15384 | OpenCV | COMPLETED | 20s | 0.26s processing |
| 15385 | PyMuPDF | COMPLETED | 20s | 0.19s processing |
| 15386 | img2pdf | COMPLETED | 19s | 0.01s processing |
| 15387 | rembg (no onnx) | FAILED | 35s | Missing onnxruntime |
| 15388 | rembg (cold) | COMPLETED | 86s | 41s import, 4s inference |
| 15389 | PaddleOCR | FAILED | 56s | API deprecated |
| 15390 | PaddleOCR | FAILED | 60s | OneDNN error |
| 15391 | rembg (warm) | COMPLETED | 90s | Model redownloaded! |

---

## Appendix E: Final Recommendations

### Immediate Actions

1. **DO NOT USE rembg on Camber** - 90s/job is unacceptable
   - Alternative: Pre-process background removal before upload
   - Alternative: Use cloud API (e.g., remove.bg) at ~$0.10/image

2. **Investigate PaddleOCR OneDNN issue**
   - Try: `export PADDLE_MKL_NUM_THREADS=1`
   - Try: `export FLAGS_use_mkldnn=false`
   - Fallback: Google Vision API

3. **Use Google Vision for ALL OCR** (~$45/month)
   - Fast API calls (~1-2s)
   - No model loading
   - Higher accuracy

### Viable Camber Use Cases

| Use Case | Expected Latency | Recommendation |
|----------|------------------|----------------|
| Schema compliance (Pillow) | 15-20s | ✅ Use Camber |
| Auto-crop/enhance (OpenCV) | 20-25s | ✅ Use Camber |
| PDF processing (PyMuPDF) | 20-25s | ✅ Use Camber |
| OCR (Google Vision) | 15-25s | ✅ Use Camber |
| Background removal (rembg) | 90s | ❌ DO NOT USE |
| OCR (PaddleOCR) | ~60-90s | ⚠️ Fix or avoid |

### Cost Estimate (Revised)

| Component | Monthly Volume | Cost |
|-----------|---------------|------|
| Camber compute (viable paths) | ~30,000 jobs | ~$150-300 |
| Google Vision API | ~30,000 calls | ~$45 |
| **Total** | - | **~$195-345/month** |
|-----------|-------------|-----------|----------|--------|
| Pillow | TBD | TBD | TBD | ⏳ |
| OpenCV | TBD | TBD | TBD | ⏳ |
| PyMuPDF | TBD | TBD | TBD | ⏳ |
| img2pdf | TBD | TBD | TBD | ⏳ |
| rembg | TBD | TBD | TBD | ⏳ |
| Google Vision | TBD | TBD | TBD | ⏳ |

---

## Appendix C: Key Contacts

- **Camber Support:** support@camber.ai
- **Feature Request:** Request `tesseract-ocr` in BASE image

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | Jan 31, 2026 | Engineering | Initial document |

---

*This document will be updated with test results as they become available.*
