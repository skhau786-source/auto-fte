# Load Test Report — Inventory Management Module

**Date:** July 21, 2026
**Tool:** Locust
**Script:** `locustfile.py`

---

## Test Configuration

| Parameter | Value |
|-----------|-------|
| Host | `http://localhost:8000` |
| User Classes | BrowseUser (3x), CreateUser (1x), MixedUser (5x) |
| Spawn Rate | 10 users/sec |
| Test Duration | 5 minutes per scenario |

---

## Scenario 1: 100 Concurrent Users

| Metric | Value |
|--------|-------|
| Total Requests | _TBD_ |
| Requests/sec | _TBD_ |
| P50 Latency | _TBD_ |
| P95 Latency | _TBD_ |
| P99 Latency | _TBD_ |
| Error Rate | _TBD_ |

---

## Scenario 2: 250 Concurrent Users

| Metric | Value |
|--------|-------|
| Total Requests | _TBD_ |
| Requests/sec | _TBD_ |
| P50 Latency | _TBD_ |
| P95 Latency | _TBD_ |
| P99 Latency | _TBD_ |
| Error Rate | _TBD_ |

---

## Scenario 3: 500 Concurrent Users

| Metric | Value |
|--------|-------|
| Total Requests | _TBD_ |
| Requests/sec | _TBD_ |
| P50 Latency | _TBD_ |
| P95 Latency | _TBD_ |
| P99 Latency | _TBD_ |
| Error Rate | _TBD_ |

---

## Running the Tests

```bash
# Install Locust
pip install locust

# Start Locust (web UI at http://localhost:8089)
locust -f locustfile.py --host=http://localhost:8000

# Headless mode (100 users, 10/sec spawn, 5 min run)
locust -f locustfile.py --host=http://localhost:8000 \
  --users=100 --spawn-rate=10 --run-time=5m \
  --headless --csv=load_test_100

locust -f locustfile.py --host=http://localhost:8000 \
  --users=250 --spawn-rate=25 --run-time=5m \
  --headless --csv=load_test_250

locust -f locustfile.py --host=http://localhost:8000 \
  --users=500 --spawn-rate=50 --run-time=5m \
  --headless --csv=load_test_500
```

---

## Expected Results

Based on code analysis, the system should handle:

| Users | Expected RPS | Expected P95 Latency |
|-------|-------------|---------------------|
| 100 | ~200 req/s | < 200ms |
| 250 | ~400 req/s | < 500ms |
| 500 | ~600 req/s | < 1000ms |
| 1000 | ~800 req/s | < 2000ms |

---

## Notes

1. **Write operations** in the Locust script use random UUIDs for variant IDs, resulting in 404 responses. These still measure request handling time but don't exercise the full business logic (database commits, transactions, logs). For accurate write latency measurements, modify the script to use real variant IDs from a seeded database.

2. **Rate limiting**: The in-memory rate limiter will trigger at `RATE_LIMIT_PER_MINUTE` (default 60) requests per IP per minute. Adjust this value for load testing:
   ```bash
   RATE_LIMIT_PER_MINUTE=10000 locust -f locustfile.py ...
   ```

3. **Worker count**: The Uvicorn server runs with 4 workers (`--workers 4` in Dockerfile). Each worker is an independent process, so the actual throughput is approximately 4× the per-worker throughput.
