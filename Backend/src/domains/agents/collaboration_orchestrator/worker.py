# ═══════════════════════════════════════════════════════════════
# agents / collaboration_orchestrator / worker.py
#
# PURPOSE: Background worker for Collaboration Orchestrator.
#          Tracks agent registry/heartbeats and periodically detects opportunities.
# ═══════════════════════════════════════════════════════════════

import asyncio
import logging
from datetime import datetime, timezone

from src.sdk.agent_base import BaseAgent
from src.sdk.database import async_session_factory
from src.sdk.events import Event
from src.sdk.logging import setup_logging

from src.domains.agents.collaboration_orchestrator.config import get_settings
from src.domains.agents.collaboration_orchestrator.handler import CollaborationOrchestratorHandler

logger = logging.getLogger(__name__)


class CollaborationOrchestratorWorker(BaseAgent):
    """Background orchestrator worker."""

    def __init__(self):
        super().__init__(agent_name="collaboration_orchestrator")
        self.settings = get_settings()
        self._detect_task = None
        self._registry: dict[str, dict] = {}

    async def on_start(self):
        logger.info("Collaboration Orchestrator Worker starting...")
        self._detect_task = asyncio.create_task(self._detection_loop())

    async def setup_subscriptions(self):
        await self.bus.subscribe("events", self._on_event)
        await self.bus.subscribe("orchestrator.registry", self._on_registry_event)
        await self.bus.subscribe("orchestrator.heartbeat", self._on_heartbeat_event)
        logger.info("Subscribed to events, orchestrator.registry, and orchestrator.heartbeat.")

    async def handle_event(self, event: Event):
        logger.warning(f"Unhandled direct event: {event.event_type}")

    async def _on_registry_event(self, data: dict):
        event = Event(**data)
        source = event.source
        if event.event_type == "agent.register":
            self._registry[source] = {"status": "active", "last_seen": datetime.now(timezone.utc)}
            logger.info(f"Agent registered: {source}")
        elif event.event_type == "agent.unregister":
            self._registry.pop(source, None)
            logger.info(f"Agent unregistered: {source}")

    async def _on_heartbeat_event(self, data: dict):
        event = Event(**data)
        source = event.source
        if source:
            self._registry[source] = {"status": "active", "last_seen": datetime.now(timezone.utc)}

    async def _on_event(self, data: dict):
        try:
            event = Event(**data)
            if event.event_type == "workflow.step.execute":
                wf_id = (event.payload or {}).get("workflow_id")
                if wf_id:
                    async with async_session_factory() as db:
                        handler = CollaborationOrchestratorHandler(db, event_bus=self.bus)
                        await handler.execute_workflow(wf_id)
                        await db.commit()
        except Exception as e:
            logger.error(f"Error processing event in Orchestrator worker: {e}")

    async def _detection_loop(self):
        while self.running:
            try:
                async with async_session_factory() as db:
                    handler = CollaborationOrchestratorHandler(db, event_bus=self.bus)
                    opps = await handler.detect_opportunities()
                    for opp in opps:
                        if not opp.get("requires_human_approval"):
                            wf = await handler.create_workflow(
                                name=opp["title"],
                                rule=opp["rule"],
                                context=opp["context"],
                            )
                            await handler.execute_workflow(wf.id)
                    await db.commit()
            except Exception as e:
                logger.error(f"Detection loop error: {e}")
            await asyncio.sleep(self.settings.DETECT_INTERVAL_SECONDS)

    async def shutdown(self):
        if self._detect_task:
            self._detect_task.cancel()
        await super().shutdown()


worker = CollaborationOrchestratorWorker()


if __name__ == "__main__":
    setup_logging("collaboration_orchestrator_worker")
    asyncio.run(worker.run())
