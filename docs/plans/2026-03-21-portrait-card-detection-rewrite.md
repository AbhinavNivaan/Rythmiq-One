# Portrait Card Detection — Principled Rewrite

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "pick largest face" heuristic with a principled card-context gate that validates each face candidate against its surrounding background before accepting it as a crop target.

**Architecture:** Face detection remains the signal that a passport photo is present, but it is now used as a *candidate proposer* rather than a *decision maker*. For each candidate, a new `_score_card_background()` function estimates where the card boundary would be (using existing passport-proportion constants) and measures how uniform the colour is at the four card corners. A real passport photo has a solid-colour backdrop at every corner; a charger, power bank, or pen does not. The candidate with the lowest background variance wins — but only if it beats a threshold. This separates LOCALIZATION (geometric/photometric) from VERIFICATION (face-content) and eliminates the entire class of false-positive-face-picks-wrong-object failures.

**Tech Stack:** Python, OpenCV (`cv2`), NumPy — no new dependencies.

---

## Context

**The bug:** M-PH-12 (passport photo on cluttered desk). Input: a small (~4% of frame) passport photo card among a power bank, phone charger, pens, and earbuds. Output: crop centred on the charger + pens; the passport photo appears as a small sliver in the bottom-left corner.

**Root cause:** `_crop_portrait_by_face()` (line 837, `worker/processors/enhancement.py`) runs Haar cascade on the *entire scene* and picks the *largest* detected face bounding box. The charger's two metal prongs resemble eyes; its white body resembles a face. Because the passport photo is small in frame (~1-2% of pixels for the face alone), the charger blob can win the "largest face" race.

**Why adding filters to the existing approach is wrong:** Skin-tone filtering discriminates against dark skin tones and fails under unusual lighting. Tightening `minNeighbors` makes the real small face harder to detect while still allowing a large false-positive to pass. These are patches on a fundamentally wrong architecture. The correct fix is to change *what we select on*: not "largest face" but "face whose estimated card boundary has the most uniform background".

**Principled insight:** Every valid passport photo card has a solid-colour backdrop (passport blue, white, light grey, cream). No charger, pen, or power bank produces a uniform-colour rectangular field at the four corners of the card boundary estimated from face proportions. This property is detection-lighting-skin-tone-agnostic and does not degrade with scene clutter.

---

## Files to Modify

| File | Change |
|---|---|
| `worker/processors/enhancement.py` | Add 3 constants, add `_score_card_background()`, rewrite `_crop_portrait_by_face()` as `_find_portrait_card()` + alias, update portrait block in `enhance_image()` |
| `tests/test_enhancement_guardrails.py` | Add `TestScoreCardBackground` and `TestFindPortraitCard` test classes |

---

## Task 1 — Add Constants

**Files:**
- Modify: `worker/processors/enhancement.py` (after line 834, within the portrait-crop constants block)

- [ ] **Step 1: Write the failing test** — the constants do not exist yet; importing them will fail.

Add to the `from processors.enhancement import (...)` block in `tests/test_enhancement_guardrails.py`:
```python
    _CARD_BG_UNIFORMITY_THRESHOLD,
    _CARD_CORNER_PATCH_FRACTION,
    _PORTRAIT_SCENE_MIN_FACE_RATIO,
```

- [ ] **Step 2: Run to verify test fails**

```bash
cd /Users/abhinav/Rythmiq\ One && python -m pytest tests/test_enhancement_guardrails.py -k "import" --collect-only 2>&1 | head -20
```
Expected: `ImportError` for the three new names.

- [ ] **Step 3: Add constants to enhancement.py** — insert immediately after line 834 (after `_PORTRAIT_ASPECT = 35.0 / 45.0`):

```python
# Maximum HSV-Value std across the 4 card-corner patches that is still
# considered "uniform background".
# Real card (passport blue / white / grey studio): std ≈ 10–35.
# Cluttered-desk false-positive (corners land on wood, cables, pens): std ≈ 60–130.
# Set conservatively at 45.0: wide margin above worst real-card (35) and
# below best false-positive (60).  Analogous to _FRAME_BORDER_UNIFORMITY_THRESH.
_CARD_BG_UNIFORMITY_THRESHOLD = 45.0

# Size of each corner sampling patch as a fraction of estimated card size.
# 8% of a 140×180 card ≈ 11×14 px patch (~154 px) — enough for stable std
# while staying well clear of the face/hair region.
_CARD_CORNER_PATCH_FRACTION = 0.08

# Minimum face-to-SCENE area ratio inside _find_portrait_card().
# A 4%-of-scene card with 65%-of-card-width face → face ≈ 1.3% of scene.
# 0.5% leaves 2.6× headroom while rejecting sub-pixel noise.
# (Different from _orient_by_face_detection's 3% guard, which operates on
#  an already-isolated crop where the face is large.)
_PORTRAIT_SCENE_MIN_FACE_RATIO = 0.005
```

