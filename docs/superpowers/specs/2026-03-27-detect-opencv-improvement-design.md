# Design: Improve /detect Auto-Detect Quality (OpenCV-only)

_Date: 2026-03-27_
_Status: Approved_

---

## Problem

The `/detect` endpoint returns `null` on common real-world inputs — e.g. a white A4 document on a wooden table — even though the full enhancement pipeline handles these cases correctly. Two bugs explain the gap:

1. **First-match instead of best-match (Stage 1):** `/detect` returns the first quad found across edge maps. The full pipeline picks the *largest* quad across all edge maps. An early edge map can match a small internal element (QR code, college seal) before the outer boundary is found.
2. **Stage 2 missing from `/detect`:** The full pipeline falls back to `_find_filled_document_blob()` (blob-based detection) when edge-based quad detection fails. This stage — specifically designed for white paper on wood via a brightness-value mask — is never called in `/detect`.

**Observed failure:** A white A4 letter on a wooden table returns `null`, showing the "No document detected — adjust corners manually" fallback. The same document with slightly more table margin visible detects correctly, confirming the algorithm *can* work — it just needs the right strategy to be reached.

---

## Solution

Two targeted changes to `worker/` only. No Vision API, pure OpenCV. Response contract unchanged.

### Change 1 — Stage 1: best-match (server.py)

Replace the first-match loop in `/detect` with a best-match loop identical to `detect_and_crop_document()`:

```
# Before (first-match):
for edge_img in edge_maps:
    result = _find_quad_contour(...)
    if result is not None:
        return result  # ← stops at first match

# After (best-match):
best_corners, best_area = None, 0
for edge_img in edge_maps:
    result = _find_quad_contour(...)
    if result is not None and result[1] > best_area:
        best_corners, best_area = result
if best_corners is not None:
    return best_corners
```

### Change 2 — Stage 2: blob corner detection (enhancement.py + server.py)

Add `_find_blob_corners(img, min_area, max_area) → Optional[ndarray[float32]]` to `enhancement.py`.

This function is extracted from `_find_filled_document_blob` — same binary threshold strategies, same hull+solidity+aspect guards — but stops before `_perspective_crop`. It returns the 4 corners from `minAreaRect → boxPoints` as a `(4, 2) float32` array, or `None`.

Export it alongside the other functions imported by `server.py`.

`/detect` calls it as a fallback:

```
# Stage 1: best quad across all edge maps
best_corners = ... (see Change 1)
if best_corners is not None:
    return normalise(best_corners)

# Stage 2: blob corner detection
blob_corners = _find_blob_corners(img, min_area, max_area)
if blob_corners is not None:
    return normalise(blob_corners)

return null
```

#### Threshold strategies in `_find_blob_corners` (in order):
| Strategy | Signal | Best for |
|---|---|---|
| A — V>180 bright mask | High Value channel | White paper on any background |
| B — Otsu on blurred gray | Adaptive contrast | General luminance separation |
| C — Inverted Otsu | Inverse | Dark card on light background |
| D — Fixed thresholds (40/60/90/120/150/180) | Multiple levels | Mid-tone scenes |
| E — Saturation Otsu | High saturation | Coloured cards (PAN, Aadhaar) on neutral surface |
| F — Inverted saturation Otsu | Low saturation | White/grey paper on coloured background |

For each binary candidate: morphological close (fill holes) → open (denoise) → find contours → convex hull → area/solidity/aspect checks → `minAreaRect → boxPoints`.

Returns the corners of the largest passing candidate.

---

## Files Changed

| File | Change |
|---|---|
| `worker/processors/enhancement.py` | Add `_find_blob_corners()` function; add to exports |
| `worker/server.py` | Import `_find_blob_corners`; change Stage 1 to best-match; add Stage 2 call |

No changes to: `app-v2/`, `app/api/`, schemas, tests (existing tests unaffected).

---

## What This Fixes

- White A4 paper on wooden table: Strategy A (V>180) cleanly isolates paper → blob → corners
- Documents that fill most of the frame: blob detection doesn't rely on background edge contrast
- Internal element false positives (QR codes, seals): best-match picks the largest quad, not the first

## What This Does Not Fix

- Documents on very cluttered backgrounds where the paper has low contrast to surroundings
- Extreme tilt (>45°): `minAreaRect` aspect ratio check may reject
- These are addressed by the future feedback logging + ML training path

---

## Scope Boundary

OpenCV only. No Vision API. No latency increase for the success path (Stage 1 fast path still runs first). Stage 2 only runs when Stage 1 returns nothing — worst case adds ~50-100ms for blob strategy iteration on a full-resolution image, well within acceptable UX range.

---

## Deferred

Feedback logging (log confirmed quads vs auto-detected for future ML training) — separate follow-up sprint. See brain: `project_detect_feedback_logging.md`.
