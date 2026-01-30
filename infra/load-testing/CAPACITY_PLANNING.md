# Rythmiq One: Load Testing & Capacity Planning Report

**Date:** January 30, 2026  
**Phase:** 2A Production Readiness  
**Author:** Infrastructure & Performance Engineering  
**Status:** INSTRUMENTATION → MEASUREMENT → ANALYSIS

---

## Executive Summary

| Metric | Target | Current Status |
|--------|--------|----------------|
| CPU Budget | 200 CPU-hours/month | **PENDING MEASUREMENT** |
| Document Volume | 1,000 docs/day | Design Target |
| Fast Path Latency | 2–3 seconds | Estimated (Mock Camber) |
| Node Configuration | 16 cores | Confirmed |

**CRITICAL**: Previous estimate of ~270 CPU-hours/month suggests **35% budget overage**. This document defines the measurement framework to obtain ACTUAL values.

---

## STEP 1: CPU & Latency Instrumentation

### 1.1 Instrumentation Points (MANDATORY)

The worker pipeline consists of 6 sequential stages. Each must be individually instrumented:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        WORKER PIPELINE                                 │
├────────────────────────────────────────────────────────────────────────┤
│  FETCH → QUALITY → ENHANCE → OCR → SCHEMA → UPLOAD                    │
│    │        │         │        │       │        │                     │
│    ▼        ▼         ▼        ▼       ▼        ▼                     │
│   T1       T2        T3       T4      T5       T6                     │
│  CPU1     CPU2      CPU3     CPU4    CPU5     CPU6                    │
└────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Measurement Methodology

#### CPU Time Measurement (Python `time` module)

For CPU-bound operations, we measure **process CPU time** (not wall time):

```python
import time
import os
import resource

def get_cpu_time() -> float:
    """Get current process CPU time in seconds (user + system)."""
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime

def measure_stage(stage_name: str, func, *args, **kwargs):
    """Measure CPU time and wall time for a processing stage."""
    wall_start = time.perf_counter()
    cpu_start = get_cpu_time()
    
    result = func(*args, **kwargs)
    
    cpu_end = get_cpu_time()
    wall_end = time.perf_counter()
    
    return result, {
        "stage": stage_name,
        "cpu_seconds": cpu_end - cpu_start,
        "wall_seconds": wall_end - wall_start,
        "cpu_efficiency": (cpu_end - cpu_start) / (wall_end - wall_start) if (wall_end - wall_start) > 0 else 0,
    }
```

#### Why This is Trustworthy

| Concern | Mitigation |
|---------|------------|
| Multi-threaded libraries (OpenCV, PaddleOCR) | `resource.getrusage()` includes all thread CPU time within the process |
| Context switches | We measure RUSAGE_SELF which accounts for actual CPU consumption |
| I/O wait inflation | CPU time excludes I/O wait; wall time captures it separately |
| Mock Camber skew | Instrumentation captures actual CPU regardless of mock/real mode |

### 1.3 Stage-by-Stage Instrumentation Hooks

#### Location: `worker/worker.py` → `process_job()`

```python
# Stage instrumentation points in process_job():

STAGES = [
    ("fetch", "storage.download()"),
    ("quality_scoring", "assess_quality()"),
    ("pre_ocr", "extract_text_safe() - baseline"),
    ("enhancement", "enhance_image()"),
    ("ocr", "extract_text_safe() - final"),
    ("schema_adaptation", "adapt_to_schema()"),
    ("upload", "storage.upload_master() + upload_preview()"),
]
```

### 1.4 Cold vs Warm Execution Tracking

**Problem**: PaddleOCR has significant first-run overhead (model loading).

**Solution**: Track execution index per container lifetime:

```python
# Global counter (reset per container spawn)
_execution_count = 0

def track_execution_temperature():
    global _execution_count
    _execution_count += 1
    return "cold" if _execution_count == 1 else "warm"
```

### 1.5 Data Persistence Schema

#### New Table: `cpu_metrics`

```sql
CREATE TABLE IF NOT EXISTS cpu_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id),
    execution_temperature TEXT NOT NULL CHECK (execution_temperature IN ('cold', 'warm')),
    total_cpu_seconds FLOAT NOT NULL,
    total_wall_seconds FLOAT NOT NULL,
    
    -- Stage breakdown
    fetch_cpu_seconds FLOAT NOT NULL,
    quality_cpu_seconds FLOAT NOT NULL,
    enhancement_cpu_seconds FLOAT NOT NULL,
    ocr_cpu_seconds FLOAT NOT NULL,
    schema_cpu_seconds FLOAT NOT NULL,
    upload_cpu_seconds FLOAT NOT NULL,
    
    -- Document characteristics
    input_file_size_bytes BIGINT,
    output_file_size_bytes BIGINT,
    quality_score FLOAT,
    ocr_confidence FLOAT,
    enhancement_skipped BOOLEAN,
    
    -- Path classification
    processing_path TEXT CHECK (processing_path IN ('fast', 'standard')),
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_cpu_metrics_job_id ON cpu_metrics(job_id);
CREATE INDEX idx_cpu_metrics_created_at ON cpu_metrics(created_at);
CREATE INDEX idx_cpu_metrics_path ON cpu_metrics(processing_path);
```

