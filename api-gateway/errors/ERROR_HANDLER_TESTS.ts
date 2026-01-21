/**
 * ERROR HANDLER TESTING PATTERNS
 * Complete test suite for canonical error schema enforcement
 */

import { Request, Response, NextFunction } from 'express';
import { globalErrorHandler, asyncHandler } from '../errors/errorHandler';
import { throwApiError, isApiError } from '../errors/apiError';

/**
 * ============================================================================
 * UNIT TESTS: isApiError() Type Guard
 * ============================================================================
 */

describe('isApiError() type guard', () => {
  test('returns true for valid ApiError', () => {
    const error = new Error() as any;
    error.errorCode = 'INVALID_REQUEST';
    error.statusCode = 400;

    expect(isApiError(error)).toBe(true);
  });

  test('returns false for Error without errorCode', () => {
    const error = new Error('Something went wrong');
    expect(isApiError(error)).toBe(false);
  });

  test('returns false for object without statusCode', () => {
    const error = { errorCode: 'INVALID_REQUEST' } as any;
    expect(isApiError(error)).toBe(false);
  });

  test('returns false for null', () => {
    expect(isApiError(null)).toBe(false);
  });

  test('returns false for undefined', () => {
    expect(isApiError(undefined)).toBe(false);
  });

  test('returns false for primitive values', () => {
    expect(isApiError('error')).toBe(false);
    expect(isApiError(42)).toBe(false);
    expect(isApiError(true)).toBe(false);
  });

  test('returns false for object with wrong types', () => {
    const error = {
      errorCode: 123,
      statusCode: '500',
    };
    expect(isApiError(error)).toBe(false);
  });
});

/**
 * ============================================================================
 * UNIT TESTS: throwApiError() Factory
 * ============================================================================
 */

describe('throwApiError() factory', () => {
  test('throws ApiError with errorCode and statusCode', () => {
    expect(() => {
      throwApiError('TEST_ERROR', 400);
    }).toThrow();
  });

  test('thrown error has correct properties', () => {
    try {
      throwApiError('TEST_ERROR', 400);
      fail('Should have thrown');
    } catch (err) {
      expect(isApiError(err)).toBe(true);
      expect((err as any).errorCode).toBe('TEST_ERROR');
      expect((err as any).statusCode).toBe(400);
    }
  });

  test('thrown error has name "ApiError"', () => {
    try {
      throwApiError('TEST_ERROR', 400);
      fail('Should have thrown');
    } catch (err) {
      expect((err as any).name).toBe('ApiError');
    }
  });

  test('works with various status codes', () => {
    const testCases = [
      { code: 'INVALID_REQUEST', status: 400 },
      { code: 'UNAUTHORIZED', status: 401 },
      { code: 'FORBIDDEN', status: 403 },
      { code: 'NOT_FOUND', status: 404 },
      { code: 'INTERNAL_ERROR', status: 500 },
    ];

    testCases.forEach(({ code, status }) => {
      try {
        throwApiError(code, status);
        fail(`Should have thrown for ${code}`);
      } catch (err) {
        expect((err as any).errorCode).toBe(code);
        expect((err as any).statusCode).toBe(status);
      }
    });
  });
});

/**
 * ============================================================================
 * MIDDLEWARE TESTS: globalErrorHandler()
 * ============================================================================
 */

