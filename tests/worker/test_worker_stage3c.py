"""Worker Stage 3c wiring tests."""

import os
import sys
from typing import Any
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../worker"))


from models import InputSpec, JobPayload, MasterConstraints, StorageSpec  # noqa: E402


def _make_payload(*, extract_data: bool = True) -> JobPayload:
    return JobPayload(
        job_id="stage3c-job-001",
        user_id="stage3c-user-001",
        mode="master",
        document_type="document",
        document_category="general",
        document_subtype=None,
        input=InputSpec(
            artifact_source="spaces",
            artifact_url=None,
            raw_path="uploads/stage3c-user-001/raw.jpg",
            mime_type="image/jpeg",
            original_filename="raw.jpg",
        ),
        storage=StorageSpec(
            bucket="rythmiq-test",
            region="sgp1",
            endpoint="https://sgp1.digitaloceanspaces.com",
        ),
        master_constraints=MasterConstraints(),
        sek_b64=None,
        portal_schema=None,
        extract_data=extract_data,
    )


def test_worker_wires_stage3c_between_enhancement_and_ocr_and_cleans_temp_file() -> None:
    import worker as worker_module

    fake_image_bytes = b"\xff\xd8\xff\xe0" + b"x" * 512
    payload = _make_payload(extract_data=True)

    mock_storage = MagicMock()
    mock_storage.download.return_value = fake_image_bytes
    mock_storage.upload_master.return_value = "master/stage3c-user-001/stage3c-job-001/master.jpg"
    mock_storage.upload_preview.return_value = "preview/stage3c-user-001/stage3c-job-001/preview.jpg"

    mock_quality = MagicMock()
    mock_quality.score = 0.82
    mock_quality.breakdown = {}

    mock_enhanced = MagicMock()
    mock_enhanced.image_data = b"enhanced-image-bytes"

    mock_schema = MagicMock()
    mock_schema.image_data = b"schema-image-bytes"
    mock_schema.content_type = "image/jpeg"

    mock_ocr_result = MagicMock()
    mock_ocr_result.confidence = 0.91

    sentinel_db = object()
    stage_order: list[str] = []

    def _fake_enhance(*_args: Any, **_kwargs: Any) -> Any:
        stage_order.append("enhance")
        return mock_enhanced

    def _fake_extract(**kwargs: Any) -> dict[str, Any]:
        stage_order.append("extract")
        assert kwargs["job_id"] == "stage3c-job-001"
        assert kwargs["user_id"] == "stage3c-user-001"
        assert kwargs["document_type"] == "document"
        assert kwargs["extract_data"] is True
        assert kwargs["db_client"] is sentinel_db
        assert kwargs["image_bytes"] == b"enhanced-image-bytes"
        return {
            "status": "completed",
            "fields": {"pan_number": "ABCDE1234F"},
            "confidence": {"pan_number": 0.97},
        }

    def _fake_ocr(*_args: Any, **_kwargs: Any) -> Any:
        stage_order.append("ocr")
        return mock_ocr_result, None

    with patch("worker.create_client_from_spec", return_value=mock_storage), \
         patch("worker.assess_quality", return_value=mock_quality), \
         patch("worker.enhance_image", side_effect=_fake_enhance), \
            patch("worker.process_extraction_stage", side_effect=_fake_extract, create=True) as extract_mock, \
         patch("worker.get_supabase_client", return_value=sentinel_db, create=True) as db_client_mock, \
         patch("worker.docai_extract_text", side_effect=_fake_ocr), \
         patch("worker.adapt_master_document", return_value=mock_schema), \
         patch("worker.adapt_to_schema", return_value=mock_schema), \
         patch("worker.log_detection_sample"), \
         patch("worker.check_quality_warning", return_value=False):
        result = worker_module.process_job(payload)

    assert result.job_id == "stage3c-job-001"
    assert db_client_mock.call_count == 1
    assert extract_mock.call_count == 1

    assert stage_order == ["enhance", "extract", "ocr"]
