# Crop Preview Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Insert a crop preview step between capture and upload — after the user taps Done, each captured image is shown with a detected document quad overlay; the user adjusts corners if needed and confirms; the confirmed quad is passed to the worker, which uses it directly for perspective correction.

**Architecture:** Capture session state lives in a Zustand store (keyed by session ID) so route params stay lean. A `DocumentDetector` adapter wraps whichever on-device (or server-side fallback) detection library is chosen. The worker gains one optional field (`confirmed_crop_quad`) on `JobPayload` and `EnhancementOptions`; when present, `detect_and_crop_document()` skips its 4-stage cascade and goes straight to perspective warp.

**Tech Stack:** React Native 0.81 / Expo SDK 54 / Expo Router, react-native-gesture-handler v2.28, react-native-reanimated v4.1, react-native-svg 15.12, Zustand (new dependency), Python 3 / OpenCV / FastAPI

---

## File Map

### New files
| File | Purpose |
|---|---|
| `app-v2/stores/captureSession.ts` | Zustand store: session images, docType, confirmed crops |
| `app-v2/services/documentDetector.ts` | Adapter: `DocumentDetector` interface + implementation |
| `app-v2/components/CropOverlay.tsx` | SVG quad overlay with draggable corners (RNGH v2) |
| `app-v2/app/(tabs)/crop-preview.tsx` | New route: review + confirm one image at a time |
| `tests/worker/test_confirmed_crop_quad.py` | Worker unit tests for confirmed quad fast-path |

### Modified files
| File | What changes |
|---|---|
| `worker/processors/enhancement.py` | `EnhancementOptions` + `detect_and_crop_document()` fast-path |
| `worker/models.py` | `confirmed_crop_quad` field on `JobPayload` |
| `worker/worker.py` | Pass `confirmed_crop_quad` into `EnhancementOptions` |
| `app/api/routes/models.py` | `confirmed_crop_quad` on `SubmitJobRequest` |
| `app/api/routes/jobs.py` | Thread `confirmed_crop_quad` into `camber_payload` |
| `app-v2/services/api.ts` | `submitJob()` accepts + sends confirmed quad |
| `app-v2/services/backgroundUpload.ts` | Accept `ConfirmedCrop[]` instead of bare `string[]` |
| `app-v2/app/(tabs)/capture.tsx` | Navigate to crop-preview on Done; handle recapture mode |
| `app-v2/app/(tabs)/upload.tsx` | Read from session store; show `croppedUri` thumbnail |
| `app-v2/package.json` | Add `zustand` |

---

## Task 1: Library Research & Install

**Files:**
- Modify: `app-v2/package.json`
- Create: `app-v2/stores/captureSession.ts` (scaffold only)

### Background

You need a library that detects document corners in an **existing image URI** (not a live camera feed). The interface you are building toward is:

```ts
// The adapter you will implement in Task 7
async function detect(
  imageUri: string,
  imageWidth: number,
  imageHeight: number
): Promise<DetectionResult | null>
// where DetectionResult = { quad: [[x,y],[x,y],[x,y],[x,y]], croppedUri?: string }
// quad values are normalised 0.0–1.0 relative to imageWidth/imageHeight
```

- [ ] **Step 1: Evaluate library options**

Check these in order. Open each GitHub repo and confirm it supports static image URIs (not just live camera) and works with Expo SDK 54 (bare or managed workflow):

1. `react-native-document-scanner-plugin` (websitebeaver) — check if it has a `getScanResults(uri)` or similar static-image API
2. `@react-native-ml-kit/document-scanner` — Android-only, skip if iOS support is needed
3. Any other library you find via `npm search react-native document scanner expo`

If **no suitable on-device library exists**: implement a lightweight `/detect` endpoint on the worker (see Step 1b below) and use it as the detection source. This is the fallback path.

- [ ] **Step 1a (on-device path): Install chosen library**

```bash
cd app-v2
npx expo install <chosen-library-package>
```

Verify it appears in `package.json` dependencies.

- [ ] **Step 1b (server-side fallback path — only if Step 1a is not viable): Add `/detect` endpoint to worker**

Add to `worker/server.py`:

```python
class DetectRequest(BaseModel):
    class Config:
        extra = "allow"

class DetectResponse(BaseModel):
    quad: list[list[float]] | None  # [[x,y],[x,y],[x,y],[x,y]] normalised 0.0–1.0, or null

@app.post("/detect")
async def detect_document(request: DetectRequest) -> DetectResponse:
    """
    Fast document corner detection. Runs Stage 1 (OpenCV contour) only.
    No Vision API, no full pipeline. Returns normalised quad or null.
    """
    import base64, numpy as np, cv2
    from processors.enhancement import _find_quad_contour, _preprocess_for_edges, _order_corners, _DOC_DETECT_MIN_AREA_FRACTION, _DOC_DETECT_MAX_AREA_FRACTION

    try:
        image_b64: str = request.__dict__.get("image_b64", "")
        img_bytes = base64.b64decode(image_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return DetectResponse(quad=None)

        h, w = img.shape[:2]
        min_area = _DOC_DETECT_MIN_AREA_FRACTION * w * h
        max_area = _DOC_DETECT_MAX_AREA_FRACTION * w * h
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edge_maps = _preprocess_for_edges(gray, bgr=img)

        for edge_img in edge_maps:
            result = _find_quad_contour(edge_img, min_area, max_area)
            if result is not None:
                corners, _ = result
                ordered = _order_corners(corners)
                quad = [[float(x) / w, float(y) / h] for x, y in ordered]
                return DetectResponse(quad=quad)
    except Exception as e:
        logger.warning(f"[DETECT] failed: {e}")
    return DetectResponse(quad=None)
```

- [ ] **Step 2: Install Zustand**

```bash
cd app-v2
npx expo install zustand
```

Verify `zustand` appears in `package.json`.

- [ ] **Step 3: Commit**

```bash
cd app-v2
git add package.json
# If Step 1b: also add worker/server.py
git commit -m "feat: install zustand, add document detection dependency"
```

---

## Task 2: Capture Session Store

**Files:**
- Create: `app-v2/stores/captureSession.ts`

