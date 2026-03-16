"""
MRC (Mixed Raster Content) compression for master document creation.

Implements two output paths:
  Phase 1 — encode_as_jpeg2000_pdf : JPEG 2000 single-image PDF (pure Python, no native deps)
  Phase 2 — encode_as_mrc_pdf      : Full MRC PDF/A-3b with JBIG2 foreground + JP2 background
                                      + invisible searchable text layer from Document AI

Fallback chain (when native libs unavailable):
  pdf_mrc requested
    ├─ jbig2enc available?  YES → full MRC PDF
    │                       NO  ┐
    │                           ├─ OpenJPEG in Pillow? YES → JPEG 2000 single-image PDF
    │                           │                      NO  → raises WorkerError
    └─ Log which path was taken at INFO level

All functions are pure (no side effects, no global mutable state).
All native-dep checks are cached at module level after first call.
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Tuple

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image

if TYPE_CHECKING:
    from processors.document_ai import DocumentAIResult
    from models import MasterConstraints

from errors import ErrorCode, ProcessingStage, WorkerError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability detection (cached)
# ---------------------------------------------------------------------------

_jbig2enc_available_cache: Optional[bool] = None
_openjpeg_available_cache: Optional[bool] = None


def _jbig2enc_available() -> bool:
    """Return True if jbig2enc CLI ('jbig2' binary) is on PATH."""
    global _jbig2enc_available_cache
    if _jbig2enc_available_cache is None:
        _jbig2enc_available_cache = shutil.which("jbig2") is not None
        if _jbig2enc_available_cache:
            logger.info("jbig2enc: available")
        else:
            logger.info("jbig2enc: not found on PATH — MRC will fall back to JPEG2000")
    return _jbig2enc_available_cache


def _openjpeg_available() -> bool:
    """Return True if Pillow can encode JPEG 2000 images (OpenJPEG codec present)."""
    global _openjpeg_available_cache
    if _openjpeg_available_cache is None:
        try:
            buf = io.BytesIO()
            Image.new("RGB", (1, 1), color=(255, 255, 255)).save(buf, format="JPEG2000")
            _openjpeg_available_cache = True
            logger.info("OpenJPEG: available via Pillow")
        except Exception:
            _openjpeg_available_cache = False
            logger.warning("OpenJPEG: not available via Pillow")
    return _openjpeg_available_cache


# ---------------------------------------------------------------------------
# Layer decomposition
# ---------------------------------------------------------------------------

def decompose_layers(
    img: NDArray[np.uint8],
) -> Tuple[NDArray[np.uint8], NDArray[np.uint8]]:
    """
    Split a BGR document image into foreground (text/line art) and background layers.

    Uses Sauvola adaptive thresholding, which locally normalises contrast and
    handles documents with uneven lighting far better than global Otsu or
    fixed-window adaptive Gaussian methods.

    Returns:
        foreground_mask : uint8 H×W array, values 0 or 255.
                          255 = text/line art pixel.
        background      : uint8 BGR H×W×3 array.  Text pixels are replaced with
                          hard white to avoid haloing artefacts in the JPEG2000
                          background layer (fast; median infill can be added later).
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)

    # --- Sauvola adaptive thresholding ----------------------------------
    # T(x,y) = mean(x,y) * (1 + k * (std(x,y)/R - 1))
    # window_size=25, k=0.2, R=128
    window_size = 25
    k = 0.2
    R = 128.0

    # Compute local mean and local mean-of-squares via box filter
    # (integral-image based: O(N) regardless of window size)
    kernel = (window_size, window_size)
    mean = cv2.boxFilter(gray, ddepth=-1, ksize=kernel, normalize=True)
    mean_sq = cv2.boxFilter(gray * gray, ddepth=-1, ksize=kernel, normalize=True)

    # Clamp before sqrt to guard against floating-point negatives at borders
    variance = np.maximum(mean_sq - mean * mean, 0.0)
    std = np.sqrt(variance)

    threshold = mean * (1.0 + k * (std / R - 1.0))
    foreground_mask = np.where(gray < threshold, np.uint8(255), np.uint8(0))

    # Morphological closing: close sub-pixel gaps in character strokes
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    foreground_mask = cv2.morphologyEx(foreground_mask, cv2.MORPH_CLOSE, close_kernel)

    # --- Background reconstruction (hard-white fill) --------------------
    # Replace foreground pixels with white so the background layer compresses
    # cleanly.  Median-neighbourhood infill can replace this in a later phase.
    background = img.copy()
    background[foreground_mask == 255] = 255

    return foreground_mask, background


