"""
Adaptation Pipeline v2 Tests.

Tests the new features introduced in the adaptation pipeline v2:
  1. min_kb floor enforcement in compress_to_size()
  2. PDF output path in adapt_to_schema()
  3. Post-adapt compliance gate (verify_schema_compliance called automatically)
  4. SchemaDefinition + MasterConstraints carry min_kb field

Run with:
    pytest tests/test_adaptation_v2.py -v
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

# Add worker to path
sys.path.insert(0, str(Path(__file__).parent.parent / "worker"))

from models import SchemaDefinition, MasterConstraints
from processors.schema import (
    adapt_to_schema,
    adapt_master_document,
    compress_to_size,
    encode_as_pdf,
    verify_schema_compliance,
    decode_image,
)
from errors import WorkerError, ErrorCode


# =============================================================================
# Helpers
# =============================================================================

def _solid_jpeg(width: int = 400, height: int = 400, color: tuple = (200, 190, 180)) -> bytes:
    """Return a solid-colour JPEG as bytes."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _solid_cv_img(width: int = 400, height: int = 400) -> "np.ndarray":
    """Return a solid BGR numpy array."""
    return np.full((height, width, 3), (180, 190, 200), dtype=np.uint8)


# =============================================================================
# Tests: min_kb enforcement
# =============================================================================

class TestMinKbEnforcement:
    """compress_to_size() and adapt_to_schema() must raise SIZE_TOO_SMALL when
    the result falls below the min_kb threshold."""

    def test_min_kb_zero_always_passes(self):
        """min_kb=0 disables the floor check — any size is acceptable."""
        img = _solid_cv_img(100, 100)
        data, _ = compress_to_size(img, dpi=200, max_kb=200, min_kb=0)
        assert len(data) > 0

    def test_min_kb_below_actual_size_passes(self):
        """When output size > min_kb, no error is raised."""
        img = _solid_cv_img(400, 400)
        data, _ = compress_to_size(img, dpi=200, max_kb=200, min_kb=1)
        # A 400x400 JPEG should be well above 1KB
        assert len(data) >= 1024

    def test_min_kb_above_actual_size_raises(self):
        """When output size < min_kb, SIZE_TOO_SMALL must be raised."""
        # Use a very small image (1x1) — it will produce a tiny JPEG
        img = _solid_cv_img(1, 1)
        with pytest.raises(WorkerError) as exc_info:
            compress_to_size(img, dpi=200, max_kb=200, min_kb=50)  # 50KB minimum on a 1x1 px image
        assert exc_info.value.code == ErrorCode.SIZE_TOO_SMALL

    def test_size_too_small_error_includes_details(self):
        """SIZE_TOO_SMALL error must include output_size_kb and min_kb in details."""
        img = _solid_cv_img(1, 1)
        with pytest.raises(WorkerError) as exc_info:
            compress_to_size(img, dpi=200, max_kb=200, min_kb=50)
        err = exc_info.value
        assert err.details is not None
        assert "output_size_kb" in err.details
        assert "min_kb" in err.details
        assert err.details["min_kb"] == 50

    def test_adapt_to_schema_propagates_min_kb(self):
        """adapt_to_schema() propagates min_kb from SchemaDefinition to compress_to_size."""
        schema = SchemaDefinition(
            target_width=1,
            target_height=1,
            target_dpi=200,
            max_kb=200,
            filename_pattern="{job_id}",
            min_kb=50,  # Impossible for a 1x1 image
        )
        jpeg = _solid_jpeg(100, 100)
        with pytest.raises(WorkerError) as exc_info:
            adapt_to_schema(jpeg, schema, job_id="test-job-id")
        assert exc_info.value.code == ErrorCode.SIZE_TOO_SMALL

    def test_schema_definition_min_kb_default_is_zero(self):
        """SchemaDefinition.min_kb defaults to 0 for backward compatibility."""
        schema = SchemaDefinition(
            target_width=400,
            target_height=400,
            target_dpi=200,
            max_kb=200,
            filename_pattern="{job_id}",
        )
        assert schema.min_kb == 0

    def test_schema_definition_from_dict_parses_min_kb(self):
        """SchemaDefinition.from_dict() correctly parses min_kb."""
        schema = SchemaDefinition.from_dict({
            "target_width": 400,
            "target_height": 400,
            "target_dpi": 200,
            "max_kb": 200,
            "min_kb": 10,
            "filename_pattern": "{job_id}",
        })
        assert schema.min_kb == 10

    def test_master_constraints_has_min_kb(self):
        """MasterConstraints must carry min_kb (default 0)."""
        mc = MasterConstraints()
        assert mc.min_kb == 0

    def test_master_constraints_from_dict_parses_min_kb(self):
        """MasterConstraints.from_dict() correctly parses min_kb."""
        mc = MasterConstraints.from_dict({"min_kb": 5})
        assert mc.min_kb == 5


