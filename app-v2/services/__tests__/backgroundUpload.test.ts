import { startBackgroundUpload } from '../backgroundUpload';
import { documentsApi } from '../api';

(globalThis as any).fetch = jest.fn();

describe('startBackgroundUpload', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    (documentsApi.createMasterJob as any) = jest.fn().mockResolvedValue({
      job_id: 'job_1',
      upload_url: 'https://example.com/upload',
      expires_at: new Date().toISOString(),
    });
    (documentsApi.uploadToPresignedUrl as any) = jest.fn().mockResolvedValue(undefined);
    (documentsApi.submitJob as any) = jest.fn().mockResolvedValue({
      job_id: 'job_1',
      status: 'queued',
    });

    ((globalThis as any).fetch as jest.Mock).mockResolvedValue({
      blob: async () => ({ size: 2048 }),
    });
  });

  it('forwards extractData to submitJob', async () => {
    const queryClient = {
      invalidateQueries: jest.fn(),
    } as any;

    (startBackgroundUpload as any)(
      [
        {
          originalUri: 'file://image-1.jpg',
          quad: [[0, 0], [1, 0], [1, 1], [0, 1]],
          quadSource: 'manual',
        },
      ] as any,
      'PAN Front',
      'identity',
      'PAN Card',
      'document',
      queryClient,
      'jpeg',
      undefined,
      true,
    );

    await new Promise(resolve => setTimeout(resolve, 0));
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(documentsApi.submitJob).toHaveBeenCalledWith(
      'job_1',
      'jpeg',
      [[0, 0], [1, 0], [1, 1], [0, 1]],
      'identity',
      'PAN Card',
      'manual',
      true,
    );
  });
});
