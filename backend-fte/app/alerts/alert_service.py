"""
Alert Service — monitors inventory conditions and triggers notifications.

Alert conditions:
1. Low Inventory — variant quantity drops below threshold
2. Shopify API Failure — sync to Shopify fails
3. Webhook Failure — webhook processing errors
4. Retry Failure — retry worker exhausts all attempts
5. Dead Letter Queue — transactions that cannot be recovered
6. High API Error Rate — error rate exceeds threshold
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Store, ProductVariant, InventoryTransaction, InventoryLog
from app.alerts.notifier import AlertNotifier, Alert

logger = logging.getLogger(__name__)

HIGH_ERROR_RATE_THRESHOLD = 0.10  # 10% error rate triggers alert
ERROR_RATE_WINDOW_MINUTES = 60


class AlertService:
    """Evaluates conditions and fires alerts through registered notifiers."""

    def __init__(
        self,
        db: AsyncSession,
        store: Store,
        notifier: AlertNotifier,
    ):
        self.db = db
        self.store = store
        self.notifier = notifier

    async def check_low_inventory(self, variant: ProductVariant) -> None:
        """Check if a variant is below its threshold and alert if so."""
        threshold = variant.low_stock_threshold or 10
        if variant.inventory_quantity <= threshold:
            alert = Alert(
                title="Low Inventory Alert",
                message=(
                    f"Variant '{variant.title}' (SKU: {variant.sku or 'N/A'}) "
                    f"has only {variant.inventory_quantity} units remaining. "
                    f"Threshold: {threshold}."
                ),
                level="warning",
                source="inventory",
                store_domain=self.store.shopify_domain,
                metadata={
                    "variant_id": str(variant.id),
                    "product_id": str(variant.product_id),
                    "sku": variant.sku,
                    "current_quantity": variant.inventory_quantity,
                    "threshold": threshold,
                },
            )
            await self.notifier.send_alert(alert)

    async def check_shopify_failure(self, error_message: str, variant_id: Optional[str] = None) -> None:
        """Alert on Shopify API failures."""
        alert = Alert(
            title="Shopify API Failure",
            message=f"Shopify sync failed: {error_message}",
            level="error",
            source="shopify",
            store_domain=self.store.shopify_domain,
            metadata={
                "error": error_message,
                "variant_id": variant_id,
            },
        )
        await self.notifier.send_alert(alert)

    async def check_webhook_failure(self, topic: str, error_message: str) -> None:
        """Alert on webhook processing failures."""
        alert = Alert(
            title="Webhook Processing Failure",
            message=f"Webhook '{topic}' failed: {error_message}",
            level="error",
            source="webhook",
            store_domain=self.store.shopify_domain,
            metadata={
                "topic": topic,
                "error": error_message,
            },
        )
        await self.notifier.send_alert(alert)

    async def check_retry_dead_letter(self, transaction_id: str, variant_id: str, attempts: int) -> None:
        """Alert when a retry has been exhausted."""
        alert = Alert(
            title="Retry Exhausted — Dead Letter",
            message=(
                f"Transaction {transaction_id} for variant {variant_id} "
                f"failed after {attempts} retry attempts and has been "
                f"moved to the dead letter queue."
            ),
            level="critical",
            source="inventory",
            store_domain=self.store.shopify_domain,
            metadata={
                "transaction_id": transaction_id,
                "variant_id": variant_id,
                "attempts": attempts,
            },
        )
        await self.notifier.send_alert(alert)

    async def check_error_rate(self) -> None:
        """
        Periodically check if the API error rate exceeds the threshold.

        Should be called by a scheduled job (every ERROR_RATE_WINDOW_MINUTES).
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=ERROR_RATE_WINDOW_MINUTES)

        from sqlalchemy import select, func
        from app.models import Product, ProductVariant

        # Count total sync attempts (transactions) in window
        total_result = await self.db.execute(
            select(func.count(InventoryTransaction.id))
            .select_from(InventoryTransaction)
            .join(ProductVariant, InventoryTransaction.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(
                Product.store_id == self.store.id,
                InventoryTransaction.created_at >= cutoff,
            )
        )
        total = total_result.scalar() or 0
        if total == 0:
            return

        # Count failures
        from app.inventory.constants import InventoryAction
        from app.models import InventoryLog

        failed_result = await self.db.execute(
            select(func.count(InventoryLog.id))
            .join(ProductVariant, InventoryLog.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(
                Product.store_id == self.store.id,
                InventoryLog.action == InventoryAction.SHOPIFY_SYNC_FAILED.value,
                InventoryLog.created_at >= cutoff,
            )
        )
        failed = failed_result.scalar() or 0

        error_rate = failed / total if total > 0 else 0
        if error_rate >= HIGH_ERROR_RATE_THRESHOLD:
            alert = Alert(
                title="High API Error Rate",
                message=(
                    f"Error rate in the last {ERROR_RATE_WINDOW_MINUTES} minutes "
                    f"is {error_rate:.1%} ({failed}/{total} operations failed). "
                    f"Threshold: {HIGH_ERROR_RATE_THRESHOLD:.0%}."
                ),
                level="error",
                source="shopify",
                store_domain=self.store.shopify_domain,
                metadata={
                    "error_rate": str(error_rate),
                    "total_operations": total,
                    "failed_operations": failed,
                    "window_minutes": ERROR_RATE_WINDOW_MINUTES,
                },
            )
            await self.notifier.send_alert(alert)
