"""
Tests for JWT authentication.
"""

import pytest
from datetime import timedelta
from app.core.auth import (
    create_access_token,
    decode_token,
    is_public_route,
    TokenInfo
)


class TestJWTTokens:
    """Tests for JWT token creation and validation."""
    
    def test_create_and_decode_token(self):
        """Should create valid token that can be decoded."""
        token = create_access_token(
            user_id="user123",
            roles=["user", "admin"],
            permissions=["read", "write"]
        )
        
        decoded = decode_token(token)
        
        assert decoded is not None
        assert decoded.user_id == "user123"
        assert "user" in decoded.roles
        assert "admin" in decoded.roles
        assert "read" in decoded.permissions
    
    def test_expired_token_returns_none(self):
        """Expired token should return None."""
        token = create_access_token(
            user_id="user123",
            expires_delta=timedelta(seconds=-1)  # Already expired
        )
        
        decoded = decode_token(token)
        
        assert decoded is None
    
    def test_invalid_token_returns_none(self):
        """Invalid token should return None."""
        decoded = decode_token("invalid.token.here")
        
        assert decoded is None
    
    def test_token_with_default_expiry(self):
        """Token with default expiry should be valid."""
        token = create_access_token(user_id="user123")
        
        decoded = decode_token(token)
        
        assert decoded is not None
        assert decoded.user_id == "user123"


class TestPublicRoutes:
    """Tests for public route checking."""
    
    def test_health_is_public(self):
        """Health endpoint should be public."""
        assert is_public_route("/health") == True
    
    def test_metrics_is_public(self):
        """Metrics endpoint should be public."""
        assert is_public_route("/metrics") == True
    
    def test_auth_login_is_public(self):
        """Login endpoint should be public."""
        assert is_public_route("/api/auth/login") == True
    
    def test_api_users_is_protected(self):
        """Users API should be protected."""
        assert is_public_route("/api/users/123") == False
    
    def test_api_orders_is_protected(self):
        """Orders API should be protected."""
        assert is_public_route("/api/orders") == False


class TestAuthEndpoints:
    """Tests for auth API endpoints."""
    
    def test_login_returns_token(self, client):
        """Login should return access token."""
        response = client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "testpass"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    def test_login_invalid_credentials(self, client):
        """Login with empty credentials should fail."""
        response = client.post(
            "/api/auth/login",
            json={"username": "", "password": ""}
        )
        
        assert response.status_code == 401
    
    def test_register_success(self, client):
        """Registration should succeed."""
        response = client.post(
            "/api/auth/register",
            json={"username": "newuser", "email": "new@example.com"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "newuser"
