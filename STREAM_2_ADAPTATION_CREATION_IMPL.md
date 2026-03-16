# Stream 2: Adaptation Creation — Implementation Plan

**Status:** Ready for implementation  
**Prerequisites:** Stream 1 (`mrc.py`, `MasterConstraints` updates, Dockerfile jbig2enc) must be merged first  
**Files touched:** `worker/models.py`, `worker/processors/schema.py`, `worker/processors/enhancement.py`, `worker/requirements.txt`, `worker/Dockerfile.production`, `db/schema.sql`  
**Risk level:** Medium — modifies the hot path (`adapt_to_schema`) used on every portal job

---

## 1. Overview and Goals

Stream 2 closes the remaining gaps in the **portal-mode (Stage 5) adaptation pipeline**: the path taken when a user uploads a document and the system must produce a pixel-perfect output that satisfies a portal's published requirements (exact dimensions, DPI, file size, and now colour mode).

The OSS reference report (Section 3.2 — Document Transformation Compliance) identified ITU-T T.44 as the governing standard for portal document adaption. T.44 defines four constraint tiers that must be applied in strict order:

```
Tier 1 → output format      (JPEG / PNG / PDF)
Tier 2 → colour mode        (colour / greyscale / binary)
Tier 3 → dimensions + DPI   (resize, DPI embed)
Tier 4 → file size          (compression)
```

Currently the pipeline enforces Tier 1, 3, and 4 but **skips Tier 2 entirely**. The result is that a portal requiring a greyscale signature image may receive a full-RGB file because the adaptation code has no mechanism to perform or verify colour conversion. There is also no post-adaptation OCR quality gate to confirm that compression did not destroy the legibility of the output.

### Audit gaps closed by Stream 2

| Gap ID | Description | Severity | Work Package |
|--------|-------------|----------|--------------|
| GAP-04 | `colour_mode` absent from `SchemaDefinition` | HIGH | WP-1 |
| GAP-04 | Colour conversion step missing in `adapt_to_schema()` | HIGH | WP-2, WP-3 |
| GAP-04 | `verify_schema_compliance()` does not check colour mode | HIGH | WP-4 |
| GAP-06 | No post-adaptation OCR quality gate | MEDIUM | WP-5, WP-6 |
| GAP-02 | Sauvola absent from adaptation binarisation path | LOW | WP-7 |

---

## 2. Stream 1 / Stream 2 Boundary

Stream 1 added `MasterConstraints` fields (`use_mrc`, `jpeg2000_ratio`, `jbig2_*`) and the `processors/mrc.py` module. Those changes touch `adapt_master_document()` only and are entirely separate from `adapt_to_schema()`.

Stream 2 **does not touch** `adapt_master_document()`, `encode_as_mrc_pdf()`, or anything in `mrc.py`. The boundary is clean.

---

## 3. Current State Snapshot (as-of post-Stream-1)

### 3.1 `SchemaDefinition` (worker/models.py)

```python
@dataclass(frozen=True)
class SchemaDefinition:
    target_width: int
    target_height: int
    target_dpi: int
    max_kb: int
    filename_pattern: str
    min_kb: int = 0
    output_format: str = "jpeg"
    quality: int = 85
    fit_mode: str = "stretch"        # "stretch" | "letterbox"

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> SchemaDefinition:
        fit_mode = str(data.get("fit_mode", "stretch")).lower()
        if fit_mode not in ("stretch", "letterbox"):
            fit_mode = "stretch"
        return SchemaDefinition(
            target_width=int(data.get("target_width", 600)),
            target_height=int(data.get("target_height", 800)),
            target_dpi=int(data.get("target_dpi", 300)),
            max_kb=int(data.get("max_kb", 200)),
            filename_pattern=str(data.get("filename_pattern", "{job_id}")),
            min_kb=int(data.get("min_kb", 0)),
            output_format=str(data.get("output_format", "jpeg")),
            quality=int(data.get("quality", 85)),
            fit_mode=fit_mode,
        )
```

**Missing:** `colour_mode`, `min_ocr_confidence`

### 3.2 `adapt_to_schema()` execution order (worker/processors/schema.py)

```
decode_image()
  │
  ├─► [PDF early-return if output_format == "pdf"]
  │
resize_exact()          ← Tier 3
  │
compress_to_size()      ← Tier 4
  │
normalize_filename()
  │
verify_schema_compliance()
```

**Missing between decode and resize:** Tier 2 colour mode conversion.

### 3.3 `verify_schema_compliance()` checks

Currently verifies:
- File size ≤ `max_kb`
- Pixel dimensions == (`target_width`, `target_height`)
- DPI metadata == `target_dpi`

**Missing:** colour mode verification, OCR confidence gate.

### 3.4 Tesseract adapter (worker/ocr/tesseract_adapter.py)

`extract_text(data, language, max_size_bytes) → OCRResult` exists and is fully implemented. It returns `OCRResult(text, confidence, page_count)` where `confidence` is normalised to 0.0–1.0.

**Problem:** `pytesseract` is **not** in `requirements.txt`, and `tesseract-ocr` is **not** installed in `Dockerfile.production`. The adapter is dead code.

