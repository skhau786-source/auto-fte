# ═══════════════════════════════════════════════════════════════
# agents / customer_support / worker.py
#
# PURPOSE: Background worker for Customer Support Agent (BaseAgent lifecycle).
# ═══════════════════════════════════════════════════════════════

import asyncio
import logging

from src.sdk.agent_base import BaseAgent
from src.sdk.database import async_session_factory
from src.sdk.events import Event
from src.sdk.logging import setup_logging

from src.domains.agents.customer_support.config import get_settings
from src.domains.agents.customer_support.handler import CustomerSupportHandler

logger = logging.getLogger(__name__)


class CustomerSupportWorker(BaseAgent):
    """Event-driven background worker for Customer Support."""

    def __init__(self):
        super().__init__(agent_name="customer_support")
        self.settings = get_settings()

    async def on_start(self):
        logger.info("Customer Support Worker started.")

    async def setup_subscriptions(self):
        """Subscribe to events channel and direct support messages."""
        await self.bus.subscribe("events", self._on_event)
        await self.bus.subscribe("agent.customer_support", self._on_event)
        logger.info("Subscribed to 'events' and 'agent.customer_support' channels.")

    async def handle_event(self, event: Event):
        logger.warning(f"Unhandled direct event: {event.event_type}")

    async def _on_event(self, data: dict):
        """Handle incoming event bus messages."""
        try:
            event = Event(**data)
            if event.event_type == "support.ticket.created":
                payload = event.payload or {}
                logger.info(f"Support ticket received for conversation {payload.get('conversation_id')}")
        except Exception as e:
            logger.error(f"Error handling event in CustomerSupportWorker: {e}")


worker = CustomerSupportWorker()


if __name__ == "__main__":
    setup_logging("customer_support_worker")
    asyncio.run(worker.run())
