# Rythmiq One — Production Observability Specification

**Document:** P1.2 — Production Observability Design  
**Author:** SRE / Backend Platform Lead  
**Date:** January 30, 2026  
**Status:** EXECUTION-READY

---

## Executive Summary

This document defines the complete observability system for Rythmiq One's production launch. It covers structured logging, correlation IDs, metrics, storage, dashboards, and operational tradeoffs.

**Core Principle:** *If we cannot observe it in production, it does not exist.*

### Existing Infrastructure Assessment

| Component | Current State | Production-Ready |
|-----------|---------------|------------------|
| Correlation IDs | ✅ Implemented in API middleware | ❌ Not propagated to worker |
| Structured Logging | ⚠️ Partial (API only, missing fields) | ❌ Needs standardization |
| CPU Metrics | ✅ MetricsCollector implemented | ⚠️ Not persisted to DB |
| Metrics Tables | ✅ Schema exists (cpu_metrics) | ⚠️ No insert path |
| Dashboards | ❌ None | ❌ Needs implementation |

---

## STEP 1 — Structured JSON Logging Standard

### 1.1 JSON Log Schema Definition

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "RythmiqLogEntry",
  "type": "object",
  "required": ["timestamp", "level", "service", "message"],
  "properties": {
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "ISO-8601 UTC timestamp with millisecond precision"
    },
    "level": {
      "type": "string",
      "enum": ["DEBUG", "INFO", "WARN", "ERROR"],
      "description": "Log severity level"
    },
    "service": {
      "type": "string",
      "enum": ["api", "worker", "webhook"],
      "description": "Emitting service identifier"
    },
    "stage": {
      "type": "string",
      "enum": ["ingestion", "quality", "pre_ocr", "enhancement", "ocr", "schema", "packaging", "delivery"],
      "description": "Processing pipeline stage (worker-only)"
    },
    "job_id": {
      "type": "string",
      "format": "uuid",
      "description": "Job UUID for correlation"
    },
    "correlation_id": {
      "type": "string",
      "format": "uuid",
      "description": "Request trace ID (propagated across services)"
    },
    "user_id_hash": {
      "type": "string",
      "description": "SHA-256 hash of user_id (first 16 chars). NEVER log raw user_id"
    },
    "latency_ms": {
      "type": "number",
      "description": "Operation duration in milliseconds"
    },
    "cpu_seconds": {
      "type": "number",
      "description": "CPU time consumed (worker stages only)"
    },
    "error_code": {
      "type": "string",
      "description": "Error code from ErrorCode enum (e.g., OCR_FAILURE)"
    },
    "error_stage": {
      "type": "string",
      "description": "Processing stage where error occurred"
    },
    "http_method": {
      "type": "string",
      "description": "HTTP method (API only)"
    },
    "http_path": {
      "type": "string",
      "description": "Request path (API only)"
    },
    "http_status": {
      "type": "integer",
      "description": "Response status code (API only)"
    },
    "message": {
      "type": "string",
      "description": "Human-readable log message"
    },
    "extra": {
      "type": "object",
      "description": "Additional context (must NOT contain PII)"
    }
  }
}
```

### 1.2 Log Emission Points

| Service | Component | Log Events |
|---------|-----------|------------|
| **api** | Middleware | Request start, request complete |
| **api** | Routes | Job created, job status queried, output delivered |
| **api** | Auth | Auth success, auth failure (no user details) |
| **worker** | Entrypoint | Job started, job completed, job failed |
| **worker** | Stages | Stage start, stage complete (each of 7 stages) |
| **worker** | Metrics | Final metrics summary |
| **webhook** | Handler | Webhook received, webhook processed, webhook rejected |

### 1.3 Log Levels by Event Type

| Event Type | Level | Rationale |
|------------|-------|-----------|
| Request received | INFO | Audit trail |
| Request completed (2xx) | INFO | Audit trail |
| Request completed (4xx) | WARN | Client error, investigate patterns |
| Request completed (5xx) | ERROR | Requires attention |
| Job created | INFO | Audit trail |
| Stage started | DEBUG | Verbose, useful for debugging only |
| Stage completed | INFO | Processing visibility |
| Job completed (success) | INFO | Audit trail |
| Job completed (failure) | ERROR | Requires investigation |
| Webhook received | INFO | Audit trail |
| Webhook auth failure | WARN | Security monitoring |
| Cold start detected | WARN | Capacity planning signal |
| OCR rollback triggered | WARN | Quality monitoring |
| Enhancement skipped | DEBUG | Optimization tracking |

### 1.4 PII BLOCKLIST — NEVER LOG

```
╔══════════════════════════════════════════════════════════════════════════╗
║                        🚨 PII BLOCKLIST 🚨                               ║
║                                                                          ║
║  The following MUST NEVER appear in logs:                               ║
║                                                                          ║
║  • OCR extracted text (raw or partial)                                  ║
║  • Original filenames (use hash or job_id reference)                    ║
║  • User email addresses                                                 ║
║  • User IP addresses (hash if needed for fraud detection)               ║
║  • Raw user_id (use user_id_hash: SHA256(user_id)[:16])                ║
║  • File contents (binary or base64)                                     ║
║  • Schema field values from documents                                   ║
║  • Any data extracted from user-uploaded content                        ║
║  • Full storage paths (use job_id reference instead)                    ║
║  • Webhook payload bodies (log only metadata)                           ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

