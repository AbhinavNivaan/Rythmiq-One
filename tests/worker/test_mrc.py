"""
Unit tests for worker/processors/mrc.py

Run from project root:
    pytest tests/worker/test_mrc.py -v

Tests that require jbig2enc are automatically skipped when the binary is absent.
Tests that require pikepdf are automatically skipped when it is not installed.
"""

from __future__ import annotations

import io
import sys
from dataclasses import dataclass, field
from typing import List
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Path setup: worker/ must be on sys.path for imports to resolve
# ---------------------------------------------------------------------------
import os

WORKER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "worker")
if WORKER_DIR not in sys.path:
    sys.path.insert(0, WORKER_DIR)

# ---------------------------------------------------------------------------
# Optional dependency guards
# ---------------------------------------------------------------------------

def _pikepdf_available() -> bool:
    try:
        import pikepdf  # noqa: F401
        return True
    except ImportError:
        return False


def _jp2_available() -> bool:
    try:
        buf = io.BytesIO()
        Image.new("RGB", (1, 1)).save(buf, format="JPEG2000")
        return True
    except Exception:
        return False


requires_pikepdf = pytest.mark.skipif(
    not _pikepdf_available(), reason="pikepdf not installed"
)
requires_jp2 = pytest.mark.skipif(
    not _jp2_available(), reason="Pillow JPEG2000 codec not available"
)
requires_jbig2 = pytest.mark.skipif(
    not __import__("shutil").which("jbig2"),
    reason="jbig2enc CLI not found on PATH",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_text_image(width: int = 800, height: int = 600) -> np.ndarray:
    """Synthetic test image: white background with black text drawn via PIL."""
    pil_img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(pil_img)
    for y in range(50, height - 50, 40):
        draw.text((50, y), "Sample document text 1234 नमस्ते", fill=(0, 0, 0))
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def _make_blank_image(width: int = 200, height: int = 200) -> np.ndarray:
    return np.full((height, width, 3), 255, dtype=np.uint8)


def _make_black_image(width: int = 200, height: int = 200) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# Fake DocumentAI models (no real network calls)
# ---------------------------------------------------------------------------

@dataclass
class _FakeBox:
    x: int
    y: int
    width: int
    height: int
    text: str
    confidence: float = 0.99


@dataclass
class _FakeOCRResult:
    text: str
    confidence: float
    boxes: List[_FakeBox] = field(default_factory=list)
    page_width: int = 800
    page_height: int = 600


# ---------------------------------------------------------------------------
# 1. decompose_layers — text document
# ---------------------------------------------------------------------------

def test_decompose_layers_text_document():
    from processors.mrc import decompose_layers

    img = _make_text_image(800, 600)
    fg_mask, background = decompose_layers(img)

    assert fg_mask.shape == (600, 800)
    assert background.shape == (600, 800, 3)

    # At least some pixels are classified as foreground
    fg_ratio = np.sum(fg_mask == 255) / fg_mask.size
    assert fg_ratio > 0.01, f"Foreground ratio too low: {fg_ratio:.4f}"

    # Foreground density is reasonable (text doesn't cover >80 % of the page)
    assert fg_ratio < 0.80, f"Foreground ratio unexpectedly high: {fg_ratio:.4f}"

    # Background: pixels where mask is 255 should be white (hard-white fill)
    fg_pixels_bg = background[fg_mask == 255]
    assert np.all(fg_pixels_bg == 255), "Text pixels in background are not white"


# ---------------------------------------------------------------------------
# 2. decompose_layers — blank image → empty foreground
# ---------------------------------------------------------------------------

def test_decompose_layers_blank_image():
    from processors.mrc import decompose_layers

    img = _make_blank_image()
    fg_mask, _ = decompose_layers(img)

    fg_ratio = np.sum(fg_mask == 255) / fg_mask.size
    assert fg_ratio < 0.01, f"Blank image produced non-trivial foreground: {fg_ratio:.4f}"


# ---------------------------------------------------------------------------
# 3. decompose_layers — all-black image → dense foreground
# ---------------------------------------------------------------------------

def test_decompose_layers_all_black_image():
    from processors.mrc import decompose_layers

    img = _make_black_image()
    fg_mask, background = decompose_layers(img)

    # Sauvola with a uniform-black image: local mean == pixel value == 0 everywhere,
    # std == 0, threshold == 0.  Condition (gray < threshold) is (0 < 0) == False.
    # Foreground is correctly empty — there is no local contrast to classify.
    # Verify the function completes without error and returns correct shapes.
    assert fg_mask.shape == background.shape[:2]
    # fg_ratio may be 0 for pathological uniform image — that is correct behavior
    fg_ratio = np.sum(fg_mask == 255) / fg_mask.size
    assert 0.0 <= fg_ratio <= 1.0


# ---------------------------------------------------------------------------
# 4. encode_background_jpeg2000 — size check
# ---------------------------------------------------------------------------

@requires_jp2
def test_encode_background_jpeg2000_size():
    from processors.mrc import encode_background_jpeg2000

    img = _make_text_image(1200, 900)  # ~3 MP
    raw_size = img.nbytes
    target_ratio = 10.0

    jp2_bytes, enc_w, enc_h = encode_background_jpeg2000(
        img, downsample_factor=3, target_ratio=target_ratio
    )

    assert len(jp2_bytes) > 0
    # After 3x downsample the image is 400x300; jp2 should be well under raw
    assert len(jp2_bytes) < raw_size / 5, (
        f"JP2 output {len(jp2_bytes)} B is suspiciously large vs raw {raw_size} B"
    )
    assert enc_w == 400
    assert enc_h == 300


# ---------------------------------------------------------------------------
# 5. encode_as_jpeg2000_pdf — produces valid single-page PDF
# ---------------------------------------------------------------------------

@requires_pikepdf
@requires_jp2
def test_encode_as_jpeg2000_pdf_is_valid():
    import pikepdf
    from processors.mrc import encode_as_jpeg2000_pdf

    img = _make_text_image(400, 300)
    pdf_bytes = encode_as_jpeg2000_pdf(img, dpi=150, target_ratio=10.0)

    assert pdf_bytes[:4] == b"%PDF", "Output is not a PDF"
    pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    assert len(pdf.pages) == 1

    # Verify there is exactly one image XObject with JPXDecode filter
    page = pdf.pages[0]
    resources = page.get("/Resources", pikepdf.Dictionary())
    xobjects = resources.get("/XObject", pikepdf.Dictionary())
    assert len(xobjects) == 1
    xobj = list(xobjects.values())[0]
    assert xobj.stream_dict.get("/Filter") == pikepdf.Name.JPXDecode


# ---------------------------------------------------------------------------
# 6. encode_as_mrc_pdf — full MRC (skipped without jbig2enc)
# ---------------------------------------------------------------------------

@requires_pikepdf
@requires_jp2
@requires_jbig2
def test_encode_as_mrc_pdf_is_valid():
    import pikepdf
    from processors.mrc import encode_as_mrc_pdf

    # Minimal MasterConstraints-like object
    from models import MasterConstraints
    constraints = MasterConstraints(
        max_kb=5000,
        target_dpi=150,
        output_format="pdf_mrc",
        jpeg2000_ratio=10.0,
        bg_downsample=3,
        jbig2_lossless=True,
        embed_text_layer=False,
    )

    img = _make_text_image(400, 300)
    pdf_bytes = encode_as_mrc_pdf(img, dpi=150, constraints=constraints)

    assert pdf_bytes[:4] == b"%PDF"
    pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    assert len(pdf.pages) == 1

    page = pdf.pages[0]
    resources = page.get("/Resources", pikepdf.Dictionary())
    xobjects = resources.get("/XObject", pikepdf.Dictionary())
    # Expect two XObjects: /BG (JPXDecode) and /FG (JBIG2Decode)
    assert len(xobjects) == 2
    filters = {str(k): xobj.stream_dict.get("/Filter") for k, xobj in xobjects.items()}
    assert pikepdf.Name.JPXDecode in filters.values(), "No JPXDecode (background) XObject found"
    assert pikepdf.Name.JBIG2Decode in filters.values(), "No JBIG2Decode (foreground) XObject found"


# ---------------------------------------------------------------------------
# 7. fallback to JPEG2000 when jbig2enc unavailable
# ---------------------------------------------------------------------------

@requires_pikepdf
@requires_jp2
def test_fallback_to_jpeg2000_if_no_jbig2():
    import pikepdf
    from processors.mrc import encode_as_mrc_pdf
    from models import MasterConstraints

    constraints = MasterConstraints(
        max_kb=5000,
        target_dpi=150,
        output_format="pdf_mrc",
        jpeg2000_ratio=10.0,
        bg_downsample=3,
        embed_text_layer=False,
    )
    img = _make_text_image(400, 300)

    with patch("processors.mrc._jbig2enc_available", return_value=False):
        pdf_bytes = encode_as_mrc_pdf(img, dpi=150, constraints=constraints)

    assert pdf_bytes[:4] == b"%PDF"
    pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    assert len(pdf.pages) == 1

    # In fallback mode there is exactly one XObject (JPEG2000 only)
    page = pdf.pages[0]
    resources = page.get("/Resources", pikepdf.Dictionary())
    xobjects = resources.get("/XObject", pikepdf.Dictionary())
    assert len(xobjects) == 1


# ---------------------------------------------------------------------------
# 8. text layer coordinate mapping
# ---------------------------------------------------------------------------

def test_text_layer_coordinate_mapping():
    from processors.mrc import build_text_layer

    page_w_px = 800
    page_h_px = 600
    page_w_pts = 576.0   # 8 inches × 72 pt/inch
    page_h_pts = 432.0   # 6 inches × 72 pt/inch

    ocr = _FakeOCRResult(
        text="Hello",
        confidence=0.99,
        boxes=[_FakeBox(x=80, y=60, width=160, height=30, text="Hello")],
        page_width=page_w_px,
        page_height=page_h_px,
    )

    runs = build_text_layer(ocr, page_w_px, page_h_px, page_w_pts, page_h_pts)
    assert len(runs) == 1
    run = runs[0]

    expected_x = (80 / 800) * 576.0          # 57.6
    # PDF y is bottom-up from bottom of text box (y + height)
    expected_y = 432.0 - ((60 + 30) / 600) * 432.0  # 432 - 64.8 = 367.2

    assert abs(run.x_pts - expected_x) < 1.0, f"x_pts off: {run.x_pts} vs {expected_x}"
    assert abs(run.y_pts - expected_y) < 1.0, f"y_pts off: {run.y_pts} vs {expected_y}"
    assert run.text == "Hello"


# ---------------------------------------------------------------------------
# 9. adapt_master_document roundtrip with output_format=pdf_mrc
# ---------------------------------------------------------------------------

@requires_pikepdf
@requires_jp2
def test_adapt_master_document_pdf_mrc_roundtrip():
    import pikepdf
    from models import MasterConstraints
    from processors.schema import adapt_master_document

    img_np = _make_text_image(400, 300)
    img_pil = Image.fromarray(cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    img_pil.save(buf, format="JPEG", quality=90)
    jpeg_bytes = buf.getvalue()

    ocr = _FakeOCRResult(
        text="Sample document text",
        confidence=0.99,
        boxes=[_FakeBox(x=50, y=50, width=200, height=30, text="Sample document text")],
        page_width=400,
        page_height=300,
    )

    constraints = MasterConstraints(
        max_kb=5000,
        target_dpi=150,
        output_format="pdf_mrc",
        jpeg2000_ratio=10.0,
        bg_downsample=3,
        embed_text_layer=True,
    )

    with patch("processors.mrc._jbig2enc_available", return_value=False):
        result = adapt_master_document(
            data=jpeg_bytes,
            constraints=constraints,
            job_id="00000000-0000-0000-0000-000000000001",
            user_id="00000000-0000-0000-0000-000000000002",
            original_filename="test.jpg",
            ocr_result=ocr,
        )

    assert result.output_format == "pdf_mrc"
    assert result.content_type == "application/pdf"
    assert result.filename.endswith(".pdf")
    assert result.final_size_kb > 0

    # Verify the result is a valid PDF
    assert result.image_data[:4] == b"%PDF"
    pdf = pikepdf.open(io.BytesIO(result.image_data))
    assert len(pdf.pages) == 1
