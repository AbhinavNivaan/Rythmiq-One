-- =============================================================================
-- CPU Metrics Table for Capacity Planning
-- Migration: 20260130_create_cpu_metrics
-- =============================================================================
-- 
-- This table stores per-job CPU usage metrics collected from the worker.
-- Used for:
-- 1. Capacity planning and budget forecasting
-- 2. Performance regression detection
-- 3. Processing path optimization analysis
--
-- Data is append-only. Old records can be archived after 90 days.
-- =============================================================================

CREATE TABLE IF NOT EXISTS cpu_metrics (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Job reference
    job_id UUID NOT NULL,
    
    -- Execution context
    execution_temperature TEXT NOT NULL CHECK (execution_temperature IN ('cold', 'warm')),
    processing_path TEXT NOT NULL CHECK (processing_path IN ('fast', 'standard')),
    
    -- Total timing
    total_cpu_seconds FLOAT NOT NULL,
    total_wall_seconds FLOAT NOT NULL,
    cpu_efficiency FLOAT GENERATED ALWAYS AS (
        CASE WHEN total_wall_seconds > 0 
             THEN total_cpu_seconds / total_wall_seconds 
             ELSE 0 
        END
    ) STORED,
    
    -- Stage breakdown (all in CPU seconds)
    fetch_cpu_seconds FLOAT NOT NULL DEFAULT 0,
    quality_cpu_seconds FLOAT NOT NULL DEFAULT 0,
    pre_ocr_cpu_seconds FLOAT NOT NULL DEFAULT 0,
    enhancement_cpu_seconds FLOAT NOT NULL DEFAULT 0,
    ocr_cpu_seconds FLOAT NOT NULL DEFAULT 0,
    schema_cpu_seconds FLOAT NOT NULL DEFAULT 0,
    upload_cpu_seconds FLOAT NOT NULL DEFAULT 0,
    
    -- Document characteristics
    input_file_size_bytes BIGINT,
    output_file_size_bytes BIGINT,
    quality_score FLOAT,
    ocr_confidence FLOAT,
    enhancement_skipped BOOLEAN DEFAULT false,
    page_count INTEGER DEFAULT 1,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- Indexes for common queries
-- =============================================================================

-- Lookup by job
CREATE INDEX IF NOT EXISTS idx_cpu_metrics_job_id 
    ON cpu_metrics(job_id);

-- Time-series analysis
CREATE INDEX IF NOT EXISTS idx_cpu_metrics_created_at 
    ON cpu_metrics(created_at DESC);

-- Path-specific analysis
CREATE INDEX IF NOT EXISTS idx_cpu_metrics_processing_path 
    ON cpu_metrics(processing_path, created_at DESC);

-- Cold/warm analysis
CREATE INDEX IF NOT EXISTS idx_cpu_metrics_temperature 
    ON cpu_metrics(execution_temperature, created_at DESC);

-- CPU budget monitoring (for aggregation queries)
CREATE INDEX IF NOT EXISTS idx_cpu_metrics_total_cpu 
    ON cpu_metrics(created_at, total_cpu_seconds);

-- =============================================================================
-- Materialized views for dashboard queries
-- =============================================================================

-- Hourly aggregates for monitoring
CREATE MATERIALIZED VIEW IF NOT EXISTS cpu_metrics_hourly AS
SELECT 
    date_trunc('hour', created_at) AS hour,
    processing_path,
    execution_temperature,
    COUNT(*) AS job_count,
    AVG(total_cpu_seconds) AS avg_cpu_seconds,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY total_cpu_seconds) AS p50_cpu_seconds,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_cpu_seconds) AS p95_cpu_seconds,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY total_cpu_seconds) AS p99_cpu_seconds,
    SUM(total_cpu_seconds) AS total_cpu_seconds,
    AVG(ocr_cpu_seconds) AS avg_ocr_cpu_seconds,
    AVG(quality_score) AS avg_quality_score
FROM cpu_metrics
GROUP BY 
    date_trunc('hour', created_at),
    processing_path,
    execution_temperature;

CREATE UNIQUE INDEX IF NOT EXISTS idx_cpu_metrics_hourly_pk 
    ON cpu_metrics_hourly(hour, processing_path, execution_temperature);