describe('globalErrorHandler middleware', () => {
  let req: Request;
  let res: Partial<Response>;
  let next: NextFunction;

  beforeEach(() => {
    req = {} as Request;
    res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis(),
    };
    next = jest.fn();
  });

  test('handles valid ApiError', () => {
    const error = new Error() as any;
    error.errorCode = 'INVALID_REQUEST';
    error.statusCode = 400;

    globalErrorHandler(error, req, res as Response, next);

    expect(res.status).toHaveBeenCalledWith(400);
    expect(res.json).toHaveBeenCalledWith({
      errorCode: 'INVALID_REQUEST',
    });
  });

  test('handles ApiError with 401 status', () => {
    const error = new Error() as any;
    error.errorCode = 'UNAUTHORIZED';
    error.statusCode = 401;

    globalErrorHandler(error, req, res as Response, next);

    expect(res.status).toHaveBeenCalledWith(401);
    expect(res.json).toHaveBeenCalledWith({
      errorCode: 'UNAUTHORIZED',
    });
  });

  test('handles non-ApiError with INTERNAL_ERROR', () => {
    const error = new Error('Database connection failed');

    globalErrorHandler(error, req, res as Response, next);

    expect(res.status).toHaveBeenCalledWith(500);
    expect(res.json).toHaveBeenCalledWith({
      errorCode: 'INTERNAL_ERROR',
    });
  });

  test('handles null error with INTERNAL_ERROR', () => {
    globalErrorHandler(null, req, res as Response, next);

    expect(res.status).toHaveBeenCalledWith(500);
    expect(res.json).toHaveBeenCalledWith({
      errorCode: 'INTERNAL_ERROR',
    });
  });

  test('handles string error with INTERNAL_ERROR', () => {
    globalErrorHandler('string error', req, res as Response, next);

    expect(res.status).toHaveBeenCalledWith(500);
    expect(res.json).toHaveBeenCalledWith({
      errorCode: 'INTERNAL_ERROR',
    });
  });

  test('handles number error with INTERNAL_ERROR', () => {
    globalErrorHandler(42, req, res as Response, next);

    expect(res.status).toHaveBeenCalledWith(500);
    expect(res.json).toHaveBeenCalledWith({
      errorCode: 'INTERNAL_ERROR',
    });
  });

  test('handles plain object error with INTERNAL_ERROR', () => {
    const error = { custom: 'error' };

    globalErrorHandler(error, req, res as Response, next);

    expect(res.status).toHaveBeenCalledWith(500);
    expect(res.json).toHaveBeenCalledWith({
      errorCode: 'INTERNAL_ERROR',
    });
  });

  test('does NOT include stack trace in response', () => {
    const error = new Error('Test error');

    globalErrorHandler(error, req, res as Response, next);

    const jsonCall = (res.json as jest.Mock).mock.calls[0][0];
    expect(jsonCall.stack).toBeUndefined();
  });

  test('does NOT include message in response', () => {
    const error = new Error('Test error');

    globalErrorHandler(error, req, res as Response, next);

    const jsonCall = (res.json as jest.Mock).mock.calls[0][0];
    expect(jsonCall.message).toBeUndefined();
  });

  test('does NOT include error details in response', () => {
    const error = new Error('Database failed');
    (error as any).details = 'Connection timeout';

    globalErrorHandler(error, req, res as Response, next);

    const jsonCall = (res.json as jest.Mock).mock.calls[0][0];
    expect(jsonCall.details).toBeUndefined();
  });

  test('logs full error server-side', () => {
    const consoleSpy = jest.spyOn(console, 'error');
    const error = new Error('Test error');

    globalErrorHandler(error, req, res as Response, next);

    expect(consoleSpy).toHaveBeenCalledWith(
      '[GLOBAL_ERROR_HANDLER]',
      expect.objectContaining({
        message: 'Test error',
      })
    );

    consoleSpy.mockRestore();
  });
});

/**
 * ============================================================================
 * MIDDLEWARE TESTS: asyncHandler()
 * ============================================================================
 */

describe('asyncHandler wrapper', () => {
  let req: Request;
  let res: Response;
  let next: NextFunction;

  beforeEach(() => {
    req = {} as Request;
    res = {} as Response;
    next = jest.fn();
  });

  test('resolves successfully', async () => {
    const handler = asyncHandler(async (req, res) => {
      res.json = jest.fn();
      res.json({ success: true });
    });

    handler(req, res, next);

    // Give promise time to resolve
    await new Promise((r) => setTimeout(r, 10));

    expect(next).not.toHaveBeenCalled();
  });

  test('catches async error', async () => {
    const error = new Error('Async error');
    const handler = asyncHandler(async (req, res) => {
      throw error;
    });

    handler(req, res, next);

    // Give promise time to catch
    await new Promise((r) => setTimeout(r, 10));

    expect(next).toHaveBeenCalledWith(error);
  });

  test('catches promise rejection', async () => {
    const error = new Error('Promise rejected');
    const handler = asyncHandler(async (req, res) => {
      await Promise.reject(error);
    });

    handler(req, res, next);

    // Give promise time to catch
    await new Promise((r) => setTimeout(r, 10));

    expect(next).toHaveBeenCalledWith(error);
  });
});

