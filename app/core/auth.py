"""
JWT Authentication for API Gateway.
"""

from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.config import settings, PUBLIC_ROUTES


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str  # subject (user_id)
    exp: datetime  # expiration
    iat: datetime  # issued at
    roles: list[str] = []
    permissions: list[str] = []


class TokenInfo(BaseModel):
    """Decoded token information."""
    user_id: str
    roles: list[str]
    permissions: list[str]
    expires_at: datetime


security = HTTPBearer(auto_error=False)


def create_access_token(
    user_id: str,
    roles: list[str] = None,
    permissions: list[str] = None,
    expires_delta: timedelta = None
) -> str:
    """Create a new JWT access token."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=30)
    
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.utcnow(),
        "roles": roles or [],
        "permissions": permissions or []
    }
    
    encoded_jwt = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )
    return encoded_jwt


def decode_token(token: str) -> Optional[TokenInfo]:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        
        return TokenInfo(
            user_id=payload["sub"],
            roles=payload.get("roles", []),
            permissions=payload.get("permissions", []),
            expires_at=datetime.fromtimestamp(payload["exp"])
        )
    except JWTError:
        return None


def is_public_route(path: str) -> bool:
    """Check if route is public (no auth required)."""
    for public_path in PUBLIC_ROUTES:
        if path.startswith(public_path):
            return True
    return False


async def validate_request_auth(request: Request) -> Optional[TokenInfo]:
    """
    Validate request authentication.
    Returns TokenInfo if valid, None for public routes.
    Raises HTTPException for invalid auth on protected routes.
    """
    path = request.url.path
    
    # Skip auth for public routes
    if is_public_route(path):
        return None
    
    # Get authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Parse Bearer token
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = auth_header[7:]  # Remove "Bearer " prefix
    
    # Decode and validate token
    token_info = decode_token(token)
    if not token_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return token_info


def require_roles(required_roles: list[str]):
    """Decorator to require specific roles."""
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            token_info = await validate_request_auth(request)
            if token_info:
                if not any(role in token_info.roles for role in required_roles):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Required roles: {required_roles}"
                    )
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_permissions(required_permissions: list[str]):
    """Decorator to require specific permissions."""
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            token_info = await validate_request_auth(request)
            if token_info:
                if not all(perm in token_info.permissions for perm in required_permissions):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Required permissions: {required_permissions}"
                    )
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator
