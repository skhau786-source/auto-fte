"""
Store-centric Allocation Engine.

In the SaaS inventory platform the store is a single inventory location.
Allocation therefore answers one question: can the store fulfill the
requested quantity from its available stock — and (optionally) it reserves
that stock for the order via the ReservationService.

The strategy framework is preserved for API compatibility and future
multi-location support, but every strategy resolves to the store's own
stock (single-location fulfillment).

Used by:
- WooCommerceOrderIntegrationService.allocate_order()
- app.inventory.allocation_router
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Store, ProductVariant, InventoryReservation
from app.inventory.constants import ReservationSource, ReservationStatus
from app.inventory.reservation_service import ReservationService
from app.inventory.allocation_strategies import (
    AllocationItem,
    AllocationItemResult,
    AllocationPlan,
    AVAILABLE_STRATEGIES,
)
from app.inventory.exceptions import (
    VariantNotFoundError,
    InvalidAllocationStrategyError,
)

logger = logging.getLogger(__name__)


class AllocationService:
    """Store-level inventory allocation orchestration."""

    def __init__(
        self,
        db: AsyncSession,
        store: Store,
        user_id: Optional[uuid.UUID] = None,
    ):
        self.db = db
        self.store = store
        self.user_id = user_id
        self.reservation_service = ReservationService(db=db, store=store, user_id=user_id)
        self.logger = logging.getLogger(f"{__name__}.AllocationService")

    # ═══════════════════════════════════════════════════════════════
    # ORDER ALLOCATION
    # ═══════════════════════════════════════════════════════════════

    async def allocate_for_woocommerce(
        self,
        items: list[AllocationItem],
        order_id: str,
        strategy_name: Optional[str] = None,
    ) -> dict:
        """Allocate (and reserve) inventory for a WooCommerce order."""
        return await self.allocate_order(
            items=items,
            order_id=order_id,
            strategy_name=strategy_name,
            auto_reserve=True,
            order_source=ReservationSource.WOOCOMMERCE,
        )

    async def allocate_order(
        self,
        items: list[AllocationItem],
        order_id: str,
        strategy_name: Optional[str] = None,
        auto_reserve: bool = True,
        order_source: ReservationSource = ReservationSource.MANUAL,
    ) -> dict:
        """
        Allocate inventory for an order.

        Each item is checked against the store's available stock. When
        `auto_reserve` is True, the fulfilled quantity is reserved through
        the ReservationService so the stock is locked for the order.

        Never raises on per-item failures — each item is fulfilled as far
        as possible and the outcome is reported in the response.
        """
        strategy = self._resolve_strategy(strategy_name)
        plan = AllocationPlan(strategy_name=strategy)
        reservation_ids: list[str] = []

        for item in items:
            result = await self._allocate_item(
                item=item,
                order_id=order_id,
                auto_reserve=auto_reserve,
                order_source=order_source,
            )
            if result.reservation_id:
                reservation_ids.append(str(result.reservation_id))
            plan.items.append(result)

        self.logger.info(
            "Allocated order %s: %d/%d units fulfilled (strategy=%s)",
            order_id, plan.total_fulfilled, plan.total_requested, strategy,
        )
        return self._plan_to_dict(plan, order_id=order_id, reservation_ids=reservation_ids)

    # ═══════════════════════════════════════════════════════════════
    # SINGLE-VARIANT ALLOCATION
    # ═══════════════════════════════════════════════════════════════

    async def allocate_variant(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        strategy_name: Optional[str] = None,
        auto_reserve: bool = True,
    ) -> AllocationPlan:
        """Allocate a single variant. Returns an AllocationPlan."""
        strategy = self._resolve_strategy(strategy_name)
        result = await self._allocate_item(
            item=AllocationItem(variant_id=variant_id, quantity=quantity),
            order_id=None,
            auto_reserve=auto_reserve,
            order_source=ReservationSource.MANUAL,
        )
        return AllocationPlan(strategy_name=strategy, items=[result])

    async def preview_allocation(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        strategy_name: Optional[str] = None,
    ) -> dict:
        """Preview allocation for a variant — no side effects."""
        variant = await self._get_variant(variant_id)
        if variant is None:
            raise VariantNotFoundError(str(variant_id))

        available = variant.inventory_quantity
        fulfilled = min(quantity, available)

        return {
            "variant_id": str(variant_id),
            "requested_quantity": quantity,
            "available_quantity": available,
            "fulfilled_quantity": fulfilled,
            "unfulfilled_quantity": quantity - fulfilled,
            "status": (
                "fulfilled" if fulfilled >= quantity
                else "partial" if fulfilled > 0
                else "out_of_stock"
            ),
            "strategy": self._resolve_strategy(strategy_name),
            "allocations": [
                {
                    "location": str(self.store.id),
                    "quantity": fulfilled,
                    "available_after": available - fulfilled,
                }
            ],
        }

    async def validate_allocation(
        self,
        variant_id: uuid.UUID,
        quantity: int,
    ) -> dict:
        """Validate that the store can fulfill a quantity for a variant."""
        variant = await self._get_variant(variant_id)
        if variant is None:
            raise VariantNotFoundError(str(variant_id))

        available = variant.inventory_quantity
        sufficient = available >= quantity
        return {
            "variant_id": str(variant_id),
            "requested_quantity": quantity,
            "available_quantity": available,
            "sufficient": sufficient,
            "message": "Sufficient stock available" if sufficient
                       else f"Only {available} units available",
        }

    # ═══════════════════════════════════════════════════════════════
    # STRATEGIES & DASHBOARD
    # ═══════════════════════════════════════════════════════════════

    async def list_strategies(self) -> list[dict]:
        """List available allocation strategies."""
        return list(AVAILABLE_STRATEGIES)

    async def get_strategy(self) -> dict:
        """Get the store's active allocation strategy."""
        name = await self._get_active_strategy()
        description = next(
            (s["description"] for s in AVAILABLE_STRATEGIES if s["name"] == name),
            "Fulfill from the store's available stock.",
        )
        return {"name": name, "description": description}

    async def get_dashboard_stats(self) -> dict:
        """Allocation statistics for dashboards."""
        conditions = [InventoryReservation.store_id == self.store.id]
        active_statuses = [
            ReservationStatus.ACTIVE, ReservationStatus.PENDING,
            ReservationStatus.COMMITTED,
        ]

        allocated_result = await self.db.execute(
            select(func.coalesce(func.sum(InventoryReservation.quantity), 0)).where(
                *conditions,
                InventoryReservation.status.in_(active_statuses),
            )
        )
        total_allocated_units = allocated_result.scalar() or 0

        active_result = await self.db.execute(
            select(func.count(InventoryReservation.id)).where(
                *conditions,
                InventoryReservation.status.in_(
                    [ReservationStatus.ACTIVE, ReservationStatus.PENDING]
                ),
            )
        )
        active_reservations = active_result.scalar() or 0

        orders_result = await self.db.execute(
            select(func.count(func.distinct(InventoryReservation.order_id))).where(
                *conditions,
                InventoryReservation.order_id.is_not(None),
            )
        )
        orders_allocated = orders_result.scalar() or 0

        return {
            "allocation_strategy": await self._get_active_strategy(),
            "total_allocated_units": total_allocated_units,
            "active_reservations": active_reservations,
            "orders_allocated": orders_allocated,
            "allocation_success_rate": 100.0,
        }

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ═══════════════════════════════════════════════════════════════

    async def _allocate_item(
        self,
        item: AllocationItem,
        order_id: Optional[str],
        auto_reserve: bool,
        order_source: ReservationSource,
    ) -> AllocationItemResult:
        variant = await self._get_variant(item.variant_id)
        if variant is None:
            self.logger.warning("Allocation: variant %s not found", item.variant_id)
            return AllocationItemResult(
                variant_id=item.variant_id,
                requested_quantity=item.quantity,
            )

        available = variant.inventory_quantity
        fulfilled = min(item.quantity, available)
        reservation_id = None

        if auto_reserve and fulfilled > 0:
            try:
                reservation = await self.reservation_service.reserve_stock(
                    variant_id=item.variant_id,
                    quantity=fulfilled,
                    order_id=order_id,
                    order_source=order_source,
                )
                reservation_id = reservation.id
            except Exception as exc:
                self.logger.error(
                    "Reservation failed for variant %s (qty %d): %s",
                    item.variant_id, fulfilled, exc,
                )
                fulfilled = 0

        return AllocationItemResult(
            variant_id=item.variant_id,
            requested_quantity=item.quantity,
            fulfilled_quantity=fulfilled,
            available_quantity=available,
            reservation_id=reservation_id,
        )

    async def _get_variant(self, variant_id: uuid.UUID) -> Optional[ProductVariant]:
        result = await self.db.execute(
            select(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .where(ProductVariant.id == variant_id)
        )
        return result.scalar_one_or_none()

    async def _get_active_strategy(self) -> str:
        """Read the store's configured allocation strategy (default: 'default')."""
        from app.models import StoreSettings
        try:
            result = await self.db.execute(
                select(StoreSettings).where(StoreSettings.store_id == self.store.id)
            )
            settings = result.scalar_one_or_none()
            return settings.allocation_strategy if settings else "default"
        except Exception as exc:
            self.logger.debug("Failed to read store settings: %s", exc)
            return "default"

    def _resolve_strategy(self, strategy_name: Optional[str]) -> str:
        name = strategy_name or "default"
        if name not in {s["name"] for s in AVAILABLE_STRATEGIES}:
            raise InvalidAllocationStrategyError(name)
        return name

    @staticmethod
    def _plan_to_dict(
        plan: AllocationPlan,
        order_id: str,
        reservation_ids: list[str],
    ) -> dict:
        return {
            "order_id": order_id,
            "strategy_used": plan.strategy_name,
            "total_items": len(plan.items),
            "total_requested": plan.total_requested,
            "total_fulfilled": plan.total_fulfilled,
            "total_unfulfilled": plan.total_unfulfilled,
            "fully_fulfilled": plan.is_fully_fulfilled,
            "partial": plan.partial,
            "status": plan.status,
            "reservation_ids": reservation_ids,
            "items": [
                {
                    "variant_id": str(i.variant_id),
                    "requested_quantity": i.requested_quantity,
                    "fulfilled_quantity": i.fulfilled_quantity,
                    "available_quantity": i.available_quantity,
                    "status": i.status,
                    "reservation_id": str(i.reservation_id) if i.reservation_id else None,
                }
                for i in plan.items
            ],
        }
