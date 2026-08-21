import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.auth.routes import router as auth_router
from app.ai_posts.routes import router as ai_posts_router
from app.instagram.routes import router as instagram_router
from app.brand_profile.routes import router as brand_profile_router
from app.comments.routes import router as comments_router
from app.scheduling.routes import router as scheduling_router
from app.notifications.routes import router as notifications_router
from app.analytics.routes import router as analytics_router
from app.scheduling.scheduler import start_scheduler, shutdown_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("static/generated_images", exist_ok=True)
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Phase 1 Routers
app.include_router(auth_router)
app.include_router(ai_posts_router)
app.include_router(instagram_router)

# Phase 2 Automation Routers
app.include_router(brand_profile_router)
app.include_router(comments_router)
app.include_router(scheduling_router)
app.include_router(notifications_router)
app.include_router(analytics_router)


@app.get("/health", tags=["System"])
async def health():
    return {"status": "healthy", "app": settings.APP_NAME}
