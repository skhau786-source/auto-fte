"""
Unified Dashboard Service — Phase 7.

Orchestrates all 6 completed phases' services to produce a single
comprehensive dashboard response. Each phase's service is called
independently (parallel-safe) and aggregated into the unified response.

Phases:
- Phase 1: InventoryService.get_dashboard()
- Phase 2: WarehouseDashboardService.get_summary()
- Phase 3: ReservationService.get_dashboard_stats()
- Phase 4: AllocationService.get_dashboard_stats()
- Phase 5: OrderIntegrationService.get_dashboard_stats()
- Phase 6: InventoryAggregationEngine.get_dashboard()
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Store
from app.dashboard.unified_schema import (
    UnifiedDashboardResponse,
    InventorySummaryWidget,
    WarehouseSummaryWidget,
    ReservationSummaryWidget,
    AllocationSummaryWidget,
    OrderIntegrationSummaryWidget,
    AggregationSummaryWidget,
    WarehouseUtilizationItem,
)
from app.dashboard.dashboard_service import DashboardService
from app.warehouse.aggregation_service import WarehouseDashboardService
from app.warehouse.reservation_service import ReservationService
from app.warehouse.allocation_service import AllocationService
from app.warehouse.aggregation_engine import InventoryAggregationEngine
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

        # ── Phase 2: Warehouse Summary ──
        try:
            wh_summary = await self._get_warehouse_summary()
        except Exception:
            wh_summary = WarehouseSummaryWidget()

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
            warehouse=wh_summary,
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
    # Phase 2 — Warehouse Summary
    # ═══════════════════════════════════════════════════════════════

    async def _get_warehouse_summary(self) -> WarehouseSummaryWidget:
        """Get warehouse metrics from WarehouseDashboardService."""
        try:
            svc = WarehouseDashboardService(db=self.db, store=self.store)
            summary = await svc.get_summary()

            # Get default warehouse name
            from app.warehouse.service import WarehouseService
            wh_svc = WarehouseService(db=self.db, store=self.store)
            default_wh = await wh_svc.get_default_warehouse()
            default_name = default_wh.name if default_wh else None

            return WarehouseSummaryWidget(
                total_warehouses=summary.get("total_warehouses", 0),
                active_warehouses=summary.get("active_warehouses", 0),
                total_capacity=summary.get("total_capacity", 0),
                total_used_capacity=summary.get("total_used_capacity", 0),
                capacity_usage_percentage=summary.get("capacity_usage_percentage", 0.0),
                pending_transfers=summary.get("pending_transfers", 0),
                in_transit_transfers=summary.get("in_transit_transfers", 0),
                low_stock_warehouse_items=summary.get("low_stock_items", 0),
                default_warehouse_name=default_name,
            )
        except Exception as exc:
            self.logger.warning("Warehouse summary failed: %s", exc)
            return WarehouseSummaryWidget()

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

            # Build warehouse utilization items
            utilization = []
            # The dashboard stats includes per-warehouse capacities
            # We enrich with capacity data from the capacity service if available
            try:
                from app.warehouse.service import CapacityService
                cap_svc = CapacityService(db=self.db, store=self.store)
                caps = await cap_svc.get_all_capacities()
                for cap in caps:
                    utilization.append(WarehouseUtilizationItem(
                        warehouse_id=str(cap.get("warehouse_id", "")),
                        warehouse_name=cap.get("warehouse_name", "Unknown"),
                        capacity=cap.get("capacity"),
                        current_usage=cap.get("current_usage", 0),
                        usage_percentage=cap.get("usage_percentage"),
                        status=cap.get("status", "normal"),
                    ))
            except Exception:
                pass

            return AllocationSummaryWidget(
                allocation_strategy=stats.get("allocation_strategy", "default_warehouse"),
                multi_warehouse_enabled=stats.get("multi_warehouse_enabled", False),
                total_warehouses=stats.get("total_warehouses", 0),
                active_warehouses=stats.get("active_warehouses", 0),
                total_capacity=stats.get("total_capacity", 0),
                total_usage=stats.get("total_usage", 0),
                utilization_percentage=stats.get("utilization_percentage", 0.0),
                high_utilization_warehouses=stats.get("high_utilization_warehouses", 0),
                top_fulfillment_warehouse_name=stats.get("top_fulfillment_warehouse_name"),
                warehouse_utilization=utilization,
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
                total_incoming_inventory=dash.get("total_incoming_inventory", 0),
                total_damaged_inventory=dash.get("total_damaged_inventory", 0),
                inventory_value=dash.get("inventory_value", 0.0),
                warehouse_count=dash.get("warehouse_count", 0),
                active_reservations_count=dash.get("active_reservations", 0),
                transfer_in_transit_count=dash.get("transfer_in_transit_count", 0),
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

