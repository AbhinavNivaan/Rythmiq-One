"""
CPU and performance metrics collection for Camber worker.

Provides accurate CPU time measurement using resource.getrusage() which
captures actual CPU consumption across all threads (important for OpenCV
and PaddleOCR which use multiple threads internally).

Usage:
    from metrics import MetricsCollector, StageTimer

    collector = MetricsCollector(job_id="...")
    
    with collector.stage("ocr"):
        result = perform_ocr(data)
    
    metrics = collector.finalize()
"""

from __future__ import annotations

import os
import resource
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Literal, Optional


# Track execution count for cold/warm classification
_execution_count = 0


def get_execution_temperature() -> Literal["cold", "warm"]:
    """
    Determine if this is a cold or warm execution.
    
    Cold = first execution in this container (model loading overhead)
    Warm = subsequent executions (models already in memory)
    """
    global _execution_count
    _execution_count += 1
    return "cold" if _execution_count == 1 else "warm"


def reset_execution_count() -> None:
    """Reset execution counter (for testing only)."""
    global _execution_count
    _execution_count = 0


@dataclass
class StageTiming:
    """Timing data for a single processing stage."""
    stage: str
    cpu_seconds: float
    wall_seconds: float
    cpu_efficiency: float  # cpu_time / wall_time (>1 means multi-threaded)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_seconds": round(self.cpu_seconds, 6),
            "wall_seconds": round(self.wall_seconds, 6),
            "cpu_efficiency": round(self.cpu_efficiency, 3),
        }


@dataclass
class DocumentCharacteristics:
    """Document properties that may affect processing time."""
    input_file_size_bytes: int = 0
    output_file_size_bytes: int = 0
    quality_score: float = 0.0
    ocr_confidence: float = 0.0
    enhancement_skipped: bool = False
    page_count: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_file_size_bytes": self.input_file_size_bytes,
            "output_file_size_bytes": self.output_file_size_bytes,
            "quality_score": round(self.quality_score, 4),
            "ocr_confidence": round(self.ocr_confidence, 4),
            "enhancement_skipped": self.enhancement_skipped,
            "page_count": self.page_count,
        }


@dataclass
class ProcessingMetrics:
    """Complete metrics for a job execution."""
    job_id: str
    execution_temperature: Literal["cold", "warm"]
    processing_path: Literal["fast", "standard"]
    total_cpu_seconds: float
    total_wall_seconds: float
    stages: Dict[str, StageTiming]
    characteristics: DocumentCharacteristics
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "execution_temperature": self.execution_temperature,
            "processing_path": self.processing_path,
            "total_cpu_seconds": round(self.total_cpu_seconds, 6),
            "total_wall_seconds": round(self.total_wall_seconds, 6),
            "cpu_efficiency": round(
                self.total_cpu_seconds / self.total_wall_seconds 
                if self.total_wall_seconds > 0 else 0, 
                3
            ),
            "stages": {
                name: timing.to_dict() 
                for name, timing in self.stages.items()
            },
            "characteristics": self.characteristics.to_dict(),
        }


def get_cpu_time() -> float:
    """
    Get current process CPU time in seconds (user + system).
    
    This uses resource.getrusage() which accurately measures CPU time
    including all threads spawned by the process. This is critical for
    libraries like PaddleOCR and OpenCV that use internal thread pools.
    
    Returns:
        Total CPU seconds consumed by this process
    """
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime


def get_memory_usage_mb() -> float:
    """Get current process memory usage in MB."""
    r = resource.getrusage(resource.RUSAGE_SELF)
    # maxrss is in kilobytes on Linux, bytes on macOS
    if os.uname().sysname == "Darwin":
        return r.ru_maxrss / (1024 * 1024)
    return r.ru_maxrss / 1024