-- Daily summary for capacity planning
CREATE MATERIALIZED VIEW IF NOT EXISTS cpu_metrics_daily AS
SELECT 
    date_trunc('day', created_at) AS day,
    processing_path,
    COUNT(*) AS job_count,
    AVG(total_cpu_seconds) AS avg_cpu_seconds,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY total_cpu_seconds) AS p50_cpu_seconds,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_cpu_seconds) AS p95_cpu_seconds,
    SUM(total_cpu_seconds) / 3600.0 AS total_cpu_hours,
    
    -- Stage breakdown
    AVG(fetch_cpu_seconds) AS avg_fetch_cpu,
    AVG(quality_cpu_seconds) AS avg_quality_cpu,
    AVG(ocr_cpu_seconds) AS avg_ocr_cpu,
    AVG(enhancement_cpu_seconds) AS avg_enhancement_cpu,
    AVG(schema_cpu_seconds) AS avg_schema_cpu,
    AVG(upload_cpu_seconds) AS avg_upload_cpu,
    
    -- Cold start impact
    AVG(CASE WHEN execution_temperature = 'cold' THEN total_cpu_seconds END) AS avg_cold_cpu,
    AVG(CASE WHEN execution_temperature = 'warm' THEN total_cpu_seconds END) AS avg_warm_cpu,
    COUNT(CASE WHEN execution_temperature = 'cold' THEN 1 END) AS cold_count,
    COUNT(CASE WHEN execution_temperature = 'warm' THEN 1 END) AS warm_count
FROM cpu_metrics
GROUP BY 
    date_trunc('day', created_at),
    processing_path;

CREATE UNIQUE INDEX IF NOT EXISTS idx_cpu_metrics_daily_pk 
    ON cpu_metrics_daily(day, processing_path);

-- =============================================================================
-- Helper function for budget monitoring
-- =============================================================================

CREATE OR REPLACE FUNCTION get_monthly_cpu_usage(
    p_year INTEGER DEFAULT EXTRACT(YEAR FROM now()),
    p_month INTEGER DEFAULT EXTRACT(MONTH FROM now())
)
RETURNS TABLE (
    processing_path TEXT,
    job_count BIGINT,
    total_cpu_hours FLOAT,
    avg_cpu_seconds FLOAT,
    p95_cpu_seconds FLOAT,
    projected_monthly_hours FLOAT
) AS $$
BEGIN
    RETURN QUERY
    WITH current_usage AS (
        SELECT 
            cm.processing_path,
            COUNT(*) AS job_count,
            SUM(cm.total_cpu_seconds) / 3600.0 AS total_cpu_hours,
            AVG(cm.total_cpu_seconds) AS avg_cpu_seconds,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY cm.total_cpu_seconds) AS p95_cpu_seconds,
            EXTRACT(DAY FROM now()) AS days_elapsed,
            EXTRACT(DAY FROM (date_trunc('month', now()) + INTERVAL '1 month' - INTERVAL '1 day')) AS days_in_month
        FROM cpu_metrics cm
        WHERE EXTRACT(YEAR FROM cm.created_at) = p_year
          AND EXTRACT(MONTH FROM cm.created_at) = p_month
        GROUP BY cm.processing_path
    )
    SELECT 
        cu.processing_path,
        cu.job_count,
        cu.total_cpu_hours,
        cu.avg_cpu_seconds,
        cu.p95_cpu_seconds,
        (cu.total_cpu_hours / cu.days_elapsed) * cu.days_in_month AS projected_monthly_hours
    FROM current_usage cu;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- Comments for documentation
-- =============================================================================

COMMENT ON TABLE cpu_metrics IS 
    'Per-job CPU usage metrics for capacity planning and performance monitoring';

COMMENT ON COLUMN cpu_metrics.execution_temperature IS 
    'cold = first execution in container (includes model loading), warm = subsequent';

COMMENT ON COLUMN cpu_metrics.processing_path IS 
    'fast = high quality input (minimal processing), standard = full pipeline';

COMMENT ON COLUMN cpu_metrics.cpu_efficiency IS 
    'Ratio of CPU time to wall time. >1 indicates multi-threaded execution';

COMMENT ON FUNCTION get_monthly_cpu_usage IS 
    'Returns current month CPU usage with projection for budget monitoring';

-- =============================================================================
-- Refresh policy (run via cron or pg_cron)
-- =============================================================================

-- Recommended refresh schedule:
-- - cpu_metrics_hourly: Every 5 minutes
-- - cpu_metrics_daily: Every hour

-- Example pg_cron setup:
-- SELECT cron.schedule('refresh-cpu-hourly', '*/5 * * * *', 'REFRESH MATERIALIZED VIEW CONCURRENTLY cpu_metrics_hourly');
-- SELECT cron.schedule('refresh-cpu-daily', '0 * * * *', 'REFRESH MATERIALIZED VIEW CONCURRENTLY cpu_metrics_daily');
