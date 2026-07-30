"""
API Router for WooCommerce Order Integration — Phase 5 (E.12).

Endpoints:
  GET    /orders/{id}/allocation      — Get order allocation summary
  GET    /orders/{id}/reservations    — Get order reservations
  POST   /orders/{id}/allocate         — Allocate inventory for an order
  POST   /orders/{id}/commit           — Commit all reservations
  POST   /orders/{id}/release          — Release all reservations
  GET    /orders/dashboard             — Order integration dashboard

Thin router layer — all business logic in WooCommerceOrderIntegrationService.
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent, Store

from app.inventory.dependencies import get_store_for_user
from app.warehouse.reservation_service import ReservationService

from app.woocommerce.order_integration_service import WooCommerceOrderIntegrationService
from app.woocommerce.models import WooCommerceOrder, WooCommerceStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orders", tags=["WooCommerce Order Integration"])


# ═══════════════════════════════════════════════════════════════════
# Dependencies
# ═══════════════════════════════════════════════════════════════════


async def _get_wc_store(db: AsyncSession = Depends(get_db)) -> WooCommerceStore:
    """Get the first active WooCommerce store (simplified — extend for multi-store)."""
    result = await db.execute(
        select(WooCommerceStore).where(
            WooCommerceStore.is_active == True,  # noqa: E712
        ).limit(1)
    )
    store = result.scalar_one_or_none()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "No active WooCommerce store found"},
        )
    return store


async def _get_wc_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
) -> WooCommerceOrder:
    """Get a WooCommerce order by its ID or number."""
    # Try by wc_order_id (int)
    try:
        wc_id = int(order_id)
        result = await db.execute(
            select(WooCommerceOrder).where(
                WooCommerceOrder.wc_order_id == wc_id,
            ).limit(1)
        )
        order = result.scalar_one_or_none()
        if order:
            return order
    except ValueError:
        pass

    # Try by UUID
    try:
        uid = uuid.UUID(order_id)
        result = await db.execute(
            select(WooCommerceOrder).where(WooCommerceOrder.id == uid).limit(1)
        )
        order = result.scalar_one_or_none()
        if order:
            return order
    except ValueError:
        pass

    # Try by order number
    result = await db.execute(
        select(WooCommerceOrder).where(
            WooCommerceOrder.number == order_id,
        ).limit(1)
    )
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"Order not found: {order_id}"},
        )
    return order


async def _get_integration_service(
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store_for_user),
    user: RegisteredStudent = Depends(get_current_user),
    wc_store: WooCommerceStore = Depends(_get_wc_store),
) -> WooCommerceOrderIntegrationService:
    """Build integration service with resolved dependencies."""
    return WooCommerceOrderIntegrationService(
        db=db, wc_store=wc_store, store=store, user_id=user.id,
    )


# ═══════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "/{order_id}/allocation",
    summary="Get order allocation summary",
)
async def get_order_allocation(
    order: WooCommerceOrder = Depends(_get_wc_order),
    service: WooCommerceOrderIntegrationService = Depends(_get_integration_service),
):
    """Get the fulfillment/allocation summary for an order."""
    return await service.get_fulfillment_summary(order)


@router.get(
    "/{order_id}/reservations",
    summary="Get order reservations",
)
async def get_order_reservations(
    order: WooCommerceOrder = Depends(_get_wc_order),
    service: WooCommerceOrderIntegrationService = Depends(_get_integration_service),
):
    """Get all reservations for an order."""
    from app.warehouse.schemas import ReservationOut
    order_id = str(order.wc_order_id)
    reservations = await service.reservation_service.repo.get_by_order(
        service.store.id, order_id,
    )
    return [
        {
            "id": r.id,
            "warehouse_id": r.warehouse_id,
            "variant_id": r.variant_id,
            "quantity": r.quantity,
            "status": r.status.value if hasattr(r.status, 'value') else str(r.status),
            "created_at": r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at),
        }
        for r in reservations
    ]


@router.post(
    "/{order_id}/allocate",
    summary="Allocate inventory for an order",
)
async def allocate_order(
    order: WooCommerceOrder = Depends(_get_wc_order),
    strategy_name: Optional[str] = Query(None),
    service: WooCommerceOrderIntegrationService = Depends(_get_integration_service),
):
    """Allocate inventory for a WooCommerce order using the allocation engine."""
    result = await service.allocate_order(
        order=order,
        strategy_name=strategy_name,
    )
    if result.get("status") == "allocation_failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result,
        )
    return result


@router.post(
    "/{order_id}/commit",
    summary="Commit all reservations for an order",
)
async def commit_order(
    order: WooCommerceOrder = Depends(_get_wc_order),
    service: WooCommerceOrderIntegrationService = Depends(_get_integration_service),
):
    """Commit all active reservations for an order (mark as fulfilled)."""
    order_id = str(order.wc_order_id)
    result = await service._commit_order_reservations(order, order_id)
    return result


@router.post(
    "/{order_id}/release",
    summary="Release all reservations for an order",
)
async def release_order(
    order: WooCommerceOrder = Depends(_get_wc_order),
    reason: str = Query("manual", description="Reason for release"),
    service: WooCommerceOrderIntegrationService = Depends(_get_integration_service),
):
    """Release all active reservations for an order (return stock to available)."""
    order_id = str(order.wc_order_id)
    result = await service._release_order_reservations(order, order_id, reason)
    return result


@router.get(
    "/dashboard",
    summary="Order integration dashboard",
)
async def order_dashboard(
    service: WooCommerceOrderIntegrationService = Depends(_get_integration_service),
):
    """Get order integration dashboard statistics."""
    # Reuse existing reservation and allocation dashboard data
    reservation_stats = await service.reservation_service.get_dashboard_stats()
    allocation_stats = await service.allocation_service.get_dashboard_stats()

    # Count orders by allocation status
    from app.woocommerce.models import WooCommerceOrder
    from app.woocommerce.constants import OrderStatus
    from sqlalchemy import func, select as sel

    total_orders_result = await service.db.execute(
        sel(func.count(WooCommerceOrder.id)).where(
            WooCommerceOrder.store_id == service.wc_store.id,
        )
    )
    total_orders = total_orders_result.scalar() or 0

    # Count by status
    pending_result = await service.db.execute(
        sel(func.count(WooCommerceOrder.id)).where(
            WooCommerceOrder.store_id == service.wc_store.id,
            WooCommerceOrder.status == OrderStatus.PENDING,
        )
    )
    processing_result = await service.db.execute(
        sel(func.count(WooCommerceOrder.id)).where(
            WooCommerceOrder.store_id == service.wc_store.id,
            WooCommerceOrder.status == OrderStatus.PROCESSING,
        )
    )
    completed_result = await service.db.execute(
        sel(func.count(WooCommerceOrder.id)).where(
            WooCommerceOrder.store_id == service.wc_store.id,
            WooCommerceOrder.status == OrderStatus.COMPLETED,
        )
    )
    cancelled_result = await service.db.execute(
        sel(func.count(WooCommerceOrder.id)).where(
            WooCommerceOrder.store_id == service.wc_store.id,
            WooCommerceOrder.status == OrderStatus.CANCELLED,
        )
    )

    return {
        "total_orders": total_orders,
        "orders_waiting_allocation": pending_result.scalar() or 0,
        "orders_processing": processing_result.scalar() or 0,
        "orders_completed": completed_result.scalar() or 0,
        "orders_cancelled": cancelled_result.scalar() or 0,
        "reservations": {
            "active_reservations": reservation_stats.get("active_reservations", 0),
            "reserved_stock_units": reservation_stats.get("reserved_stock_units", 0),
            "reservation_success_rate": reservation_stats.get("reservation_success_rate", 0),
            "expired_today": reservation_stats.get("expired_today", 0),
        },
        "allocation": {
            "allocation_strategy": allocation_stats.get("allocation_strategy", ""),
            "multi_warehouse_enabled": allocation_stats.get("multi_warehouse_enabled", False),
            "total_warehouses": allocation_stats.get("total_warehouses", 0),
        },
    }
