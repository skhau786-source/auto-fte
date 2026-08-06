"""
Unified Dashboard Service — Phase 7.

Orchestrates all active phases' services to produce a single
comprehensive dashboard response. Each phase's service is called
independently (parallel-safe) and aggregated into the unified response.

Phases:
- Phase 1: InventoryService.get_dashboard()
- Phase 3: ReservationService.get_dashboard_stats()
- Phase 4: AllocationService.get_dashboard_stats()
- Phase 5: OrderIntegrationService.get_dashboard_stats()
- Phase 6: InventoryAggregationEngine.get_dashboard()

Store-centric: the former Phase 2 workspace summary widget was removed
in the SaaS platform pivot.
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Store
from app.dashboard.unified_schema import (
    UnifiedDashboardResponse,
    InventorySummaryWidget,
    ReservationSummaryWidget,
    AllocationSummaryWidget,
    OrderIntegrationSummaryWidget,
    AggregationSummaryWidget,
)
from app.dashboard.dashboard_service import DashboardService
from app.inventory.reservation_service import ReservationService
from app.inventory.allocation_service import AllocationService
from app.inventory.aggregation_engine import InventoryAggregationEngine
from sqlalchemy import select

logger = logging.getLogger(__name__)


class UnifiedDashboardService:
    """Builds a unified dashboard by calling all phase-specific services."""

    def __init__(
        self,
        db: AsyncSession,
        store: Store,
        user_id: Optional[uuid.UUID] = None,
    ):
        self.db = db
        self.store = store
        self.user_id = user_id
        self.logger = logging.getLogger(f"{__name__}.UnifiedDashboardService")

    async def get_dashboard(self) -> UnifiedDashboardResponse:
        """Fetch all dashboard sections in parallel and combine."""
        try:
            return await self._build_all()
        except Exception as exc:
            self.logger.error("Unified dashboard build failed: %s", exc)
            return self._empty_response()

    async def _build_all(self) -> UnifiedDashboardResponse:
        """Build all dashboard sections. Each section is independent.

        Each phase getter is wrapped in try/except so that a single
        phase failure does not prevent other phases from rendering.
        """
        # ── Phase 1: Inventory Summary ──
        try:
            inv_summary = await self._get_inventory_summary()
        except Exception:
            inv_summary = InventorySummaryWidget()

        # ── Phase 3: Reservation Summary ──
        try:
            res_summary = await self._get_reservation_summary()
        except Exception:
            res_summary = ReservationSummaryWidget()

        # ── Phase 4: Allocation Summary ──
        try:
            alloc_summary = await self._get_allocation_summary()
        except Exception:
            alloc_summary = AllocationSummaryWidget()

        # ── Phase 5: Order Integration Summary ──
        try:
            order_summary = await self._get_order_integration_summary()
        except Exception:
            order_summary = OrderIntegrationSummaryWidget()

        # ── Phase 6: Aggregation Summary ──
        try:
            agg_summary = await self._get_aggregation_summary()
        except Exception:
            agg_summary = AggregationSummaryWidget()

        return UnifiedDashboardResponse(
            store_id=str(self.store.id),
            generated_at=datetime.now(timezone.utc),
            inventory=inv_summary,
            reservation=res_summary,
            allocation=alloc_summary,
            order_integration=order_summary,
            aggregation=agg_summary,
        )

    # ═══════════════════════════════════════════════════════════════
    # Phase 1 — Inventory Summary
    # ═══════════════════════════════════════════════════════════════

    async def _get_inventory_summary(self) -> InventorySummaryWidget:
        """Get inventory metrics from DashboardService."""
        try:
            svc = DashboardService(db=self.db, store=self.store)
            dash = await svc.get_dashboard()

            inv = dash.inventory_summary
            return InventorySummaryWidget(
                total_products=inv.total_products,
                total_variants=inv.total_variants,
                total_inventory_units=inv.total_inventory_units,
                total_inventory_value=inv.total_inventory_value,
                low_stock_count=inv.low_stock_count,
                out_of_stock_count=inv.out_of_stock_count,
                category_count=inv.category_count,
            )
        except Exception as exc:
            self.logger.warning("Inventory summary failed: %s", exc)
            return InventorySummaryWidget()

    # ═══════════════════════════════════════════════════════════════
    # Phase 3 — Reservation Summary
    # ═══════════════════════════════════════════════════════════════

    async def _get_reservation_summary(self) -> ReservationSummaryWidget:
        """Get reservation metrics from ReservationService."""
        try:
            svc = ReservationService(db=self.db, store=self.store, user_id=self.user_id)
            stats = await svc.get_dashboard_stats()

            return ReservationSummaryWidget(
                active_reservations=stats.get("active_reservations", 0),
                reserved_stock_units=stats.get("reserved_stock_units", 0),
                expired_today=stats.get("expired_today", 0),
                reservation_success_rate=stats.get("reservation_success_rate", 100.0),
                reservations_by_source=stats.get("reservations_by_source", {}),
            )
        except Exception as exc:
            self.logger.warning("Reservation summary failed: %s", exc)
            return ReservationSummaryWidget()

    # ═══════════════════════════════════════════════════════════════
    # Phase 4 — Allocation Summary
    # ═══════════════════════════════════════════════════════════════

    async def _get_allocation_summary(self) -> AllocationSummaryWidget:
        """Get allocation metrics from AllocationService."""
        try:
            svc = AllocationService(db=self.db, store=self.store, user_id=self.user_id)
            stats = await svc.get_dashboard_stats()

            return AllocationSummaryWidget(
                allocation_strategy=stats.get("allocation_strategy", "default"),
                total_allocated_units=stats.get("total_allocated_units", 0),
                active_reservations=stats.get("active_reservations", 0),
                orders_allocated=stats.get("orders_allocated", 0),
                allocation_success_rate=stats.get("allocation_success_rate", 100.0),
            )
        except Exception as exc:
            self.logger.warning("Allocation summary failed: %s", exc)
            return AllocationSummaryWidget()

    # ═══════════════════════════════════════════════════════════════
    # Phase 5 — Order Integration Summary
    # ═══════════════════════════════════════════════════════════════

    async def _get_order_integration_summary(self) -> OrderIntegrationSummaryWidget:
        """Get order integration metrics from WooCommerce order service."""
        try:
            from app.woocommerce.order_integration_service import (
                WooCommerceOrderIntegrationService,
            )
            from app.woocommerce.models import WooCommerceStore

            # Resolve WooCommerceStore from InventoryStore's owner_id
            wc_store_result = await self.db.execute(
                select(WooCommerceStore).where(
                    WooCommerceStore.owner_id == self.store.owner_id,
                ).limit(1)
            )
            wc_store = wc_store_result.scalar_one_or_none()

            if wc_store:
                svc = WooCommerceOrderIntegrationService(
                    db=self.db,
                    wc_store=wc_store,
                    store=self.store,
                    user_id=self.user_id,
                )
                stats = await svc.get_dashboard_stats()
                return OrderIntegrationSummaryWidget(
                    orders_waiting_allocation=stats.get("orders_waiting_allocation", 0),
                    reserved_orders=stats.get("reserved_orders", 0),
                    partially_fulfilled_orders=stats.get("partially_fulfilled_orders", 0),
                    committed_orders=stats.get("committed_orders", 0),
                    released_reservations=stats.get("released_reservations", 0),
                    allocation_success_rate=stats.get("allocation_success_rate", 100.0),
                    reservation_success_rate=stats.get("reservation_success_rate", 100.0),
                )
        except Exception as exc:
            self.logger.warning("Order integration summary failed: %s", exc)

        return OrderIntegrationSummaryWidget()

    # ═══════════════════════════════════════════════════════════════
    # Phase 6 — Aggregation Summary
    # ═══════════════════════════════════════════════════════════════

    async def _get_aggregation_summary(self) -> AggregationSummaryWidget:
        """Get aggregation metrics from InventoryAggregationEngine."""
        try:
            engine = InventoryAggregationEngine(
                db=self.db,
                store=self.store,
                user_id=self.user_id,
            )
            dash = await engine.get_dashboard()

            return AggregationSummaryWidget(
                total_available_inventory=dash.get("total_available_inventory", 0),
                total_reserved_inventory=dash.get("total_reserved_inventory", 0),
                inventory_value=dash.get("inventory_value", 0.0),
                low_stock_variants=dash.get("low_stock_variants", 0),
                out_of_stock_variants=dash.get("out_of_stock_variants", 0),
                active_reservations_count=dash.get("active_reservations", 0),
            )
        except Exception as exc:
            self.logger.warning("Aggregation summary failed: %s", exc)
            return AggregationSummaryWidget()

    # ═══════════════════════════════════════════════════════════════
    # Empty fallback
    # ═══════════════════════════════════════════════════════════════

    def _empty_response(self) -> UnifiedDashboardResponse:
        """Return an empty dashboard when everything fails."""
        return UnifiedDashboardResponse(
            store_id=str(self.store.id),
            generated_at=datetime.now(timezone.utc),
        )