- [ ] **Step 1: Create the store**

Create `app-v2/stores/captureSession.ts`:

```ts
import { create } from 'zustand'

export type NormalisedPoint = [number, number] // [x, y] in 0.0–1.0 space
export type NormalisedQuad = [NormalisedPoint, NormalisedPoint, NormalisedPoint, NormalisedPoint]

export interface CapturedImage {
  uri: string
  width: number
  height: number
}

export interface ConfirmedCrop {
  originalUri: string
  croppedUri?: string   // perspective-corrected preview if library provides it
  quad: NormalisedQuad  // normalised 0.0–1.0 relative to original image dimensions
}

interface CaptureSessionState {
  sessionId: string | null
  images: CapturedImage[]
  docType: string
  confirmed: ConfirmedCrop[]

  startSession: (images: CapturedImage[], docType: string) => string
  confirmCrop: (index: number, crop: ConfirmedCrop) => void
  replaceImage: (index: number, image: CapturedImage) => void
  clearSession: () => void
  getSession: () => { images: CapturedImage[]; docType: string; confirmed: ConfirmedCrop[] }
}

export const useCaptureSession = create<CaptureSessionState>((set, get) => ({
  sessionId: null,
  images: [],
  docType: '',
  confirmed: [],

  startSession: (images, docType) => {
    const sessionId = `session_${Date.now()}`
    set({ sessionId, images, docType, confirmed: [] })
    return sessionId
  },

  confirmCrop: (index, crop) => {
    set(state => {
      const confirmed = [...state.confirmed]
      confirmed[index] = crop
      return { confirmed }
    })
  },

  replaceImage: (index, image) => {
    set(state => {
      const images = [...state.images]
      images[index] = image
      // Clear the confirmed entry for this index so it re-runs detection
      const confirmed = [...state.confirmed]
      delete confirmed[index]
      return { images, confirmed }
    })
  },

  clearSession: () => {
    set({ sessionId: null, images: [], docType: '', confirmed: [] })
  },

  getSession: () => {
    const { images, docType, confirmed } = get()
    return { images, docType, confirmed }
  },
}))
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd app-v2
npx tsc --noEmit
```

Expected: no errors related to `captureSession.ts`.

- [ ] **Step 3: Commit**

```bash
git add app-v2/stores/captureSession.ts
git commit -m "feat: add capture session Zustand store"
```

---

## Task 3: Worker — JobPayload and EnhancementOptions

**Files:**
- Modify: `worker/models.py:219-301`
- Modify: `worker/processors/enhancement.py:44-71`
- Modify: `worker/worker.py:268-276`
- Test: `tests/worker/test_confirmed_crop_quad.py`

- [ ] **Step 1: Write failing tests first**

Create `tests/worker/test_confirmed_crop_quad.py`:

```python
"""Tests for confirmed_crop_quad threading through JobPayload and EnhancementOptions."""
import json
import pytest


def _base_payload() -> dict:
    return {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_id": "550e8400-e29b-41d4-a716-446655440001",
        "mode": "master",
        "document_type": "document",
        "input": {
            "raw_path": "uploads/test.jpg",
            "artifact_url": None,
            "mime_type": "image/jpeg",
            "original_filename": "test.jpg",
        },
        "storage": {
            "bucket": "test-bucket",
            "region": "sgp1",
            "endpoint": "https://example.com",
        },
        "master_constraints": {
            "max_kb": 2000,
            "target_dpi": 300,
            "output_format": "jpeg",
            "quality": 85,
            "filename_pattern": "{job_id}_master",
        },
    }


def test_jobpayload_parses_confirmed_crop_quad():
    """JobPayload.from_dict() should parse confirmed_crop_quad from JSON."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../worker'))
    from models import JobPayload

    payload = _base_payload()
    payload["confirmed_crop_quad"] = [
        [0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]
    ]
    job = JobPayload.from_dict(payload)

    assert job.confirmed_crop_quad is not None
    assert len(job.confirmed_crop_quad) == 4
    assert job.confirmed_crop_quad[0] == (0.1, 0.1)
    assert job.confirmed_crop_quad[3] == (0.1, 0.9)


def test_jobpayload_confirmed_crop_quad_defaults_to_none():
    """JobPayload.from_dict() should default confirmed_crop_quad to None when absent."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../worker'))
    from models import JobPayload

    job = JobPayload.from_dict(_base_payload())
    assert job.confirmed_crop_quad is None


def test_enhancement_options_accepts_confirmed_crop_quad():
    """EnhancementOptions should accept confirmed_crop_quad without error."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../worker'))
    from processors.enhancement import EnhancementOptions

    quad = ((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9))
    opts = EnhancementOptions(confirmed_crop_quad=quad)
    assert opts.confirmed_crop_quad == quad


def test_enhancement_options_confirmed_crop_quad_defaults_to_none():
    """EnhancementOptions.confirmed_crop_quad should default to None."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../worker'))
    from processors.enhancement import EnhancementOptions

    opts = EnhancementOptions()
    assert opts.confirmed_crop_quad is None
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd "/Users/abhinav/Rythmiq One"
source .venv/bin/activate
pytest tests/worker/test_confirmed_crop_quad.py -v
```

Expected: 4 failures — `confirmed_crop_quad` attribute does not exist yet.

- [ ] **Step 3: Add confirmed_crop_quad to JobPayload**

In `worker/models.py`, add the field to the `JobPayload` dataclass (after `encrypted_input` at line ~244):

```python
# Confirmed crop quad from the app's crop preview screen.
# 4 corner points in normalised 0.0–1.0 coordinates (TL, TR, BR, BL).
# When present, the enhancement pipeline skips its own document detection
# and goes straight to perspective warp using these corners.
confirmed_crop_quad: Optional[tuple] = None
```

In `JobPayload.from_dict()` (inside the `return JobPayload(...)` call at line ~288), add:

```python
confirmed_crop_quad=_parse_quad(data.get("confirmed_crop_quad")),
```

Add the helper function just above `class JobPayload` (around line 218):

