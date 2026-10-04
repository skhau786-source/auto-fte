# ═══════════════════════════════════════════════════════════════
# agents / analytics_insights / worker.py
#
# PURPOSE: Background worker for Analytics Agent (periodic rollups).
# ═══════════════════════════════════════════════════════════════

import asyncio
import logging

from src.sdk.agent_base import BaseAgent
from src.sdk.database import async_session_factory
from src.sdk.events import Event
from src.sdk.logging import setup_logging

from src.domains.agents.analytics_insights.config import get_settings
from src.domains.agents.analytics_insights.handler import AnalyticsInsightsHandler
from src.domains.agents.analytics_insights.metrics import seed_default_metrics

logger = logging.getLogger(__name__)


class AnalyticsInsightsWorker(BaseAgent):
    """Event-driven + scheduled background worker for Analytics rollups."""

    def __init__(self):
        super().__init__(agent_name="analytics_insights")
        self.settings = get_settings()
        self._rollup_task = None

    async def on_start(self):
        logger.info("Analytics Insights Worker starting...")
        async with async_session_factory() as db:
            await seed_default_metrics(db)
            await db.commit()
        # Start periodic rollup loop
        self._rollup_task = asyncio.create_task(self._rollup_loop())

    async def setup_subscriptions(self):
        await self.bus.subscribe("events", self._on_event)
        await self.bus.subscribe("agent.analytics_insights", self._on_event)
        logger.info("Subscribed to events channel for analytics hooks.")

    async def handle_event(self, event: Event):
        logger.warning(f"Unhandled direct event: {event.event_type}")

    async def _on_event(self, data: dict):
        try:
            event = Event(**data)
            if event.event_type == "analytics.refresh.requested":
                await self._run_rollup_once()
            else:
                async with async_session_factory() as db:
                    handler = AnalyticsInsightsHandler(db)
                    await handler.ingest_bus_event(event)
                    await db.commit()
        except Exception as e:
            logger.error(f"Error handling event in Analytics worker: {e}")

    async def _rollup_loop(self):
        while self.running:
            try:
                await self._run_rollup_once()
            except Exception as e:
                logger.error(f"Rollup error: {e}")
            await asyncio.sleep(self.settings.ROLLUP_INTERVAL_SECONDS)

    async def _run_rollup_once(self):
        async with async_session_factory() as db:
            handler = AnalyticsInsightsHandler(db)
            await handler.run_rollup()
            await db.commit()
            logger.info("Periodic metrics rollup completed successfully.")

    async def shutdown(self):
        if self._rollup_task:
            self._rollup_task.cancel()
        await super().shutdown()


worker = AnalyticsInsightsWorker()


if __name__ == "__main__":
    setup_logging("analytics_insights_worker")
    asyncio.run(worker.run())