# =============================================================================
# Tests: PDF output path
# =============================================================================

class TestPdfOutputPath:
    """adapt_to_schema() with output_format='pdf' should produce a valid single-page PDF."""

    def test_encode_as_pdf_returns_bytes(self):
        """encode_as_pdf() returns non-empty bytes."""
        img = _solid_cv_img(300, 400)
        pdf = encode_as_pdf(img, dpi=200)
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0

    def test_encode_as_pdf_starts_with_pdf_header(self):
        """Valid PDF files start with %PDF."""
        img = _solid_cv_img(300, 400)
        pdf = encode_as_pdf(img, dpi=200)
        assert pdf[:4] == b"%PDF"

    def test_adapt_to_schema_pdf_returns_pdf_result(self):
        """adapt_to_schema() with output_format='pdf' returns a SchemaResult with PDF bytes."""
        schema = SchemaDefinition(
            target_width=600,
            target_height=800,
            target_dpi=200,
            max_kb=300,
            filename_pattern="{job_id}_class10",
            output_format="pdf",
        )
        jpeg = _solid_jpeg(600, 800)
        result = adapt_to_schema(jpeg, schema, job_id="test-job-id")

        assert result.image_data[:4] == b"%PDF"
        assert result.filename.endswith(".pdf")

    def test_adapt_to_schema_pdf_filename_has_pdf_extension(self):
        """PDF output filename must end in .pdf."""
        schema = SchemaDefinition(
            target_width=600,
            target_height=800,
            target_dpi=200,
            max_kb=300,
            filename_pattern="{job_id}_doc",
            output_format="pdf",
        )
        result = adapt_to_schema(_solid_jpeg(200, 200), schema, job_id="test-job-id")
        assert result.filename.endswith(".pdf")

    def test_adapt_to_schema_pdf_size_within_max(self):
        """PDF output must respect max_kb limit."""
        schema = SchemaDefinition(
            target_width=600,
            target_height=800,
            target_dpi=200,
            max_kb=300,
            filename_pattern="{job_id}_doc",
            output_format="pdf",
        )
        result = adapt_to_schema(_solid_jpeg(200, 200), schema, job_id="test-job-id")
        assert result.final_size_kb <= 300

    def test_adapt_to_schema_pdf_oversized_raises(self):
        """PDF larger than max_kb should raise SIZE_EXCEEDED."""
        schema = SchemaDefinition(
            target_width=600,
            target_height=800,
            target_dpi=200,
            max_kb=1,   # 1KB — impossible for a PDF
            filename_pattern="{job_id}_doc",
            output_format="pdf",
        )
        with pytest.raises(WorkerError) as exc_info:
            adapt_to_schema(_solid_jpeg(600, 800), schema, job_id="test-job-id")
        assert exc_info.value.code == ErrorCode.SIZE_EXCEEDED

    def test_pdf_path_skips_pixel_resize(self):
        """PDF output does not enforce target_width/target_height pixel dimensions 
        (pass-through ratio is preserved)."""
        schema = SchemaDefinition(
            target_width=600,
            target_height=800,
            target_dpi=200,
            max_kb=300,
            filename_pattern="{job_id}_doc",
            output_format="pdf",
        )
        # A very different-aspect image; PDF should not fail with RESIZE_FAILED
        result = adapt_to_schema(_solid_jpeg(100, 300), schema, job_id="test-job-id")
        assert result.image_data[:4] == b"%PDF"


# =============================================================================
# Tests: post-adapt compliance gate
# =============================================================================

