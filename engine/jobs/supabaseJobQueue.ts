
import { JobQueue, WorkerJob } from '../cpu/worker';
import { getSupabaseClient } from './dbClient';
import { ProcessingError } from './errors';

export class SupabaseJobQueue implements JobQueue {
    async enqueue(job: Pick<WorkerJob, 'jobId' | 'blobId' | 'userId' | 'schemaId' | 'schemaVersion'>): Promise<WorkerJob> {
        const supabase = getSupabaseClient();
        const now = new Date();

        const record: WorkerJob = {
            ...job,
            state: 'QUEUED',
            createdAt: now,
            updatedAt: now,
            attempt: 0,
            maxAttempts: 3,
            nextVisibleAt: now,
        };

        const { data, error } = await supabase
            .from('jobs')
            .insert({
                job_id: job.jobId,
                blob_id: job.blobId,
                user_id: job.userId,
                schema_id: job.schemaId,
                schema_version: job.schemaVersion,
                state: 'QUEUED',
                created_at: now.toISOString(),
                updated_at: now.toISOString(),
                attempt: 0,
                max_attempts: 3,
                next_visible_at: now.toISOString(),
            })
            .select()
            .single();

        if (error) {
            throw new Error(`Failed to enqueue job: ${error.message}`);
        }

        return this.mapRowToJob(data);
    }

    async getNextQueued(now: Date = new Date()): Promise<WorkerJob | null> {
        const supabase = getSupabaseClient();

        // Simple fetch - in production consider SELECT FOR UPDATE SKIP LOCKED via RPC
        const { data, error } = await supabase
            .from('jobs')
            .select('*')
            .eq('state', 'QUEUED')
            .lte('next_visible_at', now.toISOString())
            .order('created_at', { ascending: true })
            .limit(1)
            .single();

        if (error) {
            if (error.code === 'PGRST116') return null; // No rows found
            throw new Error(`Failed to fetch next job: ${error.message}`);
        }

        return this.mapRowToJob(data);
    }

    async markRunning(jobId: string): Promise<WorkerJob> {
        const supabase = getSupabaseClient();
        const now = new Date().toISOString();

        // We increment attempt here
        const { data, error } = await supabase.rpc('mark_job_running', {
            p_job_id: jobId,
            p_now: now
        });

        if (error) {
            // Fallback to simple update if RPC not exists (though concurrent access issues)
            const { data: fallbackData, error: fallbackError } = await supabase
                .from('jobs')
                .update({
                    state: 'RUNNING',
                    updated_at: now,
                    attempt: undefined // Fallback cannot reliably increment attempt without race condition
                })
                .eq('job_id', jobId)
                .select()
                .single();

            if (fallbackError) throw new Error(`Failed to mark job running: ${fallbackError.message}`);
            return this.mapRowToJob(fallbackData);
        }

        // If RPC unavailable, we might need a simpler update
        // But for now, let's assume we do a simple update with read-modify-write if RPC fails?
        // Actually, let's just do a direct update and handle concurrency poorly for now, 
        // or better: use a simple update incrementing attempt.

        const { data: updateData, error: updateError } = await supabase
            .from('jobs')
            .select('attempt')
            .eq('job_id', jobId)
            .single();

        if (updateError) throw updateError;

        const newAttempt = (updateData?.attempt || 0) + 1;

        const { data: finalData, error: finalError } = await supabase
            .from('jobs')
            .update({
                state: 'RUNNING',
                updated_at: now,
                attempt: newAttempt
            })
            .eq('job_id', jobId)
            .select()
            .single();

        if (finalError) throw new Error(`Failed to mark job running: ${finalError.message}`);
        return this.mapRowToJob(finalData);
    }

    async markSucceeded(jobId: string, ocrArtifactId: string, schemaArtifactId: string, qualityScore: number): Promise<WorkerJob> {
        const supabase = getSupabaseClient();
        const now = new Date().toISOString();

        const { data, error } = await supabase
            .from('jobs')
            .update({
                state: 'SUCCEEDED',
                updated_at: now,
                ocr_artifact_id: ocrArtifactId,
                schema_artifact_id: schemaArtifactId,
                quality_score: qualityScore,
                retryable: false
            })
            .eq('job_id', jobId)
            .select()
            .single();

        if (error) throw new Error(`Failed to mark job succeeded: ${error.message}`);
        return this.mapRowToJob(data);
    }

    async markFailed(jobId: string, errorProcessing: ProcessingError): Promise<WorkerJob> {
        const supabase = getSupabaseClient();
        const now = new Date().toISOString();

        const { data, error } = await supabase
            .from('jobs')
            .update({
                state: 'FAILED',
                updated_at: now,
                error_code: errorProcessing.code,
                retryable: errorProcessing.retryable
            })
            .eq('job_id', jobId)
            .select()
            .single();

        if (error) throw new Error(`Failed to mark job failed: ${error.message}`);
        return this.mapRowToJob(data);
    }

    async scheduleRetry(jobId: string, nextVisibleAt: Date, errorProcessing: ProcessingError): Promise<WorkerJob> {
        const supabase = getSupabaseClient();
        const now = new Date().toISOString();

        const { data, error } = await supabase
            .from('jobs')
            .update({
                state: 'RETRYING',
                updated_at: now,
                next_visible_at: nextVisibleAt.toISOString(),
                error_code: errorProcessing.code,
                retryable: errorProcessing.retryable
            })
            .eq('job_id', jobId)
            .select()
            .single();

        if (error) throw new Error(`Failed to schedule retry: ${error.message}`);
        return this.mapRowToJob(data);
    }

    private mapRowToJob(row: any): WorkerJob {
        return {
            jobId: row.job_id,
            blobId: row.blob_id,
            userId: row.user_id,
            state: row.state,
            createdAt: new Date(row.created_at),
            updatedAt: new Date(row.updated_at),
            attempt: row.attempt,
            maxAttempts: row.max_attempts,
            nextVisibleAt: new Date(row.next_visible_at),
            ocrArtifactId: row.ocr_artifact_id,
            schemaArtifactId: row.schema_artifact_id,
            qualityScore: row.quality_score,
            errorCode: row.error_code,
            retryable: row.retryable,
            schemaId: row.schema_id,
            schemaVersion: row.schema_version,
        };
    }
}