### 3.5 Sauvola in mrc.py (worker/processors/mrc.py)

A full Sauvola implementation exists inline in `split_foreground_background()` (lines 104–125). Parameters: `window_size=25`, `k=0.2`, `R=128.0`, using `cv2.boxFilter` for O(N) box-filter integral computation. Stream 2 reuses this exact algorithm extracted into a shared helper.

---

## 4. Work Package 1 — `colour_mode` and `min_ocr_confidence` in `SchemaDefinition`

### What and why

`SchemaDefinition` needs two new fields:

- `colour_mode: str = "colour"` — the three valid values are `"colour"`, `"greyscale"`, and `"binary"`. Default `"colour"` preserves backward compatibility: all existing portal schemas that do not specify a colour mode continue to work exactly as before, with no conversion applied.

- `min_ocr_confidence: float = 0.0` — the minimum Tesseract confidence (0.0–1.0) required for the adapted output to pass the quality gate. Default `0.0` disables the gate. Schemas requiring legible output (photo forms, answer sheets) can set this to e.g. `0.35`.

### Validation rules

`colour_mode` must be one of `{"colour", "greyscale", "binary"}`. Any unrecognised value in `from_dict` must normalise to `"colour"` (defensive; never hard-fail on bad input here because the error surface is a JSON blob).

`min_ocr_confidence` must be in `[0.0, 1.0]`. Clamp to range in `from_dict`.

### Code — `worker/models.py`

Replace the current `SchemaDefinition` with:

```python
# Valid colour modes (ITU-T T.44 Tier 2)
_VALID_COLOUR_MODES: frozenset[str] = frozenset({"colour", "greyscale", "binary"})


@dataclass(frozen=True)
class SchemaDefinition:
    """Portal schema definition for document transformation."""
    target_width: int
    target_height: int
    target_dpi: int
    max_kb: int
    filename_pattern: str
    min_kb: int = 0
    output_format: str = "jpeg"
    quality: int = 85
    fit_mode: str = "stretch"            # "stretch" | "letterbox"
    # ITU-T T.44 Tier 2: colour mode applied BEFORE resize
    colour_mode: str = "colour"          # "colour" | "greyscale" | "binary"
    # Post-adaptation OCR gate: 0.0 = disabled
    min_ocr_confidence: float = 0.0

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> SchemaDefinition:
        """Parse schema definition from dict."""
        fit_mode = str(data.get("fit_mode", "stretch")).lower()
        if fit_mode not in ("stretch", "letterbox"):
            fit_mode = "stretch"

        colour_mode = str(data.get("colour_mode", "colour")).lower()
        if colour_mode not in _VALID_COLOUR_MODES:
            colour_mode = "colour"

        min_ocr_confidence = float(data.get("min_ocr_confidence", 0.0))
        min_ocr_confidence = max(0.0, min(1.0, min_ocr_confidence))

        return SchemaDefinition(
            target_width=int(data.get("target_width", 600)),
            target_height=int(data.get("target_height", 800)),
            target_dpi=int(data.get("target_dpi", 300)),
            max_kb=int(data.get("max_kb", 200)),
            filename_pattern=str(data.get("filename_pattern", "{job_id}")),
            min_kb=int(data.get("min_kb", 0)),
            output_format=str(data.get("output_format", "jpeg")),
            quality=int(data.get("quality", 85)),
            fit_mode=fit_mode,
            colour_mode=colour_mode,
            min_ocr_confidence=min_ocr_confidence,
        )
```

> **Backward compatibility:** every portal schema that omits `colour_mode` and `min_ocr_confidence` will parse to `"colour"` and `0.0` respectively. No existing behaviour changes.

---

## 5. Work Package 2 — Colour Conversion Logic

### Where it lives

New module-level functions in `worker/processors/schema.py`, added **above** `adapt_to_schema()`.

### 5.1 `_sauvola_threshold()`

Extracted from `mrc.py`'s inline copy. This is the same algorithm with the same defaults; extracted so schema.py does not import from mrc.py (avoids a circular dependency risk).

```python
def _sauvola_threshold(
    gray: np.ndarray,
    window_size: int = 25,
    k: float = 0.2,
    R: float = 128.0,
) -> np.ndarray:
    """
    Sauvola adaptive threshold.  Returns a uint8 binary mask where 255 = dark pixel
    (foreground text / ink) and 0 = light pixel (background).

    T(x,y) = mean(x,y) * (1 + k * (std(x,y)/R - 1))

    Uses cv2.boxFilter for O(N) box-filter integral computation (independent of
    window_size).  This is far faster than the naive per-pixel sliding window.

    Args:
        gray        : Single-channel float32 or uint8 array (H × W).
        window_size : Square window side length (pixels).  Must be odd.
        k           : Sensitivity.  Higher k → more foreground pixels kept.
        R           : Normalisation constant (128 for 8-bit images).

    Returns:
        uint8 array with values 0 or 255.
    """
    gray_f = gray.astype(np.float32)
    kernel = (window_size, window_size)
    mean = cv2.boxFilter(gray_f, ddepth=-1, ksize=kernel, normalize=True)
    mean_sq = cv2.boxFilter(gray_f * gray_f, ddepth=-1, ksize=kernel, normalize=True)
    variance = np.maximum(mean_sq - mean * mean, 0.0)
    std = np.sqrt(variance)
    threshold = mean * (1.0 + k * (std / R - 1.0))
    binary = np.where(gray_f < threshold, np.uint8(255), np.uint8(0))
    # Close sub-pixel gaps in character strokes
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, close_kernel)
    return binary
```

