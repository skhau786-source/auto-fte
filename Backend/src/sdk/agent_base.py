# ═══════════════════════════════════════════════════════════════
# fte_sdk / agent_base.py
#
# PURPOSE: Base class for ALL 7 FTE agents. Har agent isko
#          extend karega. Provides: orchestrator registration,
#          heartbeat loop, event subscription, graceful shutdown.
#
# USED BY: inventory_sync, content_scheduling, content_generation,
#          comment_engagement, customer_support, analytics_insights,
#          collaboration_orchestrator
# ═══════════════════════════════════════════════════════════════

import asyncio
import signal
import logging
from abc import ABC, abstractmethod
from typing import Optional

from src.sdk.config import get_settings
from src.sdk.event_bus import RedisEventBus, AbstractEventBus
from src.sdk.events import Event, HeartbeatEvent

logger = logging.getLogger(__name__)


# ─── BaseAgent ────────────────────────────────────────────────
# Abstract base class. Har agent:
#   1. Inherits BaseAgent
#   2. Overrides handle_event()
#   3. Optionally overrides setup_subscriptions() for custom channels
#   4. Optionally overrides on_start() for startup logic
#   5. Calls agent.run() to start

class BaseAgent(ABC):
    """Every FTE agent extends this class.

    Lifecycle:
      1. run() → connect to event bus
      2. register_with_orchestrator() → tell orchestrator we're alive
      3. on_start() → agent-specific init (override if needed)
      4. start heartbeat loop → every 30s
      5. setup_subscriptions() → listen for events
      6. handle_event() → process incoming events (MUST override)
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.settings = get_settings()
        self.bus: AbstractEventBus = RedisEventBus(self.settings.REDIS_URL)
        self.running = False
        self._heartbeat_task: Optional[asyncio.Task] = None

    # ─── run() — Agent Entry Point ─────────────────────────────
    # Call this to start the agent. It:
    # 1. Connects to event bus (Redis)
    # 2. Registers with orchestrator
    # 3. Calls on_start() hook (agent-specific init)
    # 4. Starts heartbeat loop (every 30s)
    # 5. Subscribes to events
    # 6. Blocks until shutdown signal

    async def run(self):
        """Start agent lifecycle — connect, register, listen, heartbeat."""
        self.running = True
        await self.bus.connect()
        logger.info(f"[{self.agent_name}] Connected to event bus")

        await self.register_with_orchestrator()
        await self.on_start()

        # Start background heartbeat task
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        # Subscribe to relevant event channels
        await self.setup_subscriptions()

        # Wait for SIGTERM / SIGINT
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(
                    sig, lambda: asyncio.create_task(self.shutdown())
                )
            except (NotImplementedError, RuntimeError):
                # Windows event loop, or running embedded inside uvicorn
                # (which owns the signals): skip, shutdown is cancelled by the host.
                break
        while self.running:
            await asyncio.sleep(1)

    # ─── register_with_orchestrator() ─────────────────────────
    # Sends 'agent.register' event → orchestrator knows this
    # agent is alive and ready to receive tasks.

    async def register_with_orchestrator(self):
        """Publish agent.register event so orchestrator knows we're alive."""
        event = Event(
            event_type="agent.register",
            source=self.agent_name,
            payload={"agent_name": self.agent_name, "status": "starting"},
        )
        await self.bus.publish("orchestrator.registry", event.model_dump())
        logger.info(f"[{self.agent_name}] Registered with orchestrator")

    # ─── _heartbeat_loop() (Background Task) ──────────────────
    # Every 30s: publish HeartbeatEvent to orchestrator.heartbeat.
    # Orchestrator monitors these — missing heartbeats = unhealthy.

    async def _heartbeat_loop(self):
        """Send HeartbeatEvent every 30s to orchestrator."""
        while self.running:
            event = HeartbeatEvent(
                source=self.agent_name,
                payload={"agent_name": self.agent_name, "status": "running"},
            )
            await self.bus.publish("orchestrator.heartbeat", event.model_dump())
            await asyncio.sleep(30)

    # ─── setup_subscriptions() (Override for custom channels) ─
    # Default: listen on agent.<agent_name> channel.
    # Override if agent needs additional channels (e.g. "webhook").
    # Each subscription runs in its own asyncio task internally.

    async def setup_subscriptions(self):
        """Subscribe to event channels. Override for custom routing.
        Default: listen on agent.<agent_name> for direct events."""
        await self.bus.subscribe(f"agent.{self.agent_name}", self._on_event)

    # ─── _on_event() (Internal Event Router) ──────────────────
    # Deserializes event dict → Event object.
    # If target_agent is set and doesn't match → skip.
    # Catches exceptions so one bad event doesn't crash the listener.

    async def _on_event(self, data: dict):
        """Internal router: validate event, check target, dispatch to handle_event()."""
        event = Event(**data)
        # If event targets a specific agent and it's not us → skip
        if event.target_agent and event.target_agent != self.agent_name:
            return
        try:
            await self.handle_event(event)
        except Exception as e:
            logger.error(
                f"[{self.agent_name}] Error handling event {event.event_id}: {e}"
            )

    # ─── handle_event() (ABSTRACT — MUST OVERRIDE) ────────────
    # Agent-specific event processing. Har agent apna logic
    # yahan implement karega.
    #
    # Example:
    #   if event.event_type == "webhook.received":
    #       await self.process_webhook(event.payload)

    @abstractmethod
    async def handle_event(self, event: Event):
        """Override this — all incoming events arrive here."""
        pass

    # ─── on_start() (Optional Hook) ───────────────────────────
    # Override for startup logic: initial sync, API connection,
    # cache warmup, etc.

    async def on_start(self):
        """Optional hook for agent-specific startup logic."""
        pass

    # ─── publish_event() (Helper) ─────────────────────────────
    # Shortcut for agents to publish events to the bus.
    # Goes to 'events' channel — orchestrator can route from there.

    async def publish_event(self, event: Event):
        """Publish an event to the 'events' channel."""
        await self.bus.publish("events", event.model_dump())

    # ─── shutdown() (Graceful) ────────────────────────────────
    # 1. Stop heartbeat loop
    # 2. Unregister from orchestrator
    # 3. Disconnect event bus
    # Called on SIGTERM / SIGINT

    async def shutdown(self):
        """Graceful shutdown — stop heartbeat, unregister, disconnect."""
        logger.info(f"[{self.agent_name}] Shutting down...")
        self.running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        event = Event(
            event_type="agent.unregister",
            source=self.agent_name,
            payload={"agent_name": self.agent_name},
        )
        await self.bus.publish("orchestrator.registry", event.model_dump())
        await self.bus.disconnect()
        logger.info(f"[{self.agent_name}] Shutdown complete")