```python
def _parse_quad(raw) -> Optional[tuple]:
    """Parse [[x,y],[x,y],[x,y],[x,y]] from JSON into tuple of tuples. Returns None if invalid."""
    if not raw:
        return None
    try:
        pts = list(raw)
        if len(pts) != 4:
            return None
        return tuple(tuple(float(c) for c in pt) for pt in pts)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: Add confirmed_crop_quad to EnhancementOptions**

In `worker/processors/enhancement.py`, add to the `EnhancementOptions` class (after `binarise_output` at line ~70):

```python
# Confirmed crop quad from app's crop preview (normalised 0.0–1.0).
# When set, detect_and_crop_document() skips its detection cascade.
confirmed_crop_quad: Optional[tuple] = None
```

- [ ] **Step 5: Pass confirmed_crop_quad in worker.py**

In `worker/worker.py`, update the `EnhancementOptions(...)` constructor call (around line 268) to add:

```python
confirmed_crop_quad=payload.confirmed_crop_quad,
```

The full call becomes:

```python
enhancement_options = EnhancementOptions(
    quality_score=quality_result.score,
    is_readable=quality_result.score >= READABLE_QUALITY_THRESHOLD,
    document_type=payload.document_type,
    document_category=payload.document_category,
    document_subtype=payload.document_subtype,
    quality_breakdown=quality_result.breakdown,
    binarise_output=_is_binary_schema,
    confirmed_crop_quad=payload.confirmed_crop_quad,
)
```

- [ ] **Step 6: Run tests, verify they pass**

```bash
pytest tests/worker/test_confirmed_crop_quad.py -v
```

Expected: 4 tests pass.

- [ ] **Step 7: Run existing guardrail tests to verify no regression**

```bash
pytest tests/test_enhancement_guardrails.py tests/worker/test_quality_photo_scoring.py -v
```

Expected: 51 tests pass (34 + 17).

- [ ] **Step 8: Commit**

```bash
git add worker/models.py worker/processors/enhancement.py worker/worker.py tests/worker/test_confirmed_crop_quad.py
git commit -m "feat: add confirmed_crop_quad to JobPayload and EnhancementOptions"
```

---

## Task 4: Worker — detection fast-path

**Files:**
- Modify: `worker/processors/enhancement.py:1763-1830` (detect_and_crop_document) and `2128-2163` (_enhance_document)
- Test: `tests/worker/test_confirmed_crop_quad.py` (extend)

- [ ] **Step 1: Write failing tests first**

Append to `tests/worker/test_confirmed_crop_quad.py`:

```python
def test_detect_and_crop_document_uses_confirmed_quad():
    """When confirmed_crop_quad is provided, detect_and_crop_document uses it and skips cascade."""
    import sys, os, numpy as np
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../worker'))
    from unittest.mock import patch, MagicMock
    from processors.enhancement import detect_and_crop_document

    # 100x100 white image
    img = np.ones((100, 100, 3), dtype=np.uint8) * 255

    # Quad covering 20%–80% of image (normalised)
    quad = ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8))

    with patch('processors.enhancement._perspective_crop') as mock_warp:
        mock_warp.return_value = np.ones((60, 60, 3), dtype=np.uint8) * 200
        result, was_processed = detect_and_crop_document(img, confirmed_crop_quad=quad)

    # _perspective_crop must have been called exactly once
    assert mock_warp.call_count == 1
    assert was_processed is True
    # Verify the pixel coordinates passed to _perspective_crop are correct
    call_args = mock_warp.call_args[0]
    corners_passed = call_args[1]  # second positional arg
    # TL pixel should be approximately (20, 20)
    tl = corners_passed[0]
    assert abs(tl[0] - 20.0) < 1.0
    assert abs(tl[1] - 20.0) < 1.0


def test_detect_and_crop_document_skips_quad_when_none():
    """When confirmed_crop_quad is None, the normal cascade still runs."""
    import sys, os, numpy as np
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../worker'))
    from unittest.mock import patch
    from processors.enhancement import detect_and_crop_document

    img = np.ones((100, 100, 3), dtype=np.uint8) * 255

    # If cascade runs, _find_quad_contour will be called (even if it returns None)
    with patch('processors.enhancement._find_quad_contour', return_value=None) as mock_contour:
        detect_and_crop_document(img, confirmed_crop_quad=None)

    assert mock_contour.call_count > 0
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
pytest tests/worker/test_confirmed_crop_quad.py::test_detect_and_crop_document_uses_confirmed_quad tests/worker/test_confirmed_crop_quad.py::test_detect_and_crop_document_skips_quad_when_none -v
```

Expected: 2 failures.

- [ ] **Step 3: Implement the fast-path in detect_and_crop_document**

In `worker/processors/enhancement.py`, update the `detect_and_crop_document()` function signature (line 1763):

```python
def detect_and_crop_document(
    img: NDArray[np.uint8],
    raw_data: Optional[bytes] = None,
    confirmed_crop_quad: Optional[tuple] = None,
) -> Tuple[NDArray[np.uint8], bool]:
```

Immediately after the `h, w = img.shape[:2]` line (line 1786), add the fast-path block:

```python
    # ── Fast-path: user-confirmed quad from app crop preview ─────────────
    # When the user has already verified and optionally adjusted the crop
    # corners in the app, we skip all detection stages and go straight to
    # perspective warp. _order_corners() ensures correct TL/TR/BR/BL order
    # even if the user dragged corners in an unexpected sequence.
    if confirmed_crop_quad is not None:
        try:
            pixel_pts = np.array(
                [[x * w, y * h] for x, y in confirmed_crop_quad],
                dtype=np.float32,
            )
            ordered = _order_corners(pixel_pts)
            warped = _perspective_crop(img, ordered)
            if warped is not None and warped.size > 0:
                logger.info(
                    "[ENHANCEMENT] Using confirmed crop quad from app preview: %dx%d -> %dx%d",
                    w, h, warped.shape[1], warped.shape[0],
                )
                return _hough_fine_tune_rotation(warped), True
        except Exception as _e:
            logger.warning(
                "[ENHANCEMENT] confirmed_crop_quad fast-path failed (%s), falling through to cascade",
                _e,
            )