### 1.5 Example Log Entries

**Success Case — Job Completion:**
```json
{
  "timestamp": "2026-01-30T14:23:45.123Z",
  "level": "INFO",
  "service": "worker",
  "stage": "ocr",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "correlation_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "user_id_hash": "a3f2b8c1d4e5f6g7",
  "latency_ms": 1847,
  "cpu_seconds": 2.341,
  "message": "OCR stage completed",
  "extra": {
    "ocr_confidence": 0.87,
    "processing_path": "standard",
    "execution_temperature": "warm"
  }
}
```

**Failure Case — OCR Error:**
```json
{
  "timestamp": "2026-01-30T14:25:12.456Z",
  "level": "ERROR",
  "service": "worker",
  "stage": "ocr",
  "job_id": "550e8400-e29b-41d4-a716-446655440001",
  "correlation_id": "8d0f7780-8536-51ef-a55c-f18gd2g01bf8",
  "user_id_hash": "b4g3c9d2e5f6g8h9",
  "error_code": "OCR_FAILURE",
  "error_stage": "OCR",
  "message": "OCR extraction failed",
  "extra": {
    "processing_path": "standard",
    "quality_score": 0.34
  }
}
```

**API Request Log:**
```json
{
  "timestamp": "2026-01-30T14:23:44.001Z",
  "level": "INFO",
  "service": "api",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "correlation_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "user_id_hash": "a3f2b8c1d4e5f6g7",
  "http_method": "POST",
  "http_path": "/jobs",
  "http_status": 201,
  "latency_ms": 145,
  "message": "Request completed"
}
```

### 1.6 Logger Initialization Strategy

**Python Logger Factory (shared/logging.py):**

```python
"""
Unified structured logging for Rythmiq One.
All services MUST use this logger factory.
"""

import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional


def hash_user_id(user_id: str) -> str:
    """Create anonymized user identifier. First 16 chars of SHA-256."""
    return hashlib.sha256(user_id.encode()).hexdigest()[:16]


class StructuredFormatter(logging.Formatter):
    """JSON formatter with Rythmiq schema compliance."""
    
    def __init__(self, service: str):
        super().__init__()
        self.service = service
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": self.service,
            "message": record.getMessage(),
        }
        
        # Add optional fields from record.extra
        optional_fields = [
            "stage", "job_id", "correlation_id", "user_id_hash",
            "latency_ms", "cpu_seconds", "error_code", "error_stage",
            "http_method", "http_path", "http_status", "extra"
        ]
        
        for field in optional_fields:
            value = getattr(record, field, None)
            if value is not None:
                log_entry[field] = value
        
        return json.dumps(log_entry, separators=(",", ":"), ensure_ascii=False)


def get_logger(name: str, service: str) -> logging.Logger:
    """
    Create a structured logger.
    
    Args:
        name: Logger name (usually __name__)
        service: Service identifier (api, worker, webhook)
    
    Returns:
        Configured Logger instance
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter(service))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    
    return logger


# Convenience factory functions
def get_api_logger(name: str) -> logging.Logger:
    return get_logger(name, "api")


def get_worker_logger(name: str) -> logging.Logger:
    return get_logger(name, "worker")


def get_webhook_logger(name: str) -> logging.Logger:
    return get_logger(name, "webhook")
```

---

## STEP 2 — Correlation IDs & Traceability

### 2.1 Correlation ID Strategy

**Generation:**
- UUID v4 (128-bit random)
- Generated at API gateway on first request
- Client can provide via `X-Correlation-ID` header (trusted if valid UUID)

**Propagation Flow:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CORRELATION ID FLOW                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────┐   X-Correlation-ID    ┌─────────┐   job.input_metadata   ┌─────┐│
│  │Client │ ─────────────────────►│   API   │────────────────────────►│ DB ││
│  └───────┘   (optional)          └────┬────┘   correlation_id       └─────┘│
│                                       │                                     │
│                      ┌────────────────┘                                     │
│                      │ Camber payload includes                              │
│                      │ correlation_id in metadata                           │
│                      ▼                                                      │
│                 ┌─────────┐                                                 │
│                 │ Camber  │  Passes metadata to worker                      │
│                 │  Cloud  │                                                 │
│                 └────┬────┘                                                 │
│                      │                                                      │
│                      ▼ STDIN JSON includes correlation_id                   │
│                 ┌─────────┐                                                 │
│                 │ Worker  │  Logs include correlation_id                    │
│                 └────┬────┘                                                 │
│                      │                                                      │
│                      ▼ Webhook body includes correlation_id                 │
│                 ┌─────────┐                                                 │
│                 │ Webhook │  Final state logged with correlation_id         │
│                 │ Handler │                                                 │
│                 └─────────┘                                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Implementation Details

**API Middleware (existing, needs extension):**

Current: [app/api/middleware/correlation.py](../../app/api/middleware/correlation.py)
- ✅ Generates/extracts correlation_id
- ✅ Attaches to request.state
- ❌ Not stored in job record

