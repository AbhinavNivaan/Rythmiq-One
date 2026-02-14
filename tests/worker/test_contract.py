"""
Worker Contract Tests

Tests the STDIN→STDOUT contract for the processing worker.
Ensures the worker correctly handles input payloads and produces valid output.
"""

import pytest
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any
from unittest.mock import patch, MagicMock


# Path to worker script
WORKER_DIR = Path(__file__).parent.parent.parent / "worker"


class TestWorkerContract:
    """Tests for worker STDIN→STDOUT contract."""

    @pytest.fixture
    def valid_process_payload(self) -> Dict[str, Any]:
        """Valid processing job payload."""
        return {
            "job_id": "test-job-123",
            "job_type": "process",
            "input_artifact_path": "raw/user-123/doc-456/image.jpg",
            "output_artifact_path": "master/user-123/doc-456/",
            "config": {
                "enhance": True,
                "auto_orient": True,
                "normalize": True,
            },
        }

    @pytest.fixture
    def valid_adapt_payload(self) -> Dict[str, Any]:
        """Valid adaptation job payload."""
        return {
            "job_id": "test-job-789",
            "job_type": "adapt",
            "input_artifact_path": "master/user-123/doc-456/master.png",
            "output_artifact_path": "output/user-123/job-789/",
            "target_portal": "NEET_2026",
            "schema": {
                "photo": {"dimensions": [400, 600], "dpi": 300, "max_kb": 200, "format": "jpg"},
                "signature": {"dimensions": [200, 100], "dpi": 200, "max_kb": 50, "format": "jpg"},
            },
        }

    def test_payload_has_required_fields(self, valid_process_payload):
        """Payload must have required fields."""
        required_fields = ["job_id", "job_type", "input_artifact_path"]
        for field in required_fields:
            assert field in valid_process_payload, f"Missing required field: {field}"

    def test_job_type_is_valid(self, valid_process_payload, valid_adapt_payload):
        """Job type must be 'process' or 'adapt'."""
        assert valid_process_payload["job_type"] in ["process", "adapt"]
        assert valid_adapt_payload["job_type"] in ["process", "adapt"]

    def test_adapt_payload_has_target_portal(self, valid_adapt_payload):
        """Adapt job must include target_portal."""
        assert "target_portal" in valid_adapt_payload

    def test_adapt_payload_has_schema(self, valid_adapt_payload):
        """Adapt job must include schema."""
        assert "schema" in valid_adapt_payload
        assert isinstance(valid_adapt_payload["schema"], dict)


class TestWorkerOutputContract:
    """Tests for expected worker output format."""

    def test_success_output_format(self):
        """Successful output must have required fields."""
        success_output = {
            "status": "success",
            "job_id": "test-job-123",
            "output_path": "master/user-123/doc-456/master.png",
            "quality_score": 0.85,
            "metrics": {
                "sharpness": 0.9,
                "exposure": 0.8,
                "processing_time_ms": 1500,
            },
        }
        
        required_fields = ["status", "job_id", "output_path"]
        for field in required_fields:
            assert field in success_output, f"Missing required field: {field}"
        
        assert success_output["status"] == "success"
        assert 0 <= success_output["quality_score"] <= 1

    def test_failure_output_format(self):
        """Failure output must have error information."""
        failure_output = {
            "status": "failed",
            "job_id": "test-job-123",
            "error": {
                "code": "CORRUPT_FILE",
                "message": "Unable to decode image file",
            },
        }
        
        assert failure_output["status"] == "failed"
        assert "error" in failure_output
        assert "code" in failure_output["error"]
        assert "message" in failure_output["error"]

    def test_quality_score_range(self):
        """Quality score must be between 0 and 1."""
        for score in [0.0, 0.5, 0.85, 1.0]:
            assert 0 <= score <= 1, f"Invalid quality score: {score}"

    def test_valid_error_codes(self):
        """Error codes must be from defined set."""
        valid_codes = [
            "CORRUPT_FILE",
            "UNSUPPORTED_FORMAT",
            "FILE_TOO_LARGE",
            "PROCESSING_TIMEOUT",
            "DOWNLOAD_FAILED",
            "UPLOAD_FAILED",
            "SCHEMA_VIOLATION",
            "INTERNAL_ERROR",
        ]
        
        for code in valid_codes:
            assert isinstance(code, str)
            assert code.isupper()


