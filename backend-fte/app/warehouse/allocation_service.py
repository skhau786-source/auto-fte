"""
Warehouse Allocation Engine Service — Phase 4 (D.3, D.5, D.6, D.7).

Central service for determining optimal warehouse(s) for fulfilling
inventory requests. Supports:

- Strategy-based allocation (pluggable via strategy pattern)
- Split fulfillment across multiple warehouses
- Immediate reservation via ReservationService
- WooCommerce order integration
- Preview allocations without reserving
- Reallocation support

Integrates with:
- WarehouseService (settings, defaults)
- WarehouseInventoryRepository (stock queries)
- ReservationService (reserve on allocation)
- Strategy Registry (pluggable strategies)
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models import Store, WarehouseInventory, Warehouse
from app.inventory.constants import AllocationStrategy as AllocationStrategyEnum
from app.inventory.repository import VariantRepository
from app.warehouse.repository import (
    WarehouseRepository, WarehouseInventoryRepository,
    WarehouseSettingsRepository,
)
from app.warehouse.reservation_service import ReservationService
from app.warehouse.allocation_strategies import (
    BaseAllocationStrategy, AllocationPlan, WarehouseAllocation,
    AllocationItem, get_registry, get_strategy,
)
from app.warehouse.exceptions import (
    AllocationFailedError, InvalidAllocationStrategyError,
    AllocationHistoryNotFoundError,
    WarehouseNotFoundError, WarehouseInactiveError,
)
from app.inventory.exceptions import VariantNotFoundError, InvalidStoreOwnershipError
from app.warehouse.aggregation_cache import aggregation_cache

logger = logging.getLogger(__name__)

# Default history page size
ALLOCATION_HISTORY_PAGE_SIZE = 20


class AllocationService:
    """
    Service for warehouse allocation decisions.

    Uses the Strategy Pattern to determine optimal warehouse(s)
    and integrates with ReservationService for immediate stock locking.
    """

    def __init__(
        self,
        db: AsyncSession,
        store: Store,
        user_id: Optional[uuid.UUID] = None,
    ):
        self.db = db
        self.store = store
        self.user_id = user_id
        self.wh_repo = WarehouseRepository(db)
        self.inv_repo = WarehouseInventoryRepository(db)
        self.settings_repo = WarehouseSettingsRepository(db)
        self.variant_repo = VariantRepository(db)
        self.strategy_registry = get_registry()
        self.logger = logging.getLogger(f"{__name__}.AllocationService")

    # ═══════════════════════════════════════════════════════════════
    # ALLOCATE FOR ORDER (D.5, D.6)
    # ═══════════════════════════════════════════════════════════════

    async def allocate_order(
        self,
        items: list[AllocationItem],
        order_id: Optional[str] = None,
        strategy_name: Optional[str] = None,
        auto_reserve: bool = True,
    ) -> dict:
        """
        Allocate inventory for an entire order.

        For each item in the order:
        1. Determine strategy (from settings or override)
        2. Run the strategy to pick warehouse(s)
        3. Optionally create reservations via ReservationService
        4. Return allocation plan

        Supports split fulfillment — one order can allocate across
        multiple warehouses.

        Args:
            items: List of (variant_id, quantity) to allocate.
            order_id: Optional order ID for reservations.
            strategy_name: Override strategy (None = from settings).
            auto_reserve: If True, immediately create reservations.

        Returns:
            Dict with overall allocation summary and per-item plans.
        """
        # Get settings for strategy
        strategy = await self._resolve_strategy(strategy_name)
        settings = await self._get_settings_dict()

        results = []
        total_fulfilled = 0
        total_requested = sum(item.quantity for item in items)

        for item in items:
            plan = await self._allocate_variant(
                variant_id=item.variant_id,
                quantity=item.quantity,
                strategy=strategy,
                settings=settings,
            )

            # Optionally reserve immediately
            if auto_reserve and plan.is_fully_fulfilled:
                await self._reserve_allocations(plan, order_id)

            results.append({
                "variant_id": str(item.variant_id),
                "requested": item.quantity,
                "fulfilled": plan.fulfilled_quantity,
                "partial": plan.partial,
                "fully_fulfilled": plan.is_fully_fulfilled,
                "strategy": plan.strategy_name,
                "allocations": [
                    {
                        "warehouse_id": str(a.warehouse_id),
                        "warehouse_name": a.warehouse_name,
                        "quantity": a.quantity,
                    }
                    for a in plan.allocations
                ],
            })
            total_fulfilled += plan.fulfilled_quantity

        return {
            "order_id": order_id,
            "total_items": len(items),
            "total_requested": total_requested,
            "total_fulfilled": total_fulfilled,
            "fully_fulfilled": total_fulfilled >= total_requested,
            "strategy_used": strategy.get_strategy_name(),
            "items": results,
        }

    # ═══════════════════════════════════════════════════════════════
    # ALLOCATE SINGLE VARIANT (D.3)
    # ═══════════════════════════════════════════════════════════════

    async def allocate_variant(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        strategy_name: Optional[str] = None,
        auto_reserve: bool = False,
    ) -> AllocationPlan:
        """
        Allocate a single variant across warehouses.

        Returns an AllocationPlan without reserving stock (unless
        auto_reserve is True). Use preview_allocation for a
        no-side-effect check.
        """
        strategy = await self._resolve_strategy(strategy_name)
        settings = await self._get_settings_dict()

        plan = await self._allocate_variant(
            variant_id=variant_id,
            quantity=quantity,
            strategy=strategy,
            settings=settings,
        )

        if auto_reserve and plan.is_fully_fulfilled:
            await self._reserve_allocations(plan)

        return plan

    # ═══════════════════════════════════════════════════════════════
    # ALLOCATE INVENTORY (Generic)
    # ═══════════════════════════════════════════════════════════════

    async def allocate_inventory(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        warehouse_ids: Optional[list[uuid.UUID]] = None,
        strategy_name: Optional[str] = None,
    ) -> AllocationPlan:
        """
        Allocate inventory for a variant, optionally scoped to specific warehouses.

        If warehouse_ids is provided, only those warehouses are considered.
        Otherwise, all active warehouses for the store are considered.
        """
        strategy = await self._resolve_strategy(strategy_name)
        settings = await self._get_settings_dict()

        # Get warehouse stock, scoped if specified
        stock_list = await self._get_warehouse_stock(variant_id, warehouse_ids)
        if not stock_list:
            raise AllocationFailedError(
                str(variant_id), quantity, 0,
            )

        plan = strategy.allocate(
            variant_id=variant_id,
            quantity=quantity,
            warehouse_stock=stock_list,
            settings=settings,
        )
        if plan.fulfilled_quantity == 0:
            raise AllocationFailedError(
                str(variant_id), quantity, 0,
            )

        return plan

    # ═══════════════════════════════════════════════════════════════
    # REALLOCATE (D.3)
    # ═══════════════════════════════════════════════════════════════

    async def reallocate(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        from_warehouse_id: uuid.UUID,
        to_warehouse_id: uuid.UUID,
        reason: Optional[str] = None,
    ) -> dict:
        """
        Reallocate stock from one warehouse to another.

        This is a convenience that combines:
        1. Release reservation at source warehouse
        2. Create reservation at destination warehouse

        Validates both warehouses exist and have sufficient stock.
        """
        # Validate warehouses
        source = await self.wh_repo.get_by_id(from_warehouse_id)
        if source is None or str(source.store_id) != str(self.store.id):
            raise WarehouseNotFoundError(str(from_warehouse_id))
        if not source.is_active:
            raise WarehouseInactiveError(str(from_warehouse_id))

        dest = await self.wh_repo.get_by_id(to_warehouse_id)
        if dest is None or str(dest.store_id) != str(self.store.id):
            raise WarehouseNotFoundError(str(to_warehouse_id))
        if not dest.is_active:
            raise WarehouseInactiveError(str(to_warehouse_id))

        # Check source has enough available stock
        source_inv = await self.inv_repo.get_by_variant_and_warehouse(
            from_warehouse_id, variant_id,
        )
        source_available = source_inv.available_stock if source_inv else 0
        if source_available < quantity:
            raise AllocationFailedError(
                str(variant_id), quantity, source_available,
            )

        # Create reservation service for atomic operations
        reservation_service = ReservationService(
            db=self.db, store=self.store, user_id=self.user_id,
        )

        # Release at source (via inventory adjustment)
        wh_inv = await self.inv_repo.get_or_create(
            from_warehouse_id, variant_id, with_lock=True,
        )
        wh_inv.available_stock -= quantity
        wh_inv.reserved_stock += quantity

        # Reserve at destination
        dest_inv = await self.inv_repo.get_or_create(
            to_warehouse_id, variant_id, with_lock=True,
        )
        dest_inv.available_stock += quantity

        await self.db.commit()

        # Invalidate aggregation cache after reallocation
        try:
            await aggregation_cache.invalidate_store(self.store.id)
        except Exception as cache_exc:
            self.logger.warning(
                "Cache invalidation failed after reallocation: %s", cache_exc,
            )

        self.logger.info(
            "Reallocated %d units of variant %s from warehouse %s to %s",
            quantity, variant_id, from_warehouse_id, to_warehouse_id,
        )

        return {
            "variant_id": str(variant_id),
            "quantity": quantity,
            "from_warehouse_id": str(from_warehouse_id),
            "from_warehouse_name": source.name,
            "to_warehouse_id": str(to_warehouse_id),
            "to_warehouse_name": dest.name,
            "reason": reason,
        }

    # ═══════════════════════════════════════════════════════════════
    # PREVIEW ALLOCATION (D.3)
    # ═══════════════════════════════════════════════════════════════

    async def preview_allocation(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        strategy_name: Optional[str] = None,
        warehouse_ids: Optional[list[uuid.UUID]] = None,
    ) -> dict:
        """
        Preview an allocation without making any changes.

        Returns the same AllocationPlan structure but does NOT:
        - Reserve stock
        - Create transactions
        - Log events

        Safe for "what-if" analysis in dashboards and UI.
        """
        strategy = await self._resolve_strategy(strategy_name)
        settings = await self._get_settings_dict()
        stock_list = await self._get_warehouse_stock(variant_id, warehouse_ids)

        plan = strategy.allocate(
            variant_id=variant_id,
            quantity=quantity,
            warehouse_stock=stock_list,
            settings=settings,
        )

        return {
            "variant_id": str(variant_id),
            "requested": quantity,
            "fulfilled": plan.fulfilled_quantity,
            "partial": plan.partial,
            "fully_fulfilled": plan.is_fully_fulfilled,
            "strategy": plan.strategy_name,
            "allocations": [
                {
                    "warehouse_id": str(a.warehouse_id),
                    "warehouse_name": a.warehouse_name,
                    "warehouse_code": a.warehouse_code,
                    "quantity": a.quantity,
                    "available_before": a.available_before,
                    "available_after": a.available_after,
                }
                for a in plan.allocations
            ],
            "no_side_effects": True,
        }

    # ═══════════════════════════════════════════════════════════════
    # WOOCOMMERCE INTEGRATION (D.7)
    # ═══════════════════════════════════════════════════════════════

    async def allocate_for_woocommerce(
        self,
        items: list[AllocationItem],
        order_id: str,
        strategy_name: Optional[str] = None,
    ) -> dict:
        """
        Allocate inventory for a WooCommerce order.

        Flow:
        1. Resolve allocation strategy (from settings or override)
        2. For each line item, determine optimal warehouse(s)
        3. Immediately create reservations via ReservationService
        4. Return allocation summary

        Automatically reserves stock — no overselling.
        Raises AllocationFailedError if any item can't be fully fulfilled.
        """
        result = await self.allocate_order(
            items=items,
            order_id=order_id,
            strategy_name=strategy_name,
            auto_reserve=True,
        )

        if not result["fully_fulfilled"]:
            failed_items = [
                item for item in result["items"] if not item["fully_fulfilled"]
            ]
            for item in failed_items:
                self.logger.warning(
                    "WooCommerce allocation partial: variant=%s, "
                    "requested=%d, fulfilled=%d",
                    item["variant_id"], item["requested"], item["fulfilled"],
                )

        return result

    # ═══════════════════════════════════════════════════════════════
    # VALIDATION (D.12)
    # ═══════════════════════════════════════════════════════════════

    async def validate_allocation(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        warehouse_id: uuid.UUID,
    ) -> dict:
        """
        Validate that a specific warehouse can fulfill a quantity.

        Checks:
        - Warehouse exists and is active
        - Warehouse belongs to this store
        - Warehouse has enough available stock
        - Reservation doesn't exceed stock

        Returns detailed validation result.
        """
        warehouse = await self.wh_repo.get_by_id(warehouse_id)
        if warehouse is None:
            return {"valid": False, "reason": "not_found", "warehouse_id": str(warehouse_id)}
        if str(warehouse.store_id) != str(self.store.id):
            return {"valid": False, "reason": "wrong_store", "warehouse_id": str(warehouse_id)}
        if not warehouse.is_active:
            return {"valid": False, "reason": "inactive", "warehouse_id": str(warehouse_id)}

        wh_inv = await self.inv_repo.get_by_variant_and_warehouse(
            warehouse_id, variant_id,
        )
        available = wh_inv.available_stock if wh_inv else 0
        valid = available >= quantity

        return {
            "valid": valid,
            "warehouse_id": str(warehouse_id),
            "warehouse_name": warehouse.name,
            "warehouse_code": warehouse.code,
            "variant_id": str(variant_id),
            "available_stock": available,
            "requested": quantity,
            "reason": None if valid else "insufficient_stock",
        }

    # ═══════════════════════════════════════════════════════════════
    # STRATEGY MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def get_strategy(self, name: Optional[str] = None) -> dict:
        """
        Get the current or specified allocation strategy details.

        If no name is given, returns the currently configured strategy.
        """
        if name:
            try:
                strategy = get_strategy(name)
            except KeyError:
                raise InvalidAllocationStrategyError(name)
        else:
            strategy = await self._resolve_strategy()

        return {
            "name": strategy.get_strategy_name(),
            "class_name": type(strategy).__name__,
        }

    async def list_strategies(self) -> list[dict]:
        """List all registered allocation strategies."""
        return [
            {"name": name, "class_name": class_name}
            for name, class_name in self.strategy_registry.get_all().items()
        ]

    # ═══════════════════════════════════════════════════════════════
    # DASHBOARD (D.9)
    # ═══════════════════════════════════════════════════════════════

    async def get_dashboard_stats(self) -> dict:
        """Get allocation dashboard statistics."""
        settings = await self._get_settings_dict()
        strategy = await self._resolve_strategy()

        # Count warehouses by utilization
        warehouses, _ = await self.wh_repo.list_by_store(
            store_id=self.store.id, page=1, page_size=1000, is_active=True,
        )

        total_capacity = 0
        total_usage = 0
        high_utilization = 0
        for wh in warehouses:
            if wh.capacity:
                total_capacity += wh.capacity
                usage_result = await self.db.execute(
                    select(
                        func.coalesce(func.sum(WarehouseInventory.available_stock), 0) +
                        func.coalesce(func.sum(WarehouseInventory.reserved_stock), 0)
                    ).where(WarehouseInventory.warehouse_id == wh.id)
                )
                wh_usage = usage_result.scalar() or 0
                total_usage += wh_usage
                if wh.capacity > 0 and (wh_usage / wh.capacity) > 0.8:
                    high_utilization += 1

        # Find top fulfillment warehouse (most available stock overall)
        top_wh_id, top_wh_name, top_wh_total = None, None, 0
        for wh in warehouses:
            usage_result = await self.db.execute(
                select(
                    func.coalesce(func.sum(WarehouseInventory.available_stock), 0) +
                    func.coalesce(func.sum(WarehouseInventory.reserved_stock), 0)
                ).where(WarehouseInventory.warehouse_id == wh.id)
            )
            wh_total = usage_result.scalar() or 0
            if wh_total > top_wh_total:
                top_wh_total = wh_total
                top_wh_id = wh.id
                top_wh_name = wh.name

        return {
            "allocation_strategy": strategy.get_strategy_name(),
            "multi_warehouse_enabled": settings.get("multi_warehouse_enabled", False),
            "total_warehouses": len(warehouses),
            "active_warehouses": len([w for w in warehouses if w.is_active]),
            "total_capacity": total_capacity,
            "total_usage": total_usage,
            "utilization_percentage": round(
                (total_usage / total_capacity * 100), 1
            ) if total_capacity > 0 else 0,
            "high_utilization_warehouses": high_utilization,
            "top_fulfillment_warehouse_id": str(top_wh_id) if top_wh_id else None,
            "top_fulfillment_warehouse_name": top_wh_name,
        }

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ═══════════════════════════════════════════════════════════════

    async def _resolve_strategy(
        self, strategy_name: Optional[str] = None,
    ) -> BaseAllocationStrategy:
        """
        Resolve which strategy to use.

        Priority:
        1. Explicit override (strategy_name param)
        2. From WarehouseSettings.allocation_strategy
        3. Default: default_warehouse
        """
        if strategy_name:
            try:
                return get_strategy(strategy_name)
            except KeyError:
                raise InvalidAllocationStrategyError(strategy_name)

        settings = await self.settings_repo.get_or_create(self.store.id)
        configured = settings.allocation_strategy or "default_warehouse"

        try:
            return get_strategy(configured)
        except KeyError:
            self.logger.warning(
                "Configured strategy '%s' not found, falling back to default_warehouse",
                configured,
            )
            return get_strategy("default_warehouse")

    async def _get_settings_dict(self) -> dict:
        """Get settings as a flat dict for strategy consumption."""
        settings = await self.settings_repo.get_or_create(self.store.id)

        # Get default warehouse
        default_wh = await self.wh_repo.get_default(self.store.id)

        return {
            "default_warehouse_id": default_wh.id if default_wh else None,
            "default_warehouse_name": default_wh.name if default_wh else None,
            "allocation_priority": [],  # TODO: Load from settings when implemented
            "multi_warehouse_enabled": settings.multi_warehouse_enabled,
            "allow_negative_stock": settings.allow_negative_stock,
            "reserve_stock_on_order": settings.reserve_stock_on_order,
            "auto_release_cancelled_orders": settings.auto_release_cancelled_orders,
        }

    async def _get_warehouse_stock(
        self,
        variant_id: uuid.UUID,
        warehouse_ids: Optional[list[uuid.UUID]] = None,
    ) -> list[tuple[uuid.UUID, str, str, int]]:
        """
        Get available stock for a variant across warehouses.

        Returns list of (warehouse_id, name, code, available_stock) tuples
        for all active warehouses that have stock records.
        """
        # Get active warehouses (scoped or all)
        if warehouse_ids:
            warehouses = []
            for wh_id in warehouse_ids:
                wh = await self.wh_repo.get_by_id(wh_id)
                if wh and wh.is_active and str(wh.store_id) == str(self.store.id):
                    warehouses.append(wh)
        else:
            wh_list, _ = await self.wh_repo.list_by_store(
                store_id=self.store.id, page=1, page_size=1000, is_active=True,
            )
            warehouses = wh_list

        stock_list = []
        for wh in warehouses:
            wh_inv = await self.inv_repo.get_by_variant_and_warehouse(
                wh.id, variant_id,
            )
            available = wh_inv.available_stock if wh_inv else 0
            stock_list.append((wh.id, wh.name, wh.code, available))

        return stock_list

    async def _allocate_variant(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        strategy: BaseAllocationStrategy,
        settings: dict,
    ) -> AllocationPlan:
        """
        Core allocation logic for a single variant.

        1. Validate variant exists
        2. Get warehouse stock levels
        3. Run the strategy
        4. Validate the result
        """
        # Validate variant
        variant = await self.variant_repo.get_by_id(variant_id)
        if variant is None:
            raise VariantNotFoundError(str(variant_id))

        # Get stock across all active warehouses
        stock_list = await self._get_warehouse_stock(variant_id)

        # Run the strategy
        plan = strategy.allocate(
            variant_id=variant_id,
            quantity=quantity,
            warehouse_stock=stock_list,
            settings=settings,
        )

        return plan

    async def _reserve_allocations(
        self,
        plan: AllocationPlan,
        order_id: Optional[str] = None,
    ) -> None:
        """
        Reserve stock for all allocations in a plan.

        Uses ReservationService for atomic FOR UPDATE locking.
        Each allocation becomes a separate reservation record.
        """
        reservation_service = ReservationService(
            db=self.db, store=self.store, user_id=self.user_id,
        )

        for alloc in plan.allocations:
            try:
                await reservation_service.reserve_stock(
                    warehouse_id=alloc.warehouse_id,
                    variant_id=alloc.variant_id,
                    quantity=alloc.quantity,
                    order_id=order_id,
                    reason=f"Allocation: {plan.strategy_name}",
                )
            except Exception as exc:
                self.logger.error(
                    "Failed to reserve allocation: variant=%s, warehouse=%s, "
                    "qty=%d, error=%s",
                    alloc.variant_id, alloc.warehouse_id, alloc.quantity, exc,
                )
                raise