**Required Change — Jobs Route:**

```python
# In create_job(), store correlation_id in job metadata:
job_data = {
    "user_id": str(user.id),
    "status": "pending",
    "portal_schema_version_id": portal_schema_id,
    "input_metadata": {
        "original_filename": body.filename,
        "mime_type": body.mime_type,
        "file_size_bytes": body.file_size_bytes,
        "correlation_id": correlation_id,  # ← ADD THIS
    },
}
```

**Required Change — Camber Payload:**

```python
# Include correlation_id in Camber submission:
camber_payload = {
    "job_id": str(job_id),
    "user_id": str(user.id),
    "storage_path": storage_path,
    "portal_schema_id": str(portal_schema_id),
    "correlation_id": correlation_id,  # ← ADD THIS
}
```

**Required Change — Worker Entrypoint:**

```python
# In worker, extract and use correlation_id:
correlation_id = payload.get("correlation_id", "unknown")

# Add to all log calls:
logger.info(
    "Stage completed",
    extra={
        "correlation_id": correlation_id,
        "job_id": job_id,
        "stage": "ocr",
        # ...
    }
)
```

### 2.3 Example Correlated Log Sequence

**Complete job timeline reconstructed from logs:**

```json
// 1. API receives request
{"timestamp":"2026-01-30T14:23:44.001Z","level":"INFO","service":"api","correlation_id":"7c9e6679-7425-40de-944b-e07fc1f90ae7","http_method":"POST","http_path":"/jobs","message":"Request started"}

// 2. Job created
{"timestamp":"2026-01-30T14:23:44.089Z","level":"INFO","service":"api","job_id":"550e8400-e29b-41d4-a716-446655440000","correlation_id":"7c9e6679-7425-40de-944b-e07fc1f90ae7","message":"Job created in pending state"}

// 3. API request completes
{"timestamp":"2026-01-30T14:23:44.145Z","level":"INFO","service":"api","job_id":"550e8400-e29b-41d4-a716-446655440000","correlation_id":"7c9e6679-7425-40de-944b-e07fc1f90ae7","http_status":201,"latency_ms":144,"message":"Request completed"}

// 4. Worker starts (may be delayed)
{"timestamp":"2026-01-30T14:23:47.234Z","level":"INFO","service":"worker","job_id":"550e8400-e29b-41d4-a716-446655440000","correlation_id":"7c9e6679-7425-40de-944b-e07fc1f90ae7","message":"Job processing started","extra":{"execution_temperature":"warm"}}

// 5. Worker stages
{"timestamp":"2026-01-30T14:23:47.456Z","level":"INFO","service":"worker","job_id":"550e8400-e29b-41d4-a716-446655440000","correlation_id":"7c9e6679-7425-40de-944b-e07fc1f90ae7","stage":"quality","cpu_seconds":0.087,"message":"Stage completed"}

{"timestamp":"2026-01-30T14:23:49.303Z","level":"INFO","service":"worker","job_id":"550e8400-e29b-41d4-a716-446655440000","correlation_id":"7c9e6679-7425-40de-944b-e07fc1f90ae7","stage":"ocr","cpu_seconds":2.341,"message":"Stage completed"}

// 6. Worker completes
{"timestamp":"2026-01-30T14:23:50.891Z","level":"INFO","service":"worker","job_id":"550e8400-e29b-41d4-a716-446655440000","correlation_id":"7c9e6679-7425-40de-944b-e07fc1f90ae7","cpu_seconds":3.456,"latency_ms":3657,"message":"Job completed successfully","extra":{"processing_path":"standard","quality_score":0.72,"ocr_confidence":0.87}}

// 7. Webhook received
{"timestamp":"2026-01-30T14:23:51.012Z","level":"INFO","service":"webhook","job_id":"550e8400-e29b-41d4-a716-446655440000","correlation_id":"7c9e6679-7425-40de-944b-e07fc1f90ae7","message":"Camber webhook received","extra":{"status":"success"}}

// 8. Webhook processed
{"timestamp":"2026-01-30T14:23:51.234Z","level":"INFO","service":"webhook","job_id":"550e8400-e29b-41d4-a716-446655440000","correlation_id":"7c9e6679-7425-40de-944b-e07fc1f90ae7","message":"Job transitioned to completed"}
```

**Query to reconstruct timeline:**

```sql
-- Logs stored in external logging service (Logtail, Datadog, etc.)
-- Query by correlation_id to see complete flow:
SELECT * FROM logs 
WHERE correlation_id = '7c9e6679-7425-40de-944b-e07fc1f90ae7'
ORDER BY timestamp ASC;
```

---

## STEP 3 — Metrics Definition

### 3.1 Metric Catalog

