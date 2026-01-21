import { Router, Request, Response, NextFunction } from 'express';
import { authenticateRequest, AuthenticatedRequest } from '../auth/middleware';
import { jobStore } from '../../engine/jobs/jobStore';
import { throwApiError } from '../errors/apiError';

const router = Router();

router.get(
  '/:jobId/results',
  authenticateRequest,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { jobId } = req.params;
      const userId = (req as AuthenticatedRequest).userId as string;

      const job = await jobStore.getJobForUser(jobId, userId);

      if (!job || job.state !== 'SUCCEEDED') {
        throwApiError('JOB_NOT_AVAILABLE', 404);
      }

      res.status(200).json({
        jobId: job.jobId,
        schemaOutput: job.schemaOutput ?? null,
        confidence: job.confidence ?? null,
        qualityScore: job.qualityScore ?? null,
      });
    } catch (error) {
      next(error);
    }
  },
);

export default router;
