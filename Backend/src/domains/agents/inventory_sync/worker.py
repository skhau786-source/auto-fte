# ═══════════════════════════════════════════════════════════════
# agents / inventory_sync / worker.py
#
# PURPOSE: Inventory Sync Worker — MULTI-PLATFORM.
#          Listens to Redis for webhook + sync events, processes
#          them using InventorySyncHandler. Uses BaseAgent.
#
# USED BY: docker-compose (inventory-worker service)
# ═══════════════════════════════════════════════════════════════

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.sdk.agent_base import BaseAgent
from src.sdk.database import async_session_factory
from src.sdk.events import Event
from src.sdk.logging import setup_logging

from .handler import InventorySyncHandler
from src.sdk.models.base import Store
from src.sdk.oauth.tokens import TokenManager

logger = logging.getLogger(__name__)


class InventorySyncWorker(BaseAgent):
    """Multi-platform inventory sync worker.

    Same agent, ANY platform. Handles Shopify, WooCommerce, Amazon,
    Daraz — sab kuch. Platform auto-detected from Store record.
    """

    def __init__(self):
        super().__init__(agent_name="inventory_sync")
        self.token_mgr = TokenManager()

    async def setup_subscriptions(self):
        await self.bus.subscribe("webhooks", self._on_webhook_event)
        await self.bus.subscribe("sync", self._on_sync_event)
        logger.info("[inventory_sync] Subscribed to webhooks + sync channels")

    async def handle_event(self, event: Event):
        logger.warning(f"Unhandled event type: {event.event_type}")

    # ─── Webhook Event Handler ──────────────────────────────────

    async def _on_webhook_event(self, data: dict):
        event = Event(**data)
        store_id = event.payload.get("store_id")
        topic = event.payload.get("topic")
        payload = event.payload.get("data", {})

        if not store_id or not topic:
            logger.warning(f"Invalid webhook event: {event.event_id}")
            return

        logger.info(f"Processing webhook: {topic} for store {store_id}")
        async with async_session_factory() as db:
            handler = InventorySyncHandler(db)
            await handler.handle_webhook_event(store_id, topic, payload)
            await db.commit()

    # ─── Sync Event Handler ─────────────────────────────────────

    async def _on_sync_event(self, data: dict):
        event = Event(**data)
        store_id = event.payload.get("store_id")
        sync_type = event.payload.get("sync_type", "full")
        since_days = event.payload.get("since_days", 30)

        if not store_id:
            logger.warning(f"Invalid sync event: {event.event_id}")
            return

        logger.info(f"Sync requested: type={sync_type}, store={store_id}")
        async with async_session_factory() as db:
            handler = InventorySyncHandler(db)

            try:
                if sync_type == "full":
                    await handler.initial_full_sync(store_id)
                elif sync_type == "products":
                    await handler.refresh_products(store_id)
                elif sync_type == "orders":
                    await handler.refresh_orders(store_id, since_days)
                await db.commit()
                logger.info(f"Sync complete: type={sync_type}, store={store_id}")
            except Exception as e:
                await db.rollback()
                logger.error(f"Sync failed for store {store_id}: {e}")


worker = InventorySyncWorker()


# ─── Main Entry Point ─────────────────────────────────────────

if __name__ == "__main__":
    setup_logging("inventory_sync")
    asyncio.run(worker.run())
