import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.database import AsyncSessionLocal
from app.scheduling.service import process_due_scheduled_posts

logger = logging.getLogger("scheduler")
scheduler = AsyncIOScheduler()


async def check_and_publish_due_posts():
    async with AsyncSessionLocal() as session:
        try:
            count = await process_due_scheduled_posts(session)
            if count > 0:
                logger.info(f"[APScheduler] Processed {count} due scheduled posts.")
        except Exception as e:
            logger.error(f"[APScheduler] Error in check_and_publish_due_posts: {e}")


def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(
            check_and_publish_due_posts,
            trigger="interval",
            minutes=1,
            id="publish_scheduled_posts_job",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("[APScheduler] Background post scheduling worker started (runs every 1 min).")


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("[APScheduler] Background scheduler shut down cleanly.")
