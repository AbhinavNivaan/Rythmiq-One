# Worker Pipeline — Architecture & Redesign Brief

## 1. What the Worker Does

The worker is a single-shot HTTP service (Cloud Run). Each job is one HTTP request → one JSON payload → full pipeline → one JSON result. No retries, no global state, no threads.

---

## 2. Current Pipeline (7 Stages)

```
FETCH → QUALITY → OCR(pre) → ENHANCE → OCR(post) → OUTPUT TRANSFORM → ENCRYPT → UPLOAD
```

### Stage 1: FETCH
Downloads the raw uploaded file from DigitalOcean Spaces.
- Source is either a signed URL (`artifact_url`) or a direct storage path (`raw_path`)

### Stage 2: QUALITY
Computes 4 metrics on the raw input (CPU-only, OpenCV/NumPy):

| Metric | Method | Weight |
|---|---|---|
| Sharpness | Laplacian variance | 35% |
| Exposure | Histogram std deviation | 30% |
| Noise | High-pass filter residual | 20% |
| Edge density | Canny edge pixel count | 15% |

**Problem**: All 4 metrics are calibrated for document scans (bimodal histogram = white paper + dark text). They are incorrect for photos (faces, coloured backgrounds) and produce misleading scores.

### Stage 3: OCR (pre-enhancement)
Runs PaddleOCR on the raw input. Stores confidence as `pre_ocr_confidence`.
Used later for GUARD-002 rollback comparison.
**Problem**: For photos, OCR confidence will always be ~0 (no text). This breaks GUARD-001.

### Stage 4: ENHANCE
Applies up to 3 operations, gated by guardrails:

| Operation | What it does | Guardrail |
|---|---|---|
| `correct_orientation` | Hough line detection → skew/large rotation correction via `warpAffine` | None (always ran) |
| `denoise` | `fastNlMeansDenoisingColored` (strength=7, searchWindow=21) | GUARD-001 + `is_photo` |
| `auto_white_balance` + `normalize_color` | Gray world WB → CLAHE on L channel (8×8 tiles) | GUARD-001 + `is_photo` |

**GUARD-001** skips denoise+CLAHE only if `quality_score > 0.75 AND is_readable`.
`is_readable = pre_ocr_confidence > 0.5` — always False for photos → GUARD-001 never fires for photos.

**Current state after the bug fixes**: photos now skip all 3 operations (orientation, denoise, colour). This is correct for clean photos but leaves degraded photos unprocessed.

### Stage 5: OCR (post-enhancement)
Runs PaddleOCR again on enhanced image.
**GUARD-002**: if post-OCR confidence dropped by >10% vs pre-OCR, rolls back to raw image.
**Problem**: For photos, both confidences are ~0 so rollback never triggers (correctly, but pointlessly runs OCR twice).

### Stage 6: OUTPUT TRANSFORM
Two modes:

**`master` mode** — best-quality archival copy:
- Preserves original dimensions (no resize)
- Sets DPI to 300
- JPEG quality 92, binary-search compression to fit within 2000KB

**`adapt` mode** — portal-specific rendition:
- Hard resize to exact `target_width × target_height` (INTER_LANCZOS4)
- Specific DPI, quality, format, and max_kb per portal schema
- Filename normalised per `filename_pattern`

### Stage 7: ENCRYPT + UPLOAD
- AES-256-GCM encryption if SEK provided
- Uploads master (encrypted) + preview (plaintext) to DigitalOcean Spaces
- Deletes raw upload from storage

---

## 3. Document Types

Three types flow through the same pipeline:

| Type | Current treatment | Problems |
|---|---|---|
| `document` | Full pipeline, all operations | Designed for this — mostly correct |
| `photo` | After fix: passthrough (no ops) | Clean photos fine; degraded photos unhandled |
| `signature` | Same as document | CLAHE on a black-on-white sig is OK, but NLM denoising smears fine pen strokes |

---

## 4. Known Gaps / Design Flaws

### G-1: Quality metrics are document-only
All 4 metrics assume a bimodal (text+paper) histogram and high edge density from text characters. A clean passport photo scores poorly because:
- Sharpness is high but the Laplacian fires on face edges which are few relative to document text density
- Exposure metric expects std deviation >60 from bimodal histogram; a portrait has a unimodal distribution and scores low
- Edge density: a plain background + face has fewer edges than a dense text document → penalised

**What's needed**: separate scoring functions or calibrated weights per document type.

### G-2: GUARD-001 is broken for photos
Gates on `is_readable` (OCR confidence > 0.5). Photos have no text so is_readable is always False. GUARD-001 was intended to protect high-quality documents from unnecessary processing; it never applies to photos regardless of quality.

### G-3: OCR runs twice on every job including photos
PaddleOCR is slow (~0.5–2s per image). Running it twice on photos (which have no text to protect) wastes ~1–3s per photo job.

### G-4: Orientation correction is wrong for photos
Hough-based skew detection was designed for document scans with long straight text lines. On photos, it detects edges of clothing, collar, tie, glasses frames — finds a dominant "angle" from content edges instead of page orientation — then `warpAffine` with `BORDER_REPLICATE` fans edge pixels across smooth backgrounds creating the diagonal streaking artifact.

### G-5: No photo-specific enhancement exists
For a degraded photo (dark, blurry, scanned at a tilt), the system currently does nothing. What's needed:
- Exposure check → gamma correction (not CLAHE)
- Sharpness check → unsharp mask (not NLM denoising)
- EXIF rotation (not Hough detection)
- Border/whitespace crop detection

