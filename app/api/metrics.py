"""
Prometheus-compatible metrics endpoints.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, List
from app.core.redis_client import redis_client
from app.core.circuit_breaker import CircuitBreakerRegistry


router = APIRouter()


class MetricsResponse(BaseModel):
    """Metrics response."""
    counters: Dict[str, int]
    circuits: Dict[str, dict]


@router.get("", response_model=MetricsResponse)
async def get_metrics():
    """Get all metrics."""
    counters = await redis_client.get_metrics()
    
    # Get circuit breaker statuses
    circuits = {}
    all_statuses = await CircuitBreakerRegistry.get_all_status()
    for service, status in all_statuses.items():
        circuits[service] = {
            "state": status.state.value,
            "failures": status.failures,
            "success_count": status.success_count,
            "available": status.is_available
        }
    
    return MetricsResponse(
        counters=counters,
        circuits=circuits
    )


@router.get("/prometheus")
async def get_prometheus_metrics():
    """Get metrics in Prometheus format."""
    counters = await redis_client.get_metrics()
    circuits = await CircuitBreakerRegistry.get_all_status()
    
    lines = []
    
    # Counter metrics
    lines.append("# HELP api_gateway_requests_total Total requests")
    lines.append("# TYPE api_gateway_requests_total counter")
    for name, value in counters.items():
        # Parse labels from metric name
        if ":" in name:
            metric_name, labels = name.split(":", 1)
            labels = labels.replace("=", '="').replace(",", '",') + '"'
            lines.append(f"api_gateway_{metric_name}{{{labels}}} {value}")
        else:
            lines.append(f"api_gateway_{name} {value}")
    
    # Circuit breaker metrics
    lines.append("")
    lines.append("# HELP api_gateway_circuit_state Circuit breaker state (0=closed, 1=open, 2=half_open)")
    lines.append("# TYPE api_gateway_circuit_state gauge")
    
    state_map = {"closed": 0, "open": 1, "half_open": 2}
    for service, status in circuits.items():
        state_value = state_map.get(status.state.value, -1)
        lines.append(f'api_gateway_circuit_state{{service="{service}"}} {state_value}')
    
    lines.append("")
    lines.append("# HELP api_gateway_circuit_failures Circuit breaker failure count")
    lines.append("# TYPE api_gateway_circuit_failures gauge")
    for service, status in circuits.items():
        lines.append(f'api_gateway_circuit_failures{{service="{service}"}} {status.failures}')
    
    return "\n".join(lines) + "\n"


@router.get("/latency/{service}")
async def get_latency_stats(service: str):
    """Get latency statistics for a service."""
    key = f"latency:{service}"
    
    try:
        latencies = await redis_client.client.lrange(key, 0, -1)
        if not latencies:
            return {
                "service": service,
                "samples": 0,
                "message": "No latency data available"
            }
        
        values = [float(l) for l in latencies]
        values.sort()
        
        count = len(values)
        avg = sum(values) / count
        p50 = values[int(count * 0.5)]
        p95 = values[int(count * 0.95)]
        p99 = values[int(count * 0.99)]
        
        return {
            "service": service,
            "samples": count,
            "avg_ms": round(avg, 2),
            "p50_ms": round(p50, 2),
            "p95_ms": round(p95, 2),
            "p99_ms": round(p99, 2),
            "min_ms": round(min(values), 2),
            "max_ms": round(max(values), 2)
        }
    except Exception as e:
        return {
            "service": service,
            "error": str(e)
        }


@router.post("/reset")
async def reset_metrics():
    """Reset all metrics (for testing)."""
    keys = await redis_client.client.keys("metric:*")
    if keys:
        await redis_client.client.delete(*keys)
    
    keys = await redis_client.client.keys("latency:*")
    if keys:
        await redis_client.client.delete(*keys)
    
    return {"message": "Metrics reset"}