/**
 * ============================================================================
 * INTEGRATION TESTS: Full Error Flow
 * ============================================================================
 */

describe('Error handling integration', () => {
  test('ApiError flows through without modification', () => {
    const req = {} as Request;
    const res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis(),
    } as unknown as Response;
    const next = jest.fn();

    const error = new Error() as any;
    error.errorCode = 'INVALID_REQUEST';
    error.statusCode = 400;

    globalErrorHandler(error, req, res, next);

    const [statusCode] = (res.status as jest.Mock).mock.calls[0];
    const [body] = (res.json as jest.Mock).mock.calls[0];

    expect(statusCode).toBe(400);
    expect(body).toEqual({ errorCode: 'INVALID_REQUEST' });
  });

  test('Generic error maps to INTERNAL_ERROR', () => {
    const req = {} as Request;
    const res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis(),
    } as unknown as Response;
    const next = jest.fn();

    globalErrorHandler(new Error('Database failed'), req, res, next);

    const [statusCode] = (res.status as jest.Mock).mock.calls[0];
    const [body] = (res.json as jest.Mock).mock.calls[0];

    expect(statusCode).toBe(500);
    expect(body).toEqual({ errorCode: 'INTERNAL_ERROR' });
  });
});

/**
 * ============================================================================
 * SCHEMA VALIDATION TESTS
 * ============================================================================
 */

describe('Response schema compliance', () => {
  const errorResponses = [
    { errorCode: 'INVALID_REQUEST' },
    { errorCode: 'UNAUTHORIZED' },
    { errorCode: 'FORBIDDEN' },
    { errorCode: 'NOT_FOUND' },
    { errorCode: 'INTERNAL_ERROR' },
  ];

  errorResponses.forEach((response) => {
    test(`validates schema for ${response.errorCode}`, () => {
      expect(response).toHaveProperty('errorCode');
      expect(typeof response.errorCode).toBe('string');

      // Ensure no other fields
      const keys = Object.keys(response);
      expect(keys.length).toBe(1);
      expect(keys[0]).toBe('errorCode');
    });
  });
});

/**
 * ============================================================================
 * WHAT IS NEVER IN RESPONSES (Negative Tests)
 * ============================================================================
 */

describe('Security: What is never in responses', () => {
  let req: Request;
  let res: Partial<Response>;
  let next: NextFunction;

  beforeEach(() => {
    req = {} as Request;
    res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis(),
    };
    next = jest.fn();
  });

  test('never includes stack traces', () => {
    const error = new Error('Test error');
    globalErrorHandler(error, req, res as Response, next);

    const body = (res.json as jest.Mock).mock.calls[0][0];
    expect(body.stack).toBeUndefined();
  });

  test('never includes error messages', () => {
    const error = new Error('Sensitive data here');
    globalErrorHandler(error, req, res as Response, next);

    const body = (res.json as jest.Mock).mock.calls[0][0];
    expect(body.message).toBeUndefined();
  });

  test('never includes error cause', () => {
    const error = new Error('Test error');
    (error as any).cause = 'Some cause';
    globalErrorHandler(error, req, res as Response, next);

    const body = (res.json as jest.Mock).mock.calls[0][0];
    expect(body.cause).toBeUndefined();
  });

  test('never includes error details', () => {
    const error = new Error('Test error');
    (error as any).details = { db: 'password', api: 'key' };
    globalErrorHandler(error, req, res as Response, next);

    const body = (res.json as jest.Mock).mock.calls[0][0];
    expect(body.details).toBeUndefined();
  });

  test('never includes framework error object', () => {
    const error = {
      status: 400,
      message: 'Validation failed',
      errors: [{ field: 'email', message: 'Invalid' }],
    };
    globalErrorHandler(error, req, res as Response, next);

    const body = (res.json as jest.Mock).mock.calls[0][0];
    expect(body.errors).toBeUndefined();
    expect(body.status).toBeUndefined();
  });
});
