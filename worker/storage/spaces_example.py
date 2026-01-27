"""
Example: Worker-side Spaces integration.

Shows how the Camber worker uses the Spaces client to:
1. Download raw artifact (via signed URL or direct path)
2. Process the document
3. Upload master artifact
4. Upload output ZIP

This is a reference implementation - integrate into job_handler.py as needed.
"""

import time
from dataclasses import dataclass
from typing import Optional

from storage.spaces_client import (
    WorkerSpacesClient,
    create_worker_spaces_client,
)
from storage.artifact_fetcher import fetch_artifact
from errors.error_codes import ProcessingError, ErrorCode, ProcessingStage


@dataclass
class ArtifactPaths:
    """Paths for artifacts uploaded by worker."""
    master_path: Optional[str] = None
    output_path: Optional[str] = None


def process_job_with_spaces(
    job_id: str,
    user_id: str,
    document_id: str,
    artifact_url: str,
    raw_path: Optional[str] = None,
) -> ArtifactPaths:
    """
    Process a job and upload results to Spaces.
    
    This function demonstrates the complete worker flow:
    1. Download raw artifact (via signed URL or direct Spaces path)
    2. Process document (placeholder - your OCR/transform logic)
    3. Upload master document
    4. Upload output ZIP
    
    Args:
        job_id: Job UUID (24 hex chars)
        user_id: User UUID (24 hex chars)
        document_id: Document UUID (24 hex chars, for master storage)
        artifact_url: Pre-signed URL for raw artifact download
        raw_path: Optional direct Spaces path (if not using signed URL)
        
    Returns:
        ArtifactPaths with master_path and output_path
        
    Raises:
        ProcessingError: If any step fails
    """
    # Create Spaces client (fresh instance, no caching)
    spaces = create_worker_spaces_client()
    
    # ---------------------------------------------------------------------
    # Step 1: Download raw artifact
    # ---------------------------------------------------------------------
    
    if raw_path:
        # Direct download from Spaces (worker has read permission on raw/)
        raw_bytes = spaces.download_raw(raw_path)
    else:
        # Download via pre-signed URL (existing method)
        raw_bytes = fetch_artifact(artifact_url)
    
    # ---------------------------------------------------------------------
    # Step 2: Process document (placeholder)
    # ---------------------------------------------------------------------
    
    # Your actual processing logic goes here:
    # - OCR extraction
    # - Schema transformation
    # - Result generation
    
    # For this example, we create placeholder outputs
    master_bytes = process_to_master(raw_bytes)
    output_bytes = process_to_output(raw_bytes)
    
    # ---------------------------------------------------------------------
    # Step 3: Upload master document
    # ---------------------------------------------------------------------
    
    master_path = spaces.upload_master(
        data=master_bytes,
        user_id=user_id,
        document_id=document_id,
    )
    
    # ---------------------------------------------------------------------
    # Step 4: Upload output ZIP
    # ---------------------------------------------------------------------
    
    timestamp_ms = int(time.time() * 1000)
    
    output_path = spaces.upload_output(
        data=output_bytes,
        user_id=user_id,
        job_id=job_id,
        timestamp_ms=timestamp_ms,
    )
    
    return ArtifactPaths(
        master_path=master_path,
        output_path=output_path,
    )


def process_to_master(raw_bytes: bytes) -> bytes:
    """
    Placeholder: Convert raw artifact to master document.
    
    In production, this would:
    - Decrypt raw bytes (client-side encryption key)
    - Process/normalize document
    - Re-encrypt as master format
    
    Returns:
        Encrypted master document bytes
    """
    # PLACEHOLDER: Your actual processing logic
    return raw_bytes  # In reality, this would be transformed/re-encrypted


def process_to_output(raw_bytes: bytes) -> bytes:
    """
    Placeholder: Generate output ZIP from processing.
    
    In production, this would:
    - Create ZIP with structured data, metadata, etc.
    - Encrypt the ZIP
    
    Returns:
        Encrypted ZIP bytes
    """
    import io
    import zipfile
    
    # Create a simple ZIP (placeholder)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('result.json', '{"status": "processed"}')
    
    # PLACEHOLDER: In production, encrypt this
    return buffer.getvalue()


# -----------------------------------------------------------------------------
# Integration with existing job_handler.py
# -----------------------------------------------------------------------------

"""
To integrate with the existing job_handler.py, modify execute_job() like this:

```python
from storage.spaces_client import create_worker_spaces_client
import time

def execute_job(payload: JobPayload) -> SuccessResult | FailureResult:
    try:
        # Existing: Fetch artifact
        artifact_bytes = fetch_artifact(payload.artifact_url)
        
        # Existing: OCR
        ocr_result = extract_text(...)
        
        # Existing: Transform
        transform_result = transform(...)
        
        # NEW: Upload artifacts to Spaces
        spaces = create_worker_spaces_client()
        
        # Upload master (if applicable)
        # master_path = spaces.upload_master(
        #     data=master_bytes,
        #     user_id=payload.user_id,
        #     document_id=payload.document_id,
        # )
        
        # Upload output
        timestamp_ms = int(time.time() * 1000)
        output_path = spaces.upload_output(
            data=output_bytes,
            user_id=payload.user_id,
            job_id=payload.job_id,
            timestamp_ms=timestamp_ms,
        )
        
        return SuccessResult(
            status="SUCCESS",
            job_id=payload.job_id,
            structured=transform_result.structured,
            confidence=transform_result.confidence,
            quality_score=transform_result.quality_score,
            page_count=ocr_result.page_count,
            output_path=output_path,  # NEW: Include artifact path in result
        )
    except ProcessingError as e:
        ...
```
"""
