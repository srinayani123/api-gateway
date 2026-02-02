"""
Reverse Proxy Service.

Routes requests to upstream services with:
- Circuit breaker protection
- Request/response transformation
- Latency tracking
"""

import time
import httpx
from typing import Optional
from fastapi import Request, Response, HTTPException, status

from app.config import settings, UPSTREAM_SERVICES
from app.core.circuit_breaker import CircuitBreakerRegistry, CircuitState
from app.core.redis_client import redis_client


class ProxyService:
    """
    Reverse proxy service with circuit breaker integration.
    """
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=settings.upstream_timeout,
            follow_redirects=True
        )
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
    
    async def forward_request(
        self,
        request: Request,
        service: str,
        path: str
    ) -> Response:
        """
        Forward request to upstream service.
        
        Args:
            request: Incoming FastAPI request
            service: Target service name
            path: Path to forward to
            
        Returns:
            Response from upstream service
        """
        # Get upstream URL
        upstream_url = UPSTREAM_SERVICES.get(service)
        if not upstream_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Service '{service}' not found"
            )
        
        # Check circuit breaker
        circuit = CircuitBreakerRegistry.get(service)
        circuit_status = await circuit.get_status()
        
        if not circuit_status.is_available:
            await redis_client.increment_metric(
                "circuit_rejected",
                f"service={service}"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Service '{service}' is temporarily unavailable",
                headers={"Retry-After": str(settings.circuit_recovery_timeout)}
            )
        
        # Build target URL
        target_url = f"{upstream_url}{path}"
        
        # Prepare headers (remove hop-by-hop headers)
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("connection", None)
        headers.pop("keep-alive", None)
        headers.pop("transfer-encoding", None)
        
        # Add gateway headers
        headers["X-Forwarded-For"] = request.client.host if request.client else "unknown"
        headers["X-Forwarded-Proto"] = request.url.scheme
        headers["X-Gateway-Request-Id"] = str(time.time_ns())
        
        # Get request body
        body = await request.body()
        
        start_time = time.time()
        
        try:
            # Forward request
            response = await self.client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=dict(request.query_params)
            )
            
            # Record latency
            latency_ms = (time.time() - start_time) * 1000
            await redis_client.record_latency(service, latency_ms)
            
            # Record success
            await circuit.record_success()
            await redis_client.increment_metric(
                "requests_total",
                f"service={service},status={response.status_code}"
            )
            
            # Build response
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=self._filter_response_headers(response.headers),
                media_type=response.headers.get("content-type")
            )
            
        except httpx.TimeoutException:
            await circuit.record_failure()
            await redis_client.increment_metric(
                "requests_timeout",
                f"service={service}"
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=f"Upstream service '{service}' timed out"
            )
            
        except httpx.ConnectError:
            await circuit.record_failure()
            await redis_client.increment_metric(
                "requests_connection_error",
                f"service={service}"
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Cannot connect to service '{service}'"
            )
            
        except Exception as e:
            await circuit.record_failure()
            await redis_client.increment_metric(
                "requests_error",
                f"service={service}"
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Error proxying to service '{service}': {str(e)}"
            )
    
    def _filter_response_headers(self, headers: httpx.Headers) -> dict:
        """Filter out hop-by-hop headers from response."""
        hop_by_hop = {
            "connection", "keep-alive", "proxy-authenticate",
            "proxy-authorization", "te", "trailers",
            "transfer-encoding", "upgrade"
        }
        
        return {
            k: v for k, v in headers.items()
            if k.lower() not in hop_by_hop
        }
    
    def resolve_service(self, path: str) -> tuple[str, str]:
        """
        Resolve service and remaining path from URL path.
        
        Args:
            path: Full request path (e.g., "/api/users/123")
            
        Returns:
            Tuple of (service_name, remaining_path)
        """
        # Remove /api prefix
        if path.startswith("/api/"):
            path = path[4:]  # Remove "/api"
        
        # Extract service name
        parts = path.split("/", 2)
        if len(parts) < 2:
            return None, path
        
        service = parts[1]
        remaining_path = "/" + parts[2] if len(parts) > 2 else "/"
        
        return service, remaining_path


class RequestTransformer:
    """Transform requests before forwarding."""
    
    @staticmethod
    def add_correlation_id(headers: dict) -> dict:
        """Add correlation ID for distributed tracing."""
        if "X-Correlation-Id" not in headers:
            headers["X-Correlation-Id"] = str(time.time_ns())
        return headers
    
    @staticmethod
    def sanitize_headers(headers: dict) -> dict:
        """Remove sensitive headers."""
        sensitive = {"x-api-key", "x-internal-token"}
        return {k: v for k, v in headers.items() if k.lower() not in sensitive}


class ResponseTransformer:
    """Transform responses before returning to client."""
    
    @staticmethod
    def add_gateway_headers(headers: dict, service: str, latency_ms: float) -> dict:
        """Add gateway metadata headers."""
        headers["X-Gateway-Service"] = service
        headers["X-Gateway-Latency-Ms"] = str(int(latency_ms))
        return headers


# Global proxy service instance
proxy_service = ProxyService()
