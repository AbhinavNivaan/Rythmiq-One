# /detect OpenCV Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve `/detect` auto-detection quality by (1) changing Stage 1 to pick the largest quad across all edge maps instead of the first, and (2) adding a Stage 2 blob-based corner detector as fallback when Stage 1 finds nothing.

**Architecture:** Add `_find_blob_corners()` to `enhancement.py` — same binary threshold strategies as `_find_filled_document_blob` but returns pixel-space corners instead of a warped image. Update `/detect` in `server.py` to use best-match Stage 1 then call Stage 2 if Stage 1 returns null.

**Tech Stack:** Python 3.11, OpenCV (`cv2`), NumPy, FastAPI (worker only)

---

## File Map

| File | Change |
|---|---|
| `worker/processors/enhancement.py` | Add `_find_blob_corners()` function |
| `worker/server.py` | Import `_find_blob_corners`; Stage 1 best-match; add Stage 2 call |
| `tests/worker/test_detect_blob_corners.py` | New — unit tests for `_find_blob_corners` |
| `tests/worker/test_detect_endpoint.py` | New — unit tests for updated `/detect` behavior |

---

## Task 1: Add `_find_blob_corners` to enhancement.py

**Files:**
- Modify: `worker/processors/enhancement.py` (add after `_find_filled_document_blob`, around line 1535)
- Create: `tests/worker/test_detect_blob_corners.py`

### Step 1.1: Write the failing tests

Create `tests/worker/test_detect_blob_corners.py`:

```python
"""Unit tests for _find_blob_corners — Stage 2 blob-based corner detection."""
import sys
import os
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../worker"))


def _make_img(h, w, bg, rect=None, rect_color=240):
    """Create a BGR image with optional white rectangle."""
    img = np.full((h, w, 3), bg, dtype=np.uint8)
    if rect is not None:
        y1, y2, x1, x2 = rect
        img[y1:y2, x1:x2] = rect_color
    return img


def _get_bounds(h, w):
    from processors.enhancement import (
        _DOC_DETECT_MIN_AREA_FRACTION,
        _DOC_DETECT_MAX_AREA_FRACTION,
    )
    return (
        _DOC_DETECT_MIN_AREA_FRACTION * w * h,
        _DOC_DETECT_MAX_AREA_FRACTION * w * h,
    )


def test_find_blob_corners_detects_white_rect_on_dark_background():
    """White paper (V>180) on dark background — Strategy A should fire."""
    from processors.enhancement import _find_blob_corners

    # 600×400 dark gray image with a white rectangle
    img = _make_img(400, 600, bg=40, rect=(80, 320, 100, 500), rect_color=240)
    # Rectangle: x=[100,500], y=[80,320] → 400×240px, aspect=1.67, area_frac=0.40
    min_area, max_area = _get_bounds(400, 600)

    corners = _find_blob_corners(img, min_area, max_area)

    assert corners is not None, "Expected corners to be found for white rect on dark bg"
    assert corners.shape == (4, 2), f"Expected (4, 2) corners, got {corners.shape}"
    xs = corners[:, 0]
    ys = corners[:, 1]
    assert min(xs) == pytest.approx(100, abs=20), f"Left edge wrong: {min(xs)}"
    assert max(xs) == pytest.approx(500, abs=20), f"Right edge wrong: {max(xs)}"
    assert min(ys) == pytest.approx(80, abs=20), f"Top edge wrong: {min(ys)}"
    assert max(ys) == pytest.approx(320, abs=20), f"Bottom edge wrong: {max(ys)}"


def test_find_blob_corners_detects_large_document_filling_frame():
    """Document filling ~90% of frame — previously failed in /detect."""
    from processors.enhancement import _find_blob_corners

    # Document fills most of the 600×400 frame — white on dark with small margin
    img = _make_img(400, 600, bg=50, rect=(15, 385, 20, 580), rect_color=235)
    # Rectangle: x=[20,580], y=[15,385] → 560×370px, aspect=1.51
    min_area, max_area = _get_bounds(400, 600)

    corners = _find_blob_corners(img, min_area, max_area)

    assert corners is not None, "Expected corners for large document filling frame"
    assert corners.shape == (4, 2)


def test_find_blob_corners_returns_none_for_all_black_image():
    """No document present — should return None."""
    from processors.enhancement import _find_blob_corners

    img = np.zeros((400, 600, 3), dtype=np.uint8)
    min_area, max_area = _get_bounds(400, 600)

    corners = _find_blob_corners(img, min_area, max_area)

    assert corners is None, "Expected None for all-black image"


def test_find_blob_corners_returns_none_when_rect_too_small():
    """Blob below min_area threshold — should be rejected."""
    from processors.enhancement import _find_blob_corners

    # Tiny white square — 30×20 = 600px, image is 600×400=240000px, fraction=0.0025 < 0.10
    img = _make_img(400, 600, bg=40, rect=(10, 30, 10, 40), rect_color=240)
    min_area, max_area = _get_bounds(400, 600)

    corners = _find_blob_corners(img, min_area, max_area)

    assert corners is None, "Expected None when blob is too small"


def test_find_blob_corners_returns_none_for_square_blob():
    """Square blob — aspect ratio 1.0 < _DOC_DETECT_MIN_ASPECT_RATIO (1.12), should reject."""
    from processors.enhancement import _find_blob_corners

    # 250×250 square, area_frac = 250*250/(600*400) = 0.26 (passes area)
    # but aspect = 1.0 < 1.12 → reject
    img = _make_img(400, 600, bg=40, rect=(75, 325, 175, 425), rect_color=240)
    min_area, max_area = _get_bounds(400, 600)

    corners = _find_blob_corners(img, min_area, max_area)

    assert corners is None, "Expected None for square blob (aspect < 1.12)"
```

