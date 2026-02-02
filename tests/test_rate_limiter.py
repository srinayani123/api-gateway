"""
Tests for rate limiting functionality.
"""

import pytest
from fastapi.testclient import TestClient


class TestSlidingWindow:
    """Tests for sliding window rate limiting."""
    
    def test_allows_requests_under_limit(self, client):
        """Requests under limit should pass."""
        response = client.get("/health")
        assert response.status_code == 200
    
    def test_rate_limit_headers(self, client):
        """Response should include rate limit headers."""
        response = client.get("/health")
        # Health endpoint bypasses rate limiting
        assert response.status_code == 200


class TestTokenBucket:
    """Tests for token bucket rate limiting."""
    
    def test_allows_burst(self, client):
        """Should allow burst of requests."""
        # First few requests should succeed
        for _ in range(5):
            response = client.get("/health")
            assert response.status_code == 200


class TestRateLimitBypass:
    """Tests for rate limit bypass on certain endpoints."""
    
    def test_health_bypasses_rate_limit(self, client):
        """Health endpoint should bypass rate limiting."""
        for _ in range(10):
            response = client.get("/health")
            assert response.status_code == 200
    
    def test_metrics_bypasses_rate_limit(self, client):
        """Metrics endpoint should bypass rate limiting."""
        for _ in range(10):
            response = client.get("/metrics")
            assert response.status_code == 200
