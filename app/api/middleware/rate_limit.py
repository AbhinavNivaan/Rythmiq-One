"""
Rate Limiting Middleware.

Implements token bucket rate limiting per IP address.
Prevents API abuse and protects against DDoS.
"""

import time
from dataclasses import dataclass, field
from typing import Dict

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""
    
    capacity: int
    tokens: float = field(init=False)
    refill_rate: float  # tokens per second
    last_update: float = field(default_factory=time.time)
    
    def __post_init__(self):
        self.tokens = float(self.capacity)
    
    def consume(self, tokens: int = 1) -> bool:
        """Attempt to consume tokens. Returns True if allowed."""
        now = time.time()
        elapsed = now - self.last_update
        
        # Refill tokens based on elapsed time
        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate
        )
        self.last_update = now
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def time_until_available(self) -> float:
        """Returns seconds until at least 1 token is available."""
        if self.tokens >= 1:
            return 0
        return (1 - self.tokens) / self.refill_rate


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using token bucket algorithm.
    
    Default limits:
    - 100 requests per minute for general endpoints
    - 10 requests per minute for auth endpoints
    - 20 requests per minute for upload endpoints
    """
    
    # Rate limit configurations per path prefix
    RATE_LIMITS: Dict[str, tuple] = {
        "/auth/": (10, 60),      # 10 requests per minute
        "/upload": (20, 60),     # 20 requests per minute
        "/process": (20, 60),    # 20 requests per minute
        "/adapt": (30, 60),      # 30 requests per minute
        "default": (100, 60),    # 100 requests per minute
    }
    
    # Paths to exclude from rate limiting
    EXCLUDED_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}
    
    def __init__(self, app):
        super().__init__(app)
        self.buckets: Dict[str, TokenBucket] = {}
        self._max_buckets = 10_000  # Cap to prevent unbounded growth
        self._eviction_interval = 300  # 5 minutes
        self._last_eviction = time.time()
    
    def _get_bucket_key(self, request: Request) -> str:
        """Generate a unique key for the client."""
        # Use X-Forwarded-For if behind a proxy, otherwise use client host
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        
        # Include path prefix for path-specific limits
        path = request.url.path
        for prefix in self.RATE_LIMITS:
            if prefix != "default" and path.startswith(prefix):
                return f"{client_ip}:{prefix}"
        
        return f"{client_ip}:default"
    
    def _get_rate_limit(self, path: str) -> tuple:
        """Get rate limit config for a path."""
        for prefix, limit in self.RATE_LIMITS.items():
            if prefix != "default" and path.startswith(prefix):
                return limit
        return self.RATE_LIMITS["default"]
    
    def _evict_stale_buckets(self) -> None:
        """Remove buckets that haven't been accessed in 5+ minutes."""
        now = time.time()
        if now - self._last_eviction < self._eviction_interval:
            return
        self._last_eviction = now
        stale_keys = [
            k for k, b in self.buckets.items()
            if now - b.last_update > self._eviction_interval
        ]
        for k in stale_keys:
            del self.buckets[k]
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limiting for excluded paths
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)
        
        # Periodically evict stale buckets to prevent memory leak
        self._evict_stale_buckets()
        
        bucket_key = self._get_bucket_key(request)
        
        # Get or create bucket for this client/path combination
        if bucket_key not in self.buckets:
            capacity, period = self._get_rate_limit(request.url.path)
            self.buckets[bucket_key] = TokenBucket(
                capacity=capacity,
                refill_rate=capacity / period
            )
        
        bucket = self.buckets[bucket_key]
        
        if not bucket.consume():
            # Rate limit exceeded
            retry_after = int(bucket.time_until_available()) + 1
            
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many requests. Please slow down.",
                        "retry_after": retry_after,
                    }
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(bucket.capacity),
                    "X-RateLimit-Remaining": str(int(bucket.tokens)),
                }
            )
        
        # Add rate limit headers to successful responses
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(bucket.capacity)
        response.headers["X-RateLimit-Remaining"] = str(int(bucket.tokens))
        
        return response