### G-6: Signatures use the wrong denoising
`fastNlMeansDenoisingColored` with searchWindow=21 smears fine pen strokes. Signatures need either no denoising or a sharpening pass, not smoothing.

### G-7: quality_score in the output is meaningless for photos
The API returns a `quality_score` to the app. For photos this is calibrated against document standards and will always be lower than expected, potentially triggering false warnings to the user.

---

## 5. Proposed Redesign

### 5.1 Principle
**Route by document type first, then apply only type-appropriate operations gated by measured need.**

### 5.2 New Pipeline Structure

```
FETCH → DECODE → ASSESS(type-aware) → ROUTE
                                          ├─ photo branch
                                          ├─ signature branch
                                          └─ document branch
                                       → OUTPUT TRANSFORM → ENCRYPT → UPLOAD
```

### 5.3 Photo Branch

Operations applied only when the corresponding quality check fails:

| Check | Threshold | Action if fails |
|---|---|---|
| EXIF orientation | Orientation tag != 1 (normal) | Rotate per EXIF (no Hough, no warpAffine) |
| Exposure | Mean brightness < 80 or > 200 | Gamma correction (γ computed from mean) |
| Sharpness | Laplacian variance < 100 | Unsharp mask (kernel 0, sigma 1.0, strength 1.5) |
| (no denoising) | — | NLM denoising never applied to photos |
| (no colour correction) | — | Gray world WB and CLAHE never applied to photos |
| (no OCR) | — | Skip both pre/post OCR passes for photos |

Photo quality score uses photo-calibrated weights:
- Sharpness: 50% (most important for a portrait)
- Exposure: 40%
- Noise: 10%
- Edge density: 0% (irrelevant)

### 5.4 Signature Branch

| Check | Threshold | Action if fails |
|---|---|---|
| EXIF orientation | — | Rotate per EXIF |
| Exposure | — | Binarisation (Otsu threshold) to clean up scan |
| Sharpness | — | Unsharp mask |
| (no NLM denoising) | — | Bilateral filter instead (preserves edges) |
| (no CLAHE) | — | Global histogram stretch (no tile artifacts) |

### 5.5 Document Branch (largely unchanged)

| Check | Threshold | Action |
|---|---|---|
| Orientation | Hough + EXIF | Rotate (existing logic, correct for this type) |
| Exposure | Histogram std < 40 | Auto-levels |
| Noise | Noise score < 0.6 | NLM denoising (existing) |
| Colour | Always | CLAHE (existing) |
| OCR | Always | Pre + post OCR with GUARD-002 rollback |

### 5.6 Type-Aware Quality Scoring

```python
QUALITY_WEIGHTS = {
    "photo":     {"sharpness": 0.50, "exposure": 0.40, "noise": 0.10, "edge_density": 0.00},
    "signature": {"sharpness": 0.40, "exposure": 0.30, "noise": 0.20, "edge_density": 0.10},
    "document":  {"sharpness": 0.35, "exposure": 0.30, "noise": 0.20, "edge_density": 0.15},
}
```

---

## 6. Edge Cases to Test

Once the redesign is implemented, each of the following should be tested:

### Photos
- [ ] Clean, well-lit passport photo (should pass through with no ops applied)
- [ ] Dark / underexposed photo (gamma correction should brighten it cleanly)
- [ ] Overexposed / washed-out photo (gamma correction should pull it back)
- [ ] Slightly blurry / soft photo (unsharp mask should add crispness)
- [ ] Photo shot at an angle (EXIF rotation should correct it; Hough NOT used)
- [ ] Photo from a scan (may have physical tilt — needs discussion: EXIF unavailable)
- [ ] Photo with black border from scanner (border crop should remove it)
- [ ] Very large photo (5MB+) — should compress cleanly to 2000KB master

### Documents
- [ ] Clean scan of an Aadhaar (no ops needed beyond compression)
- [ ] Dark scan (exposure correction should help)
- [ ] Skewed scan — 2-5° tilt (Hough skew correction should straighten it)
- [ ] 90° rotated scan (large rotation detection should catch it)
- [ ] Noisy scan (NLM denoising should help, OCR rollback should catch regressions)
- [ ] Very small scan (below target DPI) — upscaling question (INTER_LANCZOS4 vs no upscale)

### Signatures
- [ ] Clean ink signature on white paper
- [ ] Faint signature (low contrast) — binarisation should make it clear
- [ ] Signature with pen smear — bilateral filter should preserve stroke edges
- [ ] Signature cropped from a larger document (background noise)

### Schema Adaptation (adapt mode)
- [ ] Photo resized to portal passport spec (e.g. 600×800 at 200KB)
- [ ] Document with wrong aspect ratio for target — how is letterboxing/cropping handled? (currently it squishes — needs decision)
- [ ] Output larger than max_kb at MIN_JPEG_QUALITY — error handling

---

## 7. Files to Change

| File | Change |
|---|---|
| `processors/quality.py` | Add `assess_quality(data, document_type)` with type-aware weights; photo-specific exposure metric |
| `processors/enhancement.py` | Replace single `enhance_image` with routed `enhance_photo`, `enhance_signature`, `enhance_document` called from a dispatcher |
| `worker.py` | Skip OCR stages for photos/signatures; pass `document_type` through quality assessment |
| `models.py` | Add `QualityBreakdown` fields if new metrics added; no structural changes needed |
| `processors/schema.py` | Add letterbox/pad option to `adapt_to_schema` for aspect ratio mismatches |
