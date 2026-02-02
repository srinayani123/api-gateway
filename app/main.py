"""
API Gateway - Main Application
Production-ready API Gateway with rate limiting, circuit breaker, and JWT auth.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis

from app.config import settings
from app.api import health, proxy, metrics
from app.middleware.rate_limiter import RateLimiterMiddleware
from app.core.redis_client import redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown events."""
    print("Starting up API Gateway...")
    
    # Initialize Redis connection
    await redis_client.initialize()
    print("Redis connected")
    
    yield
    
    # Cleanup
    await redis_client.close()
    print("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    description="Production-ready API Gateway with rate limiting, circuit breaker, and JWT authentication",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiter middleware
app.add_middleware(RateLimiterMiddleware)

# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(metrics.router, prefix="/metrics", tags=["Metrics"])
app.include_router(proxy.router, prefix="/api", tags=["Proxy"])