class TestPostAdaptComplianceGate:
    """adapt_to_schema() must call verify_schema_compliance() after adaptation
    and raise SCHEMA_FAILED if the output doesn't match the schema."""

    def test_normal_adapt_passes_compliance(self):
        """A standard JPEG adapt should pass the compliance gate."""
        schema = SchemaDefinition(
            target_width=300,
            target_height=300,
            target_dpi=200,
            max_kb=200,
            filename_pattern="{job_id}",
        )
        result = adapt_to_schema(_solid_jpeg(600, 600), schema, job_id="test-job-id")
        assert result.final_width == 300
        assert result.final_height == 300

    def test_verify_schema_compliance_dimensions(self):
        """verify_schema_compliance() catches dimension mismatches."""
        schema = SchemaDefinition(
            target_width=400,
            target_height=400,
            target_dpi=200,
            max_kb=200,
            filename_pattern="{job_id}",
        )
        # Manually compress to 300x300 (wrong dimensions)
        img_300 = _solid_cv_img(300, 300)
        from processors.schema import encode_with_dpi
        data_300 = encode_with_dpi(img_300, dpi=200, format="jpeg", quality=90)
        is_ok, msg = verify_schema_compliance(data_300, schema)
        assert not is_ok
        assert "300" in msg  # Should mention the wrong dimension

    def test_verify_schema_compliance_size_exceeded(self):
        """verify_schema_compliance() catches files exceeding max_kb."""
        schema = SchemaDefinition(
            target_width=400,
            target_height=400,
            target_dpi=200,
            max_kb=1,  # 1KB — extremely small
            filename_pattern="{job_id}",
        )
        # Generate a valid 400x400 image
        from processors.schema import encode_with_dpi
        img = _solid_cv_img(400, 400)
        data = encode_with_dpi(img, dpi=200, format="jpeg", quality=95)
        is_ok, msg = verify_schema_compliance(data, schema)
        # The 400x400 JPEG will likely be > 1KB
        if len(data) > 1024:
            assert not is_ok


# =============================================================================
# Tests: neet_2026_registration v1.1.0 spec coverage
# =============================================================================

class TestNeetSchemaAdaptation:
    """Smoke-tests that the NEET 2026 pixel specs produce valid outputs."""

    NEET_SPECS = {
        "photograph_passport": {
            "target_width": 400, "target_height": 400, "target_dpi": 200,
            "max_kb": 200, "min_kb": 10, "fit_mode": "letterbox", "output_format": "jpeg",
        },
        "photograph_postcard": {
            "target_width": 800, "target_height": 1200, "target_dpi": 200,
            "max_kb": 200, "min_kb": 10, "fit_mode": "letterbox", "output_format": "jpeg",
        },
        "signature": {
            "target_width": 362, "target_height": 178, "target_dpi": 200,
            "max_kb": 30, "min_kb": 4, "fit_mode": "stretch", "output_format": "jpeg",
        },
        "left_thumb_impression": {
            "target_width": 300, "target_height": 300, "target_dpi": 200,
            "max_kb": 200, "min_kb": 10, "fit_mode": "stretch", "output_format": "jpeg",
        },
        "right_thumb_and_finger_impressions": {
            "target_width": 300, "target_height": 300, "target_dpi": 200,
            "max_kb": 200, "min_kb": 10, "fit_mode": "stretch", "output_format": "jpeg",
        },
    }

    @pytest.mark.parametrize("doc_id,spec", NEET_SPECS.items())
    def test_neet_image_spec_produces_correct_dimensions(self, doc_id: str, spec: dict):
        """Each NEET image spec produces output at exact target dimensions."""
        schema = SchemaDefinition.from_dict({**spec, "filename_pattern": f"{{job_id}}_{doc_id}"})
        # Use random-noise image — guarantees JPEG is large enough to pass min_kb
        rng = np.random.default_rng(42)
        noise = rng.integers(0, 256, (800, 600, 3), dtype=np.uint8)
        pil_noise = Image.fromarray(noise, mode="RGB")
        buf = io.BytesIO()
        pil_noise.save(buf, format="JPEG", quality=95)
        jpeg = buf.getvalue()

        result = adapt_to_schema(jpeg, schema, job_id="neet-test-job")

        assert result.final_width == spec["target_width"], f"{doc_id}: width mismatch"
        assert result.final_height == spec["target_height"], f"{doc_id}: height mismatch"
        assert result.final_size_kb <= spec["max_kb"], f"{doc_id}: exceeds max_kb"

    def test_neet_signature_max_kb_is_30(self):
        """NEET signature spec must have max_kb=30 (not legacy 50)."""
        spec = self.NEET_SPECS["signature"]
        assert spec["max_kb"] == 30, "Signature max_kb must be 30 (NTA requirement)"

    def test_neet_photo_dimensions_are_400x400(self):
        """NEET passport photo must be 400x400 (2×2 inch at 200dpi)."""
        spec = self.NEET_SPECS["photograph_passport"]
        assert spec["target_width"] == 400
        assert spec["target_height"] == 400
