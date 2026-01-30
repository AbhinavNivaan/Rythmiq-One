# Observability Quick Reference Card

**For On-Call Engineers**  
**Print this. Tape it to your monitor.**

---

## 🚨 INCIDENT RESPONSE CHECKLIST

```
□ 1. Check Operations Dashboard → Error rate & latency
□ 2. Get job_id or correlation_id from report
□ 3. Query logs: SELECT * FROM logs WHERE correlation_id = '...'
□ 4. Check error_events: SELECT * FROM get_recent_errors(50)
□ 5. Check if cold starts spiking (container issue?)
□ 6. Check if specific error_code is dominant
```

---

## 📊 KEY QUERIES

### What's the current error rate?
```sql
SELECT * FROM get_error_rate(24);
```

### What errors happened recently?
```sql
SELECT * FROM get_recent_errors(20);
```

### Is a specific job in the database?
```sql
SELECT id, status, created_at, completed_at 
FROM jobs 
WHERE id = 'JOB-UUID-HERE';
```

### Did metrics get recorded for a job?
```sql
SELECT * FROM cpu_metrics WHERE job_id = 'JOB-UUID-HERE';
```

### What's our CPU usage this month?
```sql
SELECT * FROM get_monthly_cpu_usage();
```

### P95 latency in last 24 hours?
```sql
SELECT hour, p95_cpu_seconds 
FROM cpu_metrics_hourly 
WHERE hour > now() - interval '24 hours'
ORDER BY hour DESC;
```

---

## 🔍 LOG FIELD REFERENCE

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | ISO-8601 | When it happened |
| `level` | DEBUG/INFO/WARN/ERROR | Severity |
| `service` | api/worker/webhook | Which component |
| `job_id` | UUID | The job |
| `correlation_id` | UUID | Request trace ID |
| `stage` | string | Processing stage |
| `error_code` | string | Error type |
| `cpu_seconds` | float | CPU time consumed |
| `latency_ms` | float | Wall-clock time |

---

## ⚠️ ALERT THRESHOLDS

| What | Warning | Critical |
|------|---------|----------|
| Error Rate | > 1% | > 2% |
| P95 Latency | > 20s | > 30s |
| CPU/day | > 8 hrs | > 10 hrs |
| Cold Starts | > 10% | > 20% |

---

## 🔑 ERROR CODES

| Code | Stage | Meaning |
|------|-------|---------|
| `PAYLOAD_MISSING` | INIT | Empty input |
| `PAYLOAD_INVALID` | INIT | Malformed JSON |
| `ARTIFACT_FETCH_FAILED` | FETCH | Download failed |
| `CORRUPT_DATA` | FETCH | Bad file |
| `UNSUPPORTED_FORMAT` | OCR | Unknown format |
| `OCR_FAILURE` | OCR | Extraction failed |
| `SCHEMA_INVALID` | TRANSFORM | Bad schema |
| `INTERNAL_ERROR` | ANY | Unknown error |

---

## 📈 STAGES (Pipeline Order)

```
FETCH → QUALITY → PRE-OCR → ENHANCE → OCR → SCHEMA → UPLOAD
```

OCR typically takes 60-70% of CPU time.

---

## 🛠 USEFUL COMMANDS

### Refresh materialized views manually
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY cpu_metrics_hourly;
REFRESH MATERIALIZED VIEW CONCURRENTLY cpu_metrics_daily;
REFRESH MATERIALIZED VIEW CONCURRENTLY error_events_hourly;
REFRESH MATERIALIZED VIEW CONCURRENTLY error_events_daily;
```

### Check view freshness
```sql
SELECT schemaname, matviewname, 
       pg_size_pretty(pg_relation_size(schemaname || '.' || matviewname))
FROM pg_matviews 
WHERE matviewname LIKE '%metrics%' OR matviewname LIKE '%error%';
```

---

## 🚫 PII BLOCKLIST

**NEVER appears in logs:**
- OCR text
- Filenames
- Email addresses
- IP addresses
- Raw user_id (use `user_id_hash`)
- File contents

---

## 📞 ESCALATION

1. **On-call engineer** — First responder
2. **Backend lead** — If code change needed
3. **Infra/SRE** — If infrastructure issue
4. **Founders** — If user-facing impact > 30 min

---

*Last updated: January 30, 2026*
