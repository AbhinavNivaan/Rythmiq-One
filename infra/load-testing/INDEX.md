# Load Testing & Capacity Planning Index

**Project:** Rythmiq One  
**Phase:** 2A Production Readiness (P1.1)  
**Created:** January 30, 2026

---

## Overview

This directory contains the complete load testing and capacity planning infrastructure for Rythmiq One. The goal is to MEASURE (not estimate) CPU consumption and determine if the system can support 1,000 documents/day within a 200 CPU-hours/month budget.

## Quick Start

```bash
# Full pipeline (benchmark + load test + analysis)
./run_capacity_test.sh

# Just baseline benchmark
python benchmark.py --count 50 --output results/baseline.json

# Just load test (requires API running)
locust -f locustfile.py --host http://localhost:8000
```

## Directory Structure

```
infra/load-testing/
├── INDEX.md                    # This file
├── CAPACITY_PLANNING.md        # Detailed instrumentation & test design
├── GO_NOGO_DECISION.md         # Decision form (fill after measurement)
├── benchmark.py                # CPU baseline measurement tool
├── locustfile.py               # Load test script
├── run_capacity_test.sh        # Full pipeline runner
├── requirements.txt            # Python dependencies
└── results/                    # Test output (gitignored)
    ├── baseline_YYYYMMDD.json
    └── loadtest_YYYYMMDD.csv
```

## Related Files

| File | Purpose |
|------|---------|
| [worker/metrics.py](../../worker/metrics.py) | CPU measurement utilities |
| [worker/worker_instrumented.py](../../worker/worker_instrumented.py) | Instrumented worker |
| [db/migrations/20260130_create_cpu_metrics.sql](../../db/migrations/20260130_create_cpu_metrics.sql) | Metrics persistence |

## Constraints Summary

| Constraint | Value | Status |
|------------|-------|--------|
| CPU Budget | 200 CPU-hours/month | **HARD LIMIT** |
| Target Volume | 1,000 docs/day | Business requirement |
| Max P95 Latency | 30 seconds | SLA |
| Error Rate | < 1% | SLA |

## Decision Matrix (Quick Reference)

| CPU-sec/doc | Monthly Hours | Decision |
|-------------|---------------|----------|
| ≤ 0.72s | ≤ 180 hrs | ✅ **GO** |
| 0.73-0.90s | 181-225 hrs | ⚠️ **ADJUST** |
| > 0.90s | > 225 hrs | ❌ **NO-GO** |

## Measurement Before Launch

**DO NOT SHIP** until:

1. ✅ Baseline benchmark run (≥50 documents)
2. ✅ CPU-sec/doc measured accurately
3. ✅ Load test validates P95 latency
4. ✅ GO_NOGO_DECISION.md completed
5. ✅ Sign-off from leads

## Stage Timing Reference

The worker pipeline has 6 stages, each instrumented:

```
FETCH → QUALITY → PRE-OCR → ENHANCE → OCR → SCHEMA → UPLOAD
```

Expected dominant stage: **OCR** (60-70% of CPU time)

## Optimization Options (If Needed)

| Optimization | Savings | Risk | When |
|--------------|---------|------|------|
| OCR thread tuning | 10-20% | Low | Pre-launch OK |
| Image pre-resize | 20-30% | Medium | Pre-launch OK |
| Skip pre-OCR for high quality | 5-10% | Low | Pre-launch OK |
| Lighter OCR model | 30-40% | High | Post-launch only |

---

## Support

Questions? Contact the Infrastructure team or see:
- [CAPACITY_PLANNING.md](./CAPACITY_PLANNING.md) for methodology
- [GO_NOGO_DECISION.md](./GO_NOGO_DECISION.md) for decision criteria