### 5.2 `convert_colour_mode()`

```python
# Constants
_GREYSCALE_CH_VARIANCE_THRESHOLD = 5  # max allowed per-channel variance for greyscale check

def convert_colour_mode(
    img: np.ndarray,
    mode: str,
) -> np.ndarray:
    """
    Convert a BGR image to the target colour mode.

    ITU-T T.44 Tier 2 constraint — must be applied BEFORE resizing.

    "colour"    → no-op; returns the original array unchanged
    "greyscale" → convert to greyscale then back to 3-channel BGR so
                  downstream stages (JPEG encoding, dimension checks) remain
                  channel-agnostic.  Output has R == G == B for every pixel.
    "binary"    → Sauvola adaptive thresholding → black-on-white output.
                  Returns a 3-channel image (R == G == B == 0 or 255) for
                  JPEG compatibility.

    Args:
        img  : BGR uint8 ndarray (H × W × 3).
        mode : One of "colour", "greyscale", "binary".

    Returns:
        BGR uint8 ndarray (H × W × 3).
    """
    if mode == "colour":
        return img

    if mode == "greyscale":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    if mode == "binary":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = _sauvola_threshold(gray)
        # binary: 255 = foreground (dark) → invert to black-on-white
        black_on_white = cv2.bitwise_not(mask)
        return cv2.cvtColor(black_on_white, cv2.COLOR_GRAY2BGR)

    # Defensive: unknown mode → treat as colour (caller validated earlier)
    return img
```

### Why greyscale returns 3-channel output

JPEG does not support single-channel natively in the way PIL/OpenCV typically handle it; saving a single-channel array often produces monochrome JFIF with `cv2.imwrite` but may surprise PIL. Returning a 3-channel BGR where all channels are equal is transparent to downstream code (compress_to_size, verify_schema_compliance) and guarantees compatibility with existing JPEG encoding paths.

### Why Sauvola over Otsu for binary mode

| Method | Failure mode |
|--------|-------------|
| Otsu (global) | Single threshold — fails when document has shadow gradient across the frame (mobile camera). The dark side of the document clips all text. |
| Adaptive Gaussian (cv2) | Fixed block size and constant offset. Mis-classifies pixels near shadow/highlight transitions. |
| Sauvola | Per-pixel threshold based on local mean + local std dev normalised by R. Self-calibrates to local contrast. Handles uneven lighting, glossy cards, water-stained documents. |

Otsu is still correct for signatures (high-contrast ink on white from scanner). Sauvola is correct for photographed documents with ambient lighting variation.

---

## 6. Work Package 3 — Updated Constraint Ordering in `adapt_to_schema()`

### What changes

A single insertion between `decode_image()` and `resize_exact()`:

```python
# Between decode_image() and resize_exact():
cv_img = convert_colour_mode(cv_img, schema.colour_mode)
```

This is the only required change to the main execution path. It must come BEFORE resize so that Sauvola thresholding (which depends on spatial frequency of the text) operates on the full-resolution image, not a downsampled one. Resizing binary images with Lanczos introduces sub-pixel artifacts at text edges.

### Full updated control flow for `adapt_to_schema()`

```
decode_image(data)
  │
  ├─► [PDF early-return if output_format == "pdf"]      ← unchanged
  │
convert_colour_mode(img, schema.colour_mode)            ← NEW (Tier 2)
  │
resize_exact(img, w, h, fit_mode)                       ← Tier 3  (unchanged)
  │
[dimension guard — belt-and-suspenders]                 ← unchanged
  │
compress_to_size(img, dpi, max_kb, format, quality)     ← Tier 4  (unchanged)
  │
normalize_filename(...)                                  ← unchanged
  │
verify_schema_compliance(data, schema)                   ← extended in WP-4, WP-6
```

### Complete replacement for `adapt_to_schema()` try-block

