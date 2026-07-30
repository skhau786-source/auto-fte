"""
Dashboard Service — aggregates inventory metrics for the monitoring dashboard.

Queries across multiple repositories to provide a comprehensive view
of inventory health for a store.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models import (
    Store,
    Product,
    ProductVariant,
    InventoryTransaction,
    InventoryLog,
)
from app.inventory.constants import TransactionType, InventoryAction
from app.inventory.repository import ProductRepository, VariantRepository
from app.dashboard.dashboard_schema import (
    DashboardResponse,
    DashboardSummary,
    TodayTransactionSummary,
    SyncHealthSummary,
    WebhookHealthSummary,
    RecentErrorItem,
)

logger = logging.getLogger(__name__)

SYNC_FAILURE_ACTIONS = {
    InventoryAction.SHOPIFY_SYNC_FAILED.value,
}


class DashboardService:
    """Aggregate inventory data for the monitoring dashboard."""

    def __init__(self, db: AsyncSession, store: Store):
        self.db = db
        self.store = store
        self.product_repo = ProductRepository(db)
        self.variant_repo = VariantRepository(db)

    async def get_dashboard(self) -> DashboardResponse:
        """Build the complete dashboard response."""
        inventory_summary = await self._get_inventory_summary()
        today_txns = await self._get_today_transactions()
        sync_health = await self._get_sync_health()
        webhook_health = await self._get_webhook_health()
        recent_errors = await self._get_recent_errors()

        return DashboardResponse(
            inventory_summary=inventory_summary,
            today_transactions=today_txns,
            sync_health=sync_health,
            webhook_health=webhook_health,
            recent_errors=recent_errors,
            generated_at=datetime.now(timezone.utc),
            store_id=self.store.id,
            store_domain=self.store.shopify_domain,
        )

    async def _get_inventory_summary(self) -> DashboardSummary:
        """Aggregate product/variant/inventory counts."""
        stats = await self.product_repo.dashboard_stats(self.store.id)

        # Category count
        cat_result = await self.db.execute(
            select(func.count(Product.id))
            .where(
                Product.store_id == self.store.id,
                Product.category_id.isnot(None),
            )
        )
        categorized_count = cat_result.scalar() or 0

        return DashboardSummary(
            total_products=stats["total_products"],
            total_variants=stats["total_variants"],
            total_inventory_units=stats["total_inventory_units"],
            total_inventory_value=stats.get("total_value", 0),
            low_stock_count=stats["low_stock_count"],
            out_of_stock_count=stats["out_of_stock_count"],
            category_count=categorized_count,
        )

    async def _get_today_transactions(self) -> TodayTransactionSummary:
        """Count today's transactions by type."""
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Total today
        total_result = await self.db.execute(
            select(func.count(InventoryTransaction.id))
            .select_from(InventoryTransaction)
            .join(ProductVariant, InventoryTransaction.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(
                Product.store_id == self.store.id,
                InventoryTransaction.created_at >= today_start,
            )
        )

        # Use a single query with group_by
        type_counts_query = (
            select(
                InventoryTransaction.transaction_type,
                func.count(InventoryTransaction.id),
            )
            .select_from(InventoryTransaction)
            .join(ProductVariant, InventoryTransaction.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(
                Product.store_id == self.store.id,
                InventoryTransaction.created_at >= today_start,
            )
            .group_by(InventoryTransaction.transaction_type)
        )

        type_counts: dict[str, int] = {}
        result = await self.db.execute(type_counts_query)
        for txn_type, count in result.all():
            type_counts[txn_type] = count

        return TodayTransactionSummary(
            total=total_result.scalar() or 0,
            adjustments=type_counts.get(TransactionType.ADJUSTMENT.value, 0),
            shopify_syncs=type_counts.get(TransactionType.SHOPIFY_SYNC.value, 0)
                         + type_counts.get(TransactionType.SALE.value, 0),
            low_stock_alerts=0,  # Future: alert tracking
        )

    async def _get_sync_health(self) -> SyncHealthSummary:
        """Check sync status for store."""
        from app.inventory.repository import TransactionRepository
        txn_repo = TransactionRepository(self.db)

        unsynced = await txn_repo.get_unsynced(self.store.id, limit=100)

        failed_count = sum(
            1 for t in unsynced
            if (datetime.now(timezone.utc) - t.created_at).total_seconds() > 3600
        )

        return SyncHealthSummary(
            pending_syncs=len(unsynced),
            failed_syncs=failed_count,
            dead_letter_count=0,  # Future: dead letter table
            average_sync_time_ms=None,
            last_sync_at=None,
            last_sync_status="success" if len(unsynced) == 0 else "failed",
        )

    async def _get_webhook_health(self) -> WebhookHealthSummary:
        """Check webhook health — recent activity."""
        cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)

        # Count webhook-type transactions
        webhook_result = await self.db.execute(
            select(func.count(InventoryTransaction.id))
            .select_from(InventoryTransaction)
            .join(ProductVariant, InventoryTransaction.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(
                Product.store_id == self.store.id,
                InventoryTransaction.transaction_type == TransactionType.SHOPIFY_SYNC.value,
                InventoryTransaction.created_at >= cutoff_24h,
            )
        )

        # Get last webhook timestamp
        last_wh_result = await self.db.execute(
            select(InventoryTransaction.created_at)
            .select_from(InventoryTransaction)
            .join(ProductVariant, InventoryTransaction.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(
                Product.store_id == self.store.id,
                InventoryTransaction.transaction_type == TransactionType.SHOPIFY_SYNC.value,
            )
            .order_by(InventoryTransaction.created_at.desc())
            .limit(1)
        )
        last_webhook = last_wh_result.scalar_one_or_none()

        # Count recent webhook errors (failed syncs in 24h)
        error_count = 0
        error_result = await self.db.execute(
            select(func.count(InventoryLog.id))
            .join(ProductVariant, InventoryLog.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(
                Product.store_id == self.store.id,
                InventoryLog.action.in_(SYNC_FAILURE_ACTIONS),
                InventoryLog.created_at >= cutoff_24h,
            )
        )
        error_count = error_result.scalar() or 0

        return WebhookHealthSummary(
            total_received_24h=webhook_result.scalar() or 0,
            last_webhook_at=last_webhook,
            errors_24h=error_count,
            webhooks_registered=[
                "products/update",
                "inventory_levels/update",
                "app/uninstalled",
            ],
        )

    async def _get_recent_errors(self, limit: int = 10) -> list[RecentErrorItem]:
        """Get the most recent sync/operation errors."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        result = await self.db.execute(
            select(InventoryLog)
            .join(ProductVariant, InventoryLog.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(
                Product.store_id == self.store.id,
                InventoryLog.action.in_(SYNC_FAILURE_ACTIONS),
                InventoryLog.created_at >= cutoff,
            )
            .order_by(InventoryLog.created_at.desc())
            .limit(limit)
        )

        return [
            RecentErrorItem(
                id=log.id,
                action=log.action,
                details=log.details or {},
                created_at=log.created_at,
                variant_id=log.variant_id,
            )
            for log in result.scalars().all()
        ]
