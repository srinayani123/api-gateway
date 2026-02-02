"""
Circuit Breaker Pattern Implementation.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Circuit is tripped, requests fail fast
- HALF_OPEN: Testing if service recovered
"""

import time
from enum import Enum
from typing import Optional, Callable, Any
from dataclasses import dataclass
from app.config import settings
from app.core.redis_client import redis_client


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitStatus:
    """Circuit breaker status."""
    state: CircuitState
    failures: int
    last_failure_time: float
    success_count: int
    is_available: bool


class CircuitBreaker:
    """
    Circuit Breaker implementation with Redis-backed state.
    
    Features:
    - Distributed state via Redis
    - Configurable failure threshold
    - Automatic recovery with half-open state
    - Per-service circuit tracking
    """
    
    def __init__(
        self,
        service: str,
        failure_threshold: int = None,
        recovery_timeout: int = None,
        half_open_requests: int = None
    ):
        """
        Initialize circuit breaker.
        
        Args:
            service: Service identifier
            failure_threshold: Failures before opening circuit
            recovery_timeout: Seconds before trying half-open
            half_open_requests: Successful requests to close circuit
        """
        self.service = service
        self.failure_threshold = failure_threshold or settings.circuit_failure_threshold
        self.recovery_timeout = recovery_timeout or settings.circuit_recovery_timeout
        self.half_open_requests = half_open_requests or settings.circuit_half_open_requests
    
    async def get_status(self) -> CircuitStatus:
        """Get current circuit status."""
        state_dict = await redis_client.get_circuit_state(self.service)
        state = CircuitState(state_dict["state"])
        
        # Check if we should transition from OPEN to HALF_OPEN
        if state == CircuitState.OPEN:
            time_since_failure = time.time() - state_dict["last_failure_time"]
            if time_since_failure >= self.recovery_timeout:
                state = CircuitState.HALF_OPEN
                await self._set_state(state, state_dict["failures"], 0)
        
        is_available = state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)
        
        return CircuitStatus(
            state=state,
            failures=state_dict["failures"],
            last_failure_time=state_dict["last_failure_time"],
            success_count=state_dict["success_count"],
            is_available=is_available
        )
    
    async def is_available(self) -> bool:
        """Check if circuit allows requests."""
        status = await self.get_status()
        return status.is_available
    
    async def record_success(self) -> None:
        """Record a successful request."""
        state_dict = await redis_client.get_circuit_state(self.service)
        state = CircuitState(state_dict["state"])
        
        if state == CircuitState.HALF_OPEN:
            success_count = state_dict["success_count"] + 1
            
            if success_count >= self.half_open_requests:
                # Circuit recovered - close it
                await self._set_state(CircuitState.CLOSED, 0, 0)
                await redis_client.increment_metric(
                    "circuit_closed", 
                    f"service={self.service}"
                )
            else:
                await self._set_state(state, state_dict["failures"], success_count)
        
        elif state == CircuitState.CLOSED:
            # Reset failures on success
            if state_dict["failures"] > 0:
                await self._set_state(CircuitState.CLOSED, 0, 0)
        
        await redis_client.increment_metric(
            "requests_success",
            f"service={self.service}"
        )
    
    async def record_failure(self) -> None:
        """Record a failed request."""
        state_dict = await redis_client.get_circuit_state(self.service)
        state = CircuitState(state_dict["state"])
        failures = state_dict["failures"] + 1
        
        if state == CircuitState.HALF_OPEN:
            # Failure during recovery - reopen circuit
            await self._set_state(CircuitState.OPEN, failures, 0)
            await redis_client.increment_metric(
                "circuit_opened",
                f"service={self.service}"
            )
        
        elif state == CircuitState.CLOSED:
            if failures >= self.failure_threshold:
                # Threshold exceeded - open circuit
                await self._set_state(CircuitState.OPEN, failures, 0)
                await redis_client.increment_metric(
                    "circuit_opened",
                    f"service={self.service}"
                )
            else:
                await self._set_state(CircuitState.CLOSED, failures, 0)
        
        await redis_client.increment_metric(
            "requests_failed",
            f"service={self.service}"
        )
    
    async def _set_state(
        self,
        state: CircuitState,
        failures: int,
        success_count: int
    ) -> None:
        """Set circuit state in Redis."""
        await redis_client.set_circuit_state(self.service, {
            "state": state.value,
            "failures": failures,
            "last_failure_time": time.time() if state == CircuitState.OPEN else 0,
            "success_count": success_count
        })


class CircuitBreakerRegistry:
    """Registry of circuit breakers per service."""
    
    _breakers: dict[str, CircuitBreaker] = {}
    
    @classmethod
    def get(cls, service: str) -> CircuitBreaker:
        """Get or create circuit breaker for service."""
        if service not in cls._breakers:
            cls._breakers[service] = CircuitBreaker(service)
        return cls._breakers[service]
    
    @classmethod
    async def get_all_status(cls) -> dict[str, CircuitStatus]:
        """Get status of all circuit breakers."""
        statuses = {}
        for service, breaker in cls._breakers.items():
            statuses[service] = await breaker.get_status()
        return statuses