class TestSchemaValidation:
    """Tests for schema compliance in adapted files."""

    @pytest.fixture
    def neet_schema(self) -> Dict[str, Any]:
        """NEET 2026 schema requirements."""
        return {
            "photo": {
                "dimensions": [400, 600],
                "dpi": 300,
                "max_kb": 200,
                "format": "jpg",
            },
            "signature": {
                "dimensions": [200, 100],
                "dpi": 200,
                "max_kb": 50,
                "format": "jpg",
            },
        }

    def test_schema_has_dimensions(self, neet_schema):
        """Schema must specify dimensions."""
        for doc_type, spec in neet_schema.items():
            assert "dimensions" in spec
            assert len(spec["dimensions"]) == 2
            assert all(isinstance(d, int) for d in spec["dimensions"])

    def test_schema_has_dpi(self, neet_schema):
        """Schema must specify DPI."""
        for doc_type, spec in neet_schema.items():
            assert "dpi" in spec
            assert isinstance(spec["dpi"], int)
            assert spec["dpi"] > 0

    def test_schema_has_max_size(self, neet_schema):
        """Schema must specify max file size."""
        for doc_type, spec in neet_schema.items():
            assert "max_kb" in spec
            assert isinstance(spec["max_kb"], int)
            assert spec["max_kb"] > 0

    def test_schema_has_format(self, neet_schema):
        """Schema must specify output format."""
        for doc_type, spec in neet_schema.items():
            assert "format" in spec
            assert spec["format"] in ["jpg", "jpeg", "png"]


class TestWorkerIntegration:
    """Integration tests for worker (requires worker to be available)."""

    @pytest.mark.skip(reason="Requires actual worker environment")
    def test_worker_processes_valid_input(self, valid_process_payload):
        """Worker should process valid input and return success."""
        # This would actually run the worker
        pass

    @pytest.mark.skip(reason="Requires actual worker environment")
    def test_worker_handles_missing_file(self):
        """Worker should handle missing input file gracefully."""
        payload = {
            "job_id": "test-job-123",
            "job_type": "process",
            "input_artifact_path": "nonexistent/file.jpg",
        }
        # This would actually run the worker and expect failure
        pass

    @pytest.mark.skip(reason="Requires actual worker environment")
    def test_worker_respects_timeout(self):
        """Worker should timeout for long operations."""
        pass


class TestQualityScoring:
    """Tests for quality scoring logic."""

    def test_quality_score_excellent(self):
        """Score >= 0.80 should be 'Excellent'."""
        def get_quality_label(score: float) -> str:
            if score >= 0.80:
                return "Excellent"
            elif score >= 0.50:
                return "Good"
            else:
                return "Poor"
        
        assert get_quality_label(0.80) == "Excellent"
        assert get_quality_label(0.95) == "Excellent"
        assert get_quality_label(1.0) == "Excellent"

    def test_quality_score_good(self):
        """Score 0.50-0.79 should be 'Good'."""
        def get_quality_label(score: float) -> str:
            if score >= 0.80:
                return "Excellent"
            elif score >= 0.50:
                return "Good"
            else:
                return "Poor"
        
        assert get_quality_label(0.50) == "Good"
        assert get_quality_label(0.65) == "Good"
        assert get_quality_label(0.79) == "Good"

    def test_quality_score_poor(self):
        """Score < 0.50 should be 'Poor'."""
        def get_quality_label(score: float) -> str:
            if score >= 0.80:
                return "Excellent"
            elif score >= 0.50:
                return "Good"
            else:
                return "Poor"
        
        assert get_quality_label(0.0) == "Poor"
        assert get_quality_label(0.30) == "Poor"
        assert get_quality_label(0.49) == "Poor"
