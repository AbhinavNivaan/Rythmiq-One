# tests/api/test_feedback_gcs.py
from unittest.mock import MagicMock, patch
import json

from app.api.services.feedback_gcs import archive_raw_upload, write_metadata, generate_signed_url


def _mock_client(bucket_mock):
    client = MagicMock()
    client.bucket.return_value = bucket_mock
    return client


def test_archive_raw_upload_uploads_jpeg():
    bucket = MagicMock()
    blob = MagicMock()
    bucket.blob.return_value = blob

    with patch("app.api.services.feedback_gcs._get_client", return_value=_mock_client(bucket)):
        result = archive_raw_upload(b"fakejpeg", "job-123", "test-bucket")

    bucket.blob.assert_called_once_with("job-123/raw.jpg")
    blob.upload_from_string.assert_called_once_with(b"fakejpeg", content_type="image/jpeg")
    assert result == "gs://test-bucket/job-123/raw.jpg"


def test_write_metadata_uploads_json():
    bucket = MagicMock()
    blob = MagicMock()
    bucket.blob.return_value = blob
    meta = {"quality_score": 0.61, "quad_source": "model"}

    with patch("app.api.services.feedback_gcs._get_client", return_value=_mock_client(bucket)):
        write_metadata("job-123", meta, "test-bucket")

    bucket.blob.assert_called_once_with("job-123/metadata.json")
    uploaded_content = blob.upload_from_string.call_args[0][0]
    assert json.loads(uploaded_content)["quality_score"] == 0.61


def test_generate_signed_url_calls_gcs():
    bucket = MagicMock()
    blob = MagicMock()
    blob.generate_signed_url.return_value = "https://signed.url/raw.jpg"
    bucket.blob.return_value = blob

    with patch("app.api.services.feedback_gcs._get_client", return_value=_mock_client(bucket)):
        url = generate_signed_url("gs://test-bucket/job-123/raw.jpg", "test-bucket")

    bucket.blob.assert_called_once_with("job-123/raw.jpg")
    assert url == "https://signed.url/raw.jpg"


def test_generate_signed_url_strips_gs_prefix():
    bucket = MagicMock()
    blob = MagicMock()
    blob.generate_signed_url.return_value = "https://signed.url/raw.jpg"
    bucket.blob.return_value = blob

    with patch("app.api.services.feedback_gcs._get_client", return_value=_mock_client(bucket)):
        generate_signed_url("gs://test-bucket/job-123/raw.jpg", "test-bucket")

    # Should strip "gs://test-bucket/" and pass only "job-123/raw.jpg"
    bucket.blob.assert_called_once_with("job-123/raw.jpg")
