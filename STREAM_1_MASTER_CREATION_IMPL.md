# Stream 1 — Master Creation Pipeline: Implementation Plan

**Status:** Pre-implementation review  
**Target files:** `worker/processors/mrc.py` (new), `worker/processors/schema.py`, `worker/models.py`, `worker/requirements.txt`, `worker/Dockerfile.production`  
**Worker entry point:** `worker/worker.py` (wiring only — no logic changes)  

---

## 1. Problem Statement

### What is stored today

`adapt_master_document()` in `worker/processors/schema.py` (line ~500) does exactly this:

```
decode image → compress_to_size (JPEG binary search) → upload
```

`compress_to_size` calls `encode_with_dpi`, which calls `PIL.Image.save(..., format="JPEG", quality=..., dpi=...)`. The master is stored as a **plain JPEG**.

For a typical Indian mark sheet scanned at 300 DPI in colour (raw enhanced output: ~2–4 MB JPEG):
- Current master size: **600 KB – 1.5 MB** (JPEG quality ~92)
- Text appearance: subject to JPEG DCT blocking artefacts at high-frequency edges
- The document's text, which is the primary information carrier, is stored using a format designed for photographs

### What we want to store

A **PDF/A-3b** file with MRC compression:
- Foreground layer (text, line art): JBIG2-encoded at native resolution — text stays pixel-perfect
- Background layer (paper texture, gradients, colour): JPEG 2000-encoded at 1/3 native resolution — nobody needs sharp paper texture
- Hidden text layer: actual character positions from Document AI output embedded as invisible PDF text, making the master searchable

Expected master size for the same document: **150–500 KB**, with visually and informationally lossless text.

The `output_format` field in `MasterConstraints` already accepts arbitrary strings. The new value will be `"pdf_mrc"`. When callers pass the existing `"jpeg"` or `"jpeg2000"`, they get the existing paths. `"pdf_mrc"` triggers the new pipeline.

---

## 2. Architecture Overview

```
adapt_master_document()
        │
        ├─ output_format == "jpeg"      → existing compress_to_size path  (no change)
        ├─ output_format == "jpeg2000"  → new: encode_as_jpeg2000()        (Phase 1 — pure Python)
        └─ output_format == "pdf_mrc"   → new: encode_as_mrc_pdf()         (Phase 2 — native deps)
                                                     │
                                         ┌──────────┴───────────┐
                                         │                       │
                                  decompose_layers()      ocr_result (passed in)
                                  ┌──────┴──────┐
                            foreground_mask   background_img
                                  │                 │
                              jbig2enc CLI    JPEG2000 (Pillow)
                              (lossless)      (downsampled 1/3)
                                  │                 │
                                  └──────┬──────────┘
                                  assemble_mrc_pdf()
                                         │
                                  embed_text_layer()   ← Document AI boxes + text
                                         │
                                  PDF/A-3b bytes
```

### Fallback chain (when native libs unavailable)

```
pdf_mrc requested
        │
        ├─ jbig2enc available?  YES ──→ full MRC PDF
        │                       NO  ──┐
        │                             ├─ OpenJPEG in Pillow? YES → JPEG 2000 single file
        │                             │                      NO  → JPEG (existing logic)
        │
        └─ Log which path was taken at INFO level
```

The fallback is silent from the caller's perspective — `adapt_master_document` always returns a `SchemaResult`. The actual format stored is reported in `SchemaResult.output_format` (a new field we add).

---

## 3. Phase 1 — JPEG 2000 Master (Pure Python, No Native Deps)

This phase can be deployed **immediately** with no Dockerfile changes.

### 3.1 What changes

**New function in `worker/processors/schema.py`:**

```python
def encode_as_jpeg2000(
    img: NDArray[np.uint8],
    dpi: int,
    target_ratio: float = 10.0,
) -> bytes:
```

**Parameters:**
- `img`: BGR image array from OpenCV (the enhanced Stage 3 output)
- `dpi`: DPI value to embed (from `MasterConstraints.target_dpi`)
- `target_ratio`: Compression ratio. `1.0` = lossless. `10.0` = 10:1 compression (recommended default for masters). Pillow passes this to OpenJPEG as `quality_layers`.

