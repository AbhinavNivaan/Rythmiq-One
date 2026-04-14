import { documentsApi } from '../api';

(globalThis as any).fetch = jest.fn();

describe('documentsApi.submitJob', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('includes extract_data in submit payload when extraction is enabled', async () => {
    ((globalThis as any).fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({ job_id: 'job_1', status: 'queued' }),
    });

    await (documentsApi.submitJob as any)(
      'job_1',
      'jpeg',
      [[0, 0], [1, 0], [1, 1], [0, 1]],
      'identity',
      'PAN Card',
      'model',
      true,
    );

    const [, request] = ((globalThis as any).fetch as jest.Mock).mock.calls[0];
    expect(JSON.parse(request.body)).toEqual(
      expect.objectContaining({
        extract_data: true,
      })
    );
  });
});
