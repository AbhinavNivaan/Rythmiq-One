"""
Regression test: worker must NOT delete raw upload after successful processing.
Deletion is deferred to the API dismiss/feedback endpoints.
The cleanup scheduler at POST /internal/cleanup/raw-uploads acts as a 24h safety net.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../worker"))

from unittest.mock import MagicMock, patch


def _make_minimal_payload():
    """Return a minimal JobPayload using the dataclass constructors."""
    from models import JobPayload, InputSpec, StorageSpec, MasterConstraints

    input_spec = InputSpec(
        artifact_source="spaces",
        artifact_url=None,
        raw_path="uploads/user-test/test-no-delete-001/raw.jpg",
        mime_type="image/jpeg",
        original_filename="raw.jpg",
    )
    storage_spec = StorageSpec(
        bucket="rythmiq-test",
        region="sgp1",
        endpoint="https://sgp1.digitaloceanspaces.com",
    )
    master_constraints = MasterConstraints()

    return JobPayload(
        job_id="test-no-delete-001",
        user_id="user-test",
        mode="master",
        document_type="document",
        document_category="general",
        document_subtype=None,
        input=input_spec,
        storage=storage_spec,
        master_constraints=master_constraints,
        sek_b64=None,
        encrypted_input=False,
        confirmed_crop_quad=None,
        portal_schema=None,
    )


def test_worker_does_not_delete_raw_upload_on_success():
    """After successful processing, storage.delete must never be called with raw_path."""
    import worker as worker_module

    # Minimal JPEG-like bytes (just needs to not crash image decode in mocked pipeline)
    fake_image_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 200

    # Build a mock storage client whose delete() we can spy on.
    mock_storage = MagicMock()
    mock_storage.download.return_value = fake_image_bytes
    mock_storage.upload_master.return_value = "master/user-test/test-no-delete-001/master.jpg"
    mock_storage.upload_preview.return_value = "preview/user-test/test-no-delete-001/preview.jpg"

    # Quality result stubs
    mock_quality = MagicMock()
    mock_quality.score = 0.85
    mock_quality.breakdown = {}

    # Enhancement result stubs
    mock_enhance = MagicMock()
    mock_enhance.image_data = fake_image_bytes
    mock_enhance.rollback = False

    # Schema result stubs
    mock_schema = MagicMock()
    mock_schema.image_data = fake_image_bytes
    mock_schema.content_type = "image/jpeg"

    # OCR stub — docai_extract_text returns (result, warning_or_None)
    mock_ocr_result = MagicMock()
    mock_ocr_result.text = ""
    mock_ocr_result.confidence = 0.0
    mock_ocr = (mock_ocr_result, None)  # (result, warning)

    payload = _make_minimal_payload()

    with patch("worker.create_client_from_spec", return_value=mock_storage), \
         patch("worker.assess_quality", return_value=mock_quality), \
         patch("worker.enhance_image", return_value=mock_enhance), \
         patch("worker.docai_extract_text", return_value=mock_ocr), \
         patch("worker.sek_from_base64", return_value=b"\x00" * 32), \
         patch("worker.adapt_to_schema", return_value=mock_schema), \
         patch("worker.adapt_master_document", return_value=mock_schema), \
         patch("worker.log_detection_sample"), \
         patch("worker.crypto_encrypt", return_value=(b"\x00" * 100, b"\x00" * 12)), \
         patch("worker.check_quality_warning", return_value=False):

        result = worker_module.process_job(payload)

    # The job must succeed
    assert result.job_id == "test-no-delete-001"
    assert result.artifacts.master_path == "master/user-test/test-no-delete-001/master.jpg"

    # storage.delete must NEVER have been called — deletion is deferred to the API layer
    mock_storage.delete.assert_not_called()