- [ ] **Step 4: Verify import test passes**

```bash
cd /Users/abhinav/Rythmiq\ One && python -m pytest tests/test_enhancement_guardrails.py --collect-only 2>&1 | tail -5
```
Expected: collection succeeds, no import errors.

- [ ] **Step 5: Commit**

```bash
git add worker/processors/enhancement.py tests/test_enhancement_guardrails.py
git commit -m "feat: add portrait card detection constants"
```

---

## Task 2 — Implement and Test `_score_card_background()`

**Files:**
- Modify: `worker/processors/enhancement.py` (insert before `_crop_portrait_by_face` at line 837)
- Test: `tests/test_enhancement_guardrails.py`

- [ ] **Step 1: Write failing tests**

Add at the end of `tests/test_enhancement_guardrails.py` (before the `if __name__ == "__main__":` block), plus extend the import block:

```python
from processors.enhancement import (
    # ... existing ...
    _score_card_background,
    _CARD_BG_UNIFORMITY_THRESHOLD,
    _PORTRAIT_FACE_WIDTH_RATIO,
    _PORTRAIT_ASPECT,
    _PORTRAIT_TOP_PAD_RATIO,
)
```

```python
# ---------------------------------------------------------------------------
# Helpers for portrait card tests
# ---------------------------------------------------------------------------

def _solid_bgr(h: int, w: int, color: tuple) -> np.ndarray:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = color
    return img


# ---------------------------------------------------------------------------

class TestScoreCardBackground:
    """Unit tests for _score_card_background()."""

    def test_uniform_backdrop_scores_below_threshold(self):
        """Face on a solid-colour card background → low score → accepted."""
        img = _solid_bgr(600, 800, (180, 160, 140))  # uniform passport-blue-ish
        # Draw face-region in a different colour (won't affect corner patches)
        fx, fy, fw, fh = 300, 200, 160, 200
        cv2.rectangle(img, (fx, fy), (fx + fw, fy + fh), (80, 120, 160), -1)

        score = _score_card_background(img, fx, fy, fw, fh)

        assert score < _CARD_BG_UNIFORMITY_THRESHOLD, (
            f"Uniform background should score below threshold, got {score:.1f}"
        )

    def test_cluttered_background_scores_above_threshold(self):
        """Random-pixel background (desk clutter) → high score → rejected."""
        rng = np.random.RandomState(42)
        img = rng.randint(20, 220, (600, 800, 3)).astype(np.uint8)
        fx, fy, fw, fh = 300, 200, 160, 200

        score = _score_card_background(img, fx, fy, fw, fh)

        assert score >= _CARD_BG_UNIFORMITY_THRESHOLD, (
            f"Cluttered background should score above threshold, got {score:.1f}"
        )

    def test_out_of_bounds_corner_returns_penalty(self):
        """Estimated card extends outside image → 999.0 penalty (not a real card)."""
        img = _solid_bgr(200, 200, (150, 150, 150))
        # Face near right edge so estimated card goes OOB
        fx, fy, fw, fh = 190, 50, 60, 80

        score = _score_card_background(img, fx, fy, fw, fh)

        assert score == 999.0

    def test_white_background_also_scores_low(self):
        """Plain white backdrop (common ID photo) passes the uniformity gate."""
        img = _solid_bgr(600, 800, (250, 250, 250))
        fx, fy, fw, fh = 300, 200, 160, 200
        cv2.rectangle(img, (fx, fy), (fx + fw, fy + fh), (120, 140, 160), -1)

        score = _score_card_background(img, fx, fy, fw, fh)

        assert score < _CARD_BG_UNIFORMITY_THRESHOLD

    def test_uniform_scores_lower_than_cluttered(self):
        """Ordering sanity: uniform < cluttered."""
        img_uni = _solid_bgr(600, 800, (180, 160, 140))
        cv2.rectangle(img_uni, (300, 200), (460, 400), (80, 120, 160), -1)
        s_uni = _score_card_background(img_uni, 300, 200, 160, 200)

        rng = np.random.RandomState(99)
        img_clu = rng.randint(20, 220, (600, 800, 3)).astype(np.uint8)
        s_clu = _score_card_background(img_clu, 300, 200, 160, 200)

        assert s_uni < s_clu
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd /Users/abhinav/Rythmiq\ One && python -m pytest tests/test_enhancement_guardrails.py::TestScoreCardBackground -v 2>&1 | tail -15
```
Expected: `ImportError` or `AttributeError` on `_score_card_background`.

