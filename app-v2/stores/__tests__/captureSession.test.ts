import { documentsApi } from '../../services/api';
import { useCaptureSession } from '../captureSession';

(globalThis as any).fetch = jest.fn();

describe('useCaptureSession', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useCaptureSession.getState().clearSession();
  });

  it('tracks categorizationResult in session snapshots', () => {
    useCaptureSession.getState().startSession([
      { uri: 'file://img.jpg', width: 1200, height: 1600 },
    ], 'ID Card');

    useCaptureSession.getState().setCategorizationResult({
      document_category: 'identity',
      document_subtype: 'PAN Card',
      suggested_name: 'PAN Card',
      suggested_owner: 'Abhinav',
      confidence: 0.94,
    });

    const session = useCaptureSession.getState().getSession();
    expect(session.categorizationResult?.document_category).toBe('identity');
    expect(session.categorizationResult?.confidence).toBe(0.94);
  });

  it('resets categorizationResult when session is cleared', () => {
    useCaptureSession.getState().startSession([
      { uri: 'file://img.jpg', width: 1200, height: 1600 },
    ], 'ID Card');

    useCaptureSession.getState().setCategorizationResult({
      document_category: 'identity',
      document_subtype: null,
      suggested_name: null,
      suggested_owner: null,
      confidence: 0.7,
    });

    useCaptureSession.getState().clearSession();

    expect(useCaptureSession.getState().categorizationResult).toBeNull();
  });
});

describe('documentsApi.categorize', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('posts image form-data to /jobs/categorize and returns response', async () => {
    ((globalThis as any).fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: async () => ({
        document_category: 'identity',
        document_subtype: 'PAN Card',
        suggested_name: 'PAN Card',
        suggested_owner: null,
        confidence: 0.91,
      }),
    });

    const result = await documentsApi.categorize('file://capture.jpg', 1080, 1920);

    expect(result.document_category).toBe('identity');
    expect((globalThis as any).fetch).toHaveBeenCalledWith(
      expect.stringContaining('/jobs/categorize'),
      expect.objectContaining({
        method: 'POST',
        body: expect.any(FormData),
      })
    );
  });
});
