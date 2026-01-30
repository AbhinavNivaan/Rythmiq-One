-- =============================================================================
-- Error Events Table for Pattern Analysis
-- Migration: 20260131_create_error_events
-- =============================================================================
-- 
-- This table stores error events for:
-- 1. Error pattern analysis and trending
-- 2. Alert rule data source
-- 3. Postmortem investigation
-- 4. Quality correlation analysis
--
-- Retention: 90 days (automated cleanup via pg_cron)
-- =============================================================================

CREATE TABLE IF NOT EXISTS error_events (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Job reference
    job_id UUID NOT NULL,
    
    -- Error classification
    error_code TEXT NOT NULL,
    error_stage TEXT NOT NULL,
    
    -- Context at time of error
    processing_path TEXT,
    quality_score FLOAT,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- Indexes for common queries
-- =============================================================================

-- Error code analysis (most common)
CREATE INDEX IF NOT EXISTS idx_error_events_code 
    ON error_events(error_code, created_at DESC);

-- Job lookup (for postmortems)
CREATE INDEX IF NOT EXISTS idx_error_events_job 
    ON error_events(job_id);

-- Time-series queries
CREATE INDEX IF NOT EXISTS idx_error_events_time 
    ON error_events(created_at DESC);

-- Stage-specific analysis
CREATE INDEX IF NOT EXISTS idx_error_events_stage 
    ON error_events(error_stage, created_at DESC);

-- =============================================================================
-- Materialized view for dashboard queries
-- =============================================================================

-- Daily error aggregates
CREATE MATERIALIZED VIEW IF NOT EXISTS error_events_daily AS
SELECT 
    date_trunc('day', created_at) AS day,
    error_code,
    error_stage,
    COUNT(*) AS count,
    AVG(quality_score) AS avg_quality_score
FROM error_events
GROUP BY 
    date_trunc('day', created_at),
    error_code,
    error_stage;

CREATE UNIQUE INDEX IF NOT EXISTS idx_error_events_daily_pk 
    ON error_events_daily(day, error_code, error_stage);

-- Hourly error rates (for alerting)
CREATE MATERIALIZED VIEW IF NOT EXISTS error_events_hourly AS
SELECT 
    date_trunc('hour', created_at) AS hour,
    error_code,
    COUNT(*) AS count
FROM error_events
GROUP BY 
    date_trunc('hour', created_at),
    error_code;

CREATE UNIQUE INDEX IF NOT EXISTS idx_error_events_hourly_pk 
    ON error_events_hourly(hour, error_code);

-- =============================================================================
-- Helper functions
-- =============================================================================

-- Get error rate for a time window
CREATE OR REPLACE FUNCTION get_error_rate(
    p_hours INTEGER DEFAULT 24
)
RETURNS TABLE (
    error_code TEXT,
    error_stage TEXT,
    count BIGINT,
    percentage FLOAT
) AS $$
BEGIN
    RETURN QUERY
    WITH total_jobs AS (
        SELECT COUNT(*) AS total
        FROM jobs
        WHERE created_at > now() - (p_hours || ' hours')::INTERVAL
    ),
    error_counts AS (
        SELECT 
            e.error_code,
            e.error_stage,
            COUNT(*) AS count
        FROM error_events e
        WHERE e.created_at > now() - (p_hours || ' hours')::INTERVAL
        GROUP BY e.error_code, e.error_stage
    )
    SELECT 
        ec.error_code,
        ec.error_stage,
        ec.count,
        CASE 
            WHEN tj.total > 0 THEN (ec.count * 100.0 / tj.total)
            ELSE 0
        END AS percentage
    FROM error_counts ec
    CROSS JOIN total_jobs tj
    ORDER BY ec.count DESC;
END;
$$ LANGUAGE plpgsql;

-- Get recent errors for dashboard
CREATE OR REPLACE FUNCTION get_recent_errors(
    p_limit INTEGER DEFAULT 20
)
RETURNS TABLE (
    created_at TIMESTAMPTZ,
    job_id UUID,
    error_code TEXT,
    error_stage TEXT,
    processing_path TEXT,
    quality_score FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        e.created_at,
        e.job_id,
        e.error_code,
        e.error_stage,
        e.processing_path,
        e.quality_score
    FROM error_events e
    ORDER BY e.created_at DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- Comments
-- =============================================================================

COMMENT ON TABLE error_events IS 
    'Error events for pattern analysis and alerting. Retained for 90 days.';

COMMENT ON COLUMN error_events.error_code IS 
    'Error code from ErrorCode enum (e.g., OCR_FAILURE, CORRUPT_DATA)';

COMMENT ON COLUMN error_events.error_stage IS 
    'Processing stage where error occurred (e.g., FETCH, OCR, TRANSFORM)';

COMMENT ON FUNCTION get_error_rate IS 
    'Returns error counts and percentages for a given time window';

-- =============================================================================
-- Retention cleanup (schedule via pg_cron)
-- =============================================================================

-- Recommended schedule: Weekly cleanup
-- SELECT cron.schedule(
--     'cleanup-error-events',
--     '0 3 * * 0',  -- Sunday 3 AM
--     $$DELETE FROM error_events WHERE created_at < now() - interval '90 days'$$
-- );

-- Refresh schedule for materialized views:
-- SELECT cron.schedule('refresh-errors-hourly', '*/5 * * * *', 'REFRESH MATERIALIZED VIEW CONCURRENTLY error_events_hourly');
-- SELECT cron.schedule('refresh-errors-daily', '0 * * * *', 'REFRESH MATERIALIZED VIEW CONCURRENTLY error_events_daily');
