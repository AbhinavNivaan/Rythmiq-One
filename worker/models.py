"""
Data models for the Camber CPU worker.

Defines all input/output contracts as frozen dataclasses for immutability
and deterministic behavior. No global state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


# =============================================================================
# Input Models (STDIN Contract)
# =============================================================================

@dataclass(frozen=True)
class SchemaDefinition:
    """Portal schema definition for document transformation."""
    target_width: int
    target_height: int
    target_dpi: int
    max_kb: int
    filename_pattern: str
    output_format: str = "jpeg"
    quality: int = 85

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> SchemaDefinition:
        """Parse schema definition from dict."""
        return SchemaDefinition(
            target_width=int(data.get("target_width", 600)),
            target_height=int(data.get("target_height", 800)),
            target_dpi=int(data.get("target_dpi", 300)),
            max_kb=int(data.get("max_kb", 200)),
            filename_pattern=str(data.get("filename_pattern", "{job_id}")),
            output_format=str(data.get("output_format", "jpeg")),
            quality=int(data.get("quality", 85)),
        )


@dataclass(frozen=True)
class PortalSchema:
    """Complete portal schema with metadata."""
    id: str
    name: str
    version: int
    schema_definition: SchemaDefinition

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> PortalSchema:
        """Parse portal schema from dict."""
        if not data:
            raise ValueError("portal_schema is required")
        
        schema_id = data.get("id")
        if not schema_id:
            raise ValueError("portal_schema.id is required")
        
        name = data.get("name")
        if not name:
            raise ValueError("portal_schema.name is required")
        
        version = data.get("version")
        if version is None:
            raise ValueError("portal_schema.version is required")
        
        schema_def = data.get("schema_definition", {})
        
        return PortalSchema(
            id=str(schema_id),
            name=str(name),
            version=int(version),
            schema_definition=SchemaDefinition.from_dict(schema_def),
        )


@dataclass(frozen=True)
class InputSpec:
    """Input artifact specification."""
    artifact_source: Literal["url", "path"]
    artifact_url: Optional[str]
    raw_path: Optional[str]
    mime_type: str
    original_filename: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> InputSpec:
        """Parse input spec from dict."""
        if not data:
            raise ValueError("input is required")
        
        artifact_url = data.get("artifact_url")
        raw_path = data.get("raw_path")
        
        # Import here to avoid circular dependency
        from storage.spaces_client import validate_artifact_source
        
        source = validate_artifact_source(artifact_url, raw_path)
        
        mime_type = data.get("mime_type")
        if not mime_type:
            raise ValueError("input.mime_type is required")
        
        original_filename = data.get("original_filename", "document")
        
        return InputSpec(
            artifact_source=source,
            artifact_url=artifact_url,
            raw_path=raw_path,
            mime_type=str(mime_type),
            original_filename=str(original_filename),
        )


@dataclass(frozen=True)
class StorageSpec:
    """Storage configuration for artifact upload."""
    bucket: str
    region: str
    endpoint: str

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> StorageSpec:
        """Parse storage spec from dict."""
        if not data:
            raise ValueError("storage is required")
        
        bucket = data.get("bucket")
        if not bucket:
            raise ValueError("storage.bucket is required")
        
        region = data.get("region")
        if not region:
            raise ValueError("storage.region is required")
        
        endpoint = data.get("endpoint")
        if not endpoint:
            raise ValueError("storage.endpoint is required")
        
        return StorageSpec(
            bucket=str(bucket),
            region=str(region),
            endpoint=str(endpoint),
        )


@dataclass(frozen=True)
class JobPayload:
    """
    Complete job payload from STDIN.
    
    This is the single input contract for the worker.
    All fields are validated at parse time.
    """
    job_id: str
    user_id: str
    portal_schema: PortalSchema
    input: InputSpec
    storage: StorageSpec

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> JobPayload:
        """Parse job payload from STDIN JSON dict."""
        if not isinstance(data, dict):
            raise ValueError("payload must be a JSON object")
        
        job_id = data.get("job_id")
        if not job_id:
            raise ValueError("job_id is required")
        
        user_id = data.get("user_id")
        if not user_id:
            raise ValueError("user_id is required")
        
        # Validate UUIDs
        try:
            uuid.UUID(str(job_id), version=4)
        except ValueError:
            raise ValueError(f"job_id must be a valid UUIDv4: {job_id}")
        
        try:
            uuid.UUID(str(user_id), version=4)
        except ValueError:
            raise ValueError(f"user_id must be a valid UUIDv4: {user_id}")
        
        return JobPayload(
            job_id=str(job_id),
            user_id=str(user_id),
            portal_schema=PortalSchema.from_dict(data.get("portal_schema", {})),
            input=InputSpec.from_dict(data.get("input", {})),
            storage=StorageSpec.from_dict(data.get("storage", {})),
        )


# =============================================================================
# Output Models (STDOUT Contract)
# =============================================================================

@dataclass(frozen=True)
class Artifacts:
    """Output artifact paths."""
    master_path: str
    preview_path: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "master_path": self.master_path,
            "preview_path": self.preview_path,
        }


@dataclass(frozen=True)
class Metrics:
    """Processing metrics."""
    ocr_confidence: float
    processing_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ocr_confidence": round(self.ocr_confidence, 4),
            "processing_ms": self.processing_ms,
        }


@dataclass(frozen=True)
class SuccessResult:
    """Successful processing result for STDOUT."""
    job_id: str
    quality_score: float
    warnings: List[str]
    artifacts: Artifacts
    metrics: Metrics

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": "success",
            "job_id": self.job_id,
            "quality_score": round(self.quality_score, 4),
            "warnings": list(self.warnings),
            "artifacts": self.artifacts.to_dict(),
            "metrics": self.metrics.to_dict(),
        }


@dataclass(frozen=True)
class ErrorDetail:
    """Structured error detail."""
    code: str
    stage: str
    message: str
    retryable: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "stage": self.stage,
            "message": self.message,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class FailureResult:
    """Failed processing result for STDOUT."""
    job_id: Optional[str]
    error: ErrorDetail

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": "failed",
            "job_id": self.job_id,
            "error": self.error.to_dict(),
        }


# =============================================================================
# Processing Models
# =============================================================================

@dataclass(frozen=True)
class QualityBreakdown:
    """Quality score breakdown by metric."""
    sharpness: float
    exposure: float
    noise: float
    edge_density: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "sharpness": round(self.sharpness, 4),
            "exposure": round(self.exposure, 4),
            "noise": round(self.noise, 4),
            "edge_density": round(self.edge_density, 4),
        }


@dataclass(frozen=True)
class QualityResult:
    """Quality assessment result."""
    score: float
    breakdown: QualityBreakdown

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "breakdown": self.breakdown.to_dict(),
        }


@dataclass(frozen=True)
class OCRBox:
    """OCR bounding box."""
    x: int
    y: int
    width: int
    height: int
    text: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "text": self.text,
            "confidence": round(self.confidence, 4),
        }


@dataclass(frozen=True)
class OCRResult:
    """OCR extraction result."""
    text: str
    confidence: float
    boxes: List[OCRBox]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "confidence": round(self.confidence, 4),
            "boxes": [box.to_dict() for box in self.boxes],
        }


@dataclass(frozen=True)
class EnhancementResult:
    """Image enhancement result."""
    image_data: bytes
    orientation_corrected: bool
    denoised: bool
    color_normalized: bool

    # Note: bytes cannot be in to_dict, used internally only


@dataclass(frozen=True)
class SchemaResult:
    """Schema adaptation result."""
    image_data: bytes
    final_width: int
    final_height: int
    final_dpi: int
    final_size_kb: float
    filename: str

    # Note: bytes cannot be in to_dict, used internally only
