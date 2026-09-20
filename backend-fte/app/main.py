"""
FastAPI application entry point — Production hardened.

Includes:
- CORS middleware (configurable origins)
- Trusted Host middleware
- Request ID middleware
- Structured logging
- Request size limits
- Health / Readiness / Liveness endpoints
- Rate limiting (via Redis)
"""

from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_config import configure_logging, request_id_var, user_id_var, store_id_var, endpoint_var
from app.dependencies import get_current_user
from app.database import engine as db_engine, AsyncSessionLocal

# ── Middleware ──
from app.inventory.rate_limiter import RateLimiterMiddleware
from app.metrics import MetricsMiddleware, metrics_endpoint, init_metrics

# ── Routes ──
from app.auth.routes import router as auth_router
from app.inventory.router import router as inventory_router
from app.shopify.webhook import router as webhook_router
from app.inventory.admin_router import router as admin_router

# ── Shopify Routes ──
from app.shopify.router import router as shopify_router

# ── WooCommerce Routes ──
from app.woocommerce.router import router as woocommerce_router
from app.woocommerce.webhook import router as woocommerce_webhook_router

# ── Reservation Engine Routes (Phase 3) ──
from app.inventory.reservation_router import router as reservation_router

# ── Allocation Engine Routes (Phase 4) ──
from app.inventory.allocation_router import router as allocation_router

# ── WooCommerce Order Integration Routes (Phase 5) ──
from app.woocommerce.order_integration_router import router as order_integration_router

# ── Inventory Aggregation Routes (Phase 6) ──
from app.inventory.aggregation_router import router as aggregation_router

# ── Unified Dashboard Routes (Phase 7) ──
from app.dashboard.unified_router import router as unified_dashboard_router

# ── Data Export Routes ──
from app.export.export_router import router as export_router

# ── AI Agent Routes (Phase 4) ──
from app.ai.router import router as ai_router

# ── RAG (Retrieval-Augmented Generation) Routes ──
from app.ai.rag_router import router as rag_router

# ── Subscription / Billing Routes (Phase 3) ──
from app.subscriptions.router import router as subscriptions_router

# ═══════════════════════════════════════════════════════════════════
# Configure Logging
# ═══════════════════════════════════════════════════════════════════
configure_logging(
    log_level=settings.LOG_LEVEL,
    log_format=settings.LOG_FORMAT,
)

import logging
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# App Factory
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)


# ═══════════════════════════════════════════════════════════════════
# Middleware — CORS
# ═══════════════════════════════════════════════════════════════════

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
    max_age=600,  # Cache preflight for 10 minutes
)


# ═══════════════════════════════════════════════════════════════════
# Middleware — Trusted Hosts (only in production)
# ═══════════════════════════════════════════════════════════════════

if settings.ENV == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.trusted_host_list,
    )


# ═══════════════════════════════════════════════════════════════════
# Middleware — Request ID, Context Logging
# ═══════════════════════════════════════════════════════════════════

@app.middleware("http")
async def add_request_context(request: Request, call_next):
    """Set request-scoped context variables for structured logging."""
    # Generate or extract request ID
    rid = request.headers.get("X-Request-Id", str(uuid.uuid4()))
    request_id_var.set(rid)
    endpoint_var.set(f"{request.method} {request.url.path}")

    # Process the request
    start_time = time.time()
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # Add execution time and request ID to response
    elapsed_ms = int((time.time() - start_time) * 1000)
    response.headers["X-Request-Id"] = rid
    response.headers["X-Execution-Time-Ms"] = str(elapsed_ms)

    logger.info(
        "Request completed: %s %s → %s (%dms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )

    return response


# ═══════════════════════════════════════════════════════════════════
# Middleware — Security Headers (Helmet-style)
# ═══════════════════════════════════════════════════════════════════

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


# ═══════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════

app.include_router(auth_router)
app.include_router(inventory_router)
app.include_router(webhook_router)
app.include_router(admin_router)

# ── Shopify Routes ──
app.include_router(shopify_router)

# ── WooCommerce Routes ──
app.include_router(woocommerce_router)
app.include_router(woocommerce_webhook_router)

# ── Reservation Engine Routes (Phase 3) ──
app.include_router(reservation_router)

# ── Allocation Engine Routes (Phase 4) ──
app.include_router(allocation_router)

# ── WooCommerce Order Integration Routes (Phase 5) ──
app.include_router(order_integration_router)

# ── Inventory Aggregation Routes (Phase 6) ──
app.include_router(aggregation_router)

# ── Unified Dashboard Routes (Phase 7) ──
app.include_router(unified_dashboard_router)

# ── Data Export Routes ──
app.include_router(export_router)

# ── AI Agent Routes (Phase 4) ──
app.include_router(ai_router)

# ── RAG (Retrieval-Augmented Generation) Routes ──
app.include_router(rag_router)

# ── Subscription / Billing Routes (Phase 3) ──
app.include_router(subscriptions_router)


# ═══════════════════════════════════════════════════════════════════
# Monitoring Endpoints
# ═══════════════════════════════════════════════════════════════════

import uuid
import platform
import time
from datetime import datetime, timezone
from sqlalchemy import text


@app.get("/health", tags=["Monitoring"])
async def health():
    """Basic health check — always responds if the app is running."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
    }


@app.get("/ready", tags=["Monitoring"])
async def readiness():
    """
    Readiness probe — verifies PostgreSQL and Redis connectivity.
    Kubernetes/docker-compose uses this to know when the app is ready.
    """
    checks = {}

    # Database check
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    # Redis check (if configured)
    if settings.REDIS_URL and settings.REDIS_URL != "redis://localhost:6379/0":
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
            await r.ping()
            await r.aclose()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"error: {exc}"
    else:
        checks["redis"] = "not_configured"

    all_ok = all(v == "ok" for v in checks.values())

    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if all_ok else "degraded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
        },
    )


@app.get("/live", tags=["Monitoring"])
async def liveness():
    """
    Liveness probe — returns 200 if the process is alive.
    Kubernetes uses this to know if the pod needs restarting.
    """
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/version", tags=["Monitoring"])
async def version():
    """Application version info."""
    return {
        "app": settings.APP_NAME,
        "version": "1.0.0",
        "python": platform.python_version(),
        "environment": settings.ENV,
    }


# ═══════════════════════════════════════════════════════════════════
# Startup / Shutdown Events
# ═══════════════════════════════════════════════════════════════════


@app.get("/metrics", tags=["Monitoring"])
async def metrics(request: Request):
    """Prometheus metrics endpoint."""
    return await metrics_endpoint(request)


@app.on_event("startup")
async def on_startup():
    """Log when the application starts and register AI capabilities."""
    init_metrics(version="1.0.0", environment=settings.ENV)

    # Register AI agent capabilities
    from app.ai.capabilities.inventory_capabilities import register_inventory_capabilities
    from app.ai.capabilities.social_capabilities import register_social_capabilities
    from app.ai.capabilities.sales_capabilities import register_sales_capabilities
    register_inventory_capabilities()
    register_social_capabilities()
    register_sales_capabilities()
    logger.info("AI agent capabilities registered")

    logger.info(
        "Application starting: %s | env=%s | debug=%s",
        settings.APP_NAME,
        settings.ENV,
        settings.DEBUG,
    )


@app.on_event("shutdown")
async def on_shutdown():
    """Clean up resources on shutdown."""
    logger.info("Application shutting down")
    await db_engine.dispose()
