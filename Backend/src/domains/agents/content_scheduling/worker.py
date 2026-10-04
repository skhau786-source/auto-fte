# ═══════════════════════════════════════════════════════════════
# agents / content_scheduling / worker.py
#
# PURPOSE: Event-driven worker — listens for ContentApprovedEvent
#          (from Agent 3) and creates scheduled posts.
#          Also starts the background scheduler for due posts.
#
# USED BY: main.py, docker-compose
# ═══════════════════════════════════════════════════════════════

import asyncio
import logging

from src.sdk.agent_base import BaseAgent
from src.sdk.database import async_session_factory
from src.sdk.events import Event
from src.sdk.logging import setup_logging

from src.domains.agents.content_scheduling.handler import ContentSchedulingHandler
from src.domains.agents.content_scheduling.scheduler import ContentScheduler

logger = logging.getLogger(__name__)


class ContentSchedulingWorker(BaseAgent):
    """Listens for approved content and schedules it for publishing.

    Also runs the background scheduler that polls for due posts.
    """

    def __init__(self):
        super().__init__(agent_name="content_scheduling")
        self.scheduler: ContentScheduler | None = None

    async def on_start(self):
        """Start the background scheduler on agent startup."""
        self.scheduler = ContentScheduler(
            db_factory=async_session_factory,
            event_bus=self.bus,
        )
        await self.scheduler.start()

    async def setup_subscriptions(self):
        await self.bus.subscribe("events", self._on_content_approved)
        logger.info("[content_scheduling] Subscribed to events channel")

    async def handle_event(self, event: Event):
        logger.warning(f"Unhandled event type: {event.event_type}")

    async def _on_content_approved(self, data: dict):
        """Handle ContentApprovedEvent from content_generation (Agent 3)."""
        event = Event(**data)
        if event.event_type != "content.approved":
            return  # Skip non-approved events

        payload = event.payload
        logger.info(
            f"Content approved: post #{payload.get('post_id')} "
            f"for {payload.get('platform')}"
        )

        async with async_session_factory() as db:
            handler = ContentSchedulingHandler(db)
            try:
                post = await handler.handle_content_approved(payload)
                if post:
                    await db.commit()
                    logger.info(f"  ✅ Scheduled post #{post.id} created")
                else:
                    await db.rollback()
                    logger.warning("  ⚠️ Could not schedule — no active social account")
            except Exception as e:
                await db.rollback()
                logger.error(f"  ❌ Failed to schedule: {e}")

    async def shutdown(self):
        """Stop scheduler before shutting down."""
        if self.scheduler:
            await self.scheduler.stop()
        await super().shutdown()


worker = ContentSchedulingWorker()


# ─── Main Entry Point ─────────────────────────────────────────

if __name__ == "__main__":
    setup_logging("content_scheduling")
    asyncio.run(worker.run())
