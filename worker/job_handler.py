"""
Job handler - main processing pipeline.

Orchestrates FETCH → OCR → NORMALIZE → TRANSFORM stages.
Single-shot execution: one job in, one result out, no retries.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional

from storage.artifact_fetcher import fetch_artifact
from ocr.tesseract_adapter import extract_text
from schema.validator import transform, SchemaDefinition
from errors.error_codes import ProcessingError, ErrorCode, ProcessingStage


@dataclass
class JobPayload:
    """
    Job payload received from API Gateway.
    
    Contains everything needed for processing:
    - job_id for tracking
    - artifact_url to fetch document
    - schema definition for transformation
    - optional processing options
    """
    job_id: str
    artifact_url: str
    schema: SchemaDefinition
    language: str = "eng"
    max_file_size_bytes: int = 50 * 1024 * 1024
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "JobPayload":
        """
        Parse job payload from JSON-compatible dict.
        
        Validates required fields and constructs schema.
        """
        if not isinstance(data, dict):
            raise ValueError("payload must be object")
        
        job_id = data.get("job_id")
        if not job_id:
            raise ValueError("job_id required")
        
        artifact_url = data.get("artifact_url")
        if not artifact_url:
            raise ValueError("artifact_url required")
        
        schema_data = data.get("schema")
        if not schema_data:
            raise ValueError("schema required")
        
        schema = SchemaDefinition.from_dict(schema_data)
        
        options = data.get("options", {})
        
        return JobPayload(
            job_id=str(job_id),
            artifact_url=str(artifact_url),
            schema=schema,
            language=options.get("language", "eng"),
            max_file_size_bytes=options.get("max_file_size_bytes", 50 * 1024 * 1024)
        )


@dataclass
class SuccessResult:
    """Successful processing result."""
    status: str
    job_id: str
    structured: Dict[str, str]
    confidence: Dict[str, float]
    quality_score: float
    page_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "job_id": self.job_id,
            "result": {
                "structured": self.structured,
                "confidence": self.confidence,
                "quality_score": self.quality_score,
                "page_count": self.page_count
            }
        }


@dataclass
class FailureResult:
    """Failed processing result."""
    status: str
    job_id: str
    error: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "job_id": self.job_id,
            "error": self.error
        }


def execute_job(payload: JobPayload) -> SuccessResult | FailureResult:
    """
    Execute a single job through the processing pipeline.
    
    Pipeline: FETCH → OCR → NORMALIZE → TRANSFORM
    
    No retries, no heuristics, no side effects beyond artifact fetch.
    All errors are terminal and return a FailureResult.
    
    Args:
        payload: Job payload with artifact URL and schema
        
    Returns:
        SuccessResult on success, FailureResult on any error
    """
    try:
        # Stage 1: FETCH - Download artifact
        artifact_bytes = fetch_artifact(payload.artifact_url)
        
        # Stage 2: OCR - Extract text from image
        ocr_result = extract_text(
            data=artifact_bytes,
            language=payload.language,
            max_size_bytes=payload.max_file_size_bytes
        )
        
        # Stage 3 & 4: NORMALIZE + TRANSFORM - Apply schema
        transform_result = transform(
            ocr_text=ocr_result.text,
            schema=payload.schema
        )
        
        # Success
        return SuccessResult(
            status="SUCCESS",
            job_id=payload.job_id,
            structured=transform_result.structured,
            confidence=transform_result.confidence,
            quality_score=transform_result.quality_score,
            page_count=ocr_result.page_count
        )
        
    except ProcessingError as e:
        # Known error - return structured failure
        return FailureResult(
            status="FAILED",
            job_id=payload.job_id,
            error=e.to_dict()
        )
    except Exception as e:
        # Unknown error - wrap as TRANSFORM_ERROR
        return FailureResult(
            status="FAILED",
            job_id=payload.job_id,
            error={
                "code": ErrorCode.TRANSFORM_ERROR.value,
                "stage": ProcessingStage.TRANSFORM.value,
                "details": {"reason": "internal_error"}
            }
        )
