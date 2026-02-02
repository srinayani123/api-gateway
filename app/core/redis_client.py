"""
Redis client for rate limiting and circuit breaker state.
"""

import redis.asyncio as redis
from typing import Optional
from app.config import settings


class RedisClient:
    """Async Redis client wrapper."""
    
    def __init__(self):
        self._client: Optional[redis.Redis] = None
    
    async def initialize(self) -> None:
        """Initialize Redis connection."""
        self._client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
    
    @property
    def client(self) -> redis.Redis:
        """Get Redis client."""
        if not self._client:
            raise RuntimeError("Redis client not initialized")
        return self._client
    
    # Sliding Window Rate Limiting
    async def sliding_window_increment(
        self, 
        key: str, 
        window_seconds: int
    ) -> int:
        """
        Increment counter for sliding window rate limiting.
        Returns current count in the window.
        """
        pipe = self._client.pipeline()
        now = await self._client.time()
        timestamp = now[0] * 1000 + now[1] // 1000  # milliseconds
        
        window_start = timestamp - (window_seconds * 1000)
        
        # Remove old entries
        await self._client.zremrangebyscore(key, 0, window_start)
        
        # Add current request
        await self._client.zadd(key, {str(timestamp): timestamp})
        
        # Set expiry
        await self._client.expire(key, window_seconds)
        
        # Get count
        count = await self._client.zcard(key)
        
        return count
    
    # Token Bucket Rate Limiting
    async def token_bucket_consume(
        self,
        key: str,
        capacity: int,
        refill_rate: float,
        tokens_to_consume: int = 1
    ) -> tuple[bool, int]:
        """
        Try to consume tokens from bucket.
        Returns (success, remaining_tokens).
        """
        now = await self._client.time()
        current_time = now[0] + now[1] / 1000000
        
        bucket_key = f"bucket:{key}"
        last_update_key = f"bucket_time:{key}"
        
        # Get current state
        tokens = await self._client.get(bucket_key)
        last_update = await self._client.get(last_update_key)
        
        if tokens is None:
            tokens = capacity
        else:
            tokens = float(tokens)
        
        if last_update is None:
            last_update = current_time
        else:
            last_update = float(last_update)
        
        # Calculate tokens to add based on time elapsed
        time_elapsed = current_time - last_update
        tokens_to_add = time_elapsed * refill_rate
        tokens = min(capacity, tokens + tokens_to_add)
        
        # Try to consume
        if tokens >= tokens_to_consume:
            tokens -= tokens_to_consume
            await self._client.set(bucket_key, tokens)
            await self._client.set(last_update_key, current_time)
            await self._client.expire(bucket_key, 3600)
            await self._client.expire(last_update_key, 3600)
            return True, int(tokens)
        else:
            await self._client.set(bucket_key, tokens)
            await self._client.set(last_update_key, current_time)
            return False, int(tokens)
    
    # Circuit Breaker State
    async def get_circuit_state(self, service: str) -> dict:
        """Get circuit breaker state for a service."""
        key = f"circuit:{service}"
        state = await self._client.hgetall(key)
        
        if not state:
            return {
                "state": "closed",
                "failures": 0,
                "last_failure_time": 0,
                "success_count": 0
            }
        
        return {
            "state": state.get("state", "closed"),
            "failures": int(state.get("failures", 0)),
            "last_failure_time": float(state.get("last_failure_time", 0)),
            "success_count": int(state.get("success_count", 0))
        }
    
    async def set_circuit_state(self, service: str, state: dict) -> None:
        """Set circuit breaker state for a service."""
        key = f"circuit:{service}"
        await self._client.hset(key, mapping={
            "state": state["state"],
            "failures": str(state["failures"]),
            "last_failure_time": str(state["last_failure_time"]),
            "success_count": str(state["success_count"])
        })
        await self._client.expire(key, 3600)
    
    # Metrics
    async def increment_metric(self, metric: str, labels: str = "") -> None:
        """Increment a counter metric."""
        key = f"metric:{metric}:{labels}"
        await self._client.incr(key)
        await self._client.expire(key, 86400)  # 24 hours
    
    async def record_latency(self, service: str, latency_ms: float) -> None:
        """Record request latency."""
        key = f"latency:{service}"
        await self._client.lpush(key, str(latency_ms))
        await self._client.ltrim(key, 0, 999)  # Keep last 1000
        await self._client.expire(key, 3600)
    
    async def get_metrics(self) -> dict:
        """Get all metrics."""
        keys = await self._client.keys("metric:*")
        metrics = {}
        
        for key in keys:
            value = await self._client.get(key)
            metric_name = key.replace("metric:", "")
            metrics[metric_name] = int(value) if value else 0
        
        return metrics


# Global Redis client instance
redis_client = RedisClient()
