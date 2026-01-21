import { Request, Response, NextFunction } from 'express';
import * as jwt from 'jsonwebtoken';
import { sendAuthError } from '../errors/validationErrors';

export interface AuthenticatedRequest extends Request {
  userId?: string;
}

interface TokenPayload {
  sub: string;
  iat?: number;
  exp?: number;
  [key: string]: any;
}

export function authenticateRequest(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    sendAuthError(res, 'Missing or malformed authorization header');
    return;
  }

  const token = authHeader.substring(7);

  if (!token || token.trim() === '') {
    sendAuthError(res, 'Empty authorization token');
    return;
  }

  const secret = process.env.AUTH_JWT_SECRET;
  if (!secret) {
    // This is a server configuration error - should not leak to client
    console.error('[AUTH_CONFIG_ERROR] JWT_SECRET not configured');
    res.status(500).json({ errorCode: 'SERVER_ERROR' });
    return;
  }

  try {
    const payload = jwt.verify(token, secret) as TokenPayload;

    if (!payload.sub) {
      sendAuthError(res, 'Invalid token: missing subject claim');
      return;
    }

    (req as AuthenticatedRequest).userId = payload.sub;
    next();
  } catch (error) {
    // Don't expose JWT error details (expired, invalid signature, etc.)
    const message =
      error instanceof jwt.TokenExpiredError
        ? 'Token has expired'
        : error instanceof jwt.JsonWebTokenError
          ? 'Invalid token signature'
          : 'Token verification failed';

    sendAuthError(res, message);
    return;
  }
}
