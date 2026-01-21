import { Router, Request, Response, NextFunction } from 'express';
import { authenticateRequest, AuthenticatedRequest } from '../auth/middleware';
import { jobStore } from '../../engine/jobs/jobStore';
import { throwApiError } from '../errors/apiError';

const router = Router();

router.get(
  '/:jobId',
  authenticateRequest,
  async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { jobId } = req.params;
      const userId = (req as AuthenticatedRequest).userId as string;

      const job = await jobStore.getJobForUser(jobId, userId);

      if (!job) {
        throwApiError('JOB_NOT_AVAILABLE', 404);
      }

      res.status(200).json({
        jobId: job.jobId,
        state: job.state,
        retries: job.retries,
        createdAt: job.createdAt,
        updatedAt: job.updatedAt,
        error: job.errorCode ?? null,
      });
    } catch (error) {
      next(error);
    }
  },
);

export default router;