**Algorithm:**
1. Convert BGR → RGB (`cv2.cvtColor`)
2. Create PIL Image from array
3. Call `pil_img.save(buffer, format="JPEG2000", quality_mode="rates", quality_layers=[target_ratio])` — this invokes OpenJPEG via Pillow's internal binding
4. Note: Pillow's JPEG 2000 encoder does **not** support embedding DPI metadata. We handle this by wrapping the JP2 inside a minimal single-image PDF (PIL's built-in PDF encoder supports embedded JPEG 2000 images).

**Decision point for review:** Do you want a standalone `.jp2` file, or a `.pdf` wrapper around it?

A `.pdf` wrapper:
- ✅ Can carry DPI metadata in the PDF page size definition
- ✅ Universally openable (every OS, every browser)
- ✅ Position us for the full MRC PDF later (same container format)
- ❌ Slightly more code (but Pillow's PDF encoder handles it)

A standalone `.jp2` file:
- ✅ Simpler right now
- ❌ Less universally supported (requires specific viewer)
- ❌ Dead-end — can't add text layer to a raw JP2
- ❌ DPI metadata embedded differently; patchy support in readers

**Recommendation:** PDF wrapper. PIL does this in ~3 lines with `pil_img.save(buffer, format="PDF", append_images=[pil_img])`, then we embed the JP2 instead. Actually: PIL's `format="PDF"` re-encodes the image as DCT (JPEG). To embed JP2 in PDF we need `pikepdf`. See Section 3.3.

### 3.2 Compression ratio guidance

The `target_ratio` for JPEG 2000 maps to OpenJPEG's `quality_layers` parameter:

| `target_ratio` | Typical output size (3MP scan) | Use case |
|---|---|---|
| `1.0` | ~8–15 MB | Truly lossless, no use for masters |
| `5.0` | ~400–700 KB | High quality, academic certificates |
| `10.0` | ~200–400 KB | Good default for most Indian documents |
| `20.0` | ~100–200 KB | Aggressive, acceptable for plain text |
| `40.0` | <100 KB | Only for storage-constrained environments |

The ratio is computed dynamically relative to `MasterConstraints.max_kb` if needed: `ratio = (decoded_size_kb / max_kb) * safety_factor`. We start with `target_ratio=10.0` as default and iterate if the result exceeds `max_kb`.

### 3.3 PDF embedding of JPEG 2000 — the `pikepdf` dependency question

Pillow's PDF encoder re-encodes images as JPEG internally — it does not embed raw JP2 streams into the PDF. To get a PDF that contains a JP2-compressed image stream, we need to construct the PDF at the level of its image XObject.

Two options:

**Option A: `pikepdf` (recommended)**
- `pikepdf` is an MIT-licensed Python wrapper around QPDF
- `pip install pikepdf>=8.0.0`
- Allows constructing a PDF Image XObject with `Filter: /JPXDecode` (the JPEG 2000 PDF filter)
- Approximately 30 lines of code
- **Adds ~30 MB to the Docker image** (includes QPDF native lib)

**Option B: Raw PDF construction**
- A JPEG 2000 image in a PDF is a PDF 1.4+ Image XObject with `/Filter /JPXDecode`
- The minimum valid single-image PDF is ~700 bytes of PDF structure + the raw JP2 stream
- We can write this as a pure-Python byte-string template (~50 lines)
- No new dependency
- Fragile if JP2 stream has edge cases (e.g., multi-component, unusual subsampling)

**Decision point for review:** Should we add `pikepdf` to requirements, or use the raw PDF template approach?

**Recommendation:** `pikepdf`. The maintenance burden of a raw PDF parser is too high to justify avoiding a well-maintained library. `pikepdf` will also be useful for future work (page merging for multi-page documents, text layer embedding, PDF/A conformance marking).

### 3.4 `MasterConstraints` model changes (Phase 1)

Current fields in `worker/models.py`:

```python
@dataclass(frozen=True)
class MasterConstraints:
    max_kb: int = 2000
    target_dpi: int = 300
    output_format: str = "jpeg"
    quality: int = 92
    filename_pattern: str = "{job_id}_master"
    min_kb: int = 0
```

**New fields to add:**

```python
    # Phase 1
    jpeg2000_ratio: float = 10.0          # target compression ratio for JPEG2000 output
    # Phase 2
    use_mrc: bool = True                  # enable MRC layer decomposition (pdf_mrc format)
    bg_downsample: int = 3                # background layer downsample factor (1/3 native res)
    jbig2_lossless: bool = True           # use lossless JBIG2 (strongly recommended for Indian docs)
    jbig2_threshold: float = 0.85         # symbol matching threshold (lossy mode only, ignored if lossless)
    embed_text_layer: bool = True         # embed invisible text from Document AI into the PDF
```

**`from_dict` must be updated** to parse all new fields with their defaults.

**Backward compatibility:** All new fields have defaults. No existing callers break.

---

## 4. Phase 2 — Full MRC Pipeline

### 4.1 New file: `worker/processors/mrc.py`

This is the core new module. It has no side effects, no global state, and no imports that fail gracefully-badly — all native-dep checks live here.

#### 4.1.1 Availability detection

```python
def _jbig2enc_available() -> bool:
def _openjpeg_available() -> bool:
```

`_jbig2enc_available` runs `shutil.which("jbig2")` and returns `bool`. No subprocess invoked.  
`_openjpeg_available` attempts `from PIL import Image; Image.open(...).save(..., format="JPEG2000")` on a 1×1 test image in a `BytesIO` buffer. Returns `True` if no exception.

Both results are cached module-level at first call.

#### 4.1.2 Layer decomposition

```python
def decompose_layers(
    img: NDArray[np.uint8],
) -> tuple[NDArray[np.uint8], NDArray[np.uint8]]:
    """
    Split document image into foreground and background layers.

    Returns:
        foreground_mask : uint8 array, same H×W as input, values 0 or 255.
                          255 = text/line art pixel. 0 = background.
        background      : uint8 BGR array, same shape as input.
                          Text pixels are replaced with the local background colour
                          (not hard white) to avoid haloing artefacts in the background
                          JPEG2000 layer.
    """
```

**Algorithm inside `decompose_layers`:**

Step 1 — Convert to grayscale.

Step 2 — **Sauvola adaptive thresholding** to generate `foreground_mask`.

Sauvola formula: `T(x,y) = mean(x,y) × (1 + k × (std(x,y)/R − 1))`

Where:
- `window_size = 25` (pixels) — must be odd; larger handles more gradient variation
- `k = 0.2` — controls sensitivity; higher = more pixels classified as foreground
- `R = 128.0` — normalisation constant (half the maximum standard deviation for uint8)

Implementation uses `cv2.boxFilter` on the grayscale image and its square for fast integral-image-based local mean and std. This is O(N) regardless of window size.

Why Sauvola over Otsu or adaptive Gaussian (current usage in `document_processor.py`)?
- Otsu computes a single global threshold — fails on documents with uneven mobile-camera lighting
- Adaptive Gaussian uses a fixed block size and constant offset — works for most cases but mis-classifies pixels near shadow/highlight boundaries
- Sauvola locally normalises by standard deviation — regions with low contrast (plain white paper) stay white; regions with text (high local contrast) classify the dark pixels correctly

Step 3 — **Morphological closing** on `foreground_mask` with a 2×2 kernel to close sub-pixel gaps in character strokes.

Step 4 — **Background reconstruction.** Rather than setting text pixels to hard white (which creates visible haloing in the compressed background layer), replace text pixels with the median colour of a surrounding local neighbourhood:

```
For each row of connected text pixels, sample ±10 pixels above/below
from background pixels and set text pixels to the median of those samples.
```

This avoids the "laser-printed" flat-white look where text used to be. The background layer then compresses more efficiently because there's no sharp white rectangle where text was.

**Decision point for review:** The background reconstruction described above (median infill) adds complexity. The simpler option is hard-white replacement. For Indian documents on white/cream paper, the difference is minimal. Should we start with hard-white replacement and add median infill later if needed?

#### 4.1.3 JBIG2 encoding

```python
def encode_foreground_jbig2(
    mask: NDArray[np.uint8],
    lossless: bool = True,
    threshold: float = 0.85,
) -> bytes:
    """
    Encode binary foreground mask as JBIG2 using the jbig2enc CLI.

    Returns raw JBIG2 stream bytes suitable for embedding in a PDF
    Image XObject with Filter: /JBIG2Decode.

    Raises:
        RuntimeError: if jbig2enc CLI is not available or returns non-zero exit
    """
```

**CLI invocation details:**

`jbig2enc` (the binary is named `jbig2`) is invoked as a subprocess. The binary accepts a TIFF or PNM file as input. We write the mask to a temp file as 1-bit TIFF via PIL, then invoke:

```bash
jbig2 [-s] [-t <threshold>] <input.tiff>
```

Flags:
- `-s`: enables symbol compression (groups repeated glyphs; required for good compression)
- `-t <float>`: sets symbol matching threshold (only in lossy mode; we default omit in lossless mode)

Without `-b <basename>`, `jbig2enc` writes two things:
- The global JBIG2 dictionary segment to **a temp file** named `<input>`.sym
- The page segment to **stdout**

For PDF embedding, we need both segments concatenated in the correct order. The actual invocation used by `archive-pdf-tools` is:

```bash
jbig2 -s -p page.tiff    # -p = page symbol mode (global dict)
```

This writes:
- `output.sym` — global symbol dictionary (JBIG2 segment type 0)
- `output.0001` — page data segments

Both must be concatenated and embedded as the JBIG2 stream in the PDF XObject. The global dictionary is embedded as a `/JBIG2Globals` key in the XObject's filter parameters.

**Temp directory management:** All temp files use `tempfile.TemporaryDirectory()` as a context manager, guaranteed cleanup on exception.

**Input format:** `jbig2enc` requires 1-bit TIFF. PIL writes `pil_mask.save(path, format="TIFF")` where `pil_mask` is created from the uint8 mask array via `Image.fromarray(mask.astype(np.uint8)).convert("1")`.

**Error handling:** Non-zero return code from subprocess raises `RuntimeError` with stderr decoded. The caller catches this and falls back to JBIG2-less path.

#### 4.1.4 JPEG 2000 background encoding

```python
def encode_background_jpeg2000(
    background: NDArray[np.uint8],
    downsample_factor: int = 3,
    target_ratio: float = 10.0,
) -> tuple[bytes, int, int]:
    """
    Downsample and encode background layer as JPEG 2000.

    Returns:
        (jp2_bytes, encoded_width, encoded_height)
    """
```

**Algorithm:**

Step 1 — Downsample background by `downsample_factor` using `cv2.INTER_AREA` interpolation (correct for downsampling — averages pixels rather than sampling). `INTER_AREA` is important here because `INTER_LANCZOS4` (used for resize in schema adaptation) introduces ringing artefacts when downsampling by large factors.

Step 2 — Convert BGR → RGB.

Step 3 — `pil_img.save(buffer, format="JPEG2000", quality_mode="rates", quality_layers=[target_ratio])`.

Step 4 — Return `(jp2_bytes, encoded_width, encoded_height)`. The encoded dimensions are needed for the PDF XObject dictionary.

**Why return dimensions?** The PDF Image XObject for the background layer must declare its own width and height (the downsampled dimensions). The foreground XObject declares the original full dimensions. The PDF renderer upsamples the background back to full resolution when rendering.

#### 4.1.5 PDF/A-3b assembly

```python
def assemble_mrc_pdf(
    foreground_jbig2_dict: bytes,
    foreground_jbig2_page: bytes,
    foreground_width: int,
    foreground_height: int,
    background_jp2: bytes,
    background_width: int,
    background_height: int,
    dpi: int,
    text_layer: Optional["TextLayer"] = None,
) -> bytes:
    """
    Assemble foreground and background layers into a PDF/A-3b document.

    Uses pikepdf to construct the PDF at the XObject level.
    """
```

**PDF structure produced:**

```
PDF-1.7
  Catalog
  Pages
    Page (width = foreground_width / dpi inches, height = foreground_height / dpi inches)
      Contents (render instruction stream):
        [background XObject, scaled to full page]
        [foreground XObject, positioned at origin]
        [if text_layer: text object with invisible text runs]
      Resources:
        XObject:
          /BG → Image XObject (JPEG2000, background_width × background_height)
          /FG → Image XObject (JBIG2, foreground_width × foreground_height, ColorSpace /DeviceGray)
```

**The PDF render instruction stream** scales the background XObject from its downsampled dimensions to the full page dimensions, then draws the foreground XObject at 1:1 scale. This is why the text remains sharp — it is always stored and rendered at native resolution.

**PDF/A-3b conformance:** We set the following PDF metadata:
- `/Lang` in the document catalog
- XMP metadata block with `pdfaid:part=3` and `pdfaid:conformance=B`
- `pikepdf` can write both via its `PdfMetadata` context manager

**The invisible (searchable) text layer** is an entirely separate concern covered in Section 4.2.

#### 4.1.6 Public entry point in `mrc.py`

```python
def encode_as_mrc_pdf(
    img: NDArray[np.uint8],
    dpi: int,
    constraints: "MasterConstraints",
    ocr_result: Optional["DocumentAIResult"] = None,
) -> bytes:
    """
    Main entry point for MRC PDF encoding.

    Checks native lib availability and dispatches to the correct path:
      - jbig2enc + OpenJPEG available → full MRC PDF
      - only OpenJPEG available       → JPEG2000-in-PDF (Phase 1 path)
      - neither available             → WorkerError (caller falls back at a higher level)

    Args:
        img         : BGR image array (Stage 3 enhanced output)
        dpi         : DPI to embed in the master PDF
        constraints : MasterConstraints controlling compression parameters
        ocr_result  : Optional Document AI result for text layer embedding

    Returns:
        PDF bytes
    """
```

This function:
1. Calls `_jbig2enc_available()` and `_openjpeg_available()`
2. Dispatches to `assemble_mrc_pdf` or `encode_as_jpeg2000_pdf`
3. Checks that the resulting bytes are within `constraints.max_kb`
4. If over size: increases `bg_downsample` by 1 (max 6) and retries background encoding only (foreground is lossless and should not be retouched)
5. If still over size at `bg_downsample=6`: raises `WorkerError(ErrorCode.SIZE_EXCEEDED)`

### 4.2 Searchable text layer

**Source data:** `DocumentAIResult` (returned by `processors/document_ai.py`) already provides:
- `result.text` — full document text string
- `result.boxes` — list of `DocumentAIBox(x, y, width, height, text, confidence)` in pixel coordinates
- `result.page_width`, `result.page_height` — pixel dimensions of the processed image

**How invisible text works in PDF:** A PDF text object with `Tr 3` (text rendering mode 3 = invisible) draws text that participates in text selection and search but renders no pixels. Each text run is positioned with a transformation matrix that maps the text's typographic bounding box to the visual bounding box from the OCR result.

```python
def build_text_layer(
    ocr_result: "DocumentAIResult",
    page_width: int,
    page_height: int,
    dpi: int,
) -> "TextLayer":
    """
    Convert Document AI OCR boxes into a PDF text layer.

    Returns a TextLayer dataclass containing positioned invisible text runs
    ready for pikepdf to write as a content stream.
    """
```

**Coordinate mapping:** Document AI returns pixel coordinates referenced to the image dimensions. The PDF page dimensions are in points (1/72 inch). The mapping is:

```
pdf_x = (pixel_x / page_width)  * pdf_page_width_pts
pdf_y = pdf_page_height_pts - (pixel_y / page_height) * pdf_page_height_pts   # PDF y-axis is bottom-up
```

**Font:** We use the standard PDF base font `Helvetica` which requires no font embedding and is available in all PDF readers. The font size is computed per box: `font_size = (box_height_pixels / page_height) * pdf_page_height_pts`.

**Decision point for review:** The text layer requires `ocr_result` to be passed through from `worker.py` to `adapt_master_document` and then into `encode_as_mrc_pdf`. Currently `adapt_master_document` receives no OCR result. Two options:

**Option A:** Add `ocr_result: Optional[DocumentAIResult] = None` parameter to `adapt_master_document`. Worker.py currently has `ocr_result` in scope at the call site and passes it through.

**Option B:** Skip the text layer in Phase 2 and add it in a later phase. Embed nothing. Masters are still fully MRC-compressed; they just aren't searchable until later.

**Recommendation:** Option A. The OCR data is already computed when `adapt_master_document` is called. Passing it through is 2 lines of change. Not doing it means we deliberately discard information already paid for.

---

## 5. Changes to `worker/processors/schema.py`

### 5.1 `adapt_master_document()` — routing change

Current body (lines ~500–550) calls `compress_to_size` directly. New body:

```python
def adapt_master_document(
    data: bytes,
    constraints: MasterConstraints,
    job_id: str,
    user_id: str = "",
    original_filename: str = "",
    ocr_result: Optional[DocumentAIResult] = None,   # NEW parameter
) -> SchemaResult:
```

New routing logic inside the function:

```python
fmt = constraints.output_format.lower()

if fmt == "pdf_mrc":
    from processors.mrc import encode_as_mrc_pdf
    pdf_bytes = encode_as_mrc_pdf(cv_img, constraints.target_dpi, constraints, ocr_result)
    filename = _build_filename(constraints.filename_pattern, job_id, user_id, original_filename, ".pdf")
    return SchemaResult(image_data=pdf_bytes, ..., filename=filename)

elif fmt in ("jpeg2000", "jp2"):
    from processors.mrc import encode_as_jpeg2000_pdf
    jp2_bytes = encode_as_jpeg2000_pdf(cv_img, constraints.target_dpi, constraints.jpeg2000_ratio)
    filename = _build_filename(constraints.filename_pattern, job_id, user_id, original_filename, ".pdf")
    return SchemaResult(image_data=jp2_bytes, ..., filename=filename)

else:  # "jpeg" or anything else → existing path unchanged
    compressed_data, _ = compress_to_size(...)
    ...
```

### 5.2 `SchemaResult` model — new `output_format` field

Current `SchemaResult` in `worker/models.py`:

```python
@dataclass(frozen=True)
class SchemaResult:
    image_data: bytes
    final_width: int
    final_height: int
    final_dpi: int
    final_size_kb: float
    filename: str
```

**New field:** `output_format: str = "jpeg"` — populated by the actual format used (e.g., `"jpeg"`, `"jpeg2000"`, `"pdf_mrc"`). This appears in the worker's JSON output metrics so the caller can know what format was actually stored.

---

## 6. Changes to `worker/models.py`

### 6.1 `MasterConstraints` full updated definition

```python
@dataclass(frozen=True)
class MasterConstraints:
    max_kb: int = 2000
    target_dpi: int = 300
    output_format: str = "jpeg"          # "jpeg" | "jpeg2000" | "pdf_mrc"
    quality: int = 92                    # JPEG quality (only used for output_format="jpeg")
    filename_pattern: str = "{job_id}_master"
    min_kb: int = 0

    # JPEG 2000 parameters (output_format="jpeg2000" or fallback in "pdf_mrc")
    jpeg2000_ratio: float = 10.0         # OpenJPEG quality_layers target ratio

    # MRC parameters (output_format="pdf_mrc")
    bg_downsample: int = 3               # Background layer downsample factor
    jbig2_lossless: bool = True          # Always True unless explicitly overridden
    jbig2_threshold: float = 0.85        # Symbol matching threshold (lossy only)
    embed_text_layer: bool = True        # Embed Document AI text as invisible PDF text
```

### 6.2 `from_dict` updates

Every new field must be added to `from_dict` with its default as the fallback, so existing callers that don't pass the new fields continue to work.

---

## 7. Changes to `worker/requirements.txt`

### New Python dependency

```
# PDF assembly for MRC masters (pikepdf ≥ 8.0.0)
# MIT license. Wraps QPDF for low-level PDF construction.
# Required for JPEG2000-in-PDF (Phase 1) and JBIG2-in-PDF (Phase 2) masters.
pikepdf>=8.0.0,<10.0.0
```

**pikepdf install size:** ~30 MB in the Docker image (QPDF shared library + Python wrapper).  
**Alternative if this is rejected:** Implement raw PDF byte construction (see Appendix A).

---

## 8. Changes to `worker/Dockerfile.production`

### Phase 1 (JPEG 2000 only)

**No Dockerfile changes required.** JPEG 2000 support is bundled in the PyPI Pillow wheels. `pikepdf` also includes its QPDF lib in its PyPI wheel. Both install via `pip` with no apt changes.

Verify Pillow JP2 support at build time by adding to the builder stage:

```dockerfile
RUN python -c "from PIL import features; assert features.check_codec('jpg_2000'), 'Pillow JPEG2000 not available'"
```

### Phase 2 (JBIG2 — full MRC)

The `jbig2enc` tool must be compiled from source. It depends on `libleptonica`.

**Addition to the base stage (`FROM base`):**

```dockerfile
# JBIG2 compression support for MRC masters
RUN apt-get update && apt-get install -y --no-install-recommends \
    libleptonica-dev \
    && rm -rf /var/lib/apt/lists/*
```

**New build stage between `base` and `builder` (or inside builder):**

```dockerfile
# jbig2enc — JBIG2 encoder for MRC document compression
# Apache 2.0 license. Compiled from source (no apt package available).
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    autoconf \
    automake \
    libtool \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --depth 1 https://github.com/agl/jbig2enc.git /tmp/jbig2enc \
    && cd /tmp/jbig2enc \
    && ./autogen.sh \
    && ./configure \
    && make -j$(nproc) \
    && make install \
    && rm -rf /tmp/jbig2enc
```

**Addition to runtime stage** (`FROM base AS runtime`) — the compiled binary and the leptonica runtime lib need to be present:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libleptonica7 \
    && rm -rf /var/lib/apt/lists/*
```

And copy the jbig2 binary from builder:

```dockerfile
COPY --from=builder /usr/local/bin/jbig2 /usr/local/bin/jbig2
COPY --from=builder /usr/local/lib/libjbig2enc* /usr/local/lib/
```

**OpenJPEG runtime apt package** (already satisfies what Pillow wraps internally, but needed for the `opj_compress`/`opj_decompress` CLI if we ever use them directly):

```dockerfile
# Already present in base via Pillow wheel. No additional apt package needed for JP2 via Pillow.
# Optionally add for CLI tools: libopenjp2-tools
```

**Decision point for review:** The `git clone` during Docker build introduces a network dependency and pins to HEAD of the jbig2enc repo, which could break if the repo changes. Options:

**Option A:** Clone at HEAD (current proposal) — always gets security patches, but build could fail on network error.  
**Option B:** Pin to a specific commit hash:  
```dockerfile
RUN git clone https://github.com/agl/jbig2enc.git /tmp/jbig2enc \
    && cd /tmp/jbig2enc && git checkout <commit_hash>
```
**Recommendation:** Option B with the last known-good commit. This is what production Docker images should do.

**Option C:** Build a `jbig2enc` apt package, host it on a private apt repo, install from there. Over-engineering for now.

---

## 9. Changes to `worker/worker.py`

Minimal. Only the call site for `adapt_master_document` changes to pass `ocr_result`:

```python
# Current (~ line 222):
if payload.mode == "master":
    schema_result = adapt_master_document(
        data=final_image_data,
        constraints=payload.master_constraints,
        job_id=payload.job_id,
        user_id=payload.user_id,
        original_filename=payload.input.original_filename,
    )

# New:
if payload.mode == "master":
    schema_result = adapt_master_document(
        data=final_image_data,
        constraints=payload.master_constraints,
        job_id=payload.job_id,
        user_id=payload.user_id,
        original_filename=payload.input.original_filename,
        ocr_result=ocr_result if is_text_document else None,   # pass through
    )
```

`ocr_result` is already in scope at this point (line ~214 in the current file assigns it from `docai_extract_text`), but it is currently only used for `final_ocr_confidence`. No other worker.py logic changes.

---

## 10. Storage Client — MIME type for PDF masters

`worker/storage/spaces_client.py` uploads the master with `upload_master`. Currently the content type is assumed to be `image/jpeg`. When the master is a PDF, the content type must be `application/pdf`.

**Change:** `upload_master` needs a `content_type: str = "image/jpeg"` parameter. `adapt_master_document` determines the actual content type and passes it through `SchemaResult`. The worker extracts it for the upload call.

**Decision point for review:** Is `upload_master` in `spaces_client.py` setting an explicit content-type header in the S3/Spaces PUT request, or leaving it to the client default? Check the current implementation.

---

## 11. Error Codes

New `ErrorCode` values to add to `worker/errors.py`:

```python
MRC_FAILED = "MRC_FAILED"          # MRC layer decomposition or assembly failed
JBIG2_UNAVAILABLE = "JBIG2_UNAVAILABLE"  # jbig2enc not installed
```

These should be `retryable=False` (infrastructure configuration error, not transient).

---

## 12. Test Strategy

### Unit tests for `worker/processors/mrc.py`

All tests in `tests/worker/test_mrc.py`:

1. **`test_decompose_layers_text_document`** — Feed a synthetic test image (white background, black text drawn via PIL), verify `foreground_mask` captures text pixels with >90% recall and <5% false positive rate.

2. **`test_decompose_layers_blank_image`** — All-white image → empty foreground mask.

3. **`test_decompose_layers_all_text`** — All-black image → nearly-full foreground mask.

4. **`test_encode_background_jpeg2000_size`** — Encode a 3MP test image, verify output size is within 20% of `(input_bytes / target_ratio)`.

5. **`test_encode_as_jpeg2000_pdf_is_valid`** — Produce a PDF, open with `pikepdf`, verify it is a valid single-page PDF with a JP2-encoded image XObject.

6. **`test_encode_as_mrc_pdf_is_valid`** (Phase 2 only, skipped if jbig2enc unavailable) — Produce a full MRC PDF, verify with `pikepdf` that it has two image XObjects (FG=JBIG2, BG=JPEG2000).

7. **`test_fallback_to_jpeg2000_if_no_jbig2`** — Mock `_jbig2enc_available()` to return False, confirm output format is JPEG2000.

8. **`test_text_layer_coordinate_mapping`** — Build a `TextLayer` from a synthetic `DocumentAIResult`, verify PDF coordinates are within 1pt of expected.

9. **`test_adapt_master_document_pdf_mrc_roundtrip`** — Call `adapt_master_document` with `output_format="pdf_mrc"`, open resulting PDF, extract text layer, verify OCR text matches input.

### Integration test

`tests/test_e2e_pipeline.py` or a new `tests/test_master_pipeline.py` — run the full worker with a real test image (from `tests/fixtures/`) and `mode=master, output_format=pdf_mrc`, assert:
- Output is a valid PDF
- Output size < `max_kb`
- Output contains at least 1 page
- OCR of the output page (via Tesseract) recalls >85% of the expected text

---

## 13. Open Questions / Decisions Required

Below is a summary of the decision points raised above. Please review each and indicate preference before implementation begins.

| # | Decision | Options | Recommendation |
|---|---|---|---|
| 1 | Output format for Phase 1 (JPEG 2000) | `.jp2` standalone vs `.pdf` wrapper | PDF wrapper |
| 2 | Phase 1 PDF assembly library | `pikepdf` vs raw PDF byte template | `pikepdf` |
| 3 | Background reconstruction in `decompose_layers` | Hard-white fill vs median neighbourhood infill | Start with hard-white, add infill later |
| 4 | Text layer in Phase 2 | Pass `ocr_result` through to `adapt_master_document` vs skip | Pass through (Option A) |
| 5 | jbig2enc Docker build | HEAD clone vs pinned commit hash | Pinned commit hash |
| 6 | Storage content-type for PDF masters | Needs verification of `upload_master` current behaviour | Check `spaces_client.py` |
| 7 | Which phase to implement first | Phase 1 only (safe, no Dockerfile changes) vs Phase 1 + 2 together | Phase 1 first, Phase 2 in a follow-up PR |

---

## Appendix A — Raw PDF Template (pikepdf alternative)

If `pikepdf` is rejected, a minimal valid single-image JPEG2000 PDF can be constructed as follows. This is for reference — it is not the recommended path.

A valid PDF containing a single JPEG2000 image has this structure:

```
%PDF-1.6
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R
            /MediaBox [0 0 <width_pts> <height_pts>]
            /Contents 4 0 R
            /Resources << /XObject << /Img 5 0 R >> >> >> endobj
4 0 obj << /Length <content_stream_length> >>
stream
q <width_pts> 0 0 <height_pts> 0 0 cm /Img Do Q
endstream endobj
5 0 obj << /Type /XObject /Subtype /Image
            /Width <px_width> /Height <px_height>
            /ColorSpace /DeviceRGB
            /BitsPerComponent 8
            /Filter /JPXDecode
            /Length <jp2_length> >>
stream
<raw jp2 bytes>
endstream endobj
xref
...
```

The cross-reference table and trailer must have correct byte offsets. This is manageable but error-prone. Not recommended.

---

## Appendix B — MRC Compression Ratios: Expected Results on Indian Documents

Based on the Internet Archive's published benchmarks adapted for the Indian document corpus:

| Document type | Raw enhanced JPEG (Stage 3) | JPEG master (current) | JPEG2000 master (Phase 1) | MRC PDF master (Phase 2) |
|---|---|---|---|---|
| Mark sheet (A4, 300 DPI, colour) | 2–4 MB | 600 KB–1.2 MB | 200–400 KB | 100–250 KB |
| Certificate (A4, 300 DPI, colour) | 2–4 MB | 600 KB–1.2 MB | 180–350 KB | 90–200 KB |
| PAN card (small, 150 DPI) | 300–600 KB | 80–150 KB | 30–70 KB | 20–50 KB |
| Aadhaar (A5, 200 DPI, colour) | 800 KB–1.5 MB | 200–400 KB | 80–160 KB | 50–120 KB |
| Passport photo (sRGB, 400×600px) | 200–500 KB | 50–120 KB | 40–100 KB | 30–80 KB (no foreground benefit) |

These are estimates. Actual results depend on content density. The MRC benefit is largest for text-dense documents and smallest for photographs (the foreground layer is near-empty for a photo).

**Note on photographs in MRC mode:** When `document_type="photo"`, the foreground mask will be sparse (camera-captured photos have no binary text layer). In this case, MRC degrades gracefully: the foreground JBIG2 will be tiny (sparse mask), and the background JPEG2000 carries nearly the full image. Compression ratio will be lower than for a text document but still better than JPEG. This is correct behaviour — no special case needed.