| Metric Name | Type | Labels | Description |
|-------------|------|--------|-------------|
| `rythmiq_jobs_total` | Counter | status, processing_path | Total jobs processed |
| `rythmiq_job_latency_seconds` | Histogram | processing_path, execution_temp | End-to-end job latency |
| `rythmiq_job_cpu_seconds` | Histogram | processing_path, stage | CPU time per job/stage |
| `rythmiq_errors_total` | Counter | error_code, stage | Errors by type |
| `rythmiq_quality_score` | Histogram | processing_path | Input quality distribution |
| `rythmiq_ocr_confidence` | Histogram | processing_path | OCR confidence distribution |
| `rythmiq_cold_starts_total` | Counter | - | Cold start count |
| `rythmiq_api_requests_total` | Counter | method, path, status | API request count |
| `rythmiq_api_latency_seconds` | Histogram | method, path | API response latency |

### 3.2 Metric Type Definitions

**Counter Metrics (monotonically increasing):**

```python
# Jobs processed
rythmiq_jobs_total{status="success", processing_path="fast"} 1523
rythmiq_jobs_total{status="success", processing_path="standard"} 8741  
rythmiq_jobs_total{status="failed", processing_path="standard"} 127

# Errors by code
rythmiq_errors_total{error_code="OCR_FAILURE", stage="OCR"} 45
rythmiq_errors_total{error_code="CORRUPT_DATA", stage="FETCH"} 12
rythmiq_errors_total{error_code="SCHEMA_INVALID", stage="TRANSFORM"} 8

# Cold starts
rythmiq_cold_starts_total 89
```

**Histogram Metrics (distribution tracking):**

```python
# CPU time buckets: 0.1, 0.25, 0.5, 1, 2, 5, 10, 30 seconds
rythmiq_job_cpu_seconds_bucket{processing_path="fast", le="0.5"} 1420
rythmiq_job_cpu_seconds_bucket{processing_path="fast", le="1.0"} 1510
rythmiq_job_cpu_seconds_bucket{processing_path="standard", le="2.0"} 6500
rythmiq_job_cpu_seconds_bucket{processing_path="standard", le="5.0"} 8650

# Quality score buckets: 0.25, 0.5, 0.65, 0.75, 0.85, 0.95, 1.0
rythmiq_quality_score_bucket{le="0.5"} 890
rythmiq_quality_score_bucket{le="0.75"} 5230
rythmiq_quality_score_bucket{le="0.95"} 9800

# OCR confidence buckets: 0.25, 0.5, 0.65, 0.75, 0.85, 0.95, 1.0
rythmiq_ocr_confidence_bucket{le="0.5"} 450
rythmiq_ocr_confidence_bucket{le="0.85"} 7800
```

**Gauge Metrics (point-in-time values):**

```python
# Current month CPU usage (updated hourly)
rythmiq_cpu_hours_current_month 78.5

# Jobs in processing state
rythmiq_jobs_in_progress 12
```

### 3.3 Aggregation Windows

| Metric Type | Raw Granularity | Rollup 1 | Rollup 2 |
|-------------|-----------------|----------|----------|
| Counters | Per-event | 1-minute | 1-hour |
| Histograms | Per-event | 1-minute | 1-hour |
| Gauges | 1-minute | 5-minute | 1-hour |

### 3.4 Metric Emission Points

| Metric | Emitter | Trigger |
|--------|---------|---------|
| `rythmiq_jobs_total` | Worker | Job completion |
| `rythmiq_job_latency_seconds` | Worker | Job completion |
| `rythmiq_job_cpu_seconds` | Worker | Stage completion |
| `rythmiq_errors_total` | Worker, API | Error occurrence |
| `rythmiq_quality_score` | Worker | Quality assessment complete |
| `rythmiq_ocr_confidence` | Worker | OCR complete |
| `rythmiq_cold_starts_total` | Worker | Cold start detected |
| `rythmiq_api_requests_total` | API | Request complete |
| `rythmiq_api_latency_seconds` | API | Request complete |

---

## STEP 4 — Metrics Storage Strategy

### 4.1 Decision: Hybrid (Supabase + Future TSDB)

**Recommendation: START WITH SUPABASE ONLY**

| Storage | Use Case | Justification |
|---------|----------|---------------|
| **Supabase** | Per-job metrics, billing, postmortems | Already exists, sufficient for 1K docs/day |
| **External TSDB** | NOT needed for launch | Defer until >10K docs/day or real-time alerts needed |

**Rationale:**
- 1,000 docs/day = 30,000 rows/month in cpu_metrics
- Supabase handles this easily with proper indexes
- Materialized views already exist for aggregations
- Cost: $0 additional (included in Supabase plan)

**When to add external TSDB:**
- Volume exceeds 10K docs/day
- Need sub-minute real-time alerting
- Need Prometheus/Grafana native integration

### 4.2 Supabase Table Usage

**Existing Table: `cpu_metrics`**

Already defined in [20260130_create_cpu_metrics.sql](../../db/migrations/20260130_create_cpu_metrics.sql):
- ✅ Per-job CPU breakdown
- ✅ Processing path tracking
- ✅ Cold/warm classification
- ✅ Materialized views for hourly/daily aggregates

**Missing: Insert Path from Worker**

Required addition to worker pipeline:

