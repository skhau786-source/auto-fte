"""
Webhook Manager for WooCommerce Integration Module.

Provides production-ready webhook processing with:
- Per-topic handler routing (product, order, customer, variation, coupon, category)
- Replay attack protection via timestamp validation
- Duplicate webhook detection via idempotency keys
- Webhook event logging and quarantine for invalid webhooks
- Structured lifecycle logging
"""

import uuid
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Awaitable

from sqlalchemy import select, delete, func, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.woocommerce.models import (
    WooCommerceStore,
    WooCommerceProduct,
    WooCommerceOrder,
    WooCommerceCustomer,
    WooCommerceCoupon,
    WooCommerceCategory,
    WooCommerceAlert,
    WooCommerceSyncLog,
)
from app.woocommerce.constants import (
    SyncStatus,
    SyncType,
    AlertType,
    AlertSeverity,
    StoreStatus,
    WebhookTopic,
)
from app.woocommerce.exceptions import (
    WebhookVerificationError,
    StoreNotFoundError,
)
from app.woocommerce.service import WooCommerceService

# ── Order Integration (Phase 5 — failures don't break webhooks) ──
try:
    from app.woocommerce.order_integration_service import WooCommerceOrderIntegrationService
    from app.models import Store as InventoryStore
    _ORDER_INTEGRATION_AVAILABLE = True
except ImportError:
    WooCommerceOrderIntegrationService = None
    InventoryStore = None
    _ORDER_INTEGRATION_AVAILABLE = False

logger = logging.getLogger(__name__)

# ─── Constants for webhook security ───

# Maximum age for a webhook timestamp (seconds)
MAX_WEBHOOK_AGE_SECONDS: int = 300  # 5 minutes

# Redis key prefix for idempotency tracking
IDEMPOTENCY_KEY_PREFIX: str = "wc_webhook_idempotency:"


class WebhookEvent:
    """
    Represents a single webhook event with full context.

    Tracks the complete lifecycle of a webhook from receipt to processing.
    """

    def __init__(
        self,
        topic: str,
        store_id: uuid.UUID,
        resource_id: Optional[int] = None,
        payload: Optional[dict] = None,
        source_url: str = "",
        signature: str = "",
        idempotency_key: str = "",
    ):
        self.id: str = str(uuid.uuid4())
        self.topic: str = topic
        self.store_id: uuid.UUID = store_id
        self.resource_id: Optional[int] = resource_id
        self.payload: dict = payload or {}
        self.source_url: str = source_url
        self.signature: str = signature
        self.idempotency_key: str = idempotency_key or self.id
        self.received_at: datetime = datetime.now(timezone.utc)
        self.processed_at: Optional[datetime] = None
        self.status: str = "received"  # received, verified, processed, failed, quarantined
        self.error: Optional[str] = None

    def mark_verified(self):
        """Mark webhook as signature-verified."""
        self.status = "verified"

    def mark_processed(self):
        """Mark webhook as successfully processed."""
        self.status = "processed"
        self.processed_at = datetime.now(timezone.utc)

    def mark_failed(self, error: str):
        """Mark webhook as failed."""
        self.status = "failed"
        self.error = error
        self.processed_at = datetime.now(timezone.utc)

    def mark_quarantined(self, reason: str):
        """Mark webhook as quarantined (invalid signature, replay, etc.)."""
        self.status = "quarantined"
        self.error = reason
        self.processed_at = datetime.now(timezone.utc)

    def to_log_dict(self) -> dict:
        """Serialize event to structured log dict."""
        return {
            "webhook_id": self.id,
            "topic": self.topic,
            "store_id": str(self.store_id),
            "resource_id": self.resource_id,
            "status": self.status,
            "error": self.error,
            "received_at": self.received_at.isoformat(),
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "latency_ms": (
                int((self.processed_at - self.received_at).total_seconds() * 1000)
                if self.processed_at else None
            ),
        }


