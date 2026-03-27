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