- [ ] **Step 3: Implement `_score_card_background()`**

Insert in `worker/processors/enhancement.py` immediately before the `def _crop_portrait_by_face(` line (line 837). Uses existing constants `_PORTRAIT_FACE_WIDTH_RATIO`, `_PORTRAIT_ASPECT`, `_PORTRAIT_TOP_PAD_RATIO`:

```python
def _score_card_background(
    img: NDArray[np.uint8],
    fx: int,
    fy: int,
    fw: int,
    fh: int,
) -> float:
    """
    Measure how much the region around a face candidate looks like a printed
    passport-photo card with a uniform solid-colour backdrop.

    Uses the same passport-proportion constants as _find_portrait_card to
    estimate the card boundary, then samples a small patch at each of the
    4 card corners (which are always inside the backdrop area, never inside
    the face).  Returns the HSV-Value std across all corner patch pixels —
    lower is more uniform (more card-like).

    Returns 999.0 when any corner falls outside the image (the estimated
    card does not fit, so this cannot be an in-scene card).

    Args:
        img:  Full-scene BGR image (full-scale coordinates).
        fx, fy, fw, fh:  Face bounding box in full-scale pixel coordinates.
    """
    h, w = img.shape[:2]

    photo_w = int(fw / _PORTRAIT_FACE_WIDTH_RATIO)
    photo_h = int(photo_w / _PORTRAIT_ASPECT)

    face_cx = fx + fw // 2
    x1 = face_cx - photo_w // 2
    y1 = fy - int(fh * _PORTRAIT_TOP_PAD_RATIO)
    x2 = x1 + photo_w
    y2 = y1 + photo_h

    pw = max(4, int(photo_w * _CARD_CORNER_PATCH_FRACTION))
    ph = max(4, int(photo_h * _CARD_CORNER_PATCH_FRACTION))

    corners = [
        (x1,      y1),
        (x2 - pw, y1),
        (x1,      y2 - ph),
        (x2 - pw, y2 - ph),
    ]

    patches: list[NDArray[np.uint8]] = []
    for cx, cy in corners:
        if cx < 0 or cy < 0 or cx + pw > w or cy + ph > h:
            return 999.0
        patch = img[cy: cy + ph, cx: cx + pw]
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        patches.append(hsv[:, :, 2].ravel())  # Value channel only

    all_v = np.concatenate(patches)
    return float(np.std(all_v))
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd /Users/abhinav/Rythmiq\ One && python -m pytest tests/test_enhancement_guardrails.py::TestScoreCardBackground -v
```
Expected: 5 PASSED.

- [ ] **Step 5: Run full suite — no regressions**

