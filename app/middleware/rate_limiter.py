"""
Rate Limiter Middleware.

Implements two algorithms:
1. Sliding Window - for overall request limiting
2. Token Bucket - for burst handling
"""

import time
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings
from app.core.redis_client import redis_client


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using sliding window + token bucket.
    
    - Sliding Window: Limits total requests per time window
    - Token Bucket: Allows controlled bursts while limiting sustained rate
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request through rate limiter."""
        
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/metrics"]:
            return await call_next(request)
        
        # Get client identifier
        client_id = self._get_client_id(request)
        
        try:
            # Check sliding window limit
            window_allowed, window_remaining = await self._check_sliding_window(client_id)
            
            if not window_allowed:
                await redis_client.increment_metric(
                    "rate_limit_exceeded",
                    f"type=sliding_window"
                )
                return self._rate_limit_response(
                    "Rate limit exceeded",
                    window_remaining,
                    settings.rate_limit_window_seconds
                )
            
            # Check token bucket limit
            bucket_allowed, bucket_remaining = await self._check_token_bucket(client_id)
            
            if not bucket_allowed:
                await redis_client.increment_metric(
                    "rate_limit_exceeded",
                    f"type=token_bucket"
                )
                return self._rate_limit_response(
                    "Too many requests, please slow down",
                    bucket_remaining,
                    1  # Retry after 1 second for bucket
                )
            
            # Process request
            response = await call_next(request)
            
            # Add rate limit headers
            response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_requests)
            response.headers["X-RateLimit-Remaining"] = str(window_remaining)
            response.headers["X-RateLimit-Window"] = str(settings.rate_limit_window_seconds)
            response.headers["X-TokenBucket-Remaining"] = str(bucket_remaining)
            
            return response
            
        except Exception as e:
            # If Redis fails, allow request (fail open)
            print(f"Rate limiter error: {e}")
            return await call_next(request)
    
    def _get_client_id(self, request: Request) -> str:
        """Get unique client identifier."""
        # Try to get from JWT token first
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            # Use token hash as client ID for authenticated users
            token = auth_header[7:]
            return f"user:{hash(token) % 10**9}"
        
        # Fall back to IP address
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        
        return f"ip:{ip}"
    
    async def _check_sliding_window(self, client_id: str) -> tuple[bool, int]:
        """
        Check sliding window rate limit.
        Returns (allowed, remaining_requests).
        """
        key = f"ratelimit:window:{client_id}"
        
        count = await redis_client.sliding_window_increment(
            key,
            settings.rate_limit_window_seconds
        )
        
        remaining = max(0, settings.rate_limit_requests - count)
        allowed = count <= settings.rate_limit_requests
        
        return allowed, remaining
    
    async def _check_token_bucket(self, client_id: str) -> tuple[bool, int]:
        """
        Check token bucket rate limit.
        Returns (allowed, remaining_tokens).
        """
        allowed, remaining = await redis_client.token_bucket_consume(
            client_id,
            settings.token_bucket_capacity,
            settings.token_bucket_refill_rate
        )
        
        return allowed, remaining
    
    def _rate_limit_response(
        self,
        detail: str,
        remaining: int,
        retry_after: int
    ) -> JSONResponse:
        """Create rate limit exceeded response."""
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": detail,
                "remaining": remaining,
                "retry_after": retry_after
            },
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Remaining": str(remaining)
            }
        )


class RateLimiter:
    """
    Standalone rate limiter for use in route handlers.
    
    Usage:
        limiter = RateLimiter(requests=10, window=60)
        
        @app.get("/endpoint")
        async def endpoint(request: Request):
            await limiter.check(request)
            ...
    """
    
    def __init__(
        self,
        requests: int = None,
        window: int = None,
        bucket_capacity: int = None,
        bucket_rate: float = None
    ):
        self.requests = requests or settings.rate_limit_requests
        self.window = window or settings.rate_limit_window_seconds
        self.bucket_capacity = bucket_capacity or settings.token_bucket_capacity
        self.bucket_rate = bucket_rate or settings.token_bucket_refill_rate
    
    async def check(self, request: Request) -> None:
        """Check rate limit, raise HTTPException if exceeded."""
        client_id = self._get_client_id(request)
        
        # Check sliding window
        key = f"ratelimit:custom:{client_id}"
        count = await redis_client.sliding_window_increment(key, self.window)
        
        if count > self.requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(self.window)}
            )
    
    def _get_client_id(self, request: Request) -> str:
        """Get unique client identifier."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
