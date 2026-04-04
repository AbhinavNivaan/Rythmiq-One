import { documentsApi } from '../api';

global.fetch = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  (global.fetch as jest.Mock).mockResolvedValue({
    ok: true,
    json: async () => ({ status: 'ok' }),
    text: async () => '',
  });
});

describe('dismissJob', () => {
  it('posts to /jobs/{id}/dismiss', async () => {
    await documentsApi.dismissJob('job-abc');
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/jobs/job-abc/dismiss'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('does not throw on network error (fire and forget)', async () => {
    (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('network'));
    await expect(documentsApi.dismissJob('job-abc')).resolves.not.toThrow();
  });
});

describe('reportFeedback', () => {
  it('posts to /jobs/{id}/feedback with correct body', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'received', feedback_id: 'fb-123' }),
      text: async () => '',
    });
    const result = await documentsApi.reportFeedback('job-abc', {
      category: 'wrong_crop',
      note: 'edge cut off',
      consent_granted: true,
    });
    expect(result.feedback_id).toBe('fb-123');
    const body = JSON.parse((global.fetch as jest.Mock).mock.calls[0][1].body);
    expect(body.category).toBe('wrong_crop');
    expect(body.consent_granted).toBe(true);
  });
});
