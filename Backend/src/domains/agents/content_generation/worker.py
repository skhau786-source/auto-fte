# ═══════════════════════════════════════════════════════════════
# agents / content_generation / worker.py
#
# PURPOSE: Event-driven worker — listens for content generation
#          requests (manual or auto-trigger) and processes them.
#
# USED BY: main.py
# ═══════════════════════════════════════════════════════════════

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.sdk.agent_base import BaseAgent
from src.sdk.database import async_session_factory
from src.sdk.events import Event
from src.sdk.logging import setup_logging

from src.domains.agents.content_generation.handler import ContentGenerationHandler

logger = logging.getLogger(__name__)


class ContentGenerationWorker(BaseAgent):
    """Listens for content generation requests + auto-triggers."""

    def __init__(self):
        super().__init__(agent_name="content_generation")

    async def setup_subscriptions(self):
        await self.bus.subscribe("content.generation", self._on_generate_request)
        await self.bus.subscribe("content.generate.requested", self._on_generate_request)
        logger.info("[content_generation] Subscribed to content.generation channels")

    async def handle_event(self, event: Event):
        logger.warning(f"Unhandled event type: {event.event_type}")

    async def _on_generate_request(self, data: dict):
        """Handle content generation request from event bus."""
        event = Event(**data)
        payload = event.payload
        product_id = payload.get("product_id")
        platform = payload.get("platform", "instagram")
        brand_voice_id = payload.get("brand_voice_id")
        image_model = payload.get("image_model", "")
        auto_approve = payload.get("auto_approve", None)

        if not product_id:
            logger.warning(f"Invalid generate request: missing product_id")
            return

        logger.info(f"Generating content for product {product_id} ({platform})")

        async with async_session_factory() as db:
            handler = ContentGenerationHandler(
                db=db,
                event_bus=self.bus,
            )
            try:
                post = await handler.generate_post(
                    product_id=product_id,
                    brand_voice_id=brand_voice_id,
                    platform=platform,
                    image_model=image_model,
                    auto_approve=auto_approve,
                )
                await db.commit()
                logger.info(f"✅ Content generated: post #{post.id} [{post.status}]")
            except Exception as e:
                await db.rollback()
                logger.error(f"Content generation failed for product {product_id}: {e}")


worker = ContentGenerationWorker()


# ─── Main Entry Point ─────────────────────────────────────────

if __name__ == "__main__":
    setup_logging("content_generation")
    asyncio.run(worker.run())
