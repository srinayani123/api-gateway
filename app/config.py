"""
Configuration settings for API Gateway.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Dict, List


class Settings(BaseSettings):
    """Application settings."""
    
    # Application
    app_name: str = "API Gateway"
    environment: str = "development"
    debug: bool = True
    
    # Redis
    redis_url: str = "redis://localhost:6379"
    
    # JWT Settings
    jwt_secret_key: str = "your-super-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    
    # Rate Limiting - Sliding Window
    rate_limit_requests: int = 100  # requests per window
    rate_limit_window_seconds: int = 60  # window size
    
    # Rate Limiting - Token Bucket
    token_bucket_capacity: int = 50  # max tokens
    token_bucket_refill_rate: float = 10.0  # tokens per second
    
    # Circuit Breaker
    circuit_failure_threshold: int = 5  # failures before opening
    circuit_recovery_timeout: int = 30  # seconds before half-open
    circuit_half_open_requests: int = 3  # test requests in half-open
    
    # Upstream Services
    upstream_timeout: float = 10.0  # seconds
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


# Upstream service configuration
UPSTREAM_SERVICES: Dict[str, str] = {
    "users": "http://users-service:8001",
    "orders": "http://orders-service:8002",
    "products": "http://products-service:8003",
    "payments": "http://payments-service:8004",
}

# Routes that don't require authentication
PUBLIC_ROUTES: List[str] = [
    "/health",
    "/metrics",
    "/api/auth/login",
    "/api/auth/register",
]
