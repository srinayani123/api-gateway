"""
Tests for circuit breaker functionality.
"""

import pytest
from unittest.mock import AsyncMock, patch
from app.core.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerRegistry
from app.core.redis_client import redis_client


class TestCircuitBreaker:
    """Tests for circuit breaker pattern."""
    
    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self, mock_redis):
        """Circuit should start in closed state."""
        redis_client._client = mock_redis
        
        breaker = CircuitBreaker("test-service")
        status = await breaker.get_status()
        
        assert status.state == CircuitState.CLOSED
        assert status.failures == 0
        assert status.is_available == True
    
    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self, mock_redis):
        """Circuit should open after reaching failure threshold."""
        redis_client._client = mock_redis
        
        breaker = CircuitBreaker("test-service", failure_threshold=3)
        
        # Record failures
        for _ in range(3):
            await breaker.record_failure()
        
        status = await breaker.get_status()
        assert status.state == CircuitState.OPEN
        assert status.is_available == False
    
    @pytest.mark.asyncio
    async def test_success_resets_failures(self, mock_redis):
        """Successful request should reset failure count."""
        redis_client._client = mock_redis
        
        breaker = CircuitBreaker("test-service")
        
        # Record some failures
        await breaker.record_failure()
        await breaker.record_failure()
        
        # Record success
        await breaker.record_success()
        
        status = await breaker.get_status()
        assert status.failures == 0
    
    @pytest.mark.asyncio
    async def test_half_open_closes_on_success(self, mock_redis):
        """Circuit should close after successful requests in half-open state."""
        redis_client._client = mock_redis
        
        breaker = CircuitBreaker(
            "test-service",
            failure_threshold=2,
            half_open_requests=2
        )
        
        # Set to half-open state manually
        await breaker._set_state(CircuitState.HALF_OPEN, 2, 0)
        
        # Record successful requests
        await breaker.record_success()
        await breaker.record_success()
        
        status = await breaker.get_status()
        assert status.state == CircuitState.CLOSED


class TestCircuitBreakerRegistry:
    """Tests for circuit breaker registry."""
    
    def test_get_creates_new_breaker(self):
        """Registry should create new breaker if not exists."""
        CircuitBreakerRegistry._breakers = {}
        
        breaker = CircuitBreakerRegistry.get("new-service")
        
        assert breaker is not None
        assert breaker.service == "new-service"
    
    def test_get_returns_existing_breaker(self):
        """Registry should return existing breaker."""
        CircuitBreakerRegistry._breakers = {}
        
        breaker1 = CircuitBreakerRegistry.get("same-service")
        breaker2 = CircuitBreakerRegistry.get("same-service")
        
        assert breaker1 is breaker2