```python
# worker/metrics_persistence.py
"""Persist metrics to Supabase after job completion."""

import os
from typing import Optional
from supabase import create_client

from metrics import ProcessingMetrics


def persist_metrics(metrics: ProcessingMetrics) -> bool:
    """
    Write job metrics to Supabase.
    
    Called after successful job completion.
    Failures are logged but don't fail the job.
    """
    try:
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
        
        if not supabase_url or not supabase_key:
            return False  # Silently skip in dev
        
        client = create_client(supabase_url, supabase_key)
        
        stages = metrics.stages
        
        client.table("cpu_metrics").insert({
            "job_id": metrics.job_id,
            "execution_temperature": metrics.execution_temperature,
            "processing_path": metrics.processing_path,
            "total_cpu_seconds": metrics.total_cpu_seconds,
            "total_wall_seconds": metrics.total_wall_seconds,
            "fetch_cpu_seconds": stages.get("fetch", {}).get("cpu_seconds", 0),
            "quality_cpu_seconds": stages.get("quality_scoring", {}).get("cpu_seconds", 0),
            "pre_ocr_cpu_seconds": stages.get("pre_ocr", {}).get("cpu_seconds", 0),
            "enhancement_cpu_seconds": stages.get("enhancement", {}).get("cpu_seconds", 0),
            "ocr_cpu_seconds": stages.get("ocr", {}).get("cpu_seconds", 0),
            "schema_cpu_seconds": stages.get("schema_adaptation", {}).get("cpu_seconds", 0),
            "upload_cpu_seconds": stages.get("upload", {}).get("cpu_seconds", 0),
            "input_file_size_bytes": metrics.characteristics.input_file_size_bytes,
            "output_file_size_bytes": metrics.characteristics.output_file_size_bytes,
            "quality_score": metrics.characteristics.quality_score,
            "ocr_confidence": metrics.characteristics.ocr_confidence,
            "enhancement_skipped": metrics.characteristics.enhancement_skipped,
            "page_count": metrics.characteristics.page_count,
        }).execute()
        
        return True
        
    except Exception as e:
        # Log but don't fail job
        logger.warning(f"Failed to persist metrics: {e}")
        return False
```

### 4.3 New Table: `error_events`

For error tracking and pattern analysis:

```sql
-- Add to migrations
CREATE TABLE IF NOT EXISTS error_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL,
    error_code TEXT NOT NULL,
    error_stage TEXT NOT NULL,
    processing_path TEXT,
    quality_score FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_error_events_code ON error_events(error_code, created_at DESC);
CREATE INDEX idx_error_events_job ON error_events(job_id);
CREATE INDEX idx_error_events_time ON error_events(created_at DESC);

-- Aggregation view
CREATE MATERIALIZED VIEW error_events_daily AS
SELECT 
    date_trunc('day', created_at) AS day,
    error_code,
    error_stage,
    COUNT(*) AS count
FROM error_events
GROUP BY day, error_code, error_stage;
```

### 4.4 Indexes Already Present

From existing migration:
- `idx_cpu_metrics_job_id` — Lookup by job
- `idx_cpu_metrics_created_at` — Time-series queries
- `idx_cpu_metrics_processing_path` — Path analysis
- `idx_cpu_metrics_temperature` — Cold/warm analysis
- `idx_cpu_metrics_total_cpu` — Budget aggregation

### 4.5 Retention Policy

| Table | Retention | Rationale |
|-------|-----------|-----------|
| `cpu_metrics` | 90 days | Sufficient for capacity planning |
| `cpu_metrics_hourly` | 90 days | Dashboard queries |
| `cpu_metrics_daily` | 1 year | Monthly reporting |
| `error_events` | 90 days | Pattern analysis |
| `jobs` | Indefinite | Audit trail (required) |

**Automated Cleanup (pg_cron):**

```sql
-- Schedule weekly cleanup
SELECT cron.schedule(
    'cleanup-old-metrics',
    '0 3 * * 0',  -- Sunday 3 AM
    $$
    DELETE FROM cpu_metrics WHERE created_at < now() - interval '90 days';
    DELETE FROM error_events WHERE created_at < now() - interval '90 days';
    $$
);
```

---

## STEP 5 — Dashboards (Operator-Focused)

### 5.1 Tool Recommendation: Retool

**Decision: Retool (not Grafana)**

| Factor | Retool | Grafana |
|--------|--------|---------|
| Supabase integration | ✅ Native | ⚠️ Requires plugin |
| Setup complexity | Low | Medium |
| Cost | Free tier sufficient | Free (OSS) |
| Time-series | Adequate | Excellent |
| Internal tools | ✅ Excellent | ❌ Not designed for |
| Team familiarity | ✅ Already used | ❌ New tool |

**Rationale:** Retool provides direct Supabase queries, adequate charting, and can build internal tools (like job lookup) alongside dashboards. Grafana is overkill for launch volume.

### 5.2 Dashboard 1: Operations (On-Call)

**Purpose:** Real-time health monitoring for incident response

**Refresh Rate:** 1 minute

**Layout:**