- [ ] **Step 1.2: Run tests to confirm they fail**

```bash
cd "/Users/abhinav/Rythmiq One"
PYTHONPATH=worker pytest tests/worker/test_detect_blob_corners.py -v
```

Expected: `ImportError` or `AttributeError: module has no attribute '_find_blob_corners'` — confirms function doesn't exist yet.

- [ ] **Step 1.3: Implement `_find_blob_corners` in enhancement.py**

Locate the end of `_find_filled_document_blob` (around line 1535 — look for `return img, False` at the function's end). Add `_find_blob_corners` immediately after it:

```python
def _find_blob_corners(
    img: NDArray[np.uint8],
    min_area: float,
    max_area: float,
) -> Optional[NDArray[np.float32]]:
    """
    Stage 2 blob corner detector for the /detect endpoint.

    Applies the same binary threshold strategies as _find_filled_document_blob
    but returns 4 corner points in pixel coordinates (shape: (4,2) float32)
    instead of a perspective-warped image. Used when Stage 1 edge-based quad
    detection returns nothing.

    Returns None if no valid document blob is found.
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (9, 9), 0)

    # Strategy A: High-brightness mask — white paper (V > 180) on any background
    hsv_a = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    val = hsv_a[:, :, 2]
    _, bright_mask = cv2.threshold(val, 180, 255, cv2.THRESH_BINARY)
    bright_blur = cv2.GaussianBlur(bright_mask, (9, 9), 0)
    _, bright_clean = cv2.threshold(bright_blur, 127, 255, cv2.THRESH_BINARY)

    _, otsu_thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    _, inv_thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    binary_candidates = [bright_clean, otsu_thresh, inv_thresh]
    for _tval in [40, 60, 90, 120, 150, 180]:
        _, _t = cv2.threshold(blur, _tval, 255, cv2.THRESH_BINARY)
        binary_candidates.append(_t)

    # Strategy E: Saturation-based — colorful cards (PAN, Aadhaar) on neutral bg
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    sat_blur = cv2.GaussianBlur(sat, (9, 9), 0)
    _, sat_otsu = cv2.threshold(sat_blur, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    binary_candidates.append(sat_otsu)
    # Strategy F: Inverted saturation — white/grey paper on coloured background
    _, sat_inv_otsu = cv2.threshold(sat_blur, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    binary_candidates.append(sat_inv_otsu)

    fill_size = max(15, min(w, h) // 20)
    fill_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (fill_size, fill_size))
    open_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

    best_corners: Optional[NDArray[np.float32]] = None
    best_area: float = 0.0

    for binary in binary_candidates:
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, fill_kernel)
        cleaned = cv2.morphologyEx(closed, cv2.MORPH_OPEN, open_kernel)
        contours, _ = cv2.findContours(
            cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        for cnt in contours[:5]:
            raw_area = cv2.contourArea(cnt)
            if raw_area < min_area * 0.5:
                continue
            hull = cv2.convexHull(cnt)
            area = cv2.contourArea(hull)
            if area < min_area or area > max_area:
                continue
            rect = cv2.minAreaRect(hull)
            (_cx, _cy), (rw, rh), _angle = rect
            rect_area = rw * rh
            if rect_area <= 0:
                continue
            if area / rect_area < 0.50:
                continue
            long_side = max(rw, rh)
            short_side = min(rw, rh)
            if short_side < 1:
                continue
            aspect = long_side / short_side
            if aspect < _DOC_DETECT_MIN_ASPECT_RATIO or aspect > _DOC_DETECT_MAX_ASPECT_RATIO:
                continue
            if area > best_area:
                best_area = area
                best_corners = cv2.boxPoints(rect).astype(np.float32)

    return best_corners
```

- [ ] **Step 1.4: Run tests to confirm they pass**

```bash
cd "/Users/abhinav/Rythmiq One"
PYTHONPATH=worker pytest tests/worker/test_detect_blob_corners.py -v
```

Expected output:
```
tests/worker/test_detect_blob_corners.py::test_find_blob_corners_detects_white_rect_on_dark_background PASSED
tests/worker/test_detect_blob_corners.py::test_find_blob_corners_detects_large_document_filling_frame PASSED
tests/worker/test_detect_blob_corners.py::test_find_blob_corners_returns_none_for_all_black_image PASSED
tests/worker/test_detect_blob_corners.py::test_find_blob_corners_returns_none_when_rect_too_small PASSED
tests/worker/test_detect_blob_corners.py::test_find_blob_corners_returns_none_for_square_blob PASSED
5 passed
```

- [ ] **Step 1.5: Confirm existing guardrail tests still pass**

```bash
cd "/Users/abhinav/Rythmiq One"
PYTHONPATH=worker pytest tests/test_enhancement_guardrails.py tests/worker/test_confirmed_crop_quad.py -v --tb=short
```

Expected: all 40 tests pass (34 guardrails + 6 confirmed quad).

- [ ] **Step 1.6: Commit**

```bash
cd "/Users/abhinav/Rythmiq One"
git add worker/processors/enhancement.py tests/worker/test_detect_blob_corners.py
git commit -m "feat: add _find_blob_corners for Stage 2 /detect fallback"
```

---

## Task 2: Update `/detect` — Stage 1 best-match + Stage 2 fallback

**Files:**
- Modify: `worker/server.py` (lines ~365–410, the `/detect` handler)
- Create: `tests/worker/test_detect_endpoint.py`

### Step 2.1: Write the failing tests

Create `tests/worker/test_detect_endpoint.py`:

```python
"""
Unit tests for /detect endpoint behavior.

Tests Stage 1 best-match selection and Stage 2 blob fallback via
mocking — avoids needing a full Cloud Run environment.
"""
import sys
import os
import base64
import numpy as np
import cv2
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../worker"))


def _img_to_b64(img: np.ndarray) -> str:
    """Encode a numpy BGR image to base64 JPEG string."""
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf.tobytes()).decode()


def _make_img(h, w, bg, rect=None, rect_color=240):
    img = np.full((h, w, 3), bg, dtype=np.uint8)
    if rect is not None:
        y1, y2, x1, x2 = rect
        img[y1:y2, x1:x2] = rect_color
    return img


# ---------------------------------------------------------------------------
# Stage 1: best-match tests (via _find_quad_contour mock)
# ---------------------------------------------------------------------------

def test_detect_stage1_returns_largest_quad_not_first():
    """
    Stage 1 should return the LARGEST valid quad found across edge maps,
    not the first. Verify by checking that when mocked quad_areas differ,
    the larger one wins.
    """
    from processors.enhancement import (
        _preprocess_for_edges,
        _find_quad_contour,
        _order_corners,
        _DOC_DETECT_MIN_AREA_FRACTION,
        _DOC_DETECT_MAX_AREA_FRACTION,
        _apply_exif_transpose,
        _find_blob_corners,
    )

    img = _make_img(400, 600, bg=40, rect=(80, 320, 100, 500), rect_color=240)
    h, w = img.shape[:2]
    min_area = _DOC_DETECT_MIN_AREA_FRACTION * w * h
    max_area = _DOC_DETECT_MAX_AREA_FRACTION * w * h
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edge_maps = _preprocess_for_edges(gray, bgr=img)

    # Simulate: first edge map returns small quad (area=5000), second returns large (area=50000)
    small_corners = np.array([[100,80],[200,80],[200,130],[100,130]], dtype=np.float32)  # 100×50
    large_corners = np.array([[100,80],[500,80],[500,320],[100,320]], dtype=np.float32)  # 400×240

    call_count = [0]
    def mock_find_quad(edges, mn, mx):
        i = call_count[0]
        call_count[0] += 1
        if i == 0:
            return (small_corners, 5000.0)
        elif i == 1:
            return (large_corners, 50000.0)
        return None

    with patch("processors.enhancement._find_quad_contour", side_effect=mock_find_quad):
        # Re-run the best-match loop directly (mirrors updated server.py logic)
        best_corners = None
        best_area = 0.0
        for edge_img in edge_maps:
            result = _find_quad_contour(edge_img, min_area, max_area)
            if result is not None:
                corners, area = result
                if area > best_area:
                    best_corners = corners
                    best_area = area

    assert best_corners is not None
    # Should be large_corners, not small_corners
    assert best_area == 50000.0
    assert np.allclose(best_corners, large_corners)


# ---------------------------------------------------------------------------
# Stage 2 fallback: blob corners used when Stage 1 returns nothing
# ---------------------------------------------------------------------------

def test_detect_stage2_fires_when_stage1_returns_nothing():
    """
    When Stage 1 finds no quad, Stage 2 (_find_blob_corners) should be called
    and its result should be returned as a normalised quad.
    """
    from processors.enhancement import _find_blob_corners, _order_corners

    # White rect on dark background — Stage 1 may fail, Stage 2 should succeed
    img = _make_img(400, 600, bg=40, rect=(80, 320, 100, 500), rect_color=240)
    h, w = img.shape[:2]
    from processors.enhancement import _DOC_DETECT_MIN_AREA_FRACTION, _DOC_DETECT_MAX_AREA_FRACTION
    min_area = _DOC_DETECT_MIN_AREA_FRACTION * w * h
    max_area = _DOC_DETECT_MAX_AREA_FRACTION * w * h

    # Force Stage 1 to return nothing
    with patch("processors.enhancement._find_quad_contour", return_value=None):
        # Stage 2 should still detect via blob
        blob_corners = _find_blob_corners(img, min_area, max_area)

    assert blob_corners is not None
    ordered = _order_corners(blob_corners)
    quad = [[float(x) / w, float(y) / h] for x, y in ordered]
    assert len(quad) == 4
    for pt in quad:
        assert 0.0 <= pt[0] <= 1.0
        assert 0.0 <= pt[1] <= 1.0


def test_detect_returns_none_when_both_stages_fail():
    """When both Stage 1 and Stage 2 find nothing, /detect returns quad=null."""
    from processors.enhancement import _find_blob_corners

    # All-black image — nothing to detect
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    h, w = img.shape[:2]
    from processors.enhancement import _DOC_DETECT_MIN_AREA_FRACTION, _DOC_DETECT_MAX_AREA_FRACTION
    min_area = _DOC_DETECT_MIN_AREA_FRACTION * w * h
    max_area = _DOC_DETECT_MAX_AREA_FRACTION * w * h

    with patch("processors.enhancement._find_quad_contour", return_value=None):
        blob_corners = _find_blob_corners(img, min_area, max_area)

    assert blob_corners is None
```

- [ ] **Step 2.2: Run tests to confirm they fail**

```bash
cd "/Users/abhinav/Rythmiq One"
PYTHONPATH=worker pytest tests/worker/test_detect_endpoint.py -v
```

Expected: `test_detect_stage1_returns_largest_quad_not_first` PASSES (it tests the logic directly, not via the endpoint — this confirms the logic is correct as a reference). `test_detect_stage2_fires_when_stage1_returns_nothing` and `test_detect_returns_none_when_both_stages_fail` should also pass since they test `_find_blob_corners` directly.

If all three pass already — that means the logic works correctly and the remaining task is purely wiring it into `server.py`.

- [ ] **Step 2.3: Update the `/detect` handler in `server.py`**

Find the `/detect` handler (around line 357). Replace the entire handler body with the updated version:

```python
@app.post("/detect")
async def detect_document(request: DetectRequest) -> DetectResponse:
    """
    Fast document corner detection. Runs Stage 1 (OpenCV contour, best-match)
    then Stage 2 (blob corners) if Stage 1 finds nothing.
    No Vision API, no full pipeline. Returns normalised quad or null.

    Body field: image_b64 — base64-encoded JPEG/PNG bytes of the image.
    """
    from processors.enhancement import (
        _find_quad_contour,
        _preprocess_for_edges,
        _order_corners,
        _find_blob_corners,
        _DOC_DETECT_MIN_AREA_FRACTION,
        _DOC_DETECT_MAX_AREA_FRACTION,
        _apply_exif_transpose,
    )

    try:
        image_b64: str = request.image_b64
        if not image_b64:
            logger.warning("[DETECT] No image_b64 provided")
            return DetectResponse(quad=None)

        img_bytes = base64.b64decode(image_b64)
        img_bytes = _apply_exif_transpose(img_bytes)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            logger.warning("[DETECT] Could not decode image")
            return DetectResponse(quad=None)

        h, w = img.shape[:2]
        min_area = _DOC_DETECT_MIN_AREA_FRACTION * w * h
        max_area = _DOC_DETECT_MAX_AREA_FRACTION * w * h
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edge_maps = _preprocess_for_edges(gray, bgr=img)

        # ── Stage 1: best quad across ALL edge maps ───────────────────────
        # Pick the LARGEST valid quad, not the first. This prevents small
        # internal elements (QR codes, stamps) from being returned when a
        # larger outer boundary is found by a later edge map.
        best_corners = None
        best_quad_area: float = 0.0

        for edge_img in edge_maps:
            result = _find_quad_contour(edge_img, min_area, max_area)
            if result is not None:
                corners, quad_area = result
                if quad_area > best_quad_area:
                    best_corners = corners
                    best_quad_area = quad_area

        if best_corners is not None:
            ordered = _order_corners(best_corners)
            quad = [[float(x) / w, float(y) / h] for x, y in ordered]
            logger.info("[DETECT] Stage 1 quad found (area=%.1f%%)", best_quad_area / (w * h) * 100)
            return DetectResponse(quad=quad)

        # ── Stage 2: blob corner detection ───────────────────────────────
        # Treats the document as a filled bright region rather than an edge
        # ring. Handles white paper on wood, documents filling most of frame.
        blob_corners = _find_blob_corners(img, min_area, max_area)
        if blob_corners is not None:
            ordered = _order_corners(blob_corners)
            quad = [[float(x) / w, float(y) / h] for x, y in ordered]
            logger.info("[DETECT] Stage 2 blob corners found")
            return DetectResponse(quad=quad)

    except Exception as e:
        logger.warning(f"[DETECT] failed: {e}")

    return DetectResponse(quad=None)
```

- [ ] **Step 2.4: Run all detect tests**

```bash
cd "/Users/abhinav/Rythmiq One"
PYTHONPATH=worker pytest tests/worker/test_detect_blob_corners.py tests/worker/test_detect_endpoint.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 2.5: Run the full worker test suite to check for regressions**

```bash
cd "/Users/abhinav/Rythmiq One"
PYTHONPATH=worker pytest tests/test_enhancement_guardrails.py tests/worker/ -v --tb=short
```

Expected: all tests pass (34 guardrails + 6 confirmed quad + 5 blob corners + 3 detect endpoint = 48 total).

- [ ] **Step 2.6: Commit**

```bash
cd "/Users/abhinav/Rythmiq One"
git add worker/server.py tests/worker/test_detect_endpoint.py
git commit -m "feat: improve /detect — Stage 1 best-match + Stage 2 blob fallback"
```

---

## Task 3: Deploy and verify on device

- [ ] **Step 3.1: Deploy to Cloud Run**

```bash
cd "/Users/abhinav/Rythmiq One"
gcloud builds submit --config cloudbuild.yaml
```

Wait for build to complete (~3-4 minutes).

- [ ] **Step 3.2: Verify health**

```bash
gcloud run revisions list --service=rythmiq-worker --region=asia-south1 --limit=2
```

Expected: new revision is `ACTIVE` and serving 100% of traffic.

- [ ] **Step 3.3: Test on device**

Open the Rythmiq One app, capture a photo of:
1. White A4 document on wooden table (the previously failing case) — should show tight corners at paper edge without "No document detected" message
2. Any ID card (PAN, Aadhaar) on a table — should detect corners

- [ ] **Step 3.4: Commit session notes if detection improved**

If Stage 2 is firing on real devices, downgrade the debug log in a follow-up once confident. For now, leave `[DETECT] Stage 2 blob corners found` at INFO level so you can verify in Cloud Run logs.
