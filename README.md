# API Gateway

Production-ready API Gateway with rate limiting, circuit breaker pattern, and JWT authentication.

## Features

- **Rate Limiting**
  - Sliding Window: Limits total requests per time window
  - Token Bucket: Allows controlled bursts while limiting sustained rate
  
- **Circuit Breaker**
  - Prevents cascade failures to downstream services
  - Three states: Closed, Open, Half-Open
  - Automatic recovery with configurable thresholds
  
- **JWT Authentication**
  - Stateless token-based authentication
  - Role and permission-based access control
  - Configurable public routes
  
- **Reverse Proxy**
  - Dynamic routing to upstream services
  - Request/response transformation
  - Latency tracking
  
- **Observability**
  - Prometheus-compatible metrics
  - Latency percentiles (p50, p95, p99)
  - Circuit breaker status monitoring

## Quick Start

```bash
# Start all services
docker-compose up -d

# Check health
curl http://localhost:8000/health

# Get token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpass"}' | jq -r '.access_token')

# Make authenticated request
curl http://localhost:8000/api/services \
  -H "Authorization: Bearer $TOKEN"
```

## API Endpoints

### Health & Metrics
- `GET /health` - Basic health check
- `GET /health/detailed` - Detailed health with circuit status
- `GET /metrics` - JSON metrics
- `GET /metrics/prometheus` - Prometheus format

### Authentication
- `POST /api/auth/login` - Get JWT token
- `POST /api/auth/register` - Register user

### Gateway Management
- `GET /api/services` - List upstream services
- `GET /api/circuits` - Circuit breaker status
- `POST /api/circuits/{service}/reset` - Reset circuit

### Proxy
- `ANY /api/{service}/{path}` - Proxy to upstream service

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `JWT_SECRET_KEY` | (required) | Secret for JWT signing |
| `RATE_LIMIT_REQUESTS` | `100` | Requests per window |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Window size in seconds |
| `TOKEN_BUCKET_CAPACITY` | `50` | Max tokens in bucket |
| `TOKEN_BUCKET_REFILL_RATE` | `10` | Tokens per second |
| `CIRCUIT_FAILURE_THRESHOLD` | `5` | Failures before opening |
| `CIRCUIT_RECOVERY_TIMEOUT` | `30` | Seconds before half-open |

## Rate Limiting

### Sliding Window
Tracks requests in a sliding time window. Once limit is exceeded, returns 429.

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Window: 60
```

### Token Bucket
Allows bursts up to bucket capacity, then rate-limits to refill rate.

```
X-TokenBucket-Remaining: 45
```

## Circuit Breaker

States:
1. **Closed**: Normal operation, requests pass through
2. **Open**: Circuit tripped, requests fail fast with 503
3. **Half-Open**: Testing recovery, limited requests allowed

```json
{
  "service": "users",
  "state": "closed",
  "failures": 0,
  "available": true
}
```

## Testing

```bash
# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=term-missing

# Load testing
locust -f tests/load_test.py --host=http://localhost:8000
```

## Monitoring

Start with monitoring profile:

```bash
docker-compose --profile monitoring up -d
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│ API Gateway │────▶│  Upstream   │
└─────────────┘     └─────────────┘     │  Services   │
                           │            └─────────────┘
                           │
                    ┌──────┴──────┐
                    │    Redis    │
                    │ (Rate Limit │
                    │  + Circuit) │
                    └─────────────┘
```

## License

MIT