```
┌────────────────────────────────────────────────────────────────────────────┐
│ RYTHMIQ ONE — OPERATIONS DASHBOARD                      [Last 24 Hours ▼] │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌───────────────────┐  │
│  │ JOBS (24H)          │  │ ERROR RATE          │  │ P95 LATENCY       │  │
│  │                     │  │                     │  │                   │  │
│  │      1,247          │  │       0.8%          │  │     3.2s          │  │
│  │   ▲ +12% vs yday    │  │   ✅ Under 1%       │  │  ✅ Under 30s     │  │
│  └─────────────────────┘  └─────────────────────┘  └───────────────────┘  │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ JOB THROUGHPUT (HOURLY)                                             │  │
│  │                                                                      │  │
│  │  80 ┤ ▄▄   ▄▄▄                                                      │  │
│  │  60 ┤▄██▄▄▄████▄▄▄   ▄▄                                            │  │
│  │  40 ┤████████████████████▄▄▄▄▄▄                                    │  │
│  │  20 ┤                                                               │  │
│  │   0 ┼────────────────────────────────────────────────              │  │
│  │     00  02  04  06  08  10  12  14  16  18  20  22                 │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ ERROR RATE OVER TIME                                                │  │
│  │                                                                      │  │
│  │ 2% ┤                                                                │  │
│  │ 1% ┤───────────────────────────────────────────  ← Threshold       │  │
│  │ 0% ┤▁▁▁▁▁▁▁▁▁▁▁▂▁▁▁▁▁▁▁▁▃▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁                    │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ RECENT ERRORS                                                       │  │
│  │ ─────────────────────────────────────────────────────────────────── │  │
│  │ 14:23:45  OCR_FAILURE     550e8400...  Standard path               │  │
│  │ 13:45:12  CORRUPT_DATA    661f9511...  Standard path               │  │
│  │ 12:01:33  SCHEMA_INVALID  772g0622...  Fast path                   │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

**Queries:**

```sql
-- Job count (24h)
SELECT COUNT(*) FROM jobs 
WHERE created_at > now() - interval '24 hours';

-- Error rate (24h)
SELECT 
    COUNT(*) FILTER (WHERE status = 'failed') * 100.0 / COUNT(*) 
FROM jobs 
WHERE created_at > now() - interval '24 hours';

-- P95 latency (from cpu_metrics)
SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY total_wall_seconds)
FROM cpu_metrics
WHERE created_at > now() - interval '24 hours';

-- Hourly throughput
SELECT 
    date_trunc('hour', created_at) AS hour,
    COUNT(*) AS jobs
FROM jobs
WHERE created_at > now() - interval '24 hours'
GROUP BY hour
ORDER BY hour;

-- Recent errors
SELECT 
    e.created_at,
    e.error_code,
    e.job_id,
    e.processing_path
FROM error_events e
ORDER BY e.created_at DESC
LIMIT 10;
```

### 5.3 Dashboard 2: Cost Monitoring (CPU Budget)

**Purpose:** Track CPU consumption against 200 hour/month budget

**Refresh Rate:** 15 minutes

**Layout:**

```
┌────────────────────────────────────────────────────────────────────────────┐
│ RYTHMIQ ONE — CPU BUDGET DASHBOARD                      [January 2026 ▼]  │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌───────────────────┐  │
│  │ CPU HOURS USED      │  │ PROJECTED EOM       │  │ BUDGET REMAINING  │  │
│  │                     │  │                     │  │                   │  │
│  │      78.5 hrs       │  │     162.3 hrs       │  │    121.5 hrs      │  │
│  │   █████████░░░░░░░  │  │   ✅ Under 200      │  │   ✅ 61% left     │  │
│  │      39% of 200     │  │                     │  │                   │  │
│  └─────────────────────┘  └─────────────────────┘  └───────────────────┘  │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ CPU CONSUMPTION (DAILY)                                             │  │
│  │                                                                      │  │
│  │ 10h ┤     ▄▄                                        Budget pace ──  │  │
│  │  8h ┤   ▄████▄▄                                                     │  │
│  │  6h ┤ ▄████████████▄▄▄▄                                            │  │
│  │  4h ┤▄██████████████████▄▄                                         │  │
│  │  2h ┤                                                               │  │
│  │   0 ┼────────────────────────────────────────────────              │  │
│  │     1   5   10   15   20   25   30                                 │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ CPU BY PROCESSING PATH                                              │  │
│  │                                                                      │  │
│  │ Standard ████████████████████████████████████████████  82% (64.4h) │  │
│  │ Fast     █████████                                      18% (14.1h) │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ AVG CPU PER DOCUMENT                                                │  │
│  │                                                                      │  │
│  │ Overall:   0.68s  ✅ Under 0.72s target                             │  │
│  │ Standard:  0.82s                                                    │  │
│  │ Fast:      0.31s                                                    │  │
│  │ Cold:      1.24s  (includes model loading)                          │  │
│  │ Warm:      0.65s                                                    │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

**Queries:**

```sql
-- Current month usage (use existing function)
SELECT * FROM get_monthly_cpu_usage();

-- Daily breakdown
SELECT day, total_cpu_hours 
FROM cpu_metrics_daily
WHERE day >= date_trunc('month', now())
ORDER BY day;

-- Average CPU by path
SELECT 
    processing_path,
    AVG(total_cpu_seconds) AS avg_cpu,
    SUM(total_cpu_seconds) / 3600.0 AS total_hours
FROM cpu_metrics
WHERE created_at >= date_trunc('month', now())
GROUP BY processing_path;

-- Cold vs warm
SELECT 
    execution_temperature,
    AVG(total_cpu_seconds) AS avg_cpu
FROM cpu_metrics
WHERE created_at >= date_trunc('month', now())
GROUP BY execution_temperature;
```

### 5.4 Dashboard 3: Product Health

**Purpose:** Quality and performance trends for product decisions

**Refresh Rate:** 1 hour

**Layout:**

```
┌────────────────────────────────────────────────────────────────────────────┐
│ RYTHMIQ ONE — PRODUCT HEALTH DASHBOARD                  [Last 7 Days ▼]   │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ PROCESSING PATH DISTRIBUTION                                        │  │
│  │                                                                      │  │
│  │          ████████████████████████████░░░░░░░░                       │  │
│  │          │←── Standard 76% ───→│←─ Fast 24%─→│                      │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌──────────────────────────────────┐  ┌────────────────────────────────┐ │
│  │ QUALITY SCORE DISTRIBUTION       │  │ OCR CONFIDENCE DISTRIBUTION    │ │
│  │                                  │  │                                │ │
│  │     ┌───┐                        │  │                    ┌───┐       │ │
│  │     │   │ ┌───┐                  │  │              ┌───┐ │   │       │ │
│  │ ┌───┤   ├─┤   │                  │  │        ┌───┐│   │ │   │       │ │
│  │ │   │   │ │   │ ┌───┐            │  │  ┌───┐ │   ││   │ │   │       │ │
│  │ ├───┴───┴─┴───┴─┴───┴───         │  │  ├───┴─┴───┴┴───┴─┴───┴───    │ │
│  │ 0.25 0.50 0.65 0.75 0.85 0.95   │  │  0.25 0.50 0.65 0.75 0.85 0.95│ │
│  │                                  │  │                                │ │
│  │ Median: 0.72                     │  │ Median: 0.84                   │ │
│  └──────────────────────────────────┘  └────────────────────────────────┘ │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ LATENCY PERCENTILES (TREND)                                         │  │
│  │                                                                      │  │
│  │ 6s ┤                                              ── P99            │  │
│  │ 4s ┤────────────────────────────────────────────  ── P95            │  │
│  │ 2s ┤════════════════════════════════════════════  ── P50            │  │
│  │ 0s ┼────────────────────────────────────────────────                │  │
│  │    Mon   Tue   Wed   Thu   Fri   Sat   Sun                         │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ ERROR BREAKDOWN                                                     │  │
│  │                                                                      │  │
│  │ OCR_FAILURE      ███████████████  45 (52%)                          │  │
│  │ CORRUPT_DATA     █████           12 (14%)                           │  │
│  │ SCHEMA_INVALID   ████             8 (9%)                            │  │
│  │ Other            ██████████████  21 (25%)                           │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## STEP 6 — Sampling, Performance & Tradeoffs

### 6.1 Logging Strategy

| What | Decision | Rationale |
|------|----------|-----------|
| **API requests** | 100% logged | Low volume, audit requirement |
| **Job lifecycle events** | 100% logged | Traceability requirement |
| **Stage-level events** | 100% logged | Debugging, postmortems |
| **DEBUG level logs** | Disabled in prod | Enable via env var for debugging |

**No sampling needed at launch volume (1K docs/day).**

### 6.2 Metrics Strategy

| What | Decision | Rationale |
|------|----------|-----------|
| **Per-job metrics** | 100% captured | CPU tracking requirement |
| **Error events** | 100% captured | Low volume, high value |
| **API latency** | 100% captured | SLA monitoring |

**No sampling needed.** At 1K docs/day, we have ~30K metrics rows/month. This is trivial for Supabase.

### 6.3 When to Reconsider

| Trigger | Action |
|---------|--------|
| > 10K docs/day | Consider sampling stage-level logs (keep job-level) |
| > 100K rows/month | Consider external TSDB for metrics |
| Log costs > $50/month | Reduce DEBUG logging, sample stage events |

### 6.4 Always-Log Events (Never Sample)

```
✅ NEVER SAMPLE:
- Job created
- Job completed (success or failure)
- Webhook received
- Errors (all)
- Cold starts
- API 5xx responses
- Auth failures
```

### 6.5 Performance Impact

| Operation | Overhead | Acceptable |
|-----------|----------|------------|
| Structured log emission | ~0.1ms per log | ✅ Yes |
| Metrics DB insert | ~5ms per job | ✅ Yes (async) |
| Correlation ID propagation | ~0.01ms | ✅ Yes |

**Total observability overhead: < 10ms per job (~0.3% of typical 3s job)**

---

## STEP 7 — Implementation Checklist

### 7.1 Priority Sequence

```
╔══════════════════════════════════════════════════════════════════════════╗
║                    IMPLEMENTATION PRIORITY                               ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  PHASE 1 — MUST SHIP (Week -1 before launch)                            ║
║  ──────────────────────────────────────────────────────────────────────  ║
║  □ Create shared/logging.py (structured logger)                         ║
║  □ Update API middleware to use structured logger                       ║
║  □ Update worker to use structured logger                               ║
║  □ Add correlation_id propagation (API → Camber → Worker)              ║
║  □ Add metrics persistence (worker → cpu_metrics table)                 ║
║  □ Add error_events table and persistence                               ║
║  □ Create Operations Dashboard (Retool)                                 ║
║                                                                          ║
║  PHASE 2 — SHIP IN WEEK 1                                               ║
║  ──────────────────────────────────────────────────────────────────────  ║
║  □ Create Cost Monitoring Dashboard                                     ║
║  □ Create Product Health Dashboard                                      ║
║  □ Set up materialized view refresh (pg_cron)                          ║
║  □ Add retention cleanup job                                            ║
║                                                                          ║
║  PHASE 3 — SHIP IN MONTH 1                                              ║
║  ──────────────────────────────────────────────────────────────────────  ║
║  □ Alert rules (error rate > 2%, P95 > 30s)                            ║
║  □ Anomaly detection (CPU spike alerts)                                 ║
║  □ Log shipping to external service (if needed)                         ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

