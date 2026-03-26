"""Tests for confirmed_crop_quad threading through JobPayload and EnhancementOptions."""
import json
import pytest


def _base_payload() -> dict:
    return {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "user_id": "550e8400-e29b-41d4-a716-446655440001",
        "mode": "master",
        "document_type": "document",
        "input": {
            "raw_path": "uploads/test.jpg",
            "artifact_url": None,
            "mime_type": "image/jpeg",
            "original_filename": "test.jpg",
        },
        "storage": {
            "bucket": "test-bucket",
            "region": "sgp1",
            "endpoint": "https://example.com",
        },
        "master_constraints": {
            "max_kb": 2000,
            "target_dpi": 300,
            "output_format": "jpeg",
            "quality": 85,
            "filename_pattern": "{job_id}_master",
        },
    }


def test_jobpayload_parses_confirmed_crop_quad():
    """JobPayload.from_dict() should parse confirmed_crop_quad from JSON."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../worker'))
    from models import JobPayload

    payload = _base_payload()
    payload["confirmed_crop_quad"] = [
        [0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]
    ]
    job = JobPayload.from_dict(payload)

    assert job.confirmed_crop_quad is not None
    assert len(job.confirmed_crop_quad) == 4
    assert job.confirmed_crop_quad[0] == (0.1, 0.1)
    assert job.confirmed_crop_quad[3] == (0.1, 0.9)


def test_jobpayload_confirmed_crop_quad_defaults_to_none():
    """JobPayload.from_dict() should default confirmed_crop_quad to None when absent."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../worker'))
    from models import JobPayload

    job = JobPayload.from_dict(_base_payload())
    assert job.confirmed_crop_quad is None


def test_enhancement_options_accepts_confirmed_crop_quad():
    """EnhancementOptions should accept confirmed_crop_quad without error."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../worker'))
    from processors.enhancement import EnhancementOptions

    quad = ((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9))
    opts = EnhancementOptions(confirmed_crop_quad=quad)
    assert opts.confirmed_crop_quad == quad


def test_enhancement_options_confirmed_crop_quad_defaults_to_none():
    """EnhancementOptions.confirmed_crop_quad should default to None."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../worker'))
    from processors.enhancement import EnhancementOptions

    opts = EnhancementOptions()
    assert opts.confirmed_crop_quad is None


def test_detect_and_crop_document_uses_confirmed_quad():
    """When confirmed_crop_quad is provided, detect_and_crop_document uses it and skips cascade."""
    import sys, os, numpy as np
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../worker'))
    from unittest.mock import patch, MagicMock
    from processors.enhancement import detect_and_crop_document

    # 100x100 white image
    img = np.ones((100, 100, 3), dtype=np.uint8) * 255

    # Quad covering 20%–80% of image (normalised)
    quad = ((0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8))

    with patch('processors.enhancement._perspective_crop') as mock_warp:
        mock_warp.return_value = np.ones((60, 60, 3), dtype=np.uint8) * 200
        result, was_processed = detect_and_crop_document(img, confirmed_crop_quad=quad)

    # _perspective_crop must have been called exactly once
    assert mock_warp.call_count == 1
    assert was_processed is True
    # Verify the pixel coordinates passed to _perspective_crop are correct
    call_args = mock_warp.call_args[0]
    corners_passed = call_args[1]  # second positional arg
    # TL pixel should be approximately (20, 20)
    tl = corners_passed[0]
    assert abs(tl[0] - 20.0) < 1.0
    assert abs(tl[1] - 20.0) < 1.0


def test_detect_and_crop_document_skips_quad_when_none():
    """When confirmed_crop_quad is None, the normal cascade still runs."""
    import sys, os, numpy as np
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../worker'))
    from unittest.mock import patch
    from processors.enhancement import detect_and_crop_document

    img = np.ones((100, 100, 3), dtype=np.uint8) * 255

    # If cascade runs, _find_quad_contour will be called (even if it returns None)
    with patch('processors.enhancement._find_quad_contour', return_value=None) as mock_contour:
        detect_and_crop_document(img, confirmed_crop_quad=None)

    assert mock_contour.call_count > 0
