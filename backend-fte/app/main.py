from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.auth.routes import router as auth_router
from app.ai_posts.routes import router as ai_posts_router
from app.instagram.routes import router as instagram_router

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth_router)
app.include_router(ai_posts_router)
app.include_router(instagram_router)


@app.get("/health", tags=["System"])
async def health():
    return {"status": "healthy"}