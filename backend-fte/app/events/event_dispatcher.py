"""
Domain Event System — event-driven architecture for inventory operations.

Events:
- InventoryAdjusted
- ProductCreated
- ProductUpdated
- VariantUpdated
- WebhookReceived
- ShopifySyncCompleted
- ExportGenerated
- AlertRaised

Usage:
    dispatcher = EventDispatcher()
    dispatcher.register(InventoryAdjustedHandler())
    await dispatcher.dispatch(InventoryAdjusted(variant_id=..., quantity_change=10))
"""

import abc
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Domain Events
# ═══════════════════════════════════════════════════════════════════


@dataclass
class DomainEvent:
    """Base class for all domain events."""
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            import uuid
            self.event_id = str(uuid.uuid4())


@dataclass
class InventoryAdjusted(DomainEvent):
    variant_id: UUID = field(default_factory=uuid.UUID)
    product_id: UUID = field(default_factory=uuid.UUID)
    store_id: UUID = field(default_factory=uuid.UUID)
    quantity_before: int = 0
    quantity_after: int = 0
    quantity_change: int = 0
    reason: Optional[str] = None
    performed_by: Optional[UUID] = None


@dataclass
class ProductCreated(DomainEvent):
    product_id: UUID = field(default_factory=uuid.UUID)
    store_id: UUID = field(default_factory=uuid.UUID)
    title: str = ""
    variants_count: int = 0


@dataclass
class ProductUpdated(DomainEvent):
    product_id: UUID = field(default_factory=uuid.UUID)
    store_id: UUID = field(default_factory=uuid.UUID)
    updated_fields: list[str] = field(default_factory=list)


@dataclass
class VariantUpdated(DomainEvent):
    variant_id: UUID = field(default_factory=uuid.UUID)
    product_id: UUID = field(default_factory=uuid.UUID)
    store_id: UUID = field(default_factory=uuid.UUID)
    inventory_quantity: int = 0


@dataclass
class WebhookReceived(DomainEvent):
    topic: str = ""
    shop_domain: str = ""
    store_id: UUID = field(default_factory=uuid.UUID)
    body: Optional[dict] = None


@dataclass
class ShopifySyncCompleted(DomainEvent):
    store_id: UUID = field(default_factory=uuid.UUID)
    products_created: int = 0
    products_updated: int = 0
    variants_created: int = 0
    variants_updated: int = 0
    duration_seconds: float = 0.0


@dataclass
class ExportGenerated(DomainEvent):
    store_id: UUID = field(default_factory=uuid.UUID)
    export_type: str = ""  # products, transactions, logs
    format: str = ""  # csv, json, xlsx
    record_count: int = 0


@dataclass
class AlertRaised(DomainEvent):
    alert_type: str = ""  # low_stock, shopify_failure, webhook_failure, retry_dead_letter
    severity: str = ""  # info, warning, error, critical
    title: str = ""
    message: str = ""
    metadata: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════
# Event Handlers
# ═══════════════════════════════════════════════════════════════════


class EventHandler(abc.ABC):
    """Abstract base for all event handlers."""

    @abc.abstractmethod
    async def handle(self, event: DomainEvent) -> None:
        ...

    @property
    def event_type(self):
        """Return the event class this handler processes."""
        return None


class LoggingHandler(EventHandler):
    """Default handler — logs all events."""

    async def handle(self, event: DomainEvent) -> None:
        logger.info("Event: %s | id=%s | correlation=%s",
                     type(event).__name__, event.event_id, event.correlation_id)


# ═══════════════════════════════════════════════════════════════════
# Event Dispatcher
# ═══════════════════════════════════════════════════════════════════


class EventDispatcher:
    """
    Synchronous in-process event dispatcher.

    For production use with Celery or Redis pub/sub, wrap handlers
    to enqueue background tasks instead of executing inline.
    """

    def __init__(self):
        self._handlers: dict[type, list[EventHandler]] = {}
        self._default_handlers: list[EventHandler] = [LoggingHandler()]

    def register(self, handler: EventHandler, event_type: Optional[type] = None) -> None:
        """Register a handler for a specific event type."""
        target_type = event_type or getattr(handler, 'event_type', None)
        if target_type is None:
            raise ValueError(f"Handler {type(handler).__name__} must specify an event_type")
        self._handlers.setdefault(target_type, []).append(handler)

    def register_default(self, handler: EventHandler) -> None:
        """Register a handler that receives ALL events."""
        self._default_handlers.append(handler)

    async def dispatch(self, event: DomainEvent) -> None:
        """Dispatch an event to all registered handlers."""
        event_type = type(event)

        # Run default handlers
        for handler in self._default_handlers:
            try:
                await handler.handle(event)
            except Exception as exc:
                logger.exception("Default handler %s failed for event %s: %s",
                                  type(handler).__name__, event_type.__name__, exc)

        # Run type-specific handlers
        for handler in self._handlers.get(event_type, []):
            try:
                await handler.handle(event)
            except Exception as exc:
                logger.exception("Handler %s failed for event %s: %s",
                                  type(handler).__name__, event_type.__name__, exc)

    def clear(self) -> None:
        """Remove all registered handlers (useful in tests)."""
        self._handlers.clear()


# ═══════════════════════════════════════════════════════════════════
# Global Dispatcher Instance
# ═══════════════════════════════════════════════════════════════════

_default_dispatcher: Optional[EventDispatcher] = None


def get_dispatcher() -> EventDispatcher:
    """Get or create the default event dispatcher."""
    global _default_dispatcher
    if _default_dispatcher is None:
        _default_dispatcher = EventDispatcher()
    return _default_dispatcher