```python
    try:
        # Decode image
        cv_img, _ = decode_image(data)

        # --- PDF output path ---
        if schema.output_format.lower() == "pdf":
            pdf_data = encode_as_pdf(cv_img, schema.target_dpi)
            size_kb = len(pdf_data) / 1024
            if size_kb > schema.max_kb:
                raise WorkerError(
                    code=ErrorCode.SIZE_EXCEEDED,
                    stage=ProcessingStage.SCHEMA,
                    message=f"PDF size {size_kb:.1f}KB exceeds maximum {schema.max_kb}KB",
                    details={"size_kb": round(size_kb, 1), "max_kb": schema.max_kb},
                )
            filename = normalize_filename(
                schema.filename_pattern,
                job_id=job_id,
                user_id=user_id,
                original_filename=original_filename,
            )
            if not filename.lower().endswith(".pdf"):
                filename = f"{filename}.pdf"
            return SchemaResult(
                image_data=pdf_data,
                final_width=cv_img.shape[1],
                final_height=cv_img.shape[0],
                final_dpi=schema.target_dpi,
                final_size_kb=size_kb,
                filename=filename,
            )
        # --- End PDF path ---

        # ITU-T T.44 Tier 2: colour mode conversion BEFORE resize
        cv_img = convert_colour_mode(cv_img, schema.colour_mode)

        # Resize to exact dimensions (Tier 3)
        resized = resize_exact(
            cv_img,
            schema.target_width,
            schema.target_height,
            fit_mode=schema.fit_mode,
        )

        # Belt-and-suspenders dimension guard
        h, w = resized.shape[:2]
        if w != schema.target_width or h != schema.target_height:
            raise WorkerError(
                code=ErrorCode.RESIZE_FAILED,
                stage=ProcessingStage.SCHEMA,
                message="Post-resize dimension verification failed",
            )

        # Compress to size with DPI (Tier 4)
        compressed_data, final_quality = compress_to_size(
            resized,
            dpi=schema.target_dpi,
            max_kb=schema.max_kb,
            format=schema.output_format,
            initial_quality=schema.quality,
            min_kb=schema.min_kb,
        )

        # Normalize filename
        filename = normalize_filename(
            schema.filename_pattern,
            job_id=job_id,
            user_id=user_id,
            original_filename=original_filename,
        )
        ext = ".jpg" if schema.output_format.lower() in ("jpeg", "jpg") else f".{schema.output_format.lower()}"
        if not filename.lower().endswith(ext):
            filename = f"{filename}{ext}"

        # Post-adapt compliance gate (extended in WP-4 and WP-6)
        is_compliant, compliance_msg = verify_schema_compliance(compressed_data, schema)
        if not is_compliant:
            raise WorkerError(
                code=ErrorCode.SCHEMA_FAILED,
                stage=ProcessingStage.SCHEMA,
                message=f"Post-adapt compliance check failed: {compliance_msg}",
            )

        return SchemaResult(
            image_data=compressed_data,
            final_width=schema.target_width,
            final_height=schema.target_height,
            final_dpi=schema.target_dpi,
            final_size_kb=len(compressed_data) / 1024,
            filename=filename,
            output_format=schema.output_format.lower(),
            content_type="application/pdf" if schema.output_format.lower() == "pdf" else "image/jpeg",
        )
```

**Note on binary + JPEG:** Sauvola produces a clean binary image (0 or 255 per channel). JPEG is a lossy format and will reintroduce grey pixels at encoding. This is expected and acceptable for portal submissions — the output is visually binary and the artefacts are at the sub-pixel level. If a schema requires lossless binary output, set `output_format: "png"` in the schema definition.

---

## 7. Work Package 4 — Colour Mode Verification in `verify_schema_compliance()`

### What needs to be checked

| `colour_mode` | Verification approach |
|--------------|----------------------|
| `"colour"` | No check needed (anything passes) |
| `"greyscale"` | Per-pixel: max channel difference across the image should be small. A strict check is: `np.max(img[:,:,0].astype(int) - img[:,:,2].astype(int))` ≤ tolerance. But JPEG compression re-introduces minor channel divergence. Use mean absolute channel divergence ≤ 8 as the threshold. |
| `"binary"` | Pixel value distribution: ideally ≥ 90% of pixels should be near 0 (black) or 255 (white). JPEG artefacts permit a grey midband. Check: fraction of pixels with value in [32, 224] should be ≤ 15%. |

### Implementation

Replace the current `verify_schema_compliance()` with the extended version below. The existing size, dimension, and DPI checks are preserved unchanged; colour mode and OCR checks are appended.

