# ═══════════════════════════════════════════════════════════════
# src / main.py
#
# PURPOSE: Unified FastAPI application entry point.
#          Routers: auth, ecommerce (routes/webhooks/oauth),
#          6 agent APIs. Lifespan: DB init, event bus, 7 agent workers.
# ═══════════════════════════════════════════════════════════════

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

from src.sdk.config import get_settings
from src.sdk.database import init_db
from src.dependencies import init_event_bus, close_event_bus, close_llm_client
from src.domains.auth.routes import router as auth_router
from src.sdk.database import async_session_factory
from src.domains.ecommerce import (
    routes_router, webhooks_router, oauth_router, inventory_router, reservation_router,
    aggregation_router,
)
from src.domains.ecommerce.reservation_service import expire_stale_reservations
from src.domains.chatbot.api import router as chatbot_router
from src.domains.chatbot.rag_api import router as rag_router
from src.domains.chatbot.inbox_api import router as inbox_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
settings = get_settings()


def _load_agent_routers():
    """Agent API routers lazily import karo — import failure par app start na ruke."""
    routers = []
    agent_modules = [
        ("content_generation", "router", "Content Generation"),
        ("content_scheduling", "router", "Content Scheduling"),
        ("comment_engagement", "router", "Comment Engagement"),
        ("customer_support", "router", "Customer Support"),
        ("analytics_insights", "router", "Analytics Insights"),
        ("collaboration_orchestrator", "router", "Collaboration Orchestrator"),
        ("seo_insights", "router", "SEO Insights"),
        ("customers", "router", "Customers"),
    ]
    for mod_name, attr, label in agent_modules:
        try:
            module = __import__(
                f"src.domains.agents.{mod_name}.api", fromlist=[attr]
            )
            routers.append(getattr(module, attr))
        except Exception as e:
            logger.warning(f"Agent router not loaded ({label}): {e}")
    return routers


async def _start_workers():
    """Agent workers background asyncio tasks ke taur par start karo."""
    tasks = []
    worker_modules = [
        "src.domains.agents.inventory_sync.worker",
        "src.domains.agents.content_scheduling.worker",
        "src.domains.agents.content_generation.worker",
        "src.domains.agents.comment_engagement.worker",
        "src.domains.agents.customer_support.worker",
        "src.domains.agents.analytics_insights.worker",
        "src.domains.agents.collaboration_orchestrator.worker",
        "src.domains.agents.seo_insights.worker",
        "src.domains.agents.customers.worker",
    ]
    for mod_path in worker_modules:
        try:
            module = __import__(mod_path, fromlist=["worker"])
            w = getattr(module, "worker")
            tasks.append(asyncio.create_task(w.run()))
            logger.info(f"Worker started: {mod_path.split('.')[-2]}")
        except Exception as e:
            logger.warning(f"Worker not started ({mod_path}): {e}")
    return tasks


async def _reservation_expiry_loop(interval_seconds: int = 60):
    """Expired stock reservations ka stock wapas karta rahe."""
    while True:
        try:
            async with async_session_factory() as db:
                await expire_stale_reservations(db)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Reservation expiry sweep failed: {e}")
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    await init_db()
    await init_event_bus()
    workers = await _start_workers()
    workers.append(asyncio.create_task(_reservation_expiry_loop()))
    logger.info("DB ready, event bus connected, workers running")
    yield
    for t in workers:
        t.cancel()
    await close_event_bus()
    await close_llm_client()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

app.mount("/static/chatbot_free", StaticFiles(directory="chatbot_free"), name="chatbot-free-static")
app.mount("/static/chatbot_pro", StaticFiles(directory="chatbot_pro"), name="chatbot-pro-static")


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(routes_router)
app.include_router(webhooks_router)
app.include_router(oauth_router)
app.include_router(inventory_router)
app.include_router(reservation_router)
app.include_router(aggregation_router)
app.include_router(chatbot_router)
app.include_router(rag_router)
app.include_router(inbox_router)
for _agent_router in _load_agent_routers():
    app.include_router(_agent_router)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION
    }
