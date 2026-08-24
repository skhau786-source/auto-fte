"""
Inventory Capabilities — adapter layer wrapping existing InventoryService.

These capabilities allow AI agents to safely interact with the inventory
system through the existing service layer. Agents NEVER bypass the service.

Read capabilities (safe, no approval required):
- inventory.list_products
- inventory.get_product
- inventory.get_low_stock
- inventory.get_history
- inventory.get_dashboard

Write capabilities (require human approval):
- inventory.adjust_stock

The capabilities delegate to the existing InventoryService, AggregationEngine,
and other services — they do NOT create duplicate inventory logic.
"""

import uuid
import logging
from typing import Any

from app.ai.capabilities.base import (
    BaseCapability,
    CapabilityDescriptor,
    CapabilityType,
    CapabilityCategory,
    capability_registry,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# READ CAPABILITIES (safe, no approval)
# ═══════════════════════════════════════════════════════════════════


class InventoryListProductsCapability(BaseCapability):
    """List products for the store with optional filters."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="inventory.list_products",
            display_name="List Products",
            description="List products in the store inventory with optional search, filters, and pagination.",
            capability_type=CapabilityType.READ,
            category=CapabilityCategory.INVENTORY,
            requires_approval=False,
            supported_agent_types=["inventory", "sales", "analytics", "custom"],
        )

    async def execute(self, input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        from app.models import Store
        from sqlalchemy import select

        db = context["db"]
        organization_id = context["organization_id"]

        # Find the store for this organization
        result = await db.execute(
            select(Store).where(Store.owner_id == context.get("user_id", uuid.uuid4()))
        )
        store = result.scalar_one_or_none()
        if store is None:
            return {"error": "No store found", "products": [], "total": 0}

        from app.inventory.service import InventoryService
        service = InventoryService(db=db, store=store, user_id=context.get("user_id"))

        products, total = await service.list_products(
            page=input_data.get("page", 1),
            page_size=min(input_data.get("page_size", 20), 100),
            search=input_data.get("search"),
            status=input_data.get("status"),
            low_stock_only=input_data.get("low_stock_only", False),
        )

        product_list = []
        for p in products:
            product_list.append({
                "id": str(p.id),
                "title": p.title,
                "vendor": p.vendor,
                "product_type": p.product_type,
                "status": p.status,
                "variants_count": len(p.variants) if p.variants else 0,
                "total_inventory": sum(v.inventory_quantity for v in (p.variants or [])),
            })

        return {
            "products": product_list,
            "total": total,
            "page": input_data.get("page", 1),
        }


class InventoryGetProductCapability(BaseCapability):
    """Get detailed information about a specific product."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="inventory.get_product",
            display_name="Get Product",
            description="Get detailed information about a specific product including variants and stock levels.",
            capability_type=CapabilityType.READ,
            category=CapabilityCategory.INVENTORY,
            requires_approval=False,
            supported_agent_types=["inventory", "sales", "analytics", "custom"],
        )

    async def execute(self, input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        from app.models import Store
        from sqlalchemy import select

        db = context["db"]
        product_id = input_data.get("product_id")
        if not product_id:
            return {"error": "product_id is required"}

        result = await db.execute(
            select(Store).where(Store.owner_id == context.get("user_id", uuid.uuid4()))
        )
        store = result.scalar_one_or_none()
        if store is None:
            return {"error": "No store found"}

        from app.inventory.service import InventoryService
        service = InventoryService(db=db, store=store, user_id=context.get("user_id"))

        try:
            product = await service.get_product(uuid.UUID(product_id))
        except Exception as e:
            return {"error": str(e)}

        variants = []
        for v in (product.variants or []):
            threshold = v.low_stock_threshold or 10
            if v.inventory_quantity <= 0:
                status = "out_of_stock"
            elif v.inventory_quantity <= threshold:
                status = "low_stock"
            else:
                status = "in_stock"

            variants.append({
                "id": str(v.id),
                "title": v.title,
                "sku": v.sku,
                "price": float(v.price),
                "inventory_quantity": v.inventory_quantity,
                "low_stock_threshold": threshold,
                "status": status,
            })

        return {
            "id": str(product.id),
            "title": product.title,
            "vendor": product.vendor,
            "product_type": product.product_type,
            "status": product.status,
            "variants": variants,
            "total_inventory": sum(v["inventory_quantity"] for v in variants),
        }


class InventoryGetLowStockCapability(BaseCapability):
    """Identify products with low stock levels."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="inventory.get_low_stock",
            display_name="Check Low Stock",
            description="Find all products where inventory is at or below the low-stock threshold.",
            capability_type=CapabilityType.READ,
            category=CapabilityCategory.INVENTORY,
            requires_approval=False,
            supported_agent_types=["inventory", "sales", "analytics", "custom"],
        )

    async def execute(self, input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        from app.models import Store
        from sqlalchemy import select

        db = context["db"]
        result = await db.execute(
            select(Store).where(Store.owner_id == context.get("user_id", uuid.uuid4()))
        )
        store = result.scalar_one_or_none()
        if store is None:
            return {"error": "No store found", "low_stock_items": [], "total": 0}

        from app.inventory.service import InventoryService
        service = InventoryService(db=db, store=store, user_id=context.get("user_id"))

        threshold = input_data.get("threshold", 10)
        items, total = await service.get_low_stock(
            threshold=threshold,
            page=1,
            page_size=min(input_data.get("page_size", 50), 100),
        )

        return {
            "low_stock_items": items,
            "total": total,
            "threshold": threshold,
        }


class InventoryGetHistoryCapability(BaseCapability):
    """Get inventory transaction history."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="inventory.get_history",
            display_name="Inventory History",
            description="Get the audit trail of inventory changes including adjustments, syncs, and returns.",
            capability_type=CapabilityType.READ,
            category=CapabilityCategory.INVENTORY,
            requires_approval=False,
            supported_agent_types=["inventory", "analytics", "custom"],
        )

    async def execute(self, input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        from app.models import Store
        from sqlalchemy import select

        db = context["db"]
        result = await db.execute(
            select(Store).where(Store.owner_id == context.get("user_id", uuid.uuid4()))
        )
        store = result.scalar_one_or_none()
        if store is None:
            return {"error": "No store found", "transactions": [], "total": 0}

        from app.inventory.service import InventoryService
        service = InventoryService(db=db, store=store, user_id=context.get("user_id"))

        transactions, total = await service.get_history(
            page=1,
            page_size=min(input_data.get("page_size", 20), 100),
        )

        txn_list = []
        for t in transactions:
            txn_list.append({
                "id": str(t.id),
                "variant_id": str(t.variant_id),
                "transaction_type": t.transaction_type.value if hasattr(t.transaction_type, "value") else t.transaction_type,
                "quantity_change": t.quantity_change,
                "quantity_before": t.quantity_before,
                "quantity_after": t.quantity_after,
                "reason": t.reason,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })

        return {
            "transactions": txn_list,
            "total": total,
        }


class InventoryGetDashboardCapability(BaseCapability):
    """Get aggregated inventory dashboard data."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="inventory.get_dashboard",
            display_name="Inventory Dashboard",
            description="Get comprehensive inventory metrics including totals, values, and health indicators.",
            capability_type=CapabilityType.READ,
            category=CapabilityCategory.INVENTORY,
            requires_approval=False,
            supported_agent_types=["inventory", "analytics", "sales", "custom"],
        )

    async def execute(self, input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        from app.models import Store
        from sqlalchemy import select

        db = context["db"]
        result = await db.execute(
            select(Store).where(Store.owner_id == context.get("user_id", uuid.uuid4()))
        )
        store = result.scalar_one_or_none()
        if store is None:
            return {"error": "No store found"}

        from app.inventory.aggregation_engine import InventoryAggregationEngine
        engine = InventoryAggregationEngine(db=db, store=store)

        try:
            dashboard = await engine.get_dashboard()
            return dashboard
        except Exception as e:
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════
# WRITE CAPABILITIES (require human approval)
# ═══════════════════════════════════════════════════════════════════


class InventoryAdjustStockCapability(BaseCapability):
    """Adjust inventory stock for a variant. Requires human approval."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="inventory.adjust_stock",
            display_name="Adjust Stock",
            description="Increase or decrease stock for a specific product variant. Requires human approval before execution.",
            capability_type=CapabilityType.WRITE,
            category=CapabilityCategory.INVENTORY,
            requires_approval=True,
            supported_agent_types=["inventory", "custom"],
        )

    async def execute(self, input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        from app.models import Store
        from sqlalchemy import select

        db = context["db"]
        variant_id = input_data.get("variant_id")
        quantity_change = input_data.get("quantity_change")
        reason = input_data.get("reason", "AI agent stock adjustment")

        if not variant_id or quantity_change is None:
            return {"error": "variant_id and quantity_change are required"}

        result = await db.execute(
            select(Store).where(Store.owner_id == context.get("user_id", uuid.uuid4()))
        )
        store = result.scalar_one_or_none()
        if store is None:
            return {"error": "No store found"}

        from app.inventory.service import InventoryService
        service = InventoryService(db=db, store=store, user_id=context.get("user_id"))

        try:
            adjustment_result = await service.adjust_inventory(
                variant_id=uuid.UUID(variant_id),
                quantity_change=int(quantity_change),
                reason=reason,
            )
            return {
                "success": True,
                "variant_id": adjustment_result["variant_id"],
                "quantity_before": adjustment_result["quantity_before"],
                "quantity_after": adjustment_result["quantity_after"],
                "quantity_change": adjustment_result["quantity_change"],
                "message": adjustment_result["message"],
            }
        except Exception as e:
            return {"error": str(e), "success": False}


# ═══════════════════════════════════════════════════════════════════
# WooCommerce Capabilities
# ═══════════════════════════════════════════════════════════════════


class InventoryListOrdersCapability(BaseCapability):
    """List orders from WooCommerce."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="inventory.list_orders",
            display_name="List Orders",
            description="List orders from connected WooCommerce stores with filtering and pagination.",
            capability_type=CapabilityType.READ,
            category=CapabilityCategory.INVENTORY,
            requires_approval=False,
            supported_agent_types=["inventory", "sales", "analytics", "custom"],
        )

    async def execute(self, input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        from app.models import RegisteredStudent
        from app.woocommerce.models import WooCommerceStore, WooCommerceOrder
        from sqlalchemy import select

        db = context["db"]
        user_id = context.get("user_id")
        if not user_id:
            return {"error": "user_id required", "orders": [], "total": 0}

        # Find WooCommerce store for this user
        result = await db.execute(
            select(WooCommerceStore).where(
                WooCommerceStore.owner_id == user_id,
                WooCommerceStore.is_active == True,  # noqa: E712
            )
        )
        wc_store = result.scalar_one_or_none()
        if wc_store is None:
            return {"error": "No WooCommerce store connected", "orders": [], "total": 0}

        from app.woocommerce.service import WooCommerceService
        service = WooCommerceService(db=db, user=await db.get(RegisteredStudent, user_id))

        try:
            orders, total = await service.list_orders(
                store_id=wc_store.id,
                page=1,
                page_size=min(input_data.get("page_size", 20), 50),
            )

            order_list = []
            for o in orders:
                order_list.append({
                    "id": str(o.id),
                    "wc_order_id": o.wc_order_id,
                    "number": o.number,
                    "status": o.status.value if hasattr(o.status, "value") else o.status,
                    "total": float(o.total),
                    "customer_id": o.customer_id,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                })

            return {"orders": order_list, "total": total}
        except Exception as e:
            return {"error": str(e), "orders": [], "total": 0}


# ═══════════════════════════════════════════════════════════════════
# Registration
# ═══════════════════════════════════════════════════════════════════


def register_inventory_capabilities() -> None:
    """Register all inventory capabilities with the global registry."""
    capabilities = [
        InventoryListProductsCapability(),
        InventoryGetProductCapability(),
        InventoryGetLowStockCapability(),
        InventoryGetHistoryCapability(),
        InventoryGetDashboardCapability(),
        InventoryAdjustStockCapability(),
        InventoryListOrdersCapability(),
    ]
    for cap in capabilities:
        capability_registry.register(cap)
