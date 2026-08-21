import sys
import os

sys.path.append(os.getcwd())

print("Testing app integrity in backend-merge...")

try:
    from app.config import settings
    print("  [OK] app.config loaded")

    from app.database import Base, engine
    print("  [OK] app.database loaded")

    from app import models
    print("  [OK] app.models loaded (Models: RegisteredStudent, BrandProfile, ScheduledPost, PostComment, Notification, PostAnalytics, etc.)")

    from app.auth.routes import router as auth_router
    from app.ai_posts.routes import router as ai_posts_router
    from app.instagram.routes import router as instagram_router
    from app.brand_profile.routes import router as brand_profile_router
    from app.comments.routes import router as comments_router
    from app.scheduling.routes import router as scheduling_router
    from app.notifications.routes import router as notifications_router
    from app.analytics.routes import router as analytics_router
    print("  [OK] All Phase 1 and Phase 2 routes loaded successfully")

    from app.main import app
    print("  [OK] app.main FastAPI app initialized cleanly")

    print("\nSUCCESS: All backend-merge modules passed integrity checks!")

except Exception as e:
    print(f"\nERROR: Integrity check failed: {e}")
    sys.exit(1)