### 1.6 Metrics Output Contract

The worker STDOUT contract extends to include metrics:

```json
{
    "status": "SUCCESS",
    "job_id": "uuid",
    "result": { ... },
    "metrics": {
        "total_cpu_seconds": 1.847,
        "total_wall_seconds": 2.341,
        "execution_temperature": "warm",
        "processing_path": "fast",
        "stages": {
            "fetch": { "cpu_seconds": 0.012, "wall_seconds": 0.089 },
            "quality_scoring": { "cpu_seconds": 0.234, "wall_seconds": 0.241 },
            "enhancement": { "cpu_seconds": 0.087, "wall_seconds": 0.091 },
            "ocr": { "cpu_seconds": 1.203, "wall_seconds": 1.456 },
            "schema_adaptation": { "cpu_seconds": 0.198, "wall_seconds": 0.203 },
            "upload": { "cpu_seconds": 0.113, "wall_seconds": 0.261 }
        }
    }
}
```

---

## STEP 2: Load Test Design

### 2.1 Test Profile (Production-Realistic)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Concurrent Users | 50 | Peak expected simultaneous uploaders |
| Documents per User | 5 | Typical batch size |
| Total Documents | 250 | Statistically significant sample |
| Upload Pattern | **Burst** | Real users don't space uploads evenly |
| Document Mix | 70% Fast / 30% Standard | Based on expected quality distribution |
| File Sizes | 500KB–5MB range | Typical document scans |

### 2.2 Burst Pattern Definition

```
Time    Users Active    Uploads/second
─────────────────────────────────────────
0-10s       50              25          ← Initial burst
10-30s      35              15          ← Sustained high
30-60s      20              8           ← Gradual decline
60-90s      10              4           ← Tail
```

### 2.3 Tool Selection: Locust

**Why Locust over k6 or pytest**:

| Factor | Locust | k6 | pytest |
|--------|--------|-----|--------|
| Python-native | ✅ Yes | ❌ No (JS) | ✅ Yes |
| Real-time dashboards | ✅ Built-in | ✅ Grafana | ❌ No |
| Async file uploads | ✅ Native | ⚠️ Complex | ✅ Native |
| Custom metrics | ✅ Easy | ✅ Easy | ⚠️ Manual |
| Distributed mode | ✅ Built-in | ✅ Cloud | ❌ No |

**Decision**: Locust with custom file upload task.

### 2.4 Metrics Capture Requirements

| Metric | Source | Collection Method |
|--------|--------|-------------------|
| Throughput (docs/sec) | API Gateway | Locust built-in |
| Latency P50/P95/P99 | API + Worker | Locust + webhook timing |
| Error Rate | API Gateway | HTTP status codes |
| Queue Depth | Worker queue | Custom metric endpoint |
| Worker CPU | Worker pods | Prometheus/metrics endpoint |
| DB Connections | Supabase | Connection pool stats |

### 2.5 Test Fixtures

Pre-generate test documents:

```
test-data/load-test/
├── fast-path/           # 70% of tests
│   ├── doc_001.jpg      # 800KB, high quality
│   ├── doc_002.jpg      # 1.2MB, high quality
│   └── ... (50 files)
└── standard-path/       # 30% of tests
    ├── doc_001.jpg      # 2MB, medium quality
    ├── doc_002.jpg      # 3MB, noisy scan
    └── ... (25 files)
```

---

## STEP 3: Breaking Point Analysis Framework

### 3.1 Bottleneck Identification Order

Based on architecture analysis, expected failure order:

```
1. OCR CPU Saturation (MOST LIKELY FIRST)
   └── PaddleOCR consumes 4 threads × duration
   └── 16-core node hits 100% at ~4 concurrent OCR jobs

2. Worker Queue Backlog
   └── If jobs arrive faster than OCR completes
   └── Queue depth > 50 triggers backpressure

3. DB Connection Pool
   └── Default pool: 10 connections
   └── Webhook bursts can exhaust pool

4. API Gateway Timeout
   └── 30s default timeout
   └── Only if upstream is completely blocked
```

### 3.2 Detection Signals

| Bottleneck | Detection Signal | Threshold |
|------------|------------------|-----------|
| CPU Saturation | `cpu_percent > 95%` for >30s | CRITICAL |
| Queue Backlog | `queue_depth > 100` | WARNING at 50 |
| DB Pool | `db_pool_available < 2` | WARNING |
| API Timeout | `5xx rate > 5%` | CRITICAL at 1% |

### 3.3 2× Load Scenario Prediction

At **100 concurrent users**:

| Component | Predicted State | Risk |
|-----------|-----------------|------|
| OCR Workers | **SATURATED** | HIGH - queue will grow unbounded |
| Queue Depth | >500 within 2min | HIGH |
| Latency P99 | >60s | CRITICAL |
| DB Pool | Stable (webhooks queue behind CPU) | LOW |

---

## STEP 4: Capacity Math Framework

### 4.1 Calculation Template

Once measurements are collected:

```
CPU-hours/month = (CPU-sec/doc) × (docs/day) × 30 / 3600

Example with measured values:
- CPU-sec/doc (Fast): 1.2s
- CPU-sec/doc (Standard): 2.4s
- Weighted average (70/30 split): 1.2×0.7 + 2.4×0.3 = 1.56s
```

### 4.2 Budget Projection Table (Template)

| Daily Volume | CPU-sec/doc | Monthly CPU-hours | Budget Status |
|--------------|-------------|-------------------|---------------|
| 700 | TBD | TBD | TBD |
| 1,000 | TBD | TBD | TBD |
| 1,300 | TBD | TBD | TBD |

### 4.3 Break-Even Analysis

```
Max sustainable volume = (200 CPU-hours × 3600) / (CPU-sec/doc × 30)
                       = 720,000 / (CPU-sec/doc × 30)

If CPU-sec/doc = 1.5:  Max = 16,000 docs/month = 533 docs/day
If CPU-sec/doc = 1.0:  Max = 24,000 docs/month = 800 docs/day
If CPU-sec/doc = 0.7:  Max = 34,285 docs/month = 1,142 docs/day ← TARGET
```

**TARGET**: CPU-sec/doc must be ≤ 0.72s to support 1,000 docs/day within budget.

---

## STEP 5: Optimization Strategy (Contingent)

### 5.1 Optimization Options (ROI Ordered)

| # | Optimization | Expected Savings | Risk | Required For Launch |
|---|--------------|------------------|------|---------------------|
| 1 | OCR thread tuning (4→2) | 10-20% | Low | MEASURE FIRST |
| 2 | Skip enhancement for high-quality | 15-25% | Low | Already implemented (GUARD-001) |
| 3 | Image pre-resize before OCR | 20-30% | Medium | Maybe |
| 4 | OCR model swap (lightweight) | 30-40% | High | Post-launch only |
| 5 | Batch processing | 10-15% | Medium | Post-launch only |

### 5.2 PRD Invariants (DO NOT VIOLATE)

- ❌ Cannot skip OCR
- ❌ Cannot reduce output quality below schema requirements
- ❌ Cannot increase error rate above 1%
- ❌ Cannot add GPU dependency

---

## STEP 6: GO/NO-GO Framework

### Decision Matrix

| Measured CPU-sec/doc | Volume Supported | Budget Status | Decision |
|---------------------|------------------|---------------|----------|
| ≤ 0.72s | 1,000/day | ✅ Under 200h | **GO** |
| 0.73-0.90s | 800-999/day | ⚠️ Marginal | **ADJUST** (reduce volume) |
| 0.91-1.20s | 600-799/day | ❌ Over budget | **ADJUST** (optimize) |
| > 1.20s | <600/day | ❌ Severe breach | **NO-GO** |

### Residual Risk Acceptance

Even with GO decision, monitor:
- Cold start frequency (impacts average)
- Document size distribution drift
- Quality score distribution drift
- Weekend/peak traffic patterns

---

## Next Steps (Action Items)

### Immediate (Before Load Test)

1. **[ ] Implement CPU instrumentation** in `worker/worker.py`
2. **[ ] Create `cpu_metrics` table** migration
3. **[ ] Add metrics to webhook payload**
4. **[ ] Create test document fixtures**

### Load Test Execution

5. **[ ] Run baseline measurement** (10 documents, sequential)
6. **[ ] Run load test** (250 documents, burst pattern)
7. **[ ] Collect and analyze metrics**

### Analysis & Decision

8. **[ ] Populate capacity tables** with measured values
9. **[ ] Calculate break-even volume**
10. **[ ] Issue GO/NO-GO recommendation**

---

## Appendix A: File Manifest

| File | Purpose |
|------|---------|
| `infra/load-testing/CAPACITY_PLANNING.md` | This document |
| `infra/load-testing/instrumentation.py` | CPU measurement utilities |
| `infra/load-testing/locustfile.py` | Load test script |
| `db/migrations/XXXXXX_create_cpu_metrics.sql` | Metrics table |
| `worker/metrics.py` | Worker-side metrics collection |