```

- [ ] **Step 4: Thread confirmed_crop_quad through _enhance_document**

In `_enhance_document()` (line 2163), update the call to `detect_and_crop_document`:

```python
    img, doc_found = detect_and_crop_document(
        img,
        raw_data=raw_data,
        confirmed_crop_quad=options.confirmed_crop_quad,
    )
```

- [ ] **Step 5: Run all new tests**

```bash
pytest tests/worker/test_confirmed_crop_quad.py -v
```

Expected: 6 tests pass.

- [ ] **Step 6: Run full guardrail suite to verify no regression**

```bash
pytest tests/test_enhancement_guardrails.py tests/worker/test_quality_photo_scoring.py -v
```

Expected: 51 tests pass.

- [ ] **Step 7: Commit**

```bash
git add worker/processors/enhancement.py tests/worker/test_confirmed_crop_quad.py
git commit -m "feat: add confirmed_crop_quad fast-path to detect_and_crop_document"
```

---

## Task 5: API — passthrough confirmed_crop_quad

**Files:**
- Modify: `app/api/routes/models.py:70-71`
- Modify: `app/api/routes/jobs.py:47-115` (`_submit_job_to_processing`) and `758-774` (`submit_job` handler)

- [ ] **Step 1: Add confirmed_crop_quad to SubmitJobRequest**

In `app/api/routes/models.py`, update `SubmitJobRequest` (line 70):

```python
class SubmitJobRequest(BaseModel):
    output_format: Literal["jpeg", "jpeg2000", "pdf_mrc"] = "jpeg"
    confirmed_crop_quad: list[list[float]] | None = None
    # [[x,y],[x,y],[x,y],[x,y]] normalised 0.0–1.0, TL/TR/BR/BL order
```

- [ ] **Step 2: Add confirmed_crop_quad to _submit_job_to_processing signature**

In `app/api/routes/jobs.py`, update the function signature of `_submit_job_to_processing()` (line 47) to add:

```python
    confirmed_crop_quad: list[list[float]] | None = None,
```

In the same function, add to the `camber_payload` dict (after `"encrypted_input": encrypted_input,` at line ~92):

```python
        if confirmed_crop_quad is not None:
            camber_payload["confirmed_crop_quad"] = confirmed_crop_quad
```

- [ ] **Step 3: Pass confirmed_crop_quad from submit_job handler**

In `app/api/routes/jobs.py`, update the `await _submit_job_to_processing(...)` call inside `submit_job()` (line 758) to add:

```python
        confirmed_crop_quad=body.confirmed_crop_quad,