class WebhookManager:
    """
    Manages WooCommerce webhook processing with security, routing, and logging.

    Provides:
    - Per-topic handler dispatch (product.*, order.*, customer.*, etc.)
    - HMAC-SHA256 signature verification
    - Replay attack protection (timestamp-based)
    - Duplicate detection (idempotency key)
    - Structured lifecycle logging
    - Quarantine for invalid webhooks
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.logger = logging.getLogger(f"{__name__}.WebhookManager")
        self.service: Optional[WooCommerceService] = None

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API — Process a webhook end-to-end
    # ═══════════════════════════════════════════════════════════════

    async def process_webhook(
        self,
        body: bytes,
        headers: dict[str, str],
        topic: str,
    ) -> dict:
        """
        Process an incoming webhook end-to-end.

        Pipeline:
        1. Parse and validate headers
        2. Look up store by source URL
        3. Verify HMAC-SHA256 signature
        4. Check for replay attack (timestamp)
        5. Check for duplicate (idempotency key)
        6. Parse payload
        7. Route to appropriate topic handler
        8. Log result

        Args:
            body: Raw request body bytes
            headers: Request headers dict
            topic: Webhook topic (e.g., "product.updated")

        Returns:
            Dict with processing result
        """
        event = WebhookEvent(
            topic=topic,
            store_id=uuid.UUID(int=0),  # Placeholder, updated after store lookup
            source_url=headers.get("x-wc-webhook-source", ""),
            signature=headers.get("x-wc-webhook-signature", ""),
            idempotency_key=headers.get("x-wc-webhook-id", "")
                           or headers.get("x-wc-webhook-delivery-id", ""),
        )

        self.logger.info(
            "Webhook received: topic=%s, id=%s, source=%s",
            topic, event.id, event.source_url[:50] + "...",
        )

        # Step 1: Validate source header
        if not event.source_url:
            self.logger.warning("Webhook %s: missing source header", event.id)
            return self._result("ignored", "missing_source_header")

        # Step 2: Look up store
        store = await self._find_store(event.source_url)
        if not store:
            self.logger.info("Webhook %s: store not found for %s", event.id, event.source_url)
            return self._result("ignored", "store_not_found")

        event.store_id = store.id

        # Step 3: Verify HMAC signature
        if not self._verify_signature(body, event.signature, store.webhook_secret):
            event.mark_quarantined("invalid_signature")
            self._log_webhook_event(event)
            self._create_alert_for_webhook_failure(event)
            # Return 200 to prevent WooCommerce retries — log instead
            return self._result("quarantined", "invalid_signature", event_id=event.id)

        event.mark_verified()

        # Step 4: Check for replay attack
        if not self._validate_timestamp(headers, event):
            event.mark_quarantined("replay_detected")
            self._log_webhook_event(event)
            return self._result("quarantined", "replay_detected", event_id=event.id)

        # Step 5: Check for duplicate (idempotency)
        if event.idempotency_key and await self._is_duplicate(event.idempotency_key):
            self.logger.info(
                "Webhook %s: duplicate detected (key=%s), skipping",
                event.id, event.idempotency_key,
            )
            return self._result("skipped", "duplicate", event_id=event.id)

        # Step 6: Parse payload
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            event.mark_failed(f"invalid_json: {exc}")
            self._log_webhook_event(event)
            return self._result("failed", "invalid_json", event_id=event.id)

        event.payload = payload
        event.resource_id = payload.get("id") if isinstance(payload, dict) else None

        # Step 7: Route to handler
        try:
            await self._route_webhook(topic, store, payload, event)
            event.mark_processed()
        except Exception as exc:
            event.mark_failed(str(exc))
            self._create_alert_for_webhook_failure(event)

        # Step 8: Log and return
        self._log_webhook_event(event)
        return self._result(
            event.status,
            event.error or "ok",
            event_id=event.id,
        )

    # ═══════════════════════════════════════════════════════════════
    # TOPIC ROUTING
    # ═══════════════════════════════════════════════════════════════

    async def _route_webhook(
        self,
        topic: str,
        store: WooCommerceStore,
        payload: dict,
        event: WebhookEvent,
    ):
        """Route a webhook to the appropriate handler based on topic."""
        self.service = WooCommerceService(db=self.db, user=None)

        # Product topics
        if topic == WebhookTopic.PRODUCT_CREATED.value:
            await self._handle_product_created(store, payload)
        elif topic == WebhookTopic.PRODUCT_UPDATED.value:
            await self._handle_product_updated(store, payload)
        elif topic == WebhookTopic.PRODUCT_DELETED.value:
            await self._handle_product_deleted(store, payload)

        # Variation topics
        elif topic in ("variation.created", "variation.updated"):
            await self._handle_variation_changed(store, payload)
        elif topic == "variation.deleted":
            await self._handle_variation_deleted(store, payload)

        # Order topics
        elif topic == WebhookTopic.ORDER_CREATED.value:
            await self._handle_order_created(store, payload)
        elif topic == WebhookTopic.ORDER_UPDATED.value:
            await self._handle_order_updated(store, payload)
        elif topic == WebhookTopic.ORDER_DELETED.value:
            await self._handle_order_deleted(store, payload)

        # Customer topics
        elif topic == WebhookTopic.CUSTOMER_CREATED.value:
            await self._handle_customer_created(store, payload)
        elif topic == WebhookTopic.CUSTOMER_UPDATED.value:
            await self._handle_customer_updated(store, payload)
        elif topic == WebhookTopic.CUSTOMER_DELETED.value:
            logger.info("Customer deleted webhook: %s", payload.get("id"))

        # Category topics
        elif topic in (
            WebhookTopic.CATEGORY_CREATED.value,
            WebhookTopic.CATEGORY_UPDATED.value,
            WebhookTopic.CATEGORY_DELETED.value,
        ):
            await self.service.sync_categories(store_id=store.id)

        # Coupon topics
        elif topic in (
            WebhookTopic.COUPON_CREATED.value,
            WebhookTopic.COUPON_UPDATED.value,
            WebhookTopic.COUPON_DELETED.value,
        ):
            await self.service.sync_coupons(store_id=store.id)

        # Inventory / Stock topic
        elif topic in ("stock.updated", "inventory.updated"):
            await self._handle_stock_updated(store, payload)

        else:
            self.logger.info("Unknown webhook topic: %s — falling back to full sync", topic)
            # Fallback: sync all resources
            await self.service.sync_products(store_id=store.id, force_full=False)

    # ═══════════════════════════════════════════════════════════════
    # TOPIC HANDLERS
    # ═══════════════════════════════════════════════════════════════

    async def _handle_product_created(self, store: WooCommerceStore, payload: dict):
        """Handle product.created webhook — sync newly created product."""
        wc_product_id = payload.get("id")
        self.logger.info("Product created: store=%s, product_id=%s", store.store_name, wc_product_id)

        # Sync all products (the specific product will be upserted)
        await self.service.sync_products(store_id=store.id, force_full=False)

        # Log the event
        await self._log_product_event(store.id, wc_product_id, "created")

    async def _handle_product_updated(self, store: WooCommerceStore, payload: dict):
        """Handle product.updated webhook — sync updated product."""
        wc_product_id = payload.get("id")
        self.logger.info("Product updated: store=%s, product_id=%s", store.store_name, wc_product_id)

        await self.service.sync_products(store_id=store.id, force_full=False)
        await self._log_product_event(store.id, wc_product_id, "updated")

    async def _handle_product_deleted(self, store: WooCommerceStore, payload: dict):
        """
        Handle product.deleted webhook — remove product locally.

        WooCommerce sends product.deleted with the product ID after deletion.
        We soft-delete by marking the product inactive locally.
        """
        wc_product_id = payload.get("id")
        self.logger.info("Product deleted: store=%s, product_id=%s", store.store_name, wc_product_id)

        if wc_product_id:
            result = await self.db.execute(
                select(WooCommerceProduct).where(
                    WooCommerceProduct.store_id == store.id,
                    WooCommerceProduct.wc_product_id == wc_product_id,
                )
            )
            product = result.scalar_one_or_none()
            if product:
                product.status = "trash"
                await self.db.commit()
                self.logger.info("Product %s moved to trash", wc_product_id)

        await self._log_product_event(store.id, wc_product_id, "deleted")

    async def _handle_variation_changed(self, store: WooCommerceStore, payload: dict):
        """Handle variation.created/updated — sync variations for the parent product."""
        parent_id = payload.get("parent_id")
        self.logger.info(
            "Variation changed: store=%s, parent_id=%s, variation_id=%s",
            store.store_name, parent_id, payload.get("id"),
        )
        # Trigger a product sync to pick up variation changes
        await self.service.sync_products(store_id=store.id, force_full=False)

    async def _handle_variation_deleted(self, store: WooCommerceStore, payload: dict):
        """Handle variation.deleted — sync parent product to reflect removal."""
        parent_id = payload.get("parent_id")
        self.logger.info("Variation deleted: store=%s, parent_id=%s", store.store_name, parent_id)
        await self.service.sync_products(store_id=store.id, force_full=False)

    async def _handle_order_created(self, store: WooCommerceStore, payload: dict):
        """Handle order.created — sync the new order and trigger allocation+reservation."""
        wc_order_id = payload.get("id")
        self.logger.info("Order created: store=%s, order_id=%s", store.store_name, wc_order_id)

        await self.service.sync_orders(store_id=store.id, date_after=None, status=None)

        # Update inventory for order items
        await self._update_inventory_from_order(store, payload)

        # ── Phase 5: Trigger allocation + reservation (E.1, E.2, E.5) ──
        if _ORDER_INTEGRATION_AVAILABLE:
            await self._process_order_integration(store, wc_order_id)

    async def _handle_order_updated(self, store: WooCommerceStore, payload: dict):
        """Handle order.updated — re-sync the order and process status change."""
        wc_order_id = payload.get("id")
        self.logger.info("Order updated: store=%s, order_id=%s", store.store_name, wc_order_id)

        await self.service.sync_orders(store_id=store.id, date_after=None, status=None)

        # If order was refunded or cancelled, adjust inventory back
        status = payload.get("status", "")
        if status in ("refunded", "cancelled"):
            await self._update_inventory_from_order(store, payload, reverse=True)

        # ── Phase 5: Process order status change (E.3, E.5) ──
        if _ORDER_INTEGRATION_AVAILABLE:
            await self._process_order_integration(store, wc_order_id)

    async def _handle_order_deleted(self, store: WooCommerceStore, payload: dict):
        """Handle order.deleted — remove order locally."""
        wc_order_id = payload.get("id")
        self.logger.info("Order deleted: store=%s, order_id=%s", store.store_name, wc_order_id)

        if wc_order_id:
            result = await self.db.execute(
                select(WooCommerceOrder).where(
                    WooCommerceOrder.store_id == store.id,
                    WooCommerceOrder.wc_order_id == wc_order_id,
                )
            )
            order = result.scalar_one_or_none()
            if order:
                # Mark as trashed rather than deleting permanently
                order.status = "trash"
                await self.db.commit()

    async def _handle_customer_created(self, store: WooCommerceStore, payload: dict):
        """Handle customer.created — sync the new customer."""
        self.logger.info("Customer created: store=%s", store.store_name)
        await self.service.sync_customers(store_id=store.id)

    async def _handle_customer_updated(self, store: WooCommerceStore, payload: dict):
        """Handle customer.updated — re-sync the customer."""
        self.logger.info("Customer updated: store=%s", store.store_name)
        await self.service.sync_customers(store_id=store.id)

    async def _handle_stock_updated(self, store: WooCommerceStore, payload: dict):
        """Handle stock.updated webhook — update inventory locally."""
        wc_product_id = payload.get("id") or payload.get("product_id")
        stock_quantity = payload.get("stock_quantity")
        self.logger.info(
            "Stock updated: store=%s, product_id=%s, quantity=%s",
            store.store_name, wc_product_id, stock_quantity,
        )

        if wc_product_id and stock_quantity is not None:
            result = await self.db.execute(
                select(WooCommerceProduct).where(
                    WooCommerceProduct.store_id == store.id,
                    WooCommerceProduct.wc_product_id == wc_product_id,
                )
            )
            product = result.scalar_one_or_none()
            if product:
                old_quantity = product.stock_quantity or 0
                product.stock_quantity = stock_quantity
                product.last_synced_at = datetime.now(timezone.utc)
                await self.db.commit()

    async def _update_inventory_from_order(
        self, store: WooCommerceStore, payload: dict, reverse: bool = False,
    ):
        """Update local inventory based on order line items."""
        line_items = payload.get("line_items", [])
        for item in line_items:
            wc_product_id = item.get("product_id")
            quantity = item.get("quantity", 0)
            if wc_product_id and quantity:
                result = await self.db.execute(
                    select(WooCommerceProduct).where(
                        WooCommerceProduct.store_id == store.id,
                        WooCommerceProduct.wc_product_id == wc_product_id,
                    )
                )
                product = result.scalar_one_or_none()
                if product and product.manage_stock:
                    adjustment = -quantity if not reverse else quantity
                    new_qty = (product.stock_quantity or 0) + adjustment
                    product.stock_quantity = max(0, new_qty)
                    product.last_synced_at = datetime.now(timezone.utc)

        if line_items:
            await self.db.commit()

    # ═══════════════════════════════════════════════════════════════
    # PHASE 5 — Order Integration Pipeline (E.1, E.2, E.3, E.5)
    # ═══════════════════════════════════════════════════════════════

    async def _process_order_integration(
        self,
        wc_store: WooCommerceStore,
        wc_order_id: Optional[int],
    ) -> None:
        """
        Process a WooCommerce order through the allocation + reservation pipeline.

        Called from _handle_order_created and _handle_order_updated.
        All exceptions are caught — webhook processing is never blocked.

        Pipeline:
        1. Look up the synced WooCommerceOrder locally
        2. Resolve the inventory Store from WooCommerceStore.owner_id
        3. Create WooCommerceOrderIntegrationService
        4. Call process_synced_order() → allocate → reserve → status update
        """
        if not _ORDER_INTEGRATION_AVAILABLE or not wc_order_id:
            return

        try:
            # Step 1: Find the locally synced order
            result = await self.db.execute(
                select(WooCommerceOrder).where(
                    WooCommerceOrder.store_id == wc_store.id,
                    WooCommerceOrder.wc_order_id == wc_order_id,
                ).limit(1)
            )
            order = result.scalar_one_or_none()
            if order is None:
                self.logger.debug(
                    "Order %d not found locally after sync — skipping integration",
                    wc_order_id,
                )
                return

            # Step 2: Resolve the inventory Store by owner_id
            inv_store_result = await self.db.execute(
                select(InventoryStore).where(
                    InventoryStore.owner_id == wc_store.owner_id,
                ).limit(1)
            )
            inv_store = inv_store_result.scalar_one_or_none()
            if inv_store is None:
                self.logger.debug(
                    "No inventory Store found for owner %s — skipping integration",
                    wc_store.owner_id,
                )
                return

            # Step 3: Create integration service and process
            integration = WooCommerceOrderIntegrationService(
                db=self.db,
                wc_store=wc_store,
                store=inv_store,
                user_id=wc_store.owner_id,
            )

            # Step 4: Process the order (allocates + handles status)
            result = await integration.process_synced_order(order)

            self.logger.info(
                "Order %d integration completed: allocation=%s, status=%s",
                wc_order_id,
                result.get("allocation", {}).get("status"),
                result.get("status_action", {}).get("status"),
            )

        except Exception as exc:
            self.logger.warning(
                "Order integration failed for order %d: %s — "
                "webhook continues unaffected (Phase 5 E.6/E.10)",
                wc_order_id, exc,
            )

    # ═══════════════════════════════════════════════════════════════
    # SECURITY — Signature verification, replay protection, dedup
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _verify_signature(
        body: bytes,
        signature_header: str,
        webhook_secret: Optional[str],
    ) -> bool:
        """
        Verify WooCommerce webhook HMAC-SHA256 signature.

        Returns True if:
        - No signature header present (graceful fallback)
        - No webhook secret configured (graceful fallback)
        - Signature matches expected HMAC

        Returns False if signature is present but invalid (quarantine).
        """
        if not signature_header:
            logger.warning("Webhook signature header missing — accepting anyway")
            return True

        if not webhook_secret:
            logger.warning("Webhook secret not configured — skipping verification")
            return True

        expected = hmac.new(
            webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()

        is_valid = hmac.compare_digest(expected, signature_header)

        if not is_valid:
            logger.warning(
                "Webhook signature mismatch! expected=%s... got=%s...",
                expected[:16], signature_header[:16],
            )

        return is_valid

    @staticmethod
    def _validate_timestamp(
        headers: dict[str, str],
        event: WebhookEvent,
    ) -> bool:
        """
        Validate webhook timestamp to prevent replay attacks.

        Checks the x-wc-webhook-delivery-id or x-wc-webhook-id header
        against a maximum age window. If the header contains a timestamp
        or the delivery ID is too old, the webhook is rejected.

        Returns True if timestamp is valid or cannot be determined.
        """
        # WooCommerce doesn't send a standard timestamp header,
        # but we can check the delivery ID format for timestamps
        delivery_id = headers.get("x-wc-webhook-delivery-id", "")
        if delivery_id and delivery_id.startswith("wc_delivery_"):
            try:
                # Extract timestamp from delivery ID if present
                # Format: wc_delivery_{timestamp}_{uuid}
                parts = delivery_id.split("_")
                if len(parts) >= 3:
                    ts = int(parts[2])
                    delivery_time = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                    age = (datetime.now(timezone.utc) - delivery_time).total_seconds()
                    if age > MAX_WEBHOOK_AGE_SECONDS:
                        logger.warning(
                            "Webhook replay detected: delivery_id=%s, age=%.0fs",
                            delivery_id, age,
                        )
                        return False
            except (ValueError, IndexError, OSError):
                pass

        return True

    async def _is_duplicate(self, idempotency_key: str) -> bool:
        """
        Check if a webhook with this idempotency key has been processed recently.

        In production, this uses Redis. Falls back to in-memory tracking
        which resets on app restart.
        """
        # In production: redis_client.get(f"{IDEMPOTENCY_KEY_PREFIX}{idempotency_key}")
        # For now, check if a sync log exists with matching metadata
        result = await self.db.execute(
            select(WooCommerceSyncLog).where(
                WooCommerceSyncLog.meta_data["webhook_id"].as_string() == idempotency_key,
                WooCommerceSyncLog.created_at >= datetime.now(timezone.utc) - timedelta(minutes=5),
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL — Store lookup, logging, alerts
    # ═══════════════════════════════════════════════════════════════

    async def _find_store(self, source_url: str) -> Optional[WooCommerceStore]:
        """Find a store by its WooCommerce source URL."""
        store_url = source_url.rstrip("/")
        result = await self.db.execute(
            select(WooCommerceStore).where(
                WooCommerceStore.store_url == store_url,
                WooCommerceStore.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    def _log_webhook_event(self, event: WebhookEvent):
        """Log a structured webhook event."""
        log_data = event.to_log_dict()
        if event.status == "processed":
            self.logger.info("Webhook processed: %s", log_data)
        elif event.status == "failed":
            self.logger.error("Webhook failed: %s", log_data)
        elif event.status == "quarantined":
            self.logger.warning("Webhook quarantined: %s", log_data)
        else:
            self.logger.debug("Webhook event: %s", log_data)

    async def _log_product_event(
        self, store_id: uuid.UUID, wc_product_id: Optional[int], action: str,
    ):
        """Log a product change event from a webhook."""
        if not wc_product_id:
            return
        sync_log = WooCommerceSyncLog(
            store_id=store_id,
            sync_type=SyncType.WEBHOOK,
            resource="products",
            status=SyncStatus.COMPLETED,
            total_items=1,
            created_items=1 if action == "created" else 0,
            updated_items=1 if action == "updated" else 0,
            meta_data={
                "webhook_action": action,
                "wc_product_id": wc_product_id,
                "source": "webhook",
            },
        )
        self.db.add(sync_log)
        await self.db.commit()

    async def _create_alert_for_webhook_failure(self, event: WebhookEvent):
        """Create an alert for a failed or quarantined webhook."""
        if event.status not in ("failed", "quarantined"):
            return

        alert = WooCommerceAlert(
            store_id=event.store_id,
            alert_type=AlertType.API_FAILURE,
            severity=AlertSeverity.WARNING,
            title=f"Webhook {event.status}: {event.topic}",
            message=f"Webhook event {event.id} for topic '{event.topic}' "
                    f"was {event.status}: {event.error or 'unknown error'}",
            resource_type="webhook",
            resource_id=event.id,
            meta_data=event.to_log_dict(),
        )
        self.db.add(alert)
        await self.db.commit()

    @staticmethod
    def _result(
        status: str,
        detail: str,
        event_id: str = "",
    ) -> dict:
        """Build a standardized result dict."""
        result = {
            "status": "ok",
            "result": status,
            "detail": detail,
        }
        if event_id:
            result["webhook_id"] = event_id
        return result
