"""
Sales Capabilities — adapter layer using existing WooCommerce order data.

These capabilities analyze sales data from connected WooCommerce stores.
They do NOT create duplicate sales tables — they query the existing
WooCommerceOrder and WooCommerceProduct models.

Read capabilities (safe, no approval required):
- sales.analyze_orders
- sales.top_products
- sales.revenue_summary

Write capabilities:
- None (sales analysis is read-only in this chunk)
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from app.ai.capabilities.base import (
    BaseCapability,
    CapabilityDescriptor,
    CapabilityType,
    CapabilityCategory,
    capability_registry,
)

logger = logging.getLogger(__name__)


class SalesAnalyzeOrdersCapability(BaseCapability):
    """Analyze recent orders for patterns and insights."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="sales.analyze_orders",
            display_name="Analyze Orders",
            description="Analyze recent order patterns, statuses, and trends from connected WooCommerce stores.",
            capability_type=CapabilityType.READ,
            category=CapabilityCategory.SALES,
            requires_approval=False,
            supported_agent_types=["sales", "analytics", "custom"],
        )

    async def execute(self, input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        from app.woocommerce.models import WooCommerceStore, WooCommerceOrder
        from sqlalchemy import select, func

        db = context["db"]
        user_id = context.get("user_id")
        if not user_id:
            return {"error": "user_id required"}

        # Find WooCommerce store
        result = await db.execute(
            select(WooCommerceStore).where(
                WooCommerceStore.owner_id == user_id,
                WooCommerceStore.is_active == True,  # noqa: E712
            )
        )
        wc_store = result.scalar_one_or_none()
        if wc_store is None:
            return {"error": "No WooCommerce store connected", "analysis": {}}

        # Get order counts by status
        status_counts = await db.execute(
            select(
                WooCommerceOrder.status,
                func.count(WooCommerceOrder.id),
                func.sum(WooCommerceOrder.total),
            ).where(
                WooCommerceOrder.store_id == wc_store.id,
            ).group_by(WooCommerceOrder.status)
        )
        status_data = {}
        total_revenue = 0.0
        total_orders = 0
        for row in status_counts:
            status_val = row[0].value if hasattr(row[0], "value") else str(row[0])
            count = row[1]
            revenue = float(row[2] or 0)
            status_data[status_val] = {"count": count, "revenue": revenue}
            total_revenue += revenue
            total_orders += count

        # Get recent orders (last 30 days)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        recent_result = await db.execute(
            select(func.count(WooCommerceOrder.id)).where(
                WooCommerceOrder.store_id == wc_store.id,
                WooCommerceOrder.created_at >= cutoff,
            )
        )
        recent_orders = recent_result.scalar() or 0

        return {
            "store_id": str(wc_store.id),
            "store_name": wc_store.store_name,
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "orders_by_status": status_data,
            "recent_orders_30d": recent_orders,
            "currency": "USD",
        }