```python
# Colour mode verification constants
_GREYSCALE_MAX_MEAN_CHANNEL_DIVERGENCE = 8   # max mean abs(R-B) for greyscale
_BINARY_MAX_GREY_FRACTION = 0.15             # max fraction of mid-grey pixels
_BINARY_GREY_LOW = 32                        # lower bound of "grey" band
_BINARY_GREY_HIGH = 224                      # upper bound of "grey" band


def verify_schema_compliance(
    data: bytes,
    schema: SchemaDefinition,
) -> Tuple[bool, str]:
    """
    Verify that image data complies with schema.

    Checks (in order):
      1. File size ≤ max_kb
      2. Pixel dimensions == (target_width, target_height)
      3. DPI metadata == target_dpi
      4. Colour mode    (if schema.colour_mode != "colour")
      5. OCR confidence ≥ min_ocr_confidence  (if min_ocr_confidence > 0)
    """
    try:
        # --- 1. File size ---
        size_kb = len(data) / 1024
        if size_kb > schema.max_kb:
            return False, f"Size {size_kb:.1f}KB exceeds max {schema.max_kb}KB"

        # --- 2. Dimensions ---
        nparr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return False, "Failed to decode image"

        h, w = img.shape[:2]
        if w != schema.target_width:
            return False, f"Width {w} != target {schema.target_width}"
        if h != schema.target_height:
            return False, f"Height {h} != target {schema.target_height}"

        # --- 3. DPI metadata ---
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

        # --- 4. Colour mode ---
        if schema.colour_mode == "greyscale":
            # R and B channels should be nearly equal (JPEG can add small divergence)
            b_ch = img[:, :, 0].astype(np.int32)
            r_ch = img[:, :, 2].astype(np.int32)
            mean_divergence = float(np.mean(np.abs(r_ch - b_ch)))
            if mean_divergence > _GREYSCALE_MAX_MEAN_CHANNEL_DIVERGENCE:
                return False, (
                    f"Colour mode 'greyscale' violated: "
                    f"mean R-B channel divergence {mean_divergence:.1f} > {_GREYSCALE_MAX_MEAN_CHANNEL_DIVERGENCE}"
                )

        elif schema.colour_mode == "binary":
            # Almost all pixels should be near 0 or near 255 (on any channel)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            total = gray.size
            grey_pixels = int(np.sum(
                (gray > _BINARY_GREY_LOW) & (gray < _BINARY_GREY_HIGH)
            ))
            grey_fraction = grey_pixels / total if total > 0 else 0.0
            if grey_fraction > _BINARY_MAX_GREY_FRACTION:
                return False, (
                    f"Colour mode 'binary' violated: "
                    f"{grey_fraction:.1%} mid-grey pixels exceed {_BINARY_MAX_GREY_FRACTION:.0%} threshold"
                )

        # --- 5. OCR quality gate ---
        if schema.min_ocr_confidence > 0.0:
            ok, msg = _verify_ocr_confidence(data, schema.min_ocr_confidence)
            if not ok:
                return False, msg

        return True, ""

    except Exception as e:
        return False, f"Verification error: {str(e)}"
```

---

## 8. Work Package 5 — OCR Quality Gate Infrastructure

### Problem

`worker/ocr/tesseract_adapter.py` is fully implemented but is never callable in the production container because:
1. `pytesseract` is absent from `requirements.txt`
2. `tesseract-ocr` binary is absent from `Dockerfile.production`

### 8.1 `requirements.txt` addition

Add to the OCR section of `worker/requirements.txt`:

```
# OCR — Tesseract (post-adaptation quality gate)
# Lightweight CPU-only OCR used to verify adapted output legibility.
# Primary OCR (Document AI) is used in Stage 4; this is a verification check only.
pytesseract>=0.3.10,<0.4.0
```

### 8.2 `Dockerfile.production` — runtime layer addition

In the base layer `apt-get install` block (the one that installs `libgl1`, `libglib2.0-0`, etc.) add:

```dockerfile
    # Tesseract OCR runtime (post-adaptation quality gate via tesseract_adapter.py)
    tesseract-ocr \
    tesseract-ocr-eng \
```

**Justification for English only (`tesseract-ocr-eng`):** The quality gate uses OCR confidence to detect when aggressive JPEG compression has destroyed legibility. It does not need to extract correct text — it only needs a confidence signal. English is sufficient as a proxy model for all document types. The Latin script coverage of `eng` is adequate for confidence measurement on any document.

**Image size impact:** `tesseract-ocr` + `tesseract-ocr-eng` adds approximately 30–40 MB to the production image. This is acceptable given the correctness benefit. If image size is a concern, the gate can be made opt-in via `min_ocr_confidence > 0.0` (it already is — zero disables the import).

### 8.3 Lazy import strategy

The Tesseract call should use a **deferred import** inside `_verify_ocr_confidence()` so that containers that never trigger the OCR gate (all existing schemas where `min_ocr_confidence == 0.0`) bear zero import cost:

```python
def _verify_ocr_confidence(
    data: bytes,
    min_confidence: float,
) -> Tuple[bool, str]:
    """
    Run Tesseract OCR on adapted image data and verify confidence meets the threshold.

    Lazily imports tesseract_adapter to avoid mandatory Tesseract dependency
    for schemas that do not require the OCR gate (min_ocr_confidence == 0.0).
    """
    try:
        from ocr.tesseract_adapter import extract_text, OCRResult
        from errors.error_codes import ProcessingError
    except ImportError:
        # pytesseract not installed — skip gate with a warning logged by caller
        return True, ""

    try:
        result: OCRResult = extract_text(data)
        if result.confidence < min_confidence:
            return False, (
                f"OCR confidence {result.confidence:.3f} below minimum {min_confidence:.3f} "
                f"— adapted image may be too compressed to remain legible"
            )
        return True, ""
    except ProcessingError as e:
        # OCR-specific errors (unsupported format, no text) → fail the gate
        return False, f"OCR quality gate error: {e.details.get('reason', str(e))}"
    except Exception as e:
        # Unexpected Tesseract failure → fail open (warn, do not hard-fail the job)
        return True, ""   # Do not block on transient OCR failures
```