```

- [ ] **Step 4: Run API tests to verify no regression**

```bash
cd "/Users/abhinav/Rythmiq One"
source .venv/bin/activate
pytest tests/ -k "api or job" -v --ignore=tests/worker 2>/dev/null | tail -20
```

If no API-specific tests exist, at minimum verify the FastAPI app imports cleanly:

```bash
python -c "from app.api.routes.jobs import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/models.py app/api/routes/jobs.py
git commit -m "feat: thread confirmed_crop_quad through API submit endpoint"
```

---

## Task 6: App API client

**Files:**
- Modify: `app-v2/services/api.ts:703-708` (`submitJob`)
- Modify: `app-v2/services/backgroundUpload.ts:38-80` (`startBackgroundUpload`)

- [ ] **Step 1: Update submitJob to accept and send confirmed quad**

In `app-v2/services/api.ts`, update `submitJob()` (line 703):

```ts
async submitJob(
  jobId: string,
  outputFormat: string = 'jpeg',
  confirmedCropQuad?: [[number,number],[number,number],[number,number],[number,number]],
): Promise<{ job_id: string; status: string }> {
  return apiRequest<{ job_id: string; status: string }>(`/jobs/${jobId}/submit`, {
    method: 'POST',
    body: JSON.stringify({
      output_format: outputFormat,
      ...(confirmedCropQuad ? { confirmed_crop_quad: confirmedCropQuad } : {}),
    }),
  })
},
```

- [ ] **Step 2: Update startBackgroundUpload to accept ConfirmedCrop[]**

In `app-v2/services/backgroundUpload.ts`, update the import at the top:

```ts
import { documentsApi } from './api'
import type { QueryClient } from '@tanstack/react-query'
import type { ConfirmedCrop } from '../stores/captureSession'
```

Update the function signature of `startBackgroundUpload()`:

```ts
export function startBackgroundUpload(
  confirmedCrops: ConfirmedCrop[],
  documentName: string,
  selectedCategory: string,
  selectedType: string,
  apiDocumentType: 'photo' | 'signature' | 'document',
  queryClient: QueryClient,
  outputFormat: string = 'jpeg',
) {
```

Update the loop body inside the async function. Replace:

```ts
      for (let i = 0; i < imageUris.length; i++) {
        const uri = imageUris[i];
        const name = documentName || `${selectedType}_${Date.now()}`;
        const filename = `${name}_${i + 1}.jpg`;

        const response = await fetch(uri);
        const blob = await response.blob();

        const { job_id, upload_url } = await documentsApi.createMasterJob(
          apiDocumentType,
          filename,
          'image/jpeg',
          blob.size,
          selectedCategory,
          selectedType,
        );

        await documentsApi.uploadToPresignedUrl(upload_url, uri, 'image/jpeg');
        await documentsApi.submitJob(job_id, outputFormat);
```

With:

```ts
      for (let i = 0; i < confirmedCrops.length; i++) {
        const crop = confirmedCrops[i];
        const name = documentName || `${selectedType}_${Date.now()}`;
        const filename = `${name}_${i + 1}.jpg`;

        const response = await fetch(crop.originalUri);
        const blob = await response.blob();

        const { job_id, upload_url } = await documentsApi.createMasterJob(
          apiDocumentType,
          filename,
          'image/jpeg',
          blob.size,
          selectedCategory,
          selectedType,
        );

        await documentsApi.uploadToPresignedUrl(upload_url, crop.originalUri, 'image/jpeg');
        await documentsApi.submitJob(job_id, outputFormat, crop.quad as [[number,number],[number,number],[number,number],[number,number]]);
```

Also update the `notify` call to use `confirmedCrops.length`:

```ts
  notify({ total: confirmedCrops.length, current: 0, done: false, error: undefined });
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd app-v2
npx tsc --noEmit
```

Expected: no new type errors.

- [ ] **Step 4: Commit**

```bash
git add app-v2/services/api.ts app-v2/services/backgroundUpload.ts
git commit -m "feat: pass confirmed_crop_quad through API client and background upload"
```

---

## Task 7: DocumentDetector Adapter

**Files:**
- Create: `app-v2/services/documentDetector.ts`

- [ ] **Step 1: Create the adapter module**

Create `app-v2/services/documentDetector.ts`:

```ts
/**
 * DocumentDetector — adapter for on-device (or server-side fallback) document
 * corner detection.
 *
 * Returns a quad in normalised 0.0–1.0 space relative to the original image
 * dimensions. Order: TL, TR, BR, BL.
 *
 * When detection fails or no library is available, returns null.
 * The caller (crop-preview.tsx) falls back to a full-image default quad.
 */

import type { NormalisedPoint, NormalisedQuad } from '../stores/captureSession'

export interface DetectionResult {
  quad: NormalisedQuad
  croppedUri?: string
}

/**
 * Full-image default quad. Used when detection fails so the user still
 * sees the image with adjustable corners at the four edges.
 */
export function defaultQuad(): NormalisedQuad {
  return [
    [0.02, 0.02],
    [0.98, 0.02],
    [0.98, 0.98],
    [0.02, 0.98],
  ]
}

/**
 * Detect document corners in a static image URI.
 *
 * Implementation choice (fill in during Task 7):
 *   A) On-device: wrap chosen library's static-image API
 *   B) Server-side: POST /detect with base64 image, receive quad
 *
 * Returns DetectionResult or null on failure.
 */
export async function detectDocument(
  imageUri: string,
  imageWidth: number,
  imageHeight: number,
): Promise<DetectionResult | null> {
  try {
    // ── IMPLEMENTATION: choose A or B based on library research in Task 1 ──

    // Option A (on-device library example — replace with actual library API):
    // const lib = await import('<chosen-library-package>')
    // const result = await lib.detectCorners(imageUri)
    // if (!result) return null
    // return {
    //   quad: [
    //     [result.topLeft.x / imageWidth, result.topLeft.y / imageHeight],
    //     [result.topRight.x / imageWidth, result.topRight.y / imageHeight],
    //     [result.bottomRight.x / imageWidth, result.bottomRight.y / imageHeight],
    //     [result.bottomLeft.x / imageWidth, result.bottomLeft.y / imageHeight],
    //   ],
    //   croppedUri: result.croppedImageUri,
    // }

    // Option B (server-side /detect endpoint):
    // import * as FileSystem from 'expo-file-system'
    // const b64 = await FileSystem.readAsStringAsync(imageUri, { encoding: FileSystem.EncodingType.Base64 })
    // const API_BASE_URL = process.env.EXPO_PUBLIC_WORKER_URL || 'https://rythmiq-worker-1048753379343.asia-south1.run.app'
    // const resp = await fetch(`${API_BASE_URL}/detect`, {
    //   method: 'POST',
    //   headers: { 'Content-Type': 'application/json' },
    //   body: JSON.stringify({ image_b64: b64 }),
    // })
    // const data = await resp.json()
    // if (!data.quad) return null
    // return { quad: data.quad as NormalisedQuad }

    // Until library is wired up, return null so default quad is used:
    return null
  } catch (e) {
    console.warn('[DocumentDetector] detection failed:', e)
    return null
  }
}
```

- [ ] **Step 2: Wire up the actual library**

Uncomment and fill in either Option A or Option B in the `detectDocument` function above, based on your Task 1 research. Remove the placeholder `return null` at the bottom once the real implementation is in place.

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd app-v2
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add app-v2/services/documentDetector.ts
git commit -m "feat: add DocumentDetector adapter for document corner detection"
```

---

## Task 8: CropOverlay Component

**Files:**
- Create: `app-v2/components/CropOverlay.tsx`

The overlay renders an SVG on top of the displayed image. Corner handles are draggable via RNGH v2 `GestureDetector` + Reanimated 4 shared values. The outside-quad area is dimmed with a semi-transparent overlay.

- [ ] **Step 1: Create the component**

Create `app-v2/components/CropOverlay.tsx`:

```tsx
/**
 * CropOverlay
 *
 * Renders an interactive document crop quad overlay over an image.
 * - Draggable white corner circles (40pt hit target, 12pt visible radius)
 * - Blue quad lines
 * - Blue edge midpoint handles (decorative, not draggable)
 * - Dimmed outside-quad area using SVG clip path
 * - Calls onQuadChange with normalised coords after each drag
 */

import React, { useCallback } from 'react'
import { StyleSheet, View } from 'react-native'
import Svg, { Polygon, Circle, Rect, Path, Defs, ClipPath } from 'react-native-svg'
import { Gesture, GestureDetector } from 'react-native-gesture-handler'
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  runOnJS,
} from 'react-native-reanimated'

import type { NormalisedQuad, NormalisedPoint } from '../stores/captureSession'

interface Props {
  /** Display dimensions of the image container */
  containerWidth: number
  containerHeight: number
  /** Initial quad in normalised 0.0–1.0 space */
  initialQuad: NormalisedQuad
  /** Called when the user finishes dragging a corner, with updated normalised quad */
  onQuadChange: (quad: NormalisedQuad) => void
}

const CORNER_HIT_SIZE = 40   // transparent hit target
const CORNER_RADIUS = 12     // visible circle radius
const MIDPOINT_SIZE = 10     // edge midpoint indicator

export default function CropOverlay({
  containerWidth,
  containerHeight,
  initialQuad,
  onQuadChange,
}: Props) {
  // Each corner: shared values in DISPLAY pixel space
  const corners = [0, 1, 2, 3].map(i => ({
    x: useSharedValue(initialQuad[i][0] * containerWidth),
    y: useSharedValue(initialQuad[i][1] * containerHeight),
  }))

  const emitChange = useCallback(() => {
    const quad: NormalisedQuad = corners.map(c => [
      Math.max(0, Math.min(1, c.x.value / containerWidth)),
      Math.max(0, Math.min(1, c.y.value / containerHeight)),
    ]) as NormalisedQuad
    onQuadChange(quad)
  }, [containerWidth, containerHeight, onQuadChange])

  const makeCornerGesture = (index: number) =>
    Gesture.Pan()
      .onUpdate(e => {
        corners[index].x.value = Math.max(0, Math.min(containerWidth, e.absoluteX))
        corners[index].y.value = Math.max(0, Math.min(containerHeight, e.absoluteY))
      })
      .onEnd(() => {
        runOnJS(emitChange)()
      })

  // Build polygon points string for SVG from shared values
  // We read .value directly in the render cycle (not in worklet)
  const polygonPoints = corners
    .map(c => `${c.x.value},${c.y.value}`)
    .join(' ')

  // Midpoints of each edge
  const midpoints = [
    { x: (corners[0].x.value + corners[1].x.value) / 2, y: (corners[0].y.value + corners[1].y.value) / 2 },
    { x: (corners[1].x.value + corners[2].x.value) / 2, y: (corners[1].y.value + corners[2].y.value) / 2 },
    { x: (corners[2].x.value + corners[3].x.value) / 2, y: (corners[2].y.value + corners[3].y.value) / 2 },
    { x: (corners[3].x.value + corners[0].x.value) / 2, y: (corners[3].y.value + corners[0].y.value) / 2 },
  ]

  const dimPath = `M0,0 L${containerWidth},0 L${containerWidth},${containerHeight} L0,${containerHeight} Z ` +
    `M${polygonPoints} Z`

  return (
    <View style={[StyleSheet.absoluteFillObject, { width: containerWidth, height: containerHeight }]}>
      <Svg width={containerWidth} height={containerHeight}>
        {/* Dimmed outside area */}
        <Path
          d={dimPath}
          fill="rgba(0,0,0,0.5)"
          fillRule="evenodd"
        />
        {/* Quad outline */}
        <Polygon
          points={polygonPoints}
          fill="none"
          stroke="#89C7FE"
          strokeWidth={2.5}
        />
        {/* Edge midpoint indicators */}
        {midpoints.map((mp, i) => (
          <Rect
            key={`mid-${i}`}
            x={mp.x - MIDPOINT_SIZE / 2}
            y={mp.y - MIDPOINT_SIZE / 2}
            width={MIDPOINT_SIZE}
            height={MIDPOINT_SIZE}
            rx={4}
            fill="#89C7FE"
          />
        ))}
        {/* Corner circles (visual only — gesture targets are Views below) */}
        {corners.map((c, i) => (
          <Circle
            key={`circle-${i}`}
            cx={c.x.value}
            cy={c.y.value}
            r={CORNER_RADIUS}
            fill="#FCFEFF"
            stroke="#89C7FE"
            strokeWidth={2.5}
          />
        ))}
      </Svg>

      {/* Draggable hit targets — transparent Views positioned over each corner */}
      {corners.map((c, i) => {
        const animStyle = useAnimatedStyle(() => ({
          transform: [
            { translateX: c.x.value - CORNER_HIT_SIZE / 2 },
            { translateY: c.y.value - CORNER_HIT_SIZE / 2 },
          ],
        }))
        return (
          <GestureDetector key={`gesture-${i}`} gesture={makeCornerGesture(i)}>
            <Animated.View
              style={[
                {
                  position: 'absolute',
                  width: CORNER_HIT_SIZE,
                  height: CORNER_HIT_SIZE,
                  top: 0,
                  left: 0,
                },
                animStyle,
              ]}
            />
          </GestureDetector>
        )
      })}
    </View>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd app-v2
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add app-v2/components/CropOverlay.tsx
git commit -m "feat: add CropOverlay component with draggable corners"
```

---

## Task 9: crop-preview.tsx Screen

**Files:**
- Create: `app-v2/app/(tabs)/crop-preview.tsx`

This screen:
1. Reads `sessionId` + `index` from route params
2. Runs detection on the current image
3. Shows the image with `CropOverlay`
4. "Looks Good" → saves `ConfirmedCrop` to store, navigates to next index or upload
5. "Recapture" → navigates to capture with `replaceIndex`
6. On unmount / back gesture: calls `clearSession()`

- [ ] **Step 1: Create the screen**

Create `app-v2/app/(tabs)/crop-preview.tsx`:

```tsx
/**
 * Crop Preview Screen
 *
 * Shows one captured image at a time with an interactive document quad overlay.
 * User adjusts corners if needed, then confirms ("Looks Good") or recaptures.
 * Confirmed quads accumulate in the capture session store.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react'
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Image,
  Dimensions,
  Alert,
} from 'react-native'
import { SafeAreaView } from 'react-native-safe-area-context'
import { router, useLocalSearchParams } from 'expo-router'
import { useCaptureSession, type NormalisedQuad } from '../../stores/captureSession'
import { detectDocument, defaultQuad } from '../../services/documentDetector'
import CropOverlay from '../../components/CropOverlay'

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window')

const colors = {
  inkBlack: '#070712',
  mayaBlue: '#89C7FE',
  trueCobalt: '#1A2595',
  shadowGrey: '#191B26',
  white: '#FCFEFF',
}

export default function CropPreviewScreen() {
  const params = useLocalSearchParams<{ sessionId?: string; index?: string }>()
  const index = parseInt(params.index ?? '0', 10)

  const { images, docType, confirmCrop, clearSession } = useCaptureSession()
  const currentImage = images[index]

  const [isDetecting, setIsDetecting] = useState(true)
  const [detectionFailed, setDetectionFailed] = useState(false)
  const [currentQuad, setCurrentQuad] = useState<NormalisedQuad>(defaultQuad())
  const [croppedUri, setCroppedUri] = useState<string | undefined>()
  const [hintVisible, setHintVisible] = useState(true)
  const hasInteracted = useRef(false)

  // Image display dimensions — maintain aspect ratio within screen
  const [imageLayout, setImageLayout] = useState({ width: SCREEN_WIDTH - 32, height: SCREEN_HEIGHT * 0.6 })

  // Run detection when screen mounts or image changes
  useEffect(() => {
    if (!currentImage) return
    setIsDetecting(true)
    setDetectionFailed(false)
    setHintVisible(true)
    hasInteracted.current = false

    detectDocument(currentImage.uri, currentImage.width, currentImage.height)
      .then(result => {
        if (result) {
          setCurrentQuad(result.quad)
          setCroppedUri(result.croppedUri)
          setDetectionFailed(false)
        } else {
          setCurrentQuad(defaultQuad())
          setCroppedUri(undefined)
          setDetectionFailed(true)
        }
      })
      .catch(() => {
        setCurrentQuad(defaultQuad())
        setDetectionFailed(true)
      })
      .finally(() => setIsDetecting(false))
  }, [currentImage?.uri])

  const handleQuadChange = useCallback((quad: NormalisedQuad) => {
    setCurrentQuad(quad)
    if (!hasInteracted.current) {
      hasInteracted.current = true
      setHintVisible(false)
    }
  }, [])

  const handleLooksGood = useCallback(() => {
    if (!currentImage) return

    confirmCrop(index, {
      originalUri: currentImage.uri,
      croppedUri,
      quad: currentQuad,
    })

    const nextIndex = index + 1
    if (nextIndex < images.length) {
      // More images to review
      router.replace({
        pathname: '/(tabs)/crop-preview',
        params: { sessionId: params.sessionId, index: String(nextIndex) },
      })
    } else {
      // All images confirmed — proceed to upload
      router.replace('/(tabs)/upload')
    }
  }, [currentImage, currentQuad, croppedUri, index, images.length, confirmCrop, params.sessionId])

  const handleRecapture = useCallback(() => {
    router.push({
      pathname: '/(tabs)/capture',
      params: { replaceIndex: String(index), sessionId: params.sessionId },
    })
  }, [index, params.sessionId])

  // Clear session on back gesture (user abandons flow)
  useEffect(() => {
    return () => {
      // Only clear if navigating away without completing (no confirmed crops for remaining images)
    }
  }, [])

  if (!currentImage) {
    return (
      <View style={styles.container}>
        <ActivityIndicator color={colors.mayaBlue} />
      </View>
    )
  }

  return (
    <SafeAreaView style={styles.container} edges={['top', 'bottom']}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.progressPill}>
          <Text style={styles.progressText}>Image {index + 1} of {images.length}</Text>
        </View>
        <Text style={styles.headerTitle}>Review Crop</Text>
        <View style={{ width: 80 }} />
      </View>

      {/* Image + overlay */}
      <View style={styles.imageContainer}>
        <View
          style={[styles.imageWrapper, { width: imageLayout.width, height: imageLayout.height }]}
          onLayout={e => {
            const { width, height } = e.nativeEvent.layout
            setImageLayout({ width, height })
          }}
        >
          <Image
            source={{ uri: currentImage.uri }}
            style={StyleSheet.absoluteFillObject}
            resizeMode="contain"
          />
          {!isDetecting && (
            <CropOverlay
              containerWidth={imageLayout.width}
              containerHeight={imageLayout.height}
              initialQuad={currentQuad}
              onQuadChange={handleQuadChange}
            />
          )}
          {isDetecting && (
            <View style={styles.detectingOverlay}>
              <ActivityIndicator color={colors.mayaBlue} size="large" />
            </View>
          )}
        </View>
      </View>

      {/* Hint text */}
      <View style={styles.hintContainer}>
        {hintVisible && (
          <Text style={styles.hintText}>
            {detectionFailed
              ? 'No document detected — adjust corners manually'
              : 'Drag the corners to adjust the crop'}
          </Text>
        )}
      </View>

      {/* Buttons */}
      <View style={styles.footer}>
        <TouchableOpacity style={styles.recaptureButton} onPress={handleRecapture}>
          <Text style={styles.recaptureText}>↺  Recapture</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.looksGoodButton, isDetecting && styles.buttonDisabled]}
          onPress={handleLooksGood}
          disabled={isDetecting}
        >
          <Text style={styles.looksGoodText}>Looks Good  →</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#070712',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: colors.shadowGrey,
  },
  progressPill: {
    backgroundColor: colors.shadowGrey,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
  },
  progressText: {
    color: colors.mayaBlue,
    fontSize: 13,
    fontWeight: '600',
  },
  headerTitle: {
    color: colors.white,
    fontSize: 16,
    fontWeight: '600',
  },
  imageContainer: {
    flex: 1,
    padding: 16,
    justifyContent: 'center',
    alignItems: 'center',
  },
  imageWrapper: {
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: '#0a0a14',
  },
  detectingOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  hintContainer: {
    height: 32,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 16,
  },
  hintText: {
    color: 'rgba(255,255,255,0.5)',
    fontSize: 13,
    textAlign: 'center',
  },
  footer: {
    flexDirection: 'row',
    gap: 12,
    padding: 16,
    paddingBottom: 8,
    borderTopWidth: 1,
    borderTopColor: colors.shadowGrey,
  },
  recaptureButton: {
    flex: 1,
    backgroundColor: colors.shadowGrey,
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.15)',
    borderRadius: 14,
    padding: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  recaptureText: {
    color: colors.white,
    fontSize: 15,
    fontWeight: '600',
  },
  looksGoodButton: {
    flex: 1,
    backgroundColor: colors.trueCobalt,
    borderRadius: 14,
    padding: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  looksGoodText: {
    color: colors.white,
    fontSize: 15,
    fontWeight: '600',
  },
  buttonDisabled: {
    opacity: 0.4,
  },
})
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd app-v2
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add app-v2/app/(tabs)/crop-preview.tsx
git commit -m "feat: add crop-preview screen"
```

---

## Task 10: Modify capture.tsx

**Files:**
- Modify: `app-v2/app/(tabs)/capture.tsx`

Two changes:
1. `proceedToUpload` now starts a session in the store and navigates to `crop-preview` instead of `upload`
2. Handle `replaceIndex` param — single-shot recapture mode

- [ ] **Step 1: Add imports and read replaceIndex param**

At the top of `capture.tsx`, add imports:

```tsx
import { useLocalSearchParams } from 'expo-router'
import { useCaptureSession } from '../../stores/captureSession'
```

Inside `CaptureScreen()`, add:

```tsx
const params = useLocalSearchParams<{ replaceIndex?: string; sessionId?: string }>()
const replaceIndex = params.replaceIndex !== undefined ? parseInt(params.replaceIndex, 10) : null
const { startSession, replaceImage } = useCaptureSession()
```

- [ ] **Step 2: Replace proceedToUpload**

Replace the existing `proceedToUpload` function with:

```tsx
const proceedToUpload = useCallback(() => {
  if (capturedImages.length === 0) {
    Alert.alert('No Images', 'Please capture or select at least one image.')
    return
  }

  if (replaceIndex !== null && params.sessionId) {
    // Recapture mode: replace one image in the existing session
    replaceImage(replaceIndex, capturedImages[0])
    router.replace({
      pathname: '/(tabs)/crop-preview',
      params: { sessionId: params.sessionId, index: String(replaceIndex) },
    })
    return
  }

  // Normal mode: start a new session, go to crop preview from index 0
  const sessionId = startSession(capturedImages, selectedDocType)
  router.push({
    pathname: '/(tabs)/crop-preview',
    params: { sessionId, index: '0' },
  })
}, [capturedImages, selectedDocType, replaceIndex, params.sessionId, startSession, replaceImage])
```

- [ ] **Step 3: Single-shot mode in recapture**

When `replaceIndex` is not null, the capture screen should auto-return after one photo is taken. Update `takePicture`:

```tsx
const takePicture = useCallback(async () => {
  if (!cameraRef.current || isCapturing) return
  setIsCapturing(true)
  try {
    const photo = await cameraRef.current.takePictureAsync({
      quality: 0.9,
      skipProcessing: false,
    })
    if (photo) {
      const newImage = { uri: photo.uri, width: photo.width, height: photo.height }
      if (replaceIndex !== null) {
        // Single-shot recapture: immediately replace and navigate back
        setCapturedImages([newImage])
      } else {
        setCapturedImages(prev => [...prev, newImage])
      }
    }
  } catch (error) {
    Alert.alert('Error', 'Failed to capture image. Please try again.')
  } finally {
    setIsCapturing(false)
  }
}, [isCapturing, replaceIndex])
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd app-v2
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add app-v2/app/(tabs)/capture.tsx
git commit -m "feat: navigate to crop-preview from capture; handle recapture mode"
```

---

## Task 11: Modify upload.tsx

**Files:**
- Modify: `app-v2/app/(tabs)/upload.tsx`

Two changes:
1. Read images from the session store (not from route params)
2. Show `croppedUri` as the image thumbnail if available

- [ ] **Step 1: Add session store import and read confirmed crops**

Add imports at the top of `upload.tsx`:

```tsx
import { useCaptureSession } from '../../stores/captureSession'
```

Inside `UploadScreen()`, add:

```tsx
const { getSession, clearSession } = useCaptureSession()
const session = getSession()
```

- [ ] **Step 2: Replace params-based imageUris with session-based confirmed crops**

Remove the existing `useEffect` that parses `params.images`.

Replace the existing `imageUris` and `setImageUris` state with:

```tsx
// Images come from the session store (confirmed crops), not from route params
const confirmedCrops = session.confirmed
const imageUris = confirmedCrops.map(c => c.croppedUri ?? c.originalUri)
```

The `FlatList` in the image preview section already uses `imageUris` — no change needed there for display.

- [ ] **Step 3: Update handleUpload to use confirmedCrops**

Replace:

```tsx
    startBackgroundUpload(
      imageUris,
      documentName,
      selectedCategory,
      selectedType,
      apiDocumentType,
      queryClient,
      useLossless ? 'pdf_mrc' : 'jpeg',
    );
```

With:

```tsx
    startBackgroundUpload(
      confirmedCrops,
      documentName,
      selectedCategory,
      selectedType,
      apiDocumentType,
      queryClient,
      useLossless ? 'pdf_mrc' : 'jpeg',
    )
    clearSession()
```

- [ ] **Step 4: Pre-select document category from session docType**

Replace the existing `useEffect` that reads `params.docType` — keep its logic but read from `session.docType` instead:

```tsx
useEffect(() => {
  const docType = session.docType
  if (!docType) return

  const docTypeToCategory: Record<string, DocumentCategory> = {
    Photo: 'photograph',
    Signature: 'signature',
    'ID Card': 'identity',
    'Mark Sheet': 'academic',
    Other: 'other',
  }

  const mappedCategory = docTypeToCategory[docType] ?? 'identity'
  setSelectedCategory(mappedCategory)
  setSelectedType(documentCategories[mappedCategory].types[0])
}, [session.docType])
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd app-v2
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Run full worker tests one final time**

```bash
cd "/Users/abhinav/Rythmiq One"
source .venv/bin/activate
pytest tests/worker/test_confirmed_crop_quad.py tests/test_enhancement_guardrails.py tests/worker/test_quality_photo_scoring.py -v
```

Expected: 57 tests pass (6 + 34 + 17).

- [ ] **Step 7: Final commit**

```bash
git add app-v2/app/(tabs)/upload.tsx
git commit -m "feat: upload screen reads from session store with confirmed crop quads"
```

---

## Done

All tasks complete. The full flow is now:

`capture.tsx` → (captures N images, starts session) → `crop-preview.tsx` (detects quad, user adjusts, confirms per image) → `upload.tsx` (reads confirmed crops from store) → `backgroundUpload.ts` (passes `confirmed_crop_quad` per job to API) → worker (`detect_and_crop_document()` uses quad directly, skips cascade).

To verify end-to-end manually:
1. `cd app-v2 && npm start` → open on device
2. Capture a document photo → tap Done
3. Crop preview screen appears with detected quad overlay
4. Adjust corners, tap Looks Good
5. Upload screen shows the confirmed image
6. Create Master → job processes with confirmed quad
7. Check worker logs for `[ENHANCEMENT] Using confirmed crop quad from app preview`
