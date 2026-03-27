"""
Integration tests for /detect endpoint.

Tests Stage 1 best-match selection and Stage 2 blob fallback by
posting real images to the endpoint via TestClient, patching at the
processors.enhancement module boundary.
"""
import sys
import os
import base64
import numpy as np
import cv2
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../worker"))


def _img_to_b64(img: np.ndarray) -> str:
    _, buf = cv2.imencode(".jpg", img)
    return base64.b64encode(buf.tobytes()).decode()


def _make_img(h, w, bg, rect=None, rect_color=240):
    img = np.full((h, w, 3), bg, dtype=np.uint8)
    if rect is not None:
        y1, y2, x1, x2 = rect
        img[y1:y2, x1:x2] = rect_color
    return img


@pytest.fixture
def client():
    from server import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Stage 1: best-match — largest quad wins, not first
# ---------------------------------------------------------------------------

def test_detect_stage1_returns_largest_quad_not_first(client):
    """
    Stage 1 loops all edge maps and picks the LARGEST quad.
    Verify by mocking _find_quad_contour to return small-then-large,
    and asserting the response quad matches the large one.
    """
    img = _make_img(400, 600, bg=40, rect=(80, 320, 100, 500), rect_color=240)
    h, w = 400, 600

    small_corners = np.array([[100,80],[200,80],[200,130],[100,130]], dtype=np.float32)
    large_corners = np.array([[100,80],[500,80],[500,320],[100,320]], dtype=np.float32)

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
        resp = client.post("/detect", json={"image_b64": _img_to_b64(img)})

    assert resp.status_code == 200
    data = resp.json()
    assert data["quad"] is not None
    assert len(data["quad"]) == 4
    # The quad should be normalized large_corners — check it covers most of the rect
    xs = [pt[0] for pt in data["quad"]]
    ys = [pt[1] for pt in data["quad"]]
    # large_corners spans x=[100,500], y=[80,320] — normalized: x in ~[0.17,0.83], y in ~[0.20,0.80]
    assert min(xs) == pytest.approx(100/w, abs=0.05), f"Left edge wrong: {min(xs)}"
    assert max(xs) == pytest.approx(500/w, abs=0.05), f"Right edge wrong: {max(xs)}"


# ---------------------------------------------------------------------------
# Stage 2 fallback
# ---------------------------------------------------------------------------

def test_detect_stage2_fires_when_stage1_returns_nothing(client):
    """
    When Stage 1 finds no quad, Stage 2 (_find_blob_corners) fires.
    Force Stage 1 to return None; expect a valid quad from Stage 2.
    Spy on _find_blob_corners to explicitly assert Stage 2 was called.
    """
    img = _make_img(400, 600, bg=40, rect=(80, 320, 100, 500), rect_color=240)

    from processors.enhancement import _find_blob_corners as _find_blob_corners_real

    with patch("processors.enhancement._find_quad_contour", return_value=None), \
         patch("processors.enhancement._find_blob_corners", wraps=_find_blob_corners_real) as mock_stage2:
        resp = client.post("/detect", json={"image_b64": _img_to_b64(img)})

    assert mock_stage2.call_count == 1, "Stage 2 _find_blob_corners should have been called"
    assert resp.status_code == 200
    data = resp.json()
    assert data["quad"] is not None
    assert len(data["quad"]) == 4
    for pt in data["quad"]:
        assert 0.0 <= pt[0] <= 1.0
        assert 0.0 <= pt[1] <= 1.0


def test_detect_returns_null_when_both_stages_fail(client):
    """
    All-black image: Stage 1 forced to None, Stage 2 finds nothing.
    Endpoint must return quad=null.
    """
    img = np.zeros((400, 600, 3), dtype=np.uint8)

    with patch("processors.enhancement._find_quad_contour", return_value=None):
        resp = client.post("/detect", json={"image_b64": _img_to_b64(img)})

    assert resp.status_code == 200
    data = resp.json()
    assert data["quad"] is None