**Why fail-open on unexpected exceptions?** The OCR gate is a quality check, not a security control. A transient Tesseract segfault should not block a user's document upload. Only `ProcessingError` (format issues, no text extracted) triggers a hard failure.

---

## 9. Work Package 6 — OCR Gate Integration in `verify_schema_compliance()`

This is already shown in the WP-4 code above (Step 5 of `verify_schema_compliance()`). The helper `_verify_ocr_confidence()` from WP-5 is called when `schema.min_ocr_confidence > 0.0`.

Place `_verify_ocr_confidence()` directly above `verify_schema_compliance()` in `schema.py`. It is a module-private function (underscore prefix) and should not be exported.

### Threshold guidance for schema authors

| Use case | Recommended `min_ocr_confidence` |
|----------|----------------------------------|
| Disabled (all schemas by default) | `0.0` |
| Passport photo (no text required) | `0.0` |
| Signature (no legible text expected) | `0.0` |
| Application form (typed text must survive) | `0.35` |
| Answer sheet with printed questions | `0.45` |
| Identity document with printed fields | `0.40` |

These values are conservative. Tesseract's average confidence on a clean 300 DPI JPEG of printed text is typically 0.70–0.90. A value below 0.35 almost always indicates the image is visually degraded.

---

## 10. Work Package 7 — Sauvola in `_enhance_document()` (LOW priority)

This work package is **optional and lower priority** than WP-1 through WP-6. It improves the enhancement stage for a specific set of documents. Do not implement this until WP-1 through WP-6 are merged, tested, and stable.

### Problem

`_enhance_document()` in `enhancement.py` ends with CLAHE (contrast-limited adaptive histogram equalisation). CLAHE improves global contrast but does not binarise the image. For documents that will eventually be output as `colour_mode = "binary"`, it is wasteful to apply CLAHE and then Sauvola in schema adaptation.

However, more importantly: Sauvola operating on a CLAHE-normalised image gives **better binarisation quality** than Sauvola operating on a raw photograph (which may have strong ambient gradients). The enhancement stage cleans up the signal before binarisation.

### What changes in `_enhance_document()`

Add an optional binarisation step at the end of `_enhance_document()`, gated by a new `options` flag:

```python
# In EnhancementOptions (models.py or in enhancement.py itself):
binarise_output: bool = False    # If True, apply Sauvola binarisation as final step
```

At the end of `_enhance_document()`, after CLAHE:

```python
    if options.binarise_output and not skip_enhancement:
        from processors.schema import _sauvola_threshold
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = _sauvola_threshold(gray)
        black_on_white = cv2.bitwise_not(mask)
        img = cv2.cvtColor(black_on_white, cv2.COLOR_GRAY2BGR)
        color_normalized = True
        logger.info("[ENHANCEMENT] document Sauvola binarisation applied")
```

**How this is activated:** When `worker.py` routes a job with `colour_mode == "binary"`, it can set `EnhancementOptions(binarise_output=True)` before the Stage 3 enhancement call. The Stage 5 adaptation then receives a pre-binarised image and `convert_colour_mode()` becomes a near no-op (the image is already binary).

### Note on the circular import risk

`_enhance_document()` importing from `schema.py` would create a circular dependency only if `schema.py` also imports from `enhancement.py`. Currently `schema.py` does **not** import `enhancement.py`. The import direction `enhancement → schema` is safe.

Alternatively, move `_sauvola_threshold()` to a new `worker/processors/utils.py` module that neither `schema.py` nor `enhancement.py` owns. Both can then import from `utils.py`. This is cleaner architecturally and is the recommended approach if you implement WP-7.

---

## 11. Portal Schemas Seed Data Update

### Current JSONB shape in `db/schema.sql`

```json
{
    "photo":     {"dimensions": [400, 600], "dpi": 300, "max_kb": 200, "format": "jpg"},
    "signature": {"dimensions": [200, 100], "dpi": 200, "max_kb": 50,  "format": "jpg"}
}
```

### How this maps to `SchemaDefinition`

The worker resolves `SchemaDefinition` from the `requirements` JSONB blob. The keys `dimensions[0]` → `target_width`, `dimensions[1]` → `target_height`, `dpi` → `target_dpi`, `max_kb` → `max_kb`, `format` → `output_format`.

The new `colour_mode` field maps directly: add `"colour_mode": "greyscale"` for signature schemas, `"colour_mode": "colour"` for photo schemas.

### Updated seed data