class MetricsCollector:
    """
    Collects CPU and wall-clock timing for processing stages.
    
    Thread-safe timing using resource.getrusage() which aggregates
    CPU time across all threads in the process.
    
    Example:
        collector = MetricsCollector("job-123")
        
        with collector.stage("fetch"):
            data = download_file()
        
        with collector.stage("ocr"):
            text = extract_text(data)
        
        metrics = collector.finalize()
    """
    
    # Standard stage names for consistency
    STAGE_FETCH = "fetch"
    STAGE_QUALITY = "quality_scoring"
    STAGE_PRE_OCR = "pre_ocr"
    STAGE_ENHANCEMENT = "enhancement"
    STAGE_OCR = "ocr"
    STAGE_SCHEMA = "schema_adaptation"
    STAGE_UPLOAD = "upload"
    
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.execution_temperature = get_execution_temperature()
        self._stages: Dict[str, StageTiming] = {}
        self._characteristics = DocumentCharacteristics()
        self._start_wall = time.perf_counter()
        self._start_cpu = get_cpu_time()
        self._processing_path: Literal["fast", "standard"] = "standard"
        self._finalized = False
    
    @contextmanager
    def stage(self, name: str) -> Generator[None, None, None]:
        """
        Context manager to time a processing stage.
        
        Args:
            name: Stage identifier (use STAGE_* constants)
            
        Example:
            with collector.stage(MetricsCollector.STAGE_OCR):
                result = perform_ocr(data)
        """
        wall_start = time.perf_counter()
        cpu_start = get_cpu_time()
        
        try:
            yield
        finally:
            cpu_end = get_cpu_time()
            wall_end = time.perf_counter()
            
            cpu_seconds = cpu_end - cpu_start
            wall_seconds = wall_end - wall_start
            
            self._stages[name] = StageTiming(
                stage=name,
                cpu_seconds=cpu_seconds,
                wall_seconds=wall_seconds,
                cpu_efficiency=cpu_seconds / wall_seconds if wall_seconds > 0 else 0,
            )
    
    def record_stage(
        self, 
        name: str, 
        cpu_seconds: float, 
        wall_seconds: float
    ) -> None:
        """
        Manually record stage timing (for cases where context manager isn't suitable).
        """
        self._stages[name] = StageTiming(
            stage=name,
            cpu_seconds=cpu_seconds,
            wall_seconds=wall_seconds,
            cpu_efficiency=cpu_seconds / wall_seconds if wall_seconds > 0 else 0,
        )
    
    def set_characteristics(
        self,
        input_file_size_bytes: Optional[int] = None,
        output_file_size_bytes: Optional[int] = None,
        quality_score: Optional[float] = None,
        ocr_confidence: Optional[float] = None,
        enhancement_skipped: Optional[bool] = None,
        page_count: Optional[int] = None,
    ) -> None:
        """Update document characteristics."""
        if input_file_size_bytes is not None:
            self._characteristics.input_file_size_bytes = input_file_size_bytes
        if output_file_size_bytes is not None:
            self._characteristics.output_file_size_bytes = output_file_size_bytes
        if quality_score is not None:
            self._characteristics.quality_score = quality_score
        if ocr_confidence is not None:
            self._characteristics.ocr_confidence = ocr_confidence
        if enhancement_skipped is not None:
            self._characteristics.enhancement_skipped = enhancement_skipped
        if page_count is not None:
            self._characteristics.page_count = page_count
    
    def set_processing_path(self, path: Literal["fast", "standard"]) -> None:
        """Set the processing path classification."""
        self._processing_path = path
    
    def finalize(self) -> ProcessingMetrics:
        """
        Finalize and return collected metrics.
        
        Should be called once at the end of job processing.
        
        Returns:
            ProcessingMetrics with all timing data
        """
        if self._finalized:
            raise RuntimeError("Metrics already finalized")
        
        self._finalized = True
        
        total_wall = time.perf_counter() - self._start_wall
        total_cpu = get_cpu_time() - self._start_cpu
        
        return ProcessingMetrics(
            job_id=self.job_id,
            execution_temperature=self.execution_temperature,
            processing_path=self._processing_path,
            total_cpu_seconds=total_cpu,
            total_wall_seconds=total_wall,
            stages=self._stages,
            characteristics=self._characteristics,
        )
    
    def get_stage_summary(self) -> Dict[str, float]:
        """
        Get summary of CPU seconds by stage.
        
        Useful for debugging and logging.
        """
        return {
            name: timing.cpu_seconds 
            for name, timing in self._stages.items()
        }


# =============================================================================
# Convenience functions for simpler use cases
# =============================================================================