class SalesTopProductsCapability(BaseCapability):
    """Identify top-selling products from order data."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="sales.top_products",
            display_name="Top Products",
            description="Identify best-selling products based on order history and total sales.",
            capability_type=CapabilityType.READ,
            category=CapabilityCategory.SALES,
            requires_approval=False,
            supported_agent_types=["sales", "analytics", "inventory", "custom"],
        )

    async def execute(self, input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        from app.woocommerce.models import WooCommerceStore, WooCommerceProduct
        from sqlalchemy import select

        db = context["db"]
        user_id = context.get("user_id")
        if not user_id:
            return {"error": "user_id required"}

        result = await db.execute(
            select(WooCommerceStore).where(
                WooCommerceStore.owner_id == user_id,
                WooCommerceStore.is_active == True,  # noqa: E712
            )
        )
        wc_store = result.scalar_one_or_none()
        if wc_store is None:
            return {"error": "No WooCommerce store connected", "products": []}

        # Get top products by total_sales
        limit = min(input_data.get("limit", 10), 50)
        products_result = await db.execute(
            select(WooCommerceProduct)
            .where(
                WooCommerceProduct.store_id == wc_store.id,
                WooCommerceProduct.status == "publish",
            )
            .order_by(WooCommerceProduct.total_sales.desc())
            .limit(limit)
        )
        products = list(products_result.scalars().all())

        product_list = []
        for p in products:
            product_list.append({
                "id": str(p.id),
                "wc_product_id": p.wc_product_id,
                "name": p.name,
                "sku": p.sku,
                "price": float(p.price),
                "total_sales": p.total_sales,
                "stock_quantity": p.stock_quantity,
                "stock_status": p.stock_status.value if hasattr(p.stock_status, "value") else p.stock_status,
                "average_rating": p.average_rating,
            })

        return {"products": product_list, "total": len(product_list)}


class SalesRevenueSummaryCapability(BaseCapability):
    """Get a revenue summary from existing order data."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="sales.revenue_summary",
            display_name="Revenue Summary",
            description="Get revenue summary including totals, averages, and period comparisons.",
            capability_type=CapabilityType.READ,
            category=CapabilityCategory.SALES,
            requires_approval=False,
            supported_agent_types=["sales", "analytics", "custom"],
        )

    async def execute(self, input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        from app.woocommerce.models import WooCommerceStore, WooCommerceOrder
        from sqlalchemy import select, func
        from datetime import datetime, timezone, timedelta

        db = context["db"]
        user_id = context.get("user_id")
        if not user_id:
            return {"error": "user_id required"}

        result = await db.execute(
            select(WooCommerceStore).where(
                WooCommerceStore.owner_id == user_id,
                WooCommerceStore.is_active == True,  # noqa: E712
            )
        )
        wc_store = result.scalar_one_or_none()
        if wc_store is None:
            return {"error": "No WooCommerce store connected"}

        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)

        # Last 30 days revenue
        recent = await db.execute(
            select(
                func.sum(WooCommerceOrder.total),
                func.count(WooCommerceOrder.id),
            ).where(
                WooCommerceOrder.store_id == wc_store.id,
                WooCommerceOrder.created_at >= thirty_days_ago,
            )
        )
        recent_row = recent.one()
        recent_revenue = float(recent_row[0] or 0)
        recent_orders = recent_row[1] or 0

        # Previous 30 days revenue (30-60 days ago)
        previous = await db.execute(
            select(
                func.sum(WooCommerceOrder.total),
                func.count(WooCommerceOrder.id),
            ).where(
                WooCommerceOrder.store_id == wc_store.id,
                WooCommerceOrder.created_at >= sixty_days_ago,
                WooCommerceOrder.created_at < thirty_days_ago,
            )
        )
        prev_row = previous.one()
        prev_revenue = float(prev_row[0] or 0)
        prev_orders = prev_row[1] or 0

        # Calculate change
        revenue_change = recent_revenue - prev_revenue if prev_revenue > 0 else 0
        revenue_change_pct = (revenue_change / prev_revenue * 100) if prev_revenue > 0 else 0

        avg_order_value = recent_revenue / recent_orders if recent_orders > 0 else 0

        return {
            "store_id": str(wc_store.id),
            "period": "last_30_days",
            "revenue": recent_revenue,
            "orders": recent_orders,
            "average_order_value": round(avg_order_value, 2),
            "previous_period_revenue": prev_revenue,
            "previous_period_orders": prev_orders,
            "revenue_change": round(revenue_change, 2),
            "revenue_change_pct": round(revenue_change_pct, 1),
        }


# ═══════════════════════════════════════════════════════════════════
# Registration
# ═══════════════════════════════════════════════════════════════════


def register_sales_capabilities() -> None:
    """Register all sales capabilities with the global registry."""
    capabilities = [
        SalesAnalyzeOrdersCapability(),
        SalesTopProductsCapability(),
        SalesRevenueSummaryCapability(),
    ]
    for cap in capabilities:
        capability_registry.register(cap)
