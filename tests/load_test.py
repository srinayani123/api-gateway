"""
Load testing with Locust.

Run with:
    locust -f tests/load_test.py --host=http://localhost:8000
"""

from locust import HttpUser, task, between
import json


class GatewayUser(HttpUser):
    """Simulates typical API gateway user."""
    
    wait_time = between(0.5, 2)
    
    def on_start(self):
        """Login to get token."""
        response = self.client.post(
            "/api/auth/login",
            json={"username": "loadtest", "password": "loadtest123"}
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = None
            self.headers = {}
    
    @task(5)
    def health_check(self):
        """Check health endpoint."""
        self.client.get("/health")
    
    @task(3)
    def get_services(self):
        """List available services."""
        self.client.get("/api/services", headers=self.headers)
    
    @task(2)
    def get_metrics(self):
        """Get metrics."""
        self.client.get("/metrics")
    
    @task(1)
    def detailed_health(self):
        """Get detailed health."""
        self.client.get("/health/detailed")


class BurstUser(HttpUser):
    """Simulates bursty traffic to test rate limiting."""
    
    wait_time = between(0.1, 0.3)
    
    @task
    def burst_requests(self):
        """Send rapid requests."""
        for _ in range(10):
            self.client.get("/health")


class CircuitBreakerTestUser(HttpUser):
    """Tests circuit breaker behavior."""
    
    wait_time = between(1, 3)
    
    def on_start(self):
        """Login to get token."""
        response = self.client.post(
            "/api/auth/login",
            json={"username": "circuitest", "password": "test123"}
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.headers = {}
    
    @task(3)
    def call_users_service(self):
        """Call users service (may fail)."""
        self.client.get("/api/users/1", headers=self.headers)
    
    @task(1)
    def check_circuit_status(self):
        """Check circuit breaker status."""
        self.client.get("/api/circuits", headers=self.headers)


class MixedTrafficUser(HttpUser):
    """Realistic mixed traffic pattern."""
    
    wait_time = between(0.5, 3)
    
    def on_start(self):
        """Login to get token."""
        response = self.client.post(
            "/api/auth/login",
            json={"username": "mixeduser", "password": "test123"}
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.headers = {}
    
    @task(10)
    def read_heavy(self):
        """Read operations (most common)."""
        self.client.get("/health")
    
    @task(5)
    def authenticated_read(self):
        """Authenticated read."""
        self.client.get("/api/services", headers=self.headers)
    
    @task(2)
    def metrics_read(self):
        """Read metrics."""
        self.client.get("/metrics")
    
    @task(1)
    def login_flow(self):
        """Simulate login flow."""
        self.client.post(
            "/api/auth/login",
            json={"username": "testuser", "password": "testpass"}
        )