# ---------------------------------------------------------------------------
# JBIG2 foreground encoding  (Phase 2)
# ---------------------------------------------------------------------------

def encode_foreground_jbig2(
    mask: NDArray[np.uint8],
    lossless: bool = True,
    threshold: float = 0.85,
) -> Tuple[bytes, bytes]:
    """
    Encode binary foreground mask as JBIG2 using the jbig2enc CLI.

    Returns:
        (jbig2_globals, jbig2_page) — the two byte strings that must be embedded
        separately in the PDF XObject (/JBIG2Globals and the stream body).

    Raises:
        WorkerError: if jbig2enc CLI is not available or returns non-zero exit.
    """
    if not _jbig2enc_available():
        raise WorkerError(
            code=ErrorCode.JBIG2_UNAVAILABLE,
            stage=ProcessingStage.SCHEMA,
            message="jbig2enc CLI not found. Install jbig2enc to use MRC PDF output.",
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tiff_path = f"{tmpdir}/fg.tiff"
        # jbig2enc always writes output to files named "output.*" in the CWD,
        # regardless of the input filename.  Do NOT use the input prefix here.
        sym_path = f"{tmpdir}/output.sym"
        page_path = f"{tmpdir}/output.0001"

        # Convert uint8 mask to 1-bit TIFF (required by jbig2enc)
        pil_mask = Image.fromarray(mask).convert("1")
        pil_mask.save(tiff_path, format="TIFF")

        cmd = ["jbig2", "-s", "-p"]
        if not lossless:
            cmd += ["-t", str(threshold)]
        cmd += [tiff_path]

        result = subprocess.run(
            cmd,
            capture_output=True,
            cwd=tmpdir,
        )
        if result.returncode != 0:
            raise WorkerError(
                code=ErrorCode.MRC_FAILED,
                stage=ProcessingStage.SCHEMA,
                message=f"jbig2enc failed (exit {result.returncode}): {result.stderr.decode(errors='replace')}",
            )

        # jbig2enc -s -p writes:  output.sym  (global dictionary)  +  output.0001  (page data)
        # Verify expected output exists before reading
        if not os.path.exists(sym_path) or not os.path.exists(page_path):
            # List what was actually produced to aid debugging
            produced = os.listdir(tmpdir)
            raise WorkerError(
                code=ErrorCode.MRC_FAILED,
                stage=ProcessingStage.SCHEMA,
                message=f"jbig2enc succeeded (exit 0) but expected output files not found. "
                        f"Expected: output.sym, output.0001. Produced: {produced}",
            )

        with open(sym_path, "rb") as f:
            jbig2_globals = f.read()
        with open(page_path, "rb") as f:
            jbig2_page = f.read()

    logger.debug(
        "JBIG2 encoded: globals=%d B, page=%d B", len(jbig2_globals), len(jbig2_page)
    )
    return jbig2_globals, jbig2_page


# ---------------------------------------------------------------------------
# JPEG 2000 background encoding
# ---------------------------------------------------------------------------

def encode_background_jpeg2000(
    background: NDArray[np.uint8],
    downsample_factor: int = 3,
    target_ratio: float = 10.0,
) -> Tuple[bytes, int, int]:
    """
    Downsample and encode background layer as JPEG 2000.

    Uses cv2.INTER_AREA for downsampling (correct pixel averaging, avoids ringing).

    Returns:
        (jp2_bytes, encoded_width, encoded_height)
    """
    h, w = background.shape[:2]
    new_w = max(1, w // downsample_factor)
    new_h = max(1, h // downsample_factor)

    downsampled = cv2.resize(background, (new_w, new_h), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(downsampled, cv2.COLOR_BGR2RGB)

    buf = io.BytesIO()
    Image.fromarray(rgb).save(
        buf,
        format="JPEG2000",
        quality_mode="rates",
        quality_layers=[target_ratio],
    )
    jp2_bytes = buf.getvalue()
    logger.debug(
        "JPEG2000 background encoded: %dx%d → %dx%d = %d B",
        w, h, new_w, new_h, len(jp2_bytes),
    )
    return jp2_bytes, new_w, new_h


# ---------------------------------------------------------------------------
# Searchable text layer
# ---------------------------------------------------------------------------

@dataclass
class _TextRun:
    """One positioned invisible text run destined for the PDF content stream."""
    text: str
    x_pts: float       # PDF x coordinate (bottom-left origin, points)
    y_pts: float       # PDF y coordinate (bottom-left origin, points)
    font_size: float   # points


def build_text_layer(
    ocr_result: "DocumentAIResult",
    page_width_px: int,
    page_height_px: int,
    page_width_pts: float,
    page_height_pts: float,
) -> List[_TextRun]:
    """
    Convert Document AI OCR bounding boxes into positioned invisible text runs.

    Coordinate mapping:
        pdf_x = (pixel_x / page_width_px)  * page_width_pts
        pdf_y = page_height_pts - (pixel_y / page_height_px) * page_height_pts
        (PDF y-axis is bottom-up; Document AI y-axis is top-down)
    """
    runs: List[_TextRun] = []
    for box in ocr_result.boxes:
        if not box.text.strip():
            continue

        pdf_x = (box.x / page_width_px) * page_width_pts
        # PDF y origin is bottom-left; box.y is top-left of the text box
        pdf_y = page_height_pts - ((box.y + box.height) / page_height_px) * page_height_pts
        font_size = max(1.0, (box.height / page_height_px) * page_height_pts)

        runs.append(_TextRun(text=box.text, x_pts=pdf_x, y_pts=pdf_y, font_size=font_size))

    return runs


# ---------------------------------------------------------------------------
# PDF assembly helpers
# ---------------------------------------------------------------------------

def _pts_from_pixels(pixels: int, dpi: int) -> float:
    """Convert pixel dimension to PDF points (1/72 inch)."""
    return (pixels / dpi) * 72.0


def _assemble_jpeg2000_pdf(
    jp2_bytes: bytes,
    img_width: int,
    img_height: int,
    dpi: int,
    text_runs: Optional[List[_TextRun]] = None,
) -> bytes:
    """
    Assemble a single-image JPEG2000 PDF using pikepdf.

    The image is encoded as an Image XObject with /Filter /JPXDecode.
    If text_runs are provided they are embedded as invisible text (Tr 3).
    """
    import pikepdf

    page_w_pts = _pts_from_pixels(img_width, dpi)
    page_h_pts = _pts_from_pixels(img_height, dpi)

    pdf = pikepdf.Pdf.new()

    # Build Image XObject with JPXDecode filter
    xobj = pikepdf.Stream(pdf, jp2_bytes)
    xobj.stream_dict = pikepdf.Dictionary(
        Type=pikepdf.Name.XObject,
        Subtype=pikepdf.Name.Image,
        Width=img_width,
        Height=img_height,
        ColorSpace=pikepdf.Name.DeviceRGB,
        BitsPerComponent=8,
        Filter=pikepdf.Name.JPXDecode,
    )

    # Content stream: scale image to fill page, then draw text layer
    content_parts = [
        f"q {page_w_pts:.4f} 0 0 {page_h_pts:.4f} 0 0 cm /Img Do Q"
    ]
    if text_runs:
        content_parts.append(_build_text_content_stream(text_runs))
    content_stream = "\n".join(content_parts).encode()

    resources = pikepdf.Dictionary(
        XObject=pikepdf.Dictionary(Img=xobj),
    )
    if text_runs:
        resources.Font = pikepdf.Dictionary(
            Helv=pikepdf.Dictionary(
                Type=pikepdf.Name.Font,
                Subtype=pikepdf.Name.Type1,
                BaseFont=pikepdf.Name.Helvetica,
            )
        )

    page = pikepdf.Dictionary(
        Type=pikepdf.Name.Page,
        MediaBox=pikepdf.Array([0, 0, page_w_pts, page_h_pts]),
        Contents=pikepdf.Stream(pdf, content_stream),
        Resources=resources,
    )

    pdf.make_indirect(page)
    pdf.pages.append(pikepdf.Page(page))
    _set_pdfa_metadata(pdf)

    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def _assemble_mrc_pdf_layers(
    fg_globals: bytes,
    fg_page: bytes,
    fg_width: int,
    fg_height: int,
    bg_jp2: bytes,
    bg_width: int,
    bg_height: int,
    dpi: int,
    text_runs: Optional[List[_TextRun]] = None,
) -> bytes:
    """
    Assemble foreground (JBIG2) + background (JPEG2000) layers into a PDF/A-3b.

    The background XObject is drawn first (scaled to full page), then the
    foreground is composited on top (1:1 native resolution). This is why
    text remains pixel-perfect after rendering — it is stored and drawn at
    its original capture DPI.
    """
    import pikepdf

    page_w_pts = _pts_from_pixels(fg_width, dpi)
    page_h_pts = _pts_from_pixels(fg_height, dpi)

    pdf = pikepdf.Pdf.new()

    # Background image XObject (JPEG2000, downsampled dimensions)
    bg_xobj = pikepdf.Stream(pdf, bg_jp2)
    bg_xobj.stream_dict = pikepdf.Dictionary(
        Type=pikepdf.Name.XObject,
        Subtype=pikepdf.Name.Image,
        Width=bg_width,
        Height=bg_height,
        ColorSpace=pikepdf.Name.DeviceRGB,
        BitsPerComponent=8,
        Filter=pikepdf.Name.JPXDecode,
    )

    # Foreground image XObject (JBIG2, full resolution, 1-bit image mask).
    #
    # ImageMask=True makes white pixels (bit=1) transparent so the JPEG2000
    # background shows through.  Decode=[1, 0] inverts the sample mapping:
    # bit 1 (text pixels, as encoded by decompose_layers) → paint with current
    # fill colour; bit 0 (background pixels) → transparent.
    # Per PDF spec §8.9.6.1 ColorSpace must be omitted for image masks.
    jbig2_globals_stream = pikepdf.Stream(pdf, fg_globals)
    fg_xobj = pikepdf.Stream(pdf, fg_page)
    fg_xobj.stream_dict = pikepdf.Dictionary(
        Type=pikepdf.Name.XObject,
        Subtype=pikepdf.Name.Image,
        Width=fg_width,
        Height=fg_height,
        ImageMask=pikepdf.Boolean(True),
        BitsPerComponent=1,
        Decode=pikepdf.Array([1, 0]),
        Filter=pikepdf.Name.JBIG2Decode,
        DecodeParms=pikepdf.Dictionary(
            JBIG2Globals=jbig2_globals_stream,
        ),
    )

    # Content stream: background scaled to full page, then foreground stencil
    # painted in black on top.  "0 0 0 rg" sets the non-stroking fill colour
    # used by the image-mask paint operation.
    content_parts = [
        f"q {page_w_pts:.4f} 0 0 {page_h_pts:.4f} 0 0 cm /BG Do Q",
        "0 0 0 rg",
        f"q {page_w_pts:.4f} 0 0 {page_h_pts:.4f} 0 0 cm /FG Do Q",
    ]
    if text_runs:
        content_parts.append(_build_text_content_stream(text_runs))
    content_stream = "\n".join(content_parts).encode()

    resources = pikepdf.Dictionary(
        XObject=pikepdf.Dictionary(BG=bg_xobj, FG=fg_xobj),
    )
    if text_runs:
        resources.Font = pikepdf.Dictionary(
            Helv=pikepdf.Dictionary(
                Type=pikepdf.Name.Font,
                Subtype=pikepdf.Name.Type1,
                BaseFont=pikepdf.Name.Helvetica,
            )
        )

    page = pikepdf.Dictionary(
        Type=pikepdf.Name.Page,
        MediaBox=pikepdf.Array([0, 0, page_w_pts, page_h_pts]),
        Contents=pikepdf.Stream(pdf, content_stream),
        Resources=resources,
    )

    pdf.make_indirect(page)
    pdf.pages.append(pikepdf.Page(page))
    _set_pdfa_metadata(pdf)

    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def _build_text_content_stream(runs: List[_TextRun]) -> str:
    """
    Build a PDF content-stream fragment that draws invisible text.

    Tr 3 = invisible rendering mode (text not painted, participates in search).
    Each run is positioned with Td (relative move from current point) or Tm.
    """
    parts = ["BT", "/Helv 0 Tf", "3 Tr"]  # font size 0 — overridden per-run with Tf
    for run in runs:
        # Escape parentheses and backslashes in text
        safe = run.text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        parts.append(
            f"{run.x_pts:.3f} {run.y_pts:.3f} Td "
            f"/Helv {run.font_size:.3f} Tf "
            f"({safe}) Tj"
        )
        # Reset position to absolute origin for next run (Td is cumulative)
        parts.append(f"{-run.x_pts:.3f} {-run.y_pts:.3f} Td")
    parts.append("ET")
    return "\n".join(parts)


def _set_pdfa_metadata(pdf: "pikepdf.Pdf") -> None:
    """Add minimal PDF/A-3b conformance metadata to a pikepdf document."""
    import pikepdf

    with pdf.open_metadata() as meta:
        meta["pdfaid:part"] = "3"
        meta["pdfaid:conformance"] = "B"
        meta["dc:format"] = "application/pdf"

    pdf.Root.Lang = pikepdf.String("en")


# ---------------------------------------------------------------------------
# Phase 1 public entry point — JPEG 2000 PDF
# ---------------------------------------------------------------------------

def encode_as_jpeg2000_pdf(
    img: NDArray[np.uint8],
    dpi: int,
    target_ratio: float = 10.0,
    ocr_result: Optional["DocumentAIResult"] = None,
) -> bytes:
    """
    Encode an image as a JPEG2000-in-PDF (Phase 1 path, no native deps).

    Pillow's OpenJPEG binding handles the compression. pikepdf assembles the PDF
    so that DPI metadata is carried in the page dimensions and a text layer can
    optionally be embedded.

    Args:
        img          : BGR image array (Stage 3 enhanced output)
        dpi          : DPI to encode in the PDF page size
        target_ratio : JPEG 2000 compression ratio (10.0 = 10:1)
        ocr_result   : Optional Document AI result for searchable text layer

    Returns:
        PDF bytes
    """
    if not _openjpeg_available():
        raise WorkerError(
            code=ErrorCode.MRC_FAILED,
            stage=ProcessingStage.SCHEMA,
            message="Pillow JPEG2000 codec (OpenJPEG) not available.",
        )

    h, w = img.shape[:2]
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    buf = io.BytesIO()
    Image.fromarray(rgb).save(
        buf,
        format="JPEG2000",
        quality_mode="rates",
        quality_layers=[target_ratio],
    )
    jp2_bytes = buf.getvalue()
    logger.info(
        "JPEG2000 encoded: %dx%d, ratio=%.1f, size=%d B", w, h, target_ratio, len(jp2_bytes)
    )

    text_runs: Optional[List[_TextRun]] = None
    if ocr_result is not None:
        page_w_pts = _pts_from_pixels(w, dpi)
        page_h_pts = _pts_from_pixels(h, dpi)
        text_runs = build_text_layer(ocr_result, w, h, page_w_pts, page_h_pts)

    return _assemble_jpeg2000_pdf(jp2_bytes, w, h, dpi, text_runs)


# ---------------------------------------------------------------------------
# Phase 2 public entry point — Full MRC PDF
# ---------------------------------------------------------------------------

def encode_as_mrc_pdf(
    img: NDArray[np.uint8],
    dpi: int,
    constraints: "MasterConstraints",
    ocr_result: Optional["DocumentAIResult"] = None,
) -> bytes:
    """
    Main entry point for MRC PDF encoding.

    Dispatches:
      jbig2enc + OpenJPEG available → full MRC PDF/A-3b
      only OpenJPEG available       → JPEG2000-in-PDF (Phase 1 fallback)
      neither available             → raises WorkerError

    If the result exceeds constraints.max_kb, increases bg_downsample by 1
    (up to a maximum of 6) and retries background encoding only.

    Args:
        img         : BGR image array (Stage 3 enhanced output)
        dpi         : DPI to embed in the master PDF
        constraints : MasterConstraints controlling compression parameters
        ocr_result  : Optional Document AI result for text layer embedding

    Returns:
        PDF bytes
    """
    h, w = img.shape[:2]
    page_w_pts = _pts_from_pixels(w, dpi)
    page_h_pts = _pts_from_pixels(h, dpi)

    text_runs: Optional[List[_TextRun]] = None
    if ocr_result is not None and constraints.embed_text_layer:
        text_runs = build_text_layer(ocr_result, w, h, page_w_pts, page_h_pts)

    # ---- Phase 1 fallback when jbig2enc is absent ----------------------
    if not _jbig2enc_available():
        logger.warning(
            "jbig2enc unavailable — falling back to JPEG2000-in-PDF (Phase 1)"
        )
        if not _openjpeg_available():
            raise WorkerError(
                code=ErrorCode.MRC_FAILED,
                stage=ProcessingStage.SCHEMA,
                message=(
                    "Neither jbig2enc nor Pillow JPEG2000 codec are available. "
                    "Cannot produce PDF master."
                ),
            )
        return encode_as_jpeg2000_pdf(img, dpi, constraints.jpeg2000_ratio, ocr_result)

    # ---- Full MRC path -------------------------------------------------
    foreground_mask, background = decompose_layers(img)

    try:
        fg_globals, fg_page = encode_foreground_jbig2(
            foreground_mask,
            lossless=constraints.jbig2_lossless,
            threshold=constraints.jbig2_threshold,
        )
    except WorkerError as exc:
        logger.warning("JBIG2 encoding failed (%s) — falling back to JPEG2000-in-PDF", exc)
        return encode_as_jpeg2000_pdf(img, dpi, constraints.jpeg2000_ratio, ocr_result)

    max_bg_downsample = 6
    bg_downsample = constraints.bg_downsample

    while True:
        bg_jp2, bg_w, bg_h = encode_background_jpeg2000(
            background,
            downsample_factor=bg_downsample,
            target_ratio=constraints.jpeg2000_ratio,
        )

        pdf_bytes = _assemble_mrc_pdf_layers(
            fg_globals=fg_globals,
            fg_page=fg_page,
            fg_width=w,
            fg_height=h,
            bg_jp2=bg_jp2,
            bg_width=bg_w,
            bg_height=bg_h,
            dpi=dpi,
            text_runs=text_runs,
        )

        size_kb = len(pdf_bytes) / 1024
        if size_kb <= constraints.max_kb:
            logger.info(
                "MRC PDF assembled: %dx%d, bg_ds=%d, size=%.1f KB",
                w, h, bg_downsample, size_kb,
            )
            return pdf_bytes

        if bg_downsample >= max_bg_downsample:
            raise WorkerError(
                code=ErrorCode.SIZE_EXCEEDED,
                stage=ProcessingStage.SCHEMA,
                message=(
                    f"MRC PDF size {size_kb:.1f} KB exceeds max {constraints.max_kb} KB "
                    f"even at max background downsample ({max_bg_downsample}x)."
                ),
            )

        bg_downsample += 1
        logger.info(
            "MRC PDF %.1f KB exceeds max %d KB — retrying with bg_downsample=%d",
            size_kb, constraints.max_kb, bg_downsample,
        )
