"""
WooCommerce Order Integration Service — Phase 5 (E.1–E.10).

Orchestrates the full order pipeline from WooCommerce order import
through allocation and reservation to inventory updates.

Pipeline:
WooCommerce Order → Order Sync → Allocation Engine → Reservation Engine → Store Inventory

Reuses existing services (store-centric):
- AllocationService.allocate_for_woocommerce()
- ReservationService (reserve, commit, release)
- StoreSettingsRepository (for store settings)

All failures in allocation/reservation logic are caught and logged —
WooCommerce sync always continues (E.6, E.10).
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Store
from app.inventory.constants import ReservationSource, ReservationStatus
from app.inventory.allocation_service import AllocationService
from app.inventory.allocation_strategies import AllocationItem
from app.inventory.reservation_service import ReservationService
from app.inventory.repository import StoreSettingsRepository
from app.woocommerce.models import WooCommerceStore, WooCommerceOrder, WooCommerceOrderItem
from app.woocommerce.constants import OrderStatus as WC_OrderStatus
from app.woocommerce.exceptions import (
    StoreNotFoundError, StoreInactiveError,
)

logger = logging.getLogger(__name__)


class WooCommerceOrderIntegrationService:
    """
    Orchestrates WooCommerce order → allocation → reservation → inventory.

    Each order flows through:
    1. Sync (existing, done by SyncEngine)
    2. Allocate (AllocationService.allocate_for_woocommerce)
    3. Reserve (ReservationService.reserve_stock)
    4. Status changes trigger commit/release

    All failures are isolated — WooCommerce sync never breaks.
    """

    def __init__(
        self,
        db: AsyncSession,
        wc_store: WooCommerceStore,
        store: Store,
        user_id: Optional[uuid.UUID] = None,
    ):
        self.db = db
        self.wc_store = wc_store
        self.store = store
        self.user_id = user_id
        self.allocation_service = AllocationService(
            db=db, store=store, user_id=user_id,
        )
        self.reservation_service = ReservationService(
            db=db, store=store, user_id=user_id,
        )
        self.settings_repo = StoreSettingsRepository(db)
        self.logger = logging.getLogger(f"{__name__}.WooCommerceOrderIntegrationService")

    # ═══════════════════════════════════════════════════════════════
    # E.1 — ORDER ALLOCATION (auto-call for WC orders)
    # ═══════════════════════════════════════════════════════════════

    async def allocate_order(
        self,
        order: WooCommerceOrder,
        strategy_name: Optional[str] = None,
    ) -> dict:
        """
        Allocate inventory for a WooCommerce order.

        Flow:
        1. Check StoreSettings.reserve_stock_on_order (E.4)
        2. Build allocation items from order line items
        3. Call AllocationService.allocate_for_woocommerce()
        4. Return allocation summary

        Never raises — logs and returns failure summary on error.
        """
        settings = await self.settings_repo.get_or_create(self.store.id)
        if not settings.reserve_stock_on_order:
            self.logger.info(
                "Skipping allocation for order %s: reserve_stock_on_order=False",
                order.number,
            )
            return self._order_result(order, "skipped", "reserve_stock_on_order_disabled")

        try:
            # Build allocation items from order line items
            items = []
            for line_item in order.items:
                if line_item.quantity > 0 and line_item.sku:
                    # Find inventory variant by SKU
                    variant = await self._find_inventory_variant(line_item.sku)
                    if variant:
                        items.append(AllocationItem(
                            variant_id=variant.id,
                            quantity=line_item.quantity,
                        ))
                    else:
                        self.logger.warning(
                            "No inventory variant found for SKU %s (order %s)",
                            line_item.sku, order.number,
                        )

            if not items:
                return self._order_result(order, "no_items", "no_allocatable_items")

            # Call allocation engine
            order_id = str(order.wc_order_id)
            result = await self.allocation_service.allocate_for_woocommerce(
                items=items,
                order_id=order_id,
                strategy_name=strategy_name,
            )

            # Enrich with order info
            result["order_number"] = order.number
            result["order_status"] = order.status.value

            self.logger.info(
                "Order %s allocated: %d/%d items fulfilled across %d SKUs",
                order.number,
                result.get("total_fulfilled", 0),
                result.get("total_requested", 0),
                len(result.get("items", [])),
            )

            return result

        except Exception as exc:
            self.logger.error(
                "Allocation failed for order %s: %s — WooCommerce sync continues",
                order.number, exc,
            )
            return self._order_result(
                order, "allocation_failed", str(exc),
            )

    # ═══════════════════════════════════════════════════════════════
    # E.3 — ORDER STATUS EVENTS
    # ═══════════════════════════════════════════════════════════════

    async def handle_order_status_change(
        self,
        order: WooCommerceOrder,
        previous_status: Optional[str] = None,
    ) -> dict:
        """
        Handle WooCommerce order status changes (E.3).

        Status → Action mapping:
        - pending → reserve_stock (if not already)
        - processing → keep active
        - completed → commit reservation
        - cancelled → release reservation
        - refunded → release reservation (configurable)
        - failed → release reservation

        Respects StoreSettings (E.4):
        - auto_release_cancelled_orders
        - allow_negative_stock
        """
        settings = await self.settings_repo.get_or_create(self.store.id)
        order_id = str(order.wc_order_id)

        if order.status == WC_OrderStatus.PENDING:
            # Already handled by allocate_order — ensure reservation exists
            reservations = await self.reservation_service.repo.get_by_order(
                self.store.id, order_id,
            )
            if not reservations:
                return await self.allocate_order(order)
            return self._order_result(order, "already_reserved")

        elif order.status == WC_OrderStatus.PROCESSING:
            # Keep active — check reservations exist
            reservations = await self.reservation_service.repo.get_by_order(
                self.store.id, order_id,
            )
            return self._order_result(
                order, "active",
                f"{len(reservations)} active reservations",
            )

        elif order.status == WC_OrderStatus.COMPLETED:
            return await self._commit_order_reservations(order, order_id)

        elif order.status == WC_OrderStatus.CANCELLED:
            if settings.auto_release_cancelled_orders:
                return await self._release_order_reservations(
                    order, order_id, "cancelled",
                )
            return self._order_result(order, "skipped", "auto_release_disabled")

        elif order.status == WC_OrderStatus.REFUNDED:
            # Configurable — default: release reservations
            return await self._release_order_reservations(
                order, order_id, "refunded",
            )

        elif order.status == WC_OrderStatus.FAILED:
            return await self._release_order_reservations(
                order, order_id, "failed",
            )

        else:
            self.logger.info(
                "Unhandled order status %s for order %s — no action taken",
                order.status.value, order.number,
            )
            return self._order_result(order, "no_action")

    # ═══════════════════════════════════════════════════════════════
    # E.6 — SYNC ENGINE INTEGRATION
    # ═══════════════════════════════════════════════════════════════

    async def process_synced_order(
        self,
        order: WooCommerceOrder,
    ) -> dict:
        """
        Process a synced order through the allocation pipeline.

        Called by SyncEngine after successfully syncing an order.
        Failures are caught — WooCommerce sync always continues.
        """
        try:
            # First, allocate
            allocation_result = await self.allocate_order(order)

            # Then handle status-based actions
            status_result = await self.handle_order_status_change(order)

            return {
                "order_number": order.number,
                "wc_order_id": order.wc_order_id,
                "allocation": allocation_result,
                "status_action": status_result,
            }
        except Exception as exc:
            self.logger.error(
                "Failed to process synced order %s: %s — sync continues",
                order.number, exc,
            )
            return self._order_result(order, "processing_failed", str(exc))

    # ═══════════════════════════════════════════════════════════════
    # E.7 — ORDER FULFILLMENT SUMMARY
    # ═══════════════════════════════════════════════════════════════

    async def get_fulfillment_summary(
        self,
        order: WooCommerceOrder,
    ) -> dict:
        """
        Get fulfillment status for an order (E.7, E.8).

        Returns:
        - allocated_qty: total units allocated
        - unallocated_qty: total units not yet allocated
        - location_count: number of fulfillment locations (1 for a store)
        - reservation_ids: list of reservation UUIDs
        - status: fully_allocated | partially_allocated | out_of_stock
        """
        order_id = str(order.wc_order_id)
        reservations = await self.reservation_service.repo.get_by_order(
            self.store.id, order_id,
        )

        total_qty = sum(item.quantity for item in order.items)
        allocated_qty = sum(r.quantity for r in reservations)
        unallocated_qty = total_qty - allocated_qty

        if allocated_qty >= total_qty:
            status = "fully_allocated"
        elif allocated_qty > 0:
            status = "partially_allocated"
        else:
            status = "out_of_stock"

        return {
            "order_number": order.number,
            "wc_order_id": order.wc_order_id,
            "total_quantity": total_qty,
            "allocated_quantity": allocated_qty,
            "unallocated_quantity": max(0, unallocated_qty),
            "location_count": 1 if allocated_qty > 0 else 0,
            "reservation_ids": [str(r.id) for r in reservations],
            "status": status,
        }

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL — Commit, Release, Rollback
    # ═══════════════════════════════════════════════════════════════

    async def _commit_order_reservations(
        self,
        order: WooCommerceOrder,
        order_id: str,
    ) -> dict:
        """Commit all active reservations for an order (E.9)."""
        reservations = await self.reservation_service.repo.get_by_order(
            self.store.id, order_id,
        )
        committed = 0
        errors = []

        for res in reservations:
            if res.status in (
                ReservationStatus.ACTIVE, ReservationStatus.PENDING,
            ):
                try:
                    await self.reservation_service.commit_stock(res.id)
                    committed += 1
                except Exception as exc:
                    errors.append(str(exc))
                    self.logger.error(
                        "Failed to commit reservation %s for order %s: %s",
                        res.id, order.number, exc,
                    )

        return {
            "order_number": order.number,
            "action": "commit",
            "total_reservations": len(reservations),
            "committed": committed,
            "errors": errors,
        }

    async def _release_order_reservations(
        self,
        order: WooCommerceOrder,
        order_id: str,
        reason: str,
    ) -> dict:
        """Release all active reservations for an order (E.9, E.10)."""
        try:
            released = await self.reservation_service.cancel_order(order_id)
            return {
                "order_number": order.number,
                "action": "release",
                "reason": reason,
                "reservations_released": len(released),
            }
        except Exception as exc:
            self.logger.error(
                "Failed to release reservations for order %s: %s",
                order.number, exc,
            )
            return {
                "order_number": order.number,
                "action": "release_failed",
                "reason": reason,
                "error": str(exc),
            }

    async def _find_inventory_variant(self, sku: str):
        """Find an inventory variant by SKU."""
        from app.models import ProductVariant
        result = await self.db.execute(
            select(ProductVariant).where(
                ProductVariant.sku == sku,
            ).limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _order_result(
        order: WooCommerceOrder,
        status: str,
        detail: str = "",
    ) -> dict:
        """Build a standardized order result dict."""
        return {
            "order_number": order.number,
            "wc_order_id": order.wc_order_id,
            "status": status,
            "detail": detail,
        }
