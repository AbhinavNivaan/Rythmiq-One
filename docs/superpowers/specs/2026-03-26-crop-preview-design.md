# Crop Preview Feature — Design Spec

_Date: 2026-03-26_
_Status: Approved_

---

## Problem

The current capture flow sends images directly to the worker with no intermediate feedback. If the server's edge detection produces a bad crop, the user has no recourse and no visibility. For documents with strict dimension requirements (A4, passport photo 35×45mm, PAN card, etc.), a missed edge or perspective error ruins the output silently.

---

## Solution

Insert a crop preview step between capture and upload. After the user captures all images and taps Done, they review each image one at a time with an on-device detected quad overlay. They can drag corner handles to adjust, tap Looks Good to confirm, or Recapture to replace that image. Once all images are confirmed, the confirmed quad coordinates are passed to the worker, which uses them directly for perspective correction — bypassing its own detection stages.

---

## User Flow

```
Capture (N images) → Done → Crop Preview [image 1] → Looks Good / Recapture
                                        → Crop Preview [image 2] → Looks Good / Recapture
                                        → ... → Upload (Create Master)
```

- Crop preview triggers **after Done**, not after each individual capture (batch review)
- Applies to **all document types** — no type is excluded
- Recapture replaces **only the current image**, preserving all other confirmed images

---

## Navigation Architecture

New route: `app/(tabs)/crop-preview.tsx`

Route params (lean):
```ts
{
  sessionId: string   // key into the capture session store
  index: number       // which image is currently being reviewed
}
```

**Capture session store** (Zustand slice or React Context) — single source of truth:
```ts
{
  images: CapturedImage[]       // all captured URIs + dimensions
  docType: string               // from capture screen
  confirmed: ConfirmedCrop[]    // accumulates as user confirms each image
}
```

**ConfirmedCrop shape:**
```ts
{
  originalUri: string
  croppedUri?: string           // if detection library provides it; otherwise absent
  quad: [[x,y],[x,y],[x,y],[x,y]]  // normalised 0.0–1.0 relative to original image dimensions
}
```

**CRITICAL:** Quad coordinates must be normalised relative to the **original full-resolution image dimensions**, not display size. Failure to do this will silently produce wrong crops on the server.

---

## Crop Preview Screen

### Layout
- **Header:** "Review Crop" title, progress pill top-left ("Image 2 of 3")
- **Image area:** Full photo with quad overlay — blue lines, white draggable corner circles, blue edge midpoint handles, darkened outside-quad area
- **Hint text:** "Drag the corners to adjust the crop" — disappears after first corner interaction
- **Buttons (equal size, equal width):**
  - Left: "↺ Recapture" (secondary — dark background, subtle border)
  - Right: "Looks Good →" (primary — cobalt blue background)

### On-Device Edge Detection
- Library selection criterion: **best detection quality first**
- Nice-to-have: library also returns a perspective-corrected `croppedUri` as a byproduct (used as preview thumbnail on upload screen)
- If the best library does not return a cropped image, the upload screen falls back to showing the original image thumbnail — no feature degradation otherwise
- Detection failure (no quad found): default quad covers full image, hint text changes to "No document detected — adjust corners manually". User can still proceed or recapture.

### Recapture Flow
1. User taps Recapture on image N
2. Navigate to capture screen with `replaceIndex: N` param
3. Capture screen enters single-shot mode — one photo, then auto-return
4. New URI replaces index N in the session store
5. Crop preview re-renders for index N with the new image

### Exit / Abandonment
If user exits mid-loop (back gesture, app kill), the session store is cleared. Returns to capture with clean state. No partial confirmed arrays leak into a future job.

---

## Worker Changes

### API Gateway (app/api)
The app submits jobs via the FastAPI API, which then dispatches to the Cloud Run worker. The job creation endpoint must accept and pass through `confirmed_crop_quad` as an optional field:

```python
# In the job creation request model
confirmed_crop_quad: list[list[float]] | None = None
```

This is then forwarded as-is in the worker job payload. No validation beyond checking it's a list of exactly 4 [x, y] pairs if present.

### JobPayload (worker/models.py)
Add one optional field:
```python
@dataclass(frozen=True)
class JobPayload:
    # ... existing fields unchanged ...
    confirmed_crop_quad: tuple[tuple[float, float], ...] | None = None
    # 4 points, normalised 0.0–1.0: ((x1,y1),(x2,y2),(x3,y3),(x4,y4))
```

`JobPayload.from_dict()` must parse this field from the JSON payload (list of [x,y] pairs → tuple of tuples).

### enhancement.py — detect_and_crop_document()
At the top of the function, before Stage 0:
```python
if job.confirmed_crop_quad:
    pixel_quad = denormalise(job.confirmed_crop_quad, image.shape)
    return _perspective_crop(image, pixel_quad)
```

If `confirmed_crop_quad` is absent (None), the full 4-stage cascade runs unchanged. Zero regression for existing jobs.

Portrait photos are unaffected — they route through `_find_portrait_card()`, not `detect_and_crop_document()`.

`server.py` requires no changes — `ProcessRequest` already uses `extra = "allow"`.

---

## Upload Screen Changes

- If `croppedUri` is present in the confirmed crop, show it as the image thumbnail instead of the original
- No other changes to upload screen logic

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Detection fails to find quad | Default full-image quad shown, hint text updated, user can adjust or recapture |
| Recapture mid-loop | Single-shot camera, replaces only that index, rest preserved |
| User exits mid-loop | Session store cleared, clean return to capture |
| Library returns no croppedUri | Upload screen shows original thumbnail (graceful degradation) |

---

## Testing

### Worker unit tests
- `confirmed_crop_quad` present → skips Stages 0-3, calls `_perspective_crop()` with denormalised coords
- `confirmed_crop_quad` absent → full 4-stage cascade runs (regression)
- Boundary values: coords at 0.0 and 1.0; non-square images

### App tests
- Session store: confirmed array accumulates correctly across N images; cleared on exit
- Recapture: replacing index 1 of 3 preserves confirmed[0], resets confirmed[1]
- Navigation: after all N confirmations, route lands on upload with correct session state
- Normalisation: quad coords verified relative to original image dimensions, not display

### Physical / manual (add to EDGE_CASE_TEST_MATRIX.md)
- Document on dark surface — on-device detection finds quad
- Already-framed photo — full-image quad, user taps Looks Good immediately
- Badly lit image — detection fails, default quad shown, user adjusts manually
- 2-page batch — both images confirmed sequentially, both quads reach worker

---

## What This Does Not Change

- Worker pipeline stages beyond crop (quality scoring, OCR, schema adaptation, encryption, upload) — unchanged
- Portrait photo path (`_find_portrait_card()`) — unchanged
- Signature path — unchanged
- Existing job payloads without `confirmed_crop_quad` — unchanged behaviour
