"""Unit tests for dataset_logger — GCS write for detection training data."""
import sys
import os
import json
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../worker"))


def _make_quad():
    return [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]


def test_log_detection_sample_writes_image_and_quad():
    """Happy path: writes image.jpg and quad.json to correct GCS paths."""
    from processors.dataset_logger import log_detection_sample

    mock_bucket = MagicMock()
    mock_image_blob = MagicMock()
    mock_meta_blob = MagicMock()
    mock_bucket.blob.side_effect = lambda path: (
        mock_image_blob if path.endswith("image.jpg") else mock_meta_blob
    )

    with patch("processors.dataset_logger.storage.Client") as mock_client_cls:
        mock_client_cls.return_value.bucket.return_value = mock_bucket
        log_detection_sample(
            image_bytes=b"fakejpeg",
            quad=_make_quad(),
            document_type="pan_card",
            job_id="job-123",
        )

    mock_image_blob.upload_from_string.assert_called_once_with(
        b"fakejpeg", content_type="image/jpeg"
    )
    meta_call_args = mock_meta_blob.upload_from_string.call_args
    written = json.loads(meta_call_args[0][0])
    assert written["job_id"] == "job-123"
    assert written["document_type"] == "pan_card"
    assert written["corners"] == _make_quad()
    assert "timestamp" in written


def test_log_detection_sample_uses_correct_bucket_and_path():
    """Writes to gs://rythmiq-one-dataset/detection/{job_id}/."""
    from processors.dataset_logger import log_detection_sample

    with patch("processors.dataset_logger.storage.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = MagicMock()

        log_detection_sample(
            image_bytes=b"x",
            quad=_make_quad(),
            document_type="aadhaar",
            job_id="job-abc",
        )

    mock_client.bucket.assert_called_once_with("rythmiq-one-dataset")
    paths = [c[0][0] for c in mock_bucket.blob.call_args_list]
    assert "detection/job-abc/image.jpg" in paths
    assert "detection/job-abc/quad.json" in paths


def test_log_detection_sample_never_raises():
    """GCS failure must not propagate — job processing must continue."""
    from processors.dataset_logger import log_detection_sample

    with patch("processors.dataset_logger.storage.Client", side_effect=Exception("GCS down")):
        # Must not raise
        log_detection_sample(
            image_bytes=b"x",
            quad=_make_quad(),
            document_type="document",
            job_id="job-fail",
        )