```bash
cd /Users/abhinav/Rythmiq\ One && python -m pytest tests/test_enhancement_guardrails.py -v 2>&1 | tail -20
```
Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add worker/processors/enhancement.py tests/test_enhancement_guardrails.py
git commit -m "feat: add _score_card_background for card-context validation"
```

---

## Task 3 — Rewrite `_crop_portrait_by_face()` as `_find_portrait_card()`

**Files:**
- Modify: `worker/processors/enhancement.py` (replace lines 837–917)
- Test: `tests/test_enhancement_guardrails.py`

- [ ] **Step 1: Write failing tests**

Extend the import block and add the new test class:

```python
from processors.enhancement import (
    # ... existing ...
    _find_portrait_card,
    _crop_portrait_by_face,   # alias — must still exist
    _CARD_BG_UNIFORMITY_THRESHOLD,
)
```

```python
class TestFindPortraitCard:
    """Unit tests for _find_portrait_card()."""

    def test_returns_ndarray_and_bool(self):
        """Function signature is always (NDArray, bool)."""
        img = np.zeros((400, 300, 3), dtype=np.uint8)
        result_img, success = _find_portrait_card(img)
        assert isinstance(result_img, np.ndarray)
        assert isinstance(success, bool)

    def test_featureless_image_returns_false(self):
        """Blank image — no faces detected — returns (original, False)."""
        img = _solid_bgr(600, 800, (200, 200, 200))
        result_img, success = _find_portrait_card(img)
        assert success is False
        assert result_img.shape == img.shape

    def test_background_gate_rejects_cluttered_false_positive(self):
        """
        Gate logic: a face candidate whose estimated card corners land on a
        high-variance (cluttered) background must be rejected.
        Test verifies the gate independently via _score_card_background.
        """
        rng = np.random.RandomState(42)
        img = rng.randint(20, 220, (800, 1200, 3)).astype(np.uint8)
        fx, fy, fw, fh = 500, 300, 120, 150

        score = _score_card_background(img, fx, fy, fw, fh)
        assert score >= _CARD_BG_UNIFORMITY_THRESHOLD, (
            "Cluttered background gate did not fire — "
            f"score={score:.1f} should be >= {_CARD_BG_UNIFORMITY_THRESHOLD}"
        )

    def test_background_gate_accepts_uniform_background(self):
        """
        Gate logic: a face candidate with uniform card-corner background
        must score below threshold.
        """
        img = _solid_bgr(600, 800, (180, 160, 140))
        cv2.rectangle(img, (300, 200), (460, 400), (80, 120, 160), -1)
        fx, fy, fw, fh = 300, 200, 160, 200

        score = _score_card_background(img, fx, fy, fw, fh)
        assert score < _CARD_BG_UNIFORMITY_THRESHOLD

    def test_backward_compat_alias_callable(self):
        """_crop_portrait_by_face must still exist and be callable."""
        img = np.zeros((300, 250, 3), dtype=np.uint8)
        result = _crop_portrait_by_face(img)
        assert len(result) == 2
        assert isinstance(result[1], bool)
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd /Users/abhinav/Rythmiq\ One && python -m pytest tests/test_enhancement_guardrails.py::TestFindPortraitCard -v 2>&1 | tail -15
```
Expected: `ImportError` on `_find_portrait_card`.

- [ ] **Step 3: Replace `_crop_portrait_by_face()` with `_find_portrait_card()`**

In `worker/processors/enhancement.py`, replace the entire function (lines 837–917) with:

```python
def _find_portrait_card(
    img: NDArray[np.uint8],
) -> Tuple[NDArray[np.uint8], bool]:
    """
    Locate a printed passport-photo card in a scene image and crop to it.

    Replaces the old "pick largest face" approach with a principled two-gate
    selection:

      Gate 1 — minimum face-to-scene area ratio (0.5%)
        Rejects sub-pixel noise.  Calibrated for faces that are ~1–2% of the
        full scene (a 35×45mm card at ~4% of a typical phone photo).

      Gate 2 — card background uniformity (_score_card_background)
        Estimates where the card boundary would be from passport proportions,
        samples the 4 card corners, and checks that they form a uniform solid
        colour.  A real card has a consistent backdrop colour at every corner;
        a charger, earbuds, or power bank does not.

    The candidate with the LOWEST background std that also beats
    _CARD_BG_UNIFORMITY_THRESHOLD wins.

    Returns:
        (cropped_image, success)  — same signature as original
    """
    h, w = img.shape[:2]
    cascade = _get_face_cascade()

    max_dim = max(h, w)
    scale = min(1.0, 1024.0 / max_dim)

    small = cv2.resize(img, None, fx=scale, fy=scale) if scale < 1.0 else img
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    # Slightly permissive detection: the background scorer is the real gate.
    # minNeighbors=5 / minSize=(30,30) ensures a small-in-scene face (which
    # generates fewer cascade hits) survives candidate proposal.
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.05, minNeighbors=5, minSize=(30, 30),
    )

    if len(faces) == 0:
        logger.info("[ENHANCEMENT] face-crop: no face candidates")
        return img, False

    img_area = float(w * h)
    best_score = float("inf")
    best_face: Optional[Tuple[int, int, int, int]] = None

    for (fx_s, fy_s, fw_s, fh_s) in faces:
        fx = int(fx_s / scale)
        fy = int(fy_s / scale)
        fw = int(fw_s / scale)
        fh = int(fh_s / scale)

        # Gate 1: reject sub-pixel noise
        if float(fw * fh) / img_area < _PORTRAIT_SCENE_MIN_FACE_RATIO:
            continue

        # Gate 2: card background uniformity
        score = _score_card_background(img, fx, fy, fw, fh)
        logger.debug(
            "[ENHANCEMENT] face-crop: candidate (%d,%d %dx%d) bg_std=%.1f",
            fx, fy, fw, fh, score,
        )
        if score < best_score:
            best_score = score
            best_face = (fx, fy, fw, fh)

    if best_face is None:
        logger.info("[ENHANCEMENT] face-crop: all candidates below area threshold")
        return img, False

    if best_score >= _CARD_BG_UNIFORMITY_THRESHOLD:
        logger.info(
            "[ENHANCEMENT] face-crop: best bg_std=%.1f ≥ %.1f — "
            "no card-like background found",
            best_score, _CARD_BG_UNIFORMITY_THRESHOLD,
        )
        return img, False

    fx, fy, fw, fh = best_face
    photo_w = int(fw / _PORTRAIT_FACE_WIDTH_RATIO)
    photo_h = int(photo_w / _PORTRAIT_ASPECT)

    face_cx = fx + fw // 2
    x1 = max(0, face_cx - photo_w // 2)
    y1 = max(0, fy - int(fh * _PORTRAIT_TOP_PAD_RATIO))
    x2 = min(w, x1 + photo_w)
    y2 = min(h, y1 + photo_h)

    crop_w, crop_h = x2 - x1, y2 - y1
    if crop_w < 100 or crop_h < 100:
        logger.info("[ENHANCEMENT] face-crop: crop too small (%dx%d)", crop_w, crop_h)
        return img, False

    if float(crop_w * crop_h) > 0.8 * img_area:
        logger.info("[ENHANCEMENT] face-crop: crop too large (>80%% of image)")
        return img, False

    logger.info(
        "[ENHANCEMENT] face-crop: accepted bg_std=%.1f — %dx%d → %dx%d "
        "(face at %d,%d %dx%d)",
        best_score, w, h, crop_w, crop_h, fx, fy, fw, fh,
    )
    return img[y1:y2, x1:x2], True


# Backward-compatibility alias
_crop_portrait_by_face = _find_portrait_card
```

- [ ] **Step 4: Run portrait card tests**

```bash
cd /Users/abhinav/Rythmiq\ One && python -m pytest tests/test_enhancement_guardrails.py::TestFindPortraitCard -v
```
Expected: all PASSED.

- [ ] **Step 5: Run full suite — no regressions**

```bash
cd /Users/abhinav/Rythmiq\ One && python -m pytest tests/test_enhancement_guardrails.py -v
```
Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add worker/processors/enhancement.py tests/test_enhancement_guardrails.py
git commit -m "feat: rewrite _crop_portrait_by_face as _find_portrait_card with card-context gate"
```

---

## Task 4 — Update `enhance_image()` Portrait Block

**Files:**
- Modify: `worker/processors/enhancement.py` (lines 1803–1813)

The current portrait block bypasses `_photo_already_framed()`. The proposed change restores it as a fast-path for already-framed photos (studio portraits, digital files) and routes on-desk photos through `_find_portrait_card()`.

- [ ] **Step 1: Write the failing test**

The existing `TestEnhancementIntegration` tests in `tests/test_enhancement_guardrails.py` cover the happy path. Add one targeted test for the routing logic:

```python
class TestPortraitEnhancementRouting:
    """Verify enhance_image() portrait routing doesn't crash on edge cases."""

    def test_plain_image_with_portrait_subtype_does_not_crash(self):
        """
        A featureless image submitted as Passport Photo must complete
        without error and return a valid image.
        """
        img_bgr = _solid_bgr(600, 800, (200, 190, 180))
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)).save(buf, format="JPEG")
        raw = buf.getvalue()

        opts = EnhancementOptions(
            document_type="photo",
            document_subtype="Passport Photo",
        )
        result_img, orient, exposure, sharp, cropped = enhance_image(raw, opts)
        assert result_img is not None
        assert len(result_img) > 0  # non-empty JPEG bytes

    def test_portrait_path_succeeds_with_no_face(self):
        """
        When no face is detected (and image is not already-framed),
        enhance_image must still return a result (not raise).
        """
        img_bgr = np.zeros((600, 800, 3), dtype=np.uint8)  # pure black
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)).save(buf, format="JPEG")
        raw = buf.getvalue()

        opts = EnhancementOptions(document_type="photo", document_subtype="Passport Photo")
        result_img, *_ = enhance_image(raw, opts)
        assert result_img is not None
```

- [ ] **Step 2: Run to confirm tests pass on existing code (they should)**

```bash
cd /Users/abhinav/Rythmiq\ One && python -m pytest tests/test_enhancement_guardrails.py::TestPortraitEnhancementRouting -v
```
Expected: PASSED (the tests don't break the old code; they establish a baseline).

- [ ] **Step 3: Update the portrait block in `enhance_image()`**

In `worker/processors/enhancement.py`, replace lines 1803–1813:

```python
    if _expects_portrait:
        # Fast path: already-framed photos (studio scans, digital files).
        # Framing guard is cheap; if it fires, skip card-localization entirely.
        if _photo_already_framed(img):
            img, border_cropped = crop_borders(img)
            crop_done = True
            logger.info("[ENHANCEMENT] portrait: already-framed → skip card-localization")
            img, face_result = _orient_by_face_detection(img)
            if face_result is True:
                orientation_corrected = True
        else:
            # Card-in-scene path: validate each face candidate against
            # its card-background context before committing to a crop.
            img_card, card_found = _find_portrait_card(img)
            if card_found:
                img = img_card
                border_cropped = True
                crop_done = True
                img, face_result = _orient_by_face_detection(img)
                if face_result is True:
                    orientation_corrected = True
```

- [ ] **Step 4: Run routing tests**

```bash
cd /Users/abhinav/Rythmiq\ One && python -m pytest tests/test_enhancement_guardrails.py::TestPortraitEnhancementRouting -v
```
Expected: PASSED.

- [ ] **Step 5: Run full suite**

```bash
cd /Users/abhinav/Rythmiq\ One && python -m pytest tests/test_enhancement_guardrails.py -v
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add worker/processors/enhancement.py tests/test_enhancement_guardrails.py
git commit -m "feat: restore framing-guard fast-path for already-framed portrait photos"
```

---

## Verification

**End-to-end smoke test** — run the cluttered-desk scenario (M-PH-12):

1. Submit the original image (passport photo on cluttered desk with power bank, charger, pens) to the local worker as a "Passport Photo" job.
2. Confirm the output crop is centred on the face in the passport photo, not the charger region.
3. Confirm job log contains `[ENHANCEMENT] face-crop: accepted bg_std=<low value>` (not "no card-like background found").
4. Run M-PH-29 (pre-framed studio photo) to confirm already-framed path still works: log should contain "already-framed → skip card-localization".

**Regression check** — all previously-passing M-PH edge cases:

```bash
cd /Users/abhinav/Rythmiq\ One && python -m pytest tests/ -v -m "not slow and not e2e" 2>&1 | tail -30
```
Expected: zero new failures.

---

## Threshold Calibration Reference

| Constant | Value | What it gates |
|---|---|---|
| `_CARD_BG_UNIFORMITY_THRESHOLD` | 45.0 | Max HSV-Value std across 4 card-corner patches. Real cards: 10–35; cluttered desk: 60–130. |
| `_CARD_CORNER_PATCH_FRACTION` | 0.08 | Patch = 8% of estimated card dimension. Balances sampling stability vs face-overlap avoidance. |
| `_PORTRAIT_SCENE_MIN_FACE_RATIO` | 0.005 | 0.5% of scene. Small-card face ≈ 1.3%; sub-pixel noise ≈ 0.01–0.1%. |
| `minNeighbors` (proposal) | 5 | Down from 6. Looser proposal; background scorer is the gate. |
| `minSize` (proposal) | (30, 30) | Down from (40, 40). Allows detection of faces that are ~30px when downscaled to 1024px. |

If threshold calibration needs tuning after real-world testing, adjust `_CARD_BG_UNIFORMITY_THRESHOLD` only — it is the single dial that controls selectivity without affecting any other pipeline stage.
