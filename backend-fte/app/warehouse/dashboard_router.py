"""
Dashboard & Analytics Router for the Warehouse Management module.

Provides aggregated warehouse data endpoints for the frontend dashboard.
All business logic lives in WarehouseDashboardService.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent, Store

from app.inventory.dependencies import get_store_for_user
from app.warehouse.aggregation_service import WarehouseDashboardService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/warehouse-dashboard", tags=["Warehouse Dashboard"])


async def _get_dashboard_service(
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store_for_user),
) -> WarehouseDashboardService:
    return WarehouseDashboardService(db=db, store=store)


@router.get(
    "/summary",
    summary="Get warehouse summary for dashboard",
)
async def get_summary(
    service: WarehouseDashboardService = Depends(_get_dashboard_service),
):
    """Get high-level warehouse summary for the dashboard."""
    return await service.get_summary()


@router.get(
    "/stock-distribution",
    summary="Get stock distribution across warehouses",
)
async def get_stock_distribution(
    service: WarehouseDashboardService = Depends(_get_dashboard_service),
):
    """Get stock distribution across all warehouses."""
    return await service.get_stock_distribution()


@router.get(
    "/recent-transfers",
    summary="Get recent transfer activity",
)
async def get_recent_transfers(
    limit: int = Query(10, ge=1, le=50),
    service: WarehouseDashboardService = Depends(_get_dashboard_service),
):
    """Get recent warehouse transfer activity."""
    return await service.get_recent_transfers(limit=limit)


@router.get(
    "/inventory-value",
    summary="Get inventory value across warehouses",
)
async def get_inventory_value(
    service: WarehouseDashboardService = Depends(_get_dashboard_service),
):
    """Get total inventory value across all warehouses."""
    return await service.get_inventory_value()


@router.get(
    "/warehouse-activity",
    summary="Get warehouse activity",
)
async def get_warehouse_activity(
    days: int = Query(7, ge=1, le=30),
    service: WarehouseDashboardService = Depends(_get_dashboard_service),
):
    """Get recent activity across all warehouses."""
    return await service.get_warehouse_activity(days=days)


@router.get(
    "/low-stock",
    summary="Get low stock report across warehouses",
)
async def get_low_stock_report(
    threshold: int = Query(10, ge=0),
    service: WarehouseDashboardService = Depends(_get_dashboard_service),
):
    """Get comprehensive low stock report across all warehouses."""
    return await service.get_low_stock_report(threshold=threshold)
