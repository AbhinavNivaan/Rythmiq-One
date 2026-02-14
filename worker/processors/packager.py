"""
Output packaging for Camber CPU worker.

Creates ZIP archives of processed documents:
- Master document (PDF or image)
- Schema-adapted outputs
- Manifest with metadata

Ensures reliable, organized delivery of results.
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from errors import WorkerError, ErrorCode, ProcessingStage


logger = logging.getLogger(__name__)


@dataclass
class OutputFile:
    """Represents a file to include in the output package."""
    filename: str
    data: bytes
    mime_type: str
    metadata: Dict[str, Any]


@dataclass
class PackageManifest:
    """Manifest describing the output package contents."""
    job_id: str
    created_at: str
    files: List[Dict[str, Any]]
    quality_score: float
    processing_mode: str
    portal_schema: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "created_at": self.created_at,
            "quality_score": self.quality_score,
            "processing_mode": self.processing_mode,
            "portal_schema": self.portal_schema,
            "files": self.files,
            "file_count": len(self.files),
        }


@dataclass 
class PackageResult:
    """Result from package creation."""
    zip_bytes: bytes
    manifest: PackageManifest
    total_size_bytes: int
    file_count: int


def create_output_package(
    job_id: str,
    files: List[OutputFile],
    quality_score: float,
    processing_mode: str,
    portal_schema: Optional[str] = None,
    compression: int = zipfile.ZIP_DEFLATED,
) -> PackageResult:
    """
    Create a ZIP package containing all output files.
    
    Package structure:
    - manifest.json (metadata)
    - master.pdf or master.jpg (master document)
    - adapted/ (schema-adapted files)
    
    Args:
        job_id: Job identifier
        files: List of files to include
        quality_score: Overall quality score
        processing_mode: Processing mode used
        portal_schema: Portal schema name (if applicable)
        compression: ZIP compression method
        
    Returns:
        PackageResult with ZIP bytes and metadata
    """
    if not files:
        raise WorkerError(
            code=ErrorCode.INTERNAL_ERROR,
            stage=ProcessingStage.OUTPUT,
            message="No files provided for packaging",
        )
    
    created_at = datetime.now(timezone.utc).isoformat()
    
    # Build file list for manifest
    manifest_files: List[Dict[str, Any]] = []
    total_size = 0
    
    buffer = io.BytesIO()
    
    try:
        with zipfile.ZipFile(buffer, 'w', compression) as zf:
            for f in files:
                # Add file to ZIP
                zf.writestr(f.filename, f.data)
                
                file_info = {
                    "filename": f.filename,
                    "size_bytes": len(f.data),
                    "mime_type": f.mime_type,
                    **f.metadata,
                }
                manifest_files.append(file_info)
                total_size += len(f.data)
            
            # Create and add manifest
            manifest = PackageManifest(
                job_id=job_id,
                created_at=created_at,
                files=manifest_files,
                quality_score=quality_score,
                processing_mode=processing_mode,
                portal_schema=portal_schema,
            )
            
            manifest_json = json.dumps(manifest.to_dict(), indent=2)
            zf.writestr("manifest.json", manifest_json)
        
        zip_bytes = buffer.getvalue()
        
        logger.info(
            f"Created output package: {len(files)} files, {len(zip_bytes)} bytes",
            extra={"job_id": job_id, "file_count": len(files)},
        )
        
        return PackageResult(
            zip_bytes=zip_bytes,
            manifest=manifest,
            total_size_bytes=len(zip_bytes),
            file_count=len(files),
        )
        
    except Exception as e:
        raise WorkerError(
            code=ErrorCode.INTERNAL_ERROR,
            stage=ProcessingStage.OUTPUT,
            message=f"Failed to create output package: {str(e)}",
        )


def create_master_package(
    job_id: str,
    master_bytes: bytes,
    format: str,
    quality_score: float,
    page_count: int = 1,
    quality_breakdown: Optional[Dict[str, float]] = None,
) -> PackageResult:
    """
    Create a package for master document output.
    
    Args:
        job_id: Job identifier
        master_bytes: Master document bytes
        format: Output format (pdf, jpeg)
        quality_score: Quality score
        page_count: Number of pages
        quality_breakdown: Detailed quality metrics
        
    Returns:
        PackageResult with ZIP containing master document
    """
    ext = "pdf" if format.lower() == "pdf" else "jpg"
    mime_type = "application/pdf" if format.lower() == "pdf" else "image/jpeg"
    
    master_file = OutputFile(
        filename=f"master.{ext}",
        data=master_bytes,
        mime_type=mime_type,
        metadata={
            "type": "master",
            "format": format,
            "page_count": page_count,
            "quality_breakdown": quality_breakdown or {},
        },
    )
    
    return create_output_package(
        job_id=job_id,
        files=[master_file],
        quality_score=quality_score,
        processing_mode="master",
    )


def create_adapted_package(
    job_id: str,
    adapted_files: List[Dict[str, Any]],
    quality_score: float,
    portal_schema: str,
) -> PackageResult:
    """
    Create a package for schema-adapted output.
    
    Args:
        job_id: Job identifier
        adapted_files: List of adapted file dicts with 'filename', 'data', 'dimensions'
        quality_score: Quality score
        portal_schema: Portal schema name
        
    Returns:
        PackageResult with ZIP containing adapted files
    """
    files: List[OutputFile] = []
    
    for f in adapted_files:
        ext = f.get("filename", "output.jpg").rsplit(".", 1)[-1].lower()
        mime_type = "application/pdf" if ext == "pdf" else "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
        
        output_file = OutputFile(
            filename=f"adapted/{f['filename']}",
            data=f["data"],
            mime_type=mime_type,
            metadata={
                "type": "adapted",
                "dimensions": f.get("dimensions", {}),
                "size_kb": f.get("size_kb", len(f["data"]) / 1024),
            },
        )
        files.append(output_file)
    
    return create_output_package(
        job_id=job_id,
        files=files,
        quality_score=quality_score,
        processing_mode="adapt",
        portal_schema=portal_schema,
    )


def create_combined_package(
    job_id: str,
    master_bytes: bytes,
    master_format: str,
    adapted_files: List[Dict[str, Any]],
    quality_score: float,
    portal_schema: str,
    page_count: int = 1,
) -> PackageResult:
    """
    Create a package containing both master and adapted outputs.
    
    Args:
        job_id: Job identifier
        master_bytes: Master document bytes
        master_format: Master format (pdf, jpeg)
        adapted_files: List of adapted file dicts
        quality_score: Quality score
        portal_schema: Portal schema name
        page_count: Number of pages in master
        
    Returns:
        PackageResult with ZIP containing all files
    """
    files: List[OutputFile] = []
    
    # Add master document
    ext = "pdf" if master_format.lower() == "pdf" else "jpg"
    mime_type = "application/pdf" if master_format.lower() == "pdf" else "image/jpeg"
    
    master_file = OutputFile(
        filename=f"master.{ext}",
        data=master_bytes,
        mime_type=mime_type,
        metadata={
            "type": "master",
            "format": master_format,
            "page_count": page_count,
        },
    )
    files.append(master_file)
    
    # Add adapted files
    for f in adapted_files:
        f_ext = f.get("filename", "output.jpg").rsplit(".", 1)[-1].lower()
        f_mime = "application/pdf" if f_ext == "pdf" else "image/jpeg" if f_ext in ("jpg", "jpeg") else "image/png"
        
        output_file = OutputFile(
            filename=f"adapted/{f['filename']}",
            data=f["data"],
            mime_type=f_mime,
            metadata={
                "type": "adapted",
                "dimensions": f.get("dimensions", {}),
                "size_kb": f.get("size_kb", len(f["data"]) / 1024),
            },
        )
        files.append(output_file)
    
    return create_output_package(
        job_id=job_id,
        files=files,
        quality_score=quality_score,
        processing_mode="combined",
        portal_schema=portal_schema,
    )


__all__ = [
    'create_output_package',
    'create_master_package',
    'create_adapted_package', 
    'create_combined_package',
    'OutputFile',
    'PackageResult',
    'PackageManifest',
]
