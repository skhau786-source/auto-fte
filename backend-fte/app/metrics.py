"""
Prometheus metrics for the Inventory Management module.

Tracks:
- Request count by endpoint, method, status
- Request duration (histogram)
- Inventory operations (adjustments, syncs, webhooks)
- Shopify sync operations (success/failure)
- Retry attempts
- Database query latency (approximate)

Uses the `prometheus_client` library. Metrics are exposed at GET /metrics.
"""

import time
from functools import wraps
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY, CONTENT_TYPE_LATEST

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

    # Fallback: define no-op classes so the app works without prometheus_client
    class Counter:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def inc(self, amount=1): pass

    class Histogram:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def observe(self, amount): pass

    class Gauge:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def set(self, value): pass
        def inc(self, amount=1): pass
        def dec(self, amount=1): pass
        def set_function(self, func): pass

    def generate_latest(*args, **kwargs):  # type: ignore[no-redef]
        return b"# prometheus_client not installed\n"

    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

import logging
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Define metrics
# ═══════════════════════════════════════════════════════════════════

# HTTP request metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Inventory operation counters
inventory_adjustments_total = Counter(
    "inventory_adjustments_total",
    "Total inventory adjustments",
    ["type", "status"],
)

shopify_sync_total = Counter(
    "shopify_sync_total",
    "Total Shopify sync operations",
    ["operation", "status"],
)

webhook_events_total = Counter(
    "webhook_events_total",
    "Total webhook events received",
    ["topic", "status"],
)

retry_attempts_total = Counter(
    "retry_attempts_total",
    "Total retry attempts for failed syncs",
    ["status"],
)

# Active gauges
active_requests = Gauge(
    "active_requests",
    "Number of requests currently being processed",
)

unsynced_transactions = Gauge(
    "unsynced_transactions",
    "Number of transactions waiting to be synced to Shopify",
)

# Application info
app_info = Gauge(
    "app_info",
    "Application version info",
    ["version", "environment"],
)


def init_metrics(version: str = "1.0.0", environment: str = "development"):
    """Initialize app-info gauge (set once at startup)."""
    app_info.labels(version=version, environment=environment).set(1)


# ═══════════════════════════════════════════════════════════════════
# FastAPI Middleware
# ═══════════════════════════════════════════════════════════════════


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware that records HTTP request metrics."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip metrics for the /metrics endpoint itself
        if request.url.path == "/metrics":
            return await call_next(request)

        method = request.method
        endpoint = request.url.path

        active_requests.inc()
        start_time = time.time()

        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as exc:
            status = 500
            raise
        finally:
            duration = time.time() - start_time
            http_requests_total.labels(method=method, endpoint=endpoint).inc()
            http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)
            active_requests.dec()

        return response


# ═══════════════════════════════════════════════════════════════════
# Helper functions for service layer integration
# ═══════════════════════════════════════════════════════════════════


def record_inventory_adjustment(txn_type: str, status: str = "success"):
    """Record an inventory adjustment metric."""
    inventory_adjustments_total.labels(type=txn_type, status=status).inc()


def record_shopify_sync(operation: str, status: str = "success"):
    """Record a Shopify sync metric."""
    shopify_sync_total.labels(operation=operation, status=status).inc()


def record_webhook_event(topic: str, status: str = "received"):
    """Record a webhook event metric."""
    webhook_events_total.labels(topic=topic, status=status).inc()


def record_retry_attempt(status: str = "success"):
    """Record a retry attempt metric."""
    retry_attempts_total.labels(status=status).inc()


def set_unsynced_count(count: int):
    """Set the unsynced transactions gauge."""
    unsynced_transactions.set(count)


# ═══════════════════════════════════════════════════════════════════
# Prometheus endpoint handler
# ═══════════════════════════════════════════════════════════════════


async def metrics_endpoint(request: Request) -> Response:
    """Expose Prometheus metrics at GET /metrics."""
    data = generate_latest(REGISTRY)
    return Response(
        content=data,
        media_type=CONTENT_TYPE_LATEST,
        headers={"Cache-Control": "no-cache"},
    )
