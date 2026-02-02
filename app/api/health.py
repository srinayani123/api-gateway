"""
Health check endpoints.
"""

from fastapi import APIRouter, Response
from pydantic import BaseModel
from typing import Optional
from app.core.redis_client import redis_client
from app.core.circuit_breaker import CircuitBreakerRegistry


router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    redis: str
    version: str = "1.0.0"


class DetailedHealthResponse(BaseModel):
    """Detailed health check response."""
    status: str
    redis: str
    version: str = "1.0.0"
    circuits: dict = {}


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic health check."""
    redis_status = "healthy"
    
    try:
        await redis_client.client.ping()
    except Exception:
        redis_status = "unhealthy"
    
    overall_status = "healthy" if redis_status == "healthy" else "degraded"
    
    return HealthResponse(
        status=overall_status,
        redis=redis_status
    )


@router.get("/health/detailed", response_model=DetailedHealthResponse)
async def detailed_health_check():
    """Detailed health check including circuit breaker status."""
    redis_status = "healthy"
    
    try:
        await redis_client.client.ping()
    except Exception:
        redis_status = "unhealthy"
    
    # Get circuit breaker statuses
    circuits = {}
    all_statuses = await CircuitBreakerRegistry.get_all_status()
    for service, status in all_statuses.items():
        circuits[service] = {
            "state": status.state.value,
            "failures": status.failures,
            "available": status.is_available
        }
    
    overall_status = "healthy" if redis_status == "healthy" else "degraded"
    
    return DetailedHealthResponse(
        status=overall_status,
        redis=redis_status,
        circuits=circuits
    )


@router.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe."""
    try:
        await redis_client.client.ping()
        return {"ready": True}
    except Exception:
        return Response(
            content='{"ready": false}',
            status_code=503,
            media_type="application/json"
        )


@router.get("/live")
async def liveness_check():
    """Kubernetes liveness probe."""
    return {"alive": True}
