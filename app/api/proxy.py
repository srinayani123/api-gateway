"""
Proxy endpoints for routing requests to upstream services.
"""

from fastapi import APIRouter, Request, Response, HTTPException, status
from typing import Optional
from pydantic import BaseModel

from app.services.proxy import proxy_service
from app.core.auth import validate_request_auth, create_access_token
from app.core.circuit_breaker import CircuitBreakerRegistry
from app.config import UPSTREAM_SERVICES


router = APIRouter()


class LoginRequest(BaseModel):
    """Login request body."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response."""
    access_token: str
    token_type: str = "bearer"


class CircuitStatusResponse(BaseModel):
    """Circuit breaker status response."""
    service: str
    state: str
    failures: int
    available: bool


# Auth endpoints (handled by gateway)
@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """
    Authenticate user and return JWT token.
    This is a demo endpoint - in production, this would validate against a user service.
    """
    # Demo authentication - accept any username/password
    # In production, forward to auth service or validate credentials
    if request.username and request.password:
        token = create_access_token(
            user_id=request.username,
            roles=["user"],
            permissions=["read", "write"]
        )
        return LoginResponse(access_token=token)
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials"
    )


@router.post("/auth/register")
async def register(request: Request):
    """
    Register new user.
    In production, forward to user service.
    """
    body = await request.json()
    return {
        "message": "User registered successfully",
        "username": body.get("username")
    }


# Circuit breaker management
@router.get("/circuits", response_model=list[CircuitStatusResponse])
async def get_circuit_status():
    """Get status of all circuit breakers."""
    statuses = await CircuitBreakerRegistry.get_all_status()
    
    result = []
    for service, circuit_status in statuses.items():
        result.append(CircuitStatusResponse(
            service=service,
            state=circuit_status.state.value,
            failures=circuit_status.failures,
            available=circuit_status.is_available
        ))
    
    return result


@router.post("/circuits/{service}/reset")
async def reset_circuit(service: str):
    """Manually reset a circuit breaker."""
    if service not in UPSTREAM_SERVICES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{service}' not found"
        )
    
    circuit = CircuitBreakerRegistry.get(service)
    await circuit._set_state(
        state=circuit.CircuitState.CLOSED,
        failures=0,
        success_count=0
    )
    
    return {"message": f"Circuit for '{service}' has been reset"}


@router.get("/services")
async def list_services():
    """List all configured upstream services."""
    services = []
    
    for name, url in UPSTREAM_SERVICES.items():
        circuit = CircuitBreakerRegistry.get(name)
        status = await circuit.get_status()
        
        services.append({
            "name": name,
            "url": url,
            "circuit_state": status.state.value,
            "available": status.is_available
        })
    
    return {"services": services}


# Catch-all proxy route
@router.api_route(
    "/{service}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
)
async def proxy_request(
    request: Request,
    service: str,
    path: str
) -> Response:
    """
    Proxy request to upstream service.
    
    Route pattern: /api/{service}/{path}
    
    Examples:
        GET /api/users/123 -> users-service/123
        POST /api/orders -> orders-service/
        GET /api/products/search?q=test -> products-service/search?q=test
    """
    # Validate authentication
    token_info = await validate_request_auth(request)
    
    # Add user info to headers for upstream service
    if token_info:
        request.scope["headers"] = [
            *request.scope.get("headers", []),
            (b"x-user-id", token_info.user_id.encode()),
            (b"x-user-roles", ",".join(token_info.roles).encode()),
        ]
    
    # Forward to upstream service
    target_path = f"/{path}" if path else "/"
    return await proxy_service.forward_request(request, service, target_path)


# Direct service routes for testing
@router.get("/users/{user_id}")
async def get_user(user_id: str, request: Request):
    """Get user by ID (proxied to users service)."""
    await validate_request_auth(request)
    return await proxy_service.forward_request(request, "users", f"/{user_id}")


@router.get("/orders")
async def get_orders(request: Request):
    """Get orders (proxied to orders service)."""
    await validate_request_auth(request)
    return await proxy_service.forward_request(request, "orders", "/")


@router.post("/orders")
async def create_order(request: Request):
    """Create order (proxied to orders service)."""
    await validate_request_auth(request)
    return await proxy_service.forward_request(request, "orders", "/")


@router.get("/products")
async def get_products(request: Request):
    """Get products (proxied to products service)."""
    # Products listing is public
    return await proxy_service.forward_request(request, "products", "/")


@router.get("/products/{product_id}")
async def get_product(product_id: str, request: Request):
    """Get product by ID (proxied to products service)."""
    return await proxy_service.forward_request(request, "products", f"/{product_id}")