### 7.2 Detailed Task Breakdown

| # | Task | File(s) | Estimate | Owner |
|---|------|---------|----------|-------|
| 1 | Create structured logger | `shared/logging.py` | 2h | Backend |
| 2 | Integrate logger in API | `app/api/main.py`, middleware | 2h | Backend |
| 3 | Integrate logger in worker | `worker/entrypoint.py`, stages | 3h | Backend |
| 4 | Correlation ID propagation | `app/api/routes/jobs.py`, worker | 2h | Backend |
| 5 | Metrics persistence | `worker/metrics_persistence.py` | 2h | Backend |
| 6 | Error events table | `db/migrations/`, worker | 2h | Backend |
| 7 | Operations dashboard | Retool | 4h | SRE |
| 8 | Cost dashboard | Retool | 3h | SRE |
| 9 | Product dashboard | Retool | 3h | SRE |
| 10 | MV refresh setup | Supabase pg_cron | 1h | SRE |

**Total: ~24 engineering hours**

### 7.3 Risks If Observability Is Incomplete

| Missing | Risk | Impact |
|---------|------|--------|
| Structured logging | Blind during incidents | Cannot debug production issues |
| Correlation IDs | Cannot trace job flow | Extended incident resolution time |
| Metrics persistence | No CPU tracking | Possible budget overrun undetected |
| Cost dashboard | Budget surprise | Unexpected bills, forced optimization |
| Operations dashboard | Slow incident detection | Extended user impact |

### 7.4 Week 1 Post-Launch Monitoring Checklist

```
╔══════════════════════════════════════════════════════════════════════════╗
║                    WEEK 1 MONITORING CHECKLIST                           ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  DAILY (check every morning):                                           ║
║  □ Error rate (target: < 1%)                                            ║
║  □ P95 latency (target: < 30s)                                          ║
║  □ CPU consumption rate (on track for < 200 hrs/month?)                 ║
║  □ Cold start count (should decrease after initial ramp)                ║
║                                                                          ║
║  WATCH FOR:                                                              ║
║  □ Error rate spike > 2% → Investigate immediately                      ║
║  □ P95 latency > 30s → Check for degraded OCR performance              ║
║  □ CPU burn rate > 10 hrs/day → Review processing paths                ║
║  □ Cold starts > 10% of jobs → Container scaling issue                  ║
║  □ Quality score distribution shift → Input quality change             ║
║                                                                          ║
║  EXPECTED PATTERNS:                                                      ║
║  □ Higher error rate on day 1-2 (edge cases discovered)                ║
║  □ Higher cold start rate on day 1 (container pool warming)            ║
║  □ Latency improvement after day 2 (warm containers)                   ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
```

### 7.5 Observability Definition of Done

Before launch, confirm:

- [ ] Can trace any job from API request to webhook completion using correlation_id
- [ ] Can query CPU consumption for current month
- [ ] Can see error rate trend in last 24 hours
- [ ] Can identify the most common error codes
- [ ] Can project end-of-month CPU usage
- [ ] No PII appears in any log samples (verified)
- [ ] Dashboards load in < 5 seconds

---

## Appendix A: File Manifest

| File | Purpose | Status |
|------|---------|--------|
| `shared/logging.py` | Structured logger factory | **TO CREATE** |
| `worker/metrics_persistence.py` | Metrics DB insert | **TO CREATE** |
| `db/migrations/20260131_error_events.sql` | Error tracking table | **TO CREATE** |
| `app/api/middleware/correlation.py` | Correlation ID handling | **EXISTS** (minor update) |
| `app/api/middleware/logging.py` | API logging middleware | **EXISTS** (replace with structured) |
| `worker/metrics.py` | CPU metrics collection | **EXISTS** |
| `db/migrations/20260130_create_cpu_metrics.sql` | CPU metrics table | **EXISTS** |

---

## Appendix B: Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG/INFO/WARN/ERROR) |
| `SUPABASE_URL` | Yes | - | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Yes | - | Service role key for metrics insert |
| `ENABLE_METRICS_PERSISTENCE` | No | `true` | Disable metrics writes in dev |

---

**Document End**

*This specification is EXECUTION-READY. Proceed with implementation.*