```sql
INSERT INTO public.portal_schemas (id, name, category, requirements) VALUES
('NEET_2026', 'NEET 2026', 'exam', '{
    "photo": {
        "dimensions": [400, 600], "dpi": 300, "max_kb": 200, "format": "jpg",
        "colour_mode": "colour"
    },
    "signature": {
        "dimensions": [200, 100], "dpi": 200, "max_kb": 50, "format": "jpg",
        "colour_mode": "greyscale"
    }
}'::jsonb),
('JEE_MAIN_2026', 'JEE Main 2026', 'exam', '{
    "photo": {
        "dimensions": [400, 600], "dpi": 300, "max_kb": 200, "format": "jpg",
        "colour_mode": "colour"
    },
    "signature": {
        "dimensions": [200, 100], "dpi": 200, "max_kb": 50, "format": "jpg",
        "colour_mode": "greyscale"
    }
}'::jsonb),
('UPSC_CSE_2026', 'UPSC CSE 2026', 'government', '{
    "photo": {
        "dimensions": [400, 600], "dpi": 300, "max_kb": 300, "format": "jpg",
        "colour_mode": "colour"
    },
    "signature": {
        "dimensions": [200, 100], "dpi": 200, "max_kb": 50, "format": "jpg",
        "colour_mode": "greyscale"
    }
}'::jsonb),
('CAT_2026', 'CAT 2026', 'exam', '{
    "photo": {
        "dimensions": [400, 600], "dpi": 300, "max_kb": 200, "format": "jpg",
        "colour_mode": "colour"
    },
    "signature": {
        "dimensions": [200, 100], "dpi": 200, "max_kb": 50, "format": "jpg",
        "colour_mode": "greyscale"
    }
}'::jsonb),
('GATE_2026', 'GATE 2026', 'exam', '{
    "photo": {
        "dimensions": [480, 640], "dpi": 300, "max_kb": 200, "format": "jpg",
        "colour_mode": "colour"
    },
    "signature": {
        "dimensions": [240, 120], "dpi": 200, "max_kb": 50, "format": "jpg",
        "colour_mode": "greyscale"
    }
}'::jsonb)
ON CONFLICT (id) DO UPDATE SET
    requirements = EXCLUDED.requirements,
    updated_at = NOW();
```

> **Important:** change `ON CONFLICT (id) DO NOTHING` → `ON CONFLICT (id) DO UPDATE SET requirements = EXCLUDED.requirements` for the seed data migration. The original `DO NOTHING` means a re-run of the schema script does not update existing rows — this prevents the `colour_mode` fields from being added to an already-seeded database.

### Migration strategy

Since `colour_mode` lives inside the `requirements JSONB` column (not as a separate SQL column), **no `ALTER TABLE` migration is required**. The change is entirely within the JSONB value. The seed data re-run (using `DO UPDATE`) is sufficient for both fresh installs and existing databases.

For live production databases with a `portal_schemas` table already populated, run the targeted update:

```sql
-- db/migrations/20XX_add_colour_mode_to_portal_schemas.sql
UPDATE public.portal_schemas
SET requirements = jsonb_set(
        requirements,
        '{photo,colour_mode}',
        '"colour"'
    )
WHERE active = true
  AND (requirements->'photo'->>'colour_mode') IS NULL;

UPDATE public.portal_schemas
SET requirements = jsonb_set(
        requirements,
        '{signature,colour_mode}',
        '"greyscale"'
    )
WHERE active = true
  AND (requirements->'signature'->>'colour_mode') IS NULL;
```

---

## 12. Dependency Summary

### Python packages (`worker/requirements.txt`)

| Package | Why | Change |
|---------|-----|--------|
| `pytesseract>=0.3.10,<0.4.0` | OCR quality gate adapter | **Add** |

All other packages (`cv2`, `numpy`, `PIL`, `pikepdf`) are already present.

### System packages (`worker/Dockerfile.production`, base layer)

| Package | Why | Change |
|---------|-----|--------|
| `tesseract-ocr` | Tesseract binary | **Add** |
| `tesseract-ocr-eng` | English model for confidence measurement | **Add** |

---

## 13. Testing Checklist

### Unit tests — new functions

**`convert_colour_mode()`**
- [ ] `mode="colour"` → returns input unchanged (same array or copy with identical values)
- [ ] `mode="greyscale"` → output has `R == G == B` for all pixels
- [ ] `mode="binary"` → all pixels are 0 or 255 after JPEG compression artefacts are accounted for (use tolerance, not exact equality)
- [ ] Unknown mode → returns input unchanged (no exception)

**`_sauvola_threshold()`**
- [ ] Produces 0/255-only output array
- [ ] Output shape matches input shape
- [ ] Works on solid-white input (all 0 → no foreground)
- [ ] Works on solid-black input (all 255 → all foreground)

**`verify_schema_compliance()` — colour mode checks**
- [ ] `colour_mode="colour"` skips channel check (existing test should still pass)
- [ ] `colour_mode="greyscale"` with a greyscale JPEG → passes
- [ ] `colour_mode="greyscale"` with a full-colour JPEG → fails with appropriate message
- [ ] `colour_mode="binary"` with binarised JPEG → passes
- [ ] `colour_mode="binary"` with colour photograph → fails

**`verify_schema_compliance()` — OCR gate**
- [ ] `min_ocr_confidence=0.0` → OCR gate is skipped (no `pytesseract` import attempted)
- [ ] `min_ocr_confidence=0.35` on clean text image → passes
- [ ] `min_ocr_confidence=0.35` on noise/blank image → fails with legibility message
- [ ] `min_ocr_confidence=0.35` with `pytesseract` import error → gate is skipped (fail-open)