def measure_function(func, *args, **kwargs) -> tuple[Any, StageTiming]:
    """
    Measure a single function call.
    
    Returns:
        Tuple of (function_result, timing)
    """
    wall_start = time.perf_counter()
    cpu_start = get_cpu_time()
    
    result = func(*args, **kwargs)
    
    cpu_end = get_cpu_time()
    wall_end = time.perf_counter()
    
    cpu_seconds = cpu_end - cpu_start
    wall_seconds = wall_end - wall_start
    
    timing = StageTiming(
        stage="measured",
        cpu_seconds=cpu_seconds,
        wall_seconds=wall_seconds,
        cpu_efficiency=cpu_seconds / wall_seconds if wall_seconds > 0 else 0,
    )
    
    return result, timing


# =============================================================================
# Metrics aggregation utilities
# =============================================================================

@dataclass
class AggregatedMetrics:
    """Aggregated metrics across multiple jobs."""
    job_count: int
    avg_cpu_seconds: float
    p50_cpu_seconds: float
    p95_cpu_seconds: float
    p99_cpu_seconds: float
    min_cpu_seconds: float
    max_cpu_seconds: float
    total_cpu_seconds: float
    stage_breakdown: Dict[str, float]  # stage -> avg cpu seconds


def aggregate_metrics(metrics_list: List[ProcessingMetrics]) -> AggregatedMetrics:
    """
    Aggregate metrics from multiple jobs.
    
    Args:
        metrics_list: List of ProcessingMetrics from individual jobs
        
    Returns:
        AggregatedMetrics with statistical summaries
    """
    if not metrics_list:
        return AggregatedMetrics(
            job_count=0,
            avg_cpu_seconds=0,
            p50_cpu_seconds=0,
            p95_cpu_seconds=0,
            p99_cpu_seconds=0,
            min_cpu_seconds=0,
            max_cpu_seconds=0,
            total_cpu_seconds=0,
            stage_breakdown={},
        )
    
    cpu_times = sorted([m.total_cpu_seconds for m in metrics_list])
    n = len(cpu_times)
    
    # Collect stage data
    stage_totals: Dict[str, List[float]] = {}
    for m in metrics_list:
        for stage_name, timing in m.stages.items():
            if stage_name not in stage_totals:
                stage_totals[stage_name] = []
            stage_totals[stage_name].append(timing.cpu_seconds)
    
    stage_breakdown = {
        name: sum(times) / len(times) 
        for name, times in stage_totals.items()
    }
    
    return AggregatedMetrics(
        job_count=n,
        avg_cpu_seconds=sum(cpu_times) / n,
        p50_cpu_seconds=cpu_times[int(n * 0.50)],
        p95_cpu_seconds=cpu_times[int(n * 0.95)] if n > 20 else cpu_times[-1],
        p99_cpu_seconds=cpu_times[int(n * 0.99)] if n > 100 else cpu_times[-1],
        min_cpu_seconds=cpu_times[0],
        max_cpu_seconds=cpu_times[-1],
        total_cpu_seconds=sum(cpu_times),
        stage_breakdown=stage_breakdown,
    )


def calculate_monthly_cpu_hours(
    avg_cpu_seconds: float,
    docs_per_day: int,
    days_per_month: int = 30,
) -> float:
    """
    Calculate monthly CPU hours from per-document average.
    
    Args:
        avg_cpu_seconds: Average CPU seconds per document
        docs_per_day: Daily document volume
        days_per_month: Days in billing period (default 30)
        
    Returns:
        Total CPU hours for the month
    """
    total_seconds = avg_cpu_seconds * docs_per_day * days_per_month
    return total_seconds / 3600


def calculate_max_sustainable_volume(
    avg_cpu_seconds: float,
    budget_cpu_hours: float,
    days_per_month: int = 30,
) -> int:
    """
    Calculate maximum sustainable daily volume within CPU budget.
    
    Args:
        avg_cpu_seconds: Average CPU seconds per document
        budget_cpu_hours: Monthly CPU hour budget
        days_per_month: Days in billing period (default 30)
        
    Returns:
        Maximum documents per day
    """
    budget_seconds = budget_cpu_hours * 3600
    total_docs = budget_seconds / avg_cpu_seconds
    return int(total_docs / days_per_month)
