# Observability Index

**Project:** Rythmiq One  
**Phase:** P1.2 — Production Observability  
**Created:** January 30, 2026

---

## Quick Reference

| Question | Where to Look |
|----------|---------------|
| How do I trace a job? | Query logs by `correlation_id` |
| What's our error rate? | Operations Dashboard or `SELECT * FROM get_error_rate(24)` |
| Are we on budget? | Cost Dashboard or `SELECT * FROM get_monthly_cpu_usage()` |
| Why did job X fail? | Query `error_events` by `job_id` |
| What's P95 latency? | `SELECT p95_cpu_seconds FROM cpu_metrics_hourly` |

---

## Files in This Directory

| File | Purpose |
|------|---------|
| [OBSERVABILITY_SPEC.md](OBSERVABILITY_SPEC.md) | Complete observability design specification |
| [QUICK_REFERENCE.md](QUICK_REFERENCE.md) | On-call quick reference card |

## Related Implementation Files

| File | Purpose |
|------|---------|
| [shared/logging.py](../../shared/logging.py) | Structured logger factory |
| [worker/metrics.py](../../worker/metrics.py) | CPU metrics collection |
| [worker/metrics_persistence.py](../../worker/metrics_persistence.py) | Metrics DB persistence |
| [db/migrations/20260130_create_cpu_metrics.sql](../../db/migrations/20260130_create_cpu_metrics.sql) | CPU metrics table |
| [db/migrations/20260131_create_error_events.sql](../../db/migrations/20260131_create_error_events.sql) | Error events table |
| [app/api/middleware/correlation.py](../../app/api/middleware/correlation.py) | Correlation ID middleware |

---

## Dashboards

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| Operations | `[TBD - Retool]` | Real-time health monitoring |
| Cost Monitoring | `[TBD - Retool]` | CPU budget tracking |
| Product Health | `[TBD - Retool]` | Quality & performance trends |

---

## Key Metrics

### Counters
- `rythmiq_jobs_total{status, processing_path}` — Job count
- `rythmiq_errors_total{error_code, stage}` — Error count
- `rythmiq_cold_starts_total` — Cold start count

### Histograms
- `rythmiq_job_cpu_seconds{processing_path, stage}` — CPU time distribution
- `rythmiq_quality_score` — Input quality distribution
- `rythmiq_ocr_confidence` — OCR confidence distribution

---

## Useful Queries

### Current Month CPU Usage
```sql
SELECT * FROM get_monthly_cpu_usage();
```

### Error Rate (Last 24h)
```sql
SELECT * FROM get_error_rate(24);
```

### Recent Errors
```sql
SELECT * FROM get_recent_errors(20);
```

### Job Timeline (by Correlation ID)
```sql
-- In external logging service:
SELECT * FROM logs 
WHERE correlation_id = 'YOUR-ID-HERE'
ORDER BY timestamp ASC;
```

### P95 Latency Trend (Hourly)
```sql
SELECT hour, p95_cpu_seconds 
FROM cpu_metrics_hourly 
WHERE hour > now() - interval '24 hours'
ORDER BY hour;
```

---

## Alert Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Error Rate | > 1% | > 2% |
| P95 Latency | > 20s | > 30s |
| CPU Burn Rate | > 8 hrs/day | > 10 hrs/day |
| Cold Start Rate | > 10% | > 20% |

---

## On-Call Runbook Links

- [Incident Response Playbook](../docs/INCIDENT_RUNBOOK.md) *(to be created)*
- [Postmortem Template](../docs/POSTMORTEM_TEMPLATE.md) *(to be created)*