**`SchemaDefinition.from_dict()`**
- [ ] Missing `colour_mode` key → defaults to `"colour"`
- [ ] `colour_mode="GREYSCALE"` (uppercase) → normalised to `"greyscale"`
- [ ] `colour_mode="invalid"` → normalised to `"colour"`
- [ ] `min_ocr_confidence=-0.5` → clamped to `0.0`
- [ ] `min_ocr_confidence=1.5` → clamped to `1.0`

### Integration tests

- [ ] Portal job with `colour_mode="greyscale"` produces a greyscale JPEG at the correct dimensions
- [ ] Portal job with `colour_mode="binary"` produces a near-binary JPEG
- [ ] Existing portal jobs with no `colour_mode` in JSONB continue to produce colour output unchanged
- [ ] `min_ocr_confidence=0.40` with a heavily over-compressed JPEG → job fails at SCHEMA stage with code `SCHEMA_FAILED`
- [ ] `min_ocr_confidence=0.40` with a clean 300 DPI scan → job succeeds

### Regression tests

- [ ] All existing `test_schema_validation.py` tests still pass unmodified
- [ ] `test_adaptation_v2.py` photo and signature round-trips are unchanged

---

## 14. Rollout Strategy

### Phase 1 — Code merge (no schema changes)

Merge WP-1 through WP-6. Because:
- `colour_mode` defaults to `"colour"` → zero behaviour change for all existing schemas
- `min_ocr_confidence` defaults to `0.0` → OCR gate disabled by default for all existing schemas

After this merge, the production container can be deployed with no risk. Existing jobs in flight are unaffected.

### Phase 2 — Dockerfile build

Build and push the updated production Docker image with `tesseract-ocr` added. This is the only infrastructure change. Monitor container startup time and image size.

### Phase 3 — Signature schema update

Update the `signature` sub-schema for NEET_2026 and the other exam schemas with `"colour_mode": "greyscale"`. Run the migration SQL against the live database. Smoke test one signature upload end-to-end.

### Phase 4 — OCR gate activation (optional, manual per schema)

For any schema where portal submission failures are being observed due to over-compressed outputs, set `"min_ocr_confidence": 0.35` in that schema's JSONB requirements. This is gated per schema and can be enabled one at a time.

### Phase 5 — WP-7 (Sauvola in enhancement, optional)

Implement only after Phase 1–4 are stable. This is a further quality optimisation and is not required for correctness.

---

## 15. Full Change Summary

| File | Change type | Description |
|------|------------|-------------|
| `worker/models.py` | Modify | Add `colour_mode: str = "colour"` and `min_ocr_confidence: float = 0.0` to `SchemaDefinition`; update `from_dict` with clamping and normalisation |
| `worker/processors/schema.py` | Modify | Add `_VALID_COLOUR_MODES`, `_sauvola_threshold()`, `convert_colour_mode()`, `_GREYSCALE_MAX_MEAN_CHANNEL_DIVERGENCE`, `_BINARY_MAX_GREY_FRACTION`, `_verify_ocr_confidence()`; update `adapt_to_schema()` to call `convert_colour_mode()` between decode and resize; extend `verify_schema_compliance()` with colour mode check and OCR gate |
| `worker/requirements.txt` | Modify | Add `pytesseract>=0.3.10,<0.4.0` |
| `worker/Dockerfile.production` | Modify | Add `tesseract-ocr` and `tesseract-ocr-eng` system packages to base layer |
| `db/schema.sql` | Modify | Add `"colour_mode"` to all `portal_schemas` seed entries; change `DO NOTHING` → `DO UPDATE` |
| `db/migrations/20XX_add_colour_mode_to_portal_schemas.sql` | New | SQL to backfill `colour_mode` into existing production schemas via JSONB update |

**Files NOT touched by Stream 2:**
- `worker/processors/mrc.py` — Stream 1 only
- `worker/processors/enhancement.py` — WP-7 only (optional, later phase)
- `worker/worker.py` — no stage wiring changes needed (colour conversion is inside adapt_to_schema)
- `worker/ocr/tesseract_adapter.py` — already correct, no changes needed

---

## 16. Open Decisions

The following decisions are noted but do not block implementation. Defaults have been chosen conservatively and can be adjusted without interface changes.

| Decision | Default chosen | Alternative |
|----------|---------------|-------------|
| Sauvola `window_size` | 25 (from mrc.py) | 51 for larger images (≥ 1200px wide) |
| Sauvola `k` | 0.2 (from mrc.py) | 0.5 for higher-contrast documents |
| Greyscale channel divergence tolerance | 8 (mean R-B) | Stricter: 4; looser: 12 |
| Binary grey-pixel tolerance | 15% | Stricter: 8% (before JPEG artefacts at quality ≥ 85 are taken into account) |
| OCR fail-open on unexpected exceptions | Yes (fail-open) | Fail-closed (reject output on any OCR error) |
| Tesseract language model | `eng` only | Add `hin` (Hindi) for better confidence signal on Devanagari documents |
| WP-7 `binarise_output` gating | `EnhancementOptions` flag | Check `colour_mode` from job payload directly in `worker.py` |
