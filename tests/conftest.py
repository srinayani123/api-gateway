"""
Test configuration and fixtures.
"""

import pytest
import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app
from app.core.redis_client import redis_client


class MockRedis:
    """Mock Redis client for testing."""
    
    def __init__(self):
        self._data = {}
        self._sorted_sets = {}
        self._hashes = {}
        self._lists = {}
    
    async def ping(self):
        return True
    
    async def get(self, key):
        return self._data.get(key)
    
    async def set(self, key, value, ex=None):
        self._data[key] = str(value)
        return True
    
    async def incr(self, key):
        val = int(self._data.get(key, 0)) + 1
        self._data[key] = str(val)
        return val
    
    async def expire(self, key, seconds):
        return True
    
    async def delete(self, *keys):
        for key in keys:
            self._data.pop(key, None)
        return len(keys)
    
    async def keys(self, pattern):
        import fnmatch
        pattern = pattern.replace("*", ".*")
        return [k for k in self._data.keys() if fnmatch.fnmatch(k, pattern.replace(".*", "*"))]
    
    async def time(self):
        import time
        t = time.time()
        return (int(t), int((t % 1) * 1000000))
    
    # Sorted sets
    async def zadd(self, key, mapping):
        if key not in self._sorted_sets:
            self._sorted_sets[key] = {}
        self._sorted_sets[key].update(mapping)
        return len(mapping)
    
    async def zremrangebyscore(self, key, min_score, max_score):
        if key not in self._sorted_sets:
            return 0
        to_remove = [
            k for k, v in self._sorted_sets[key].items()
            if v >= min_score and v <= max_score
        ]
        for k in to_remove:
            del self._sorted_sets[key][k]
        return len(to_remove)
    
    async def zcard(self, key):
        return len(self._sorted_sets.get(key, {}))
    
    # Hashes
    async def hgetall(self, key):
        return self._hashes.get(key, {})
    
    async def hset(self, key, mapping):
        if key not in self._hashes:
            self._hashes[key] = {}
        self._hashes[key].update(mapping)
        return len(mapping)
    
    # Lists
    async def lpush(self, key, *values):
        if key not in self._lists:
            self._lists[key] = []
        for v in values:
            self._lists[key].insert(0, v)
        return len(self._lists[key])
    
    async def ltrim(self, key, start, end):
        if key in self._lists:
            if end == -1:
                self._lists[key] = self._lists[key][start:]
            else:
                self._lists[key] = self._lists[key][start:end+1]
        return True
    
    async def lrange(self, key, start, end):
        if key not in self._lists:
            return []
        if end == -1:
            return self._lists[key][start:]
        return self._lists[key][start:end+1]
    
    def pipeline(self):
        return self


@pytest.fixture
def mock_redis():
    """Create mock Redis instance."""
    return MockRedis()


@pytest.fixture
def client(mock_redis):
    """Create test client with mocked Redis."""
    redis_client._client = mock_redis
    return TestClient(app)


@pytest.fixture
async def async_client(mock_redis):
    """Create async test client."""
    redis_client._client = mock_redis
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
