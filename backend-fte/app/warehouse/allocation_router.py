"""
API Router for the Warehouse Allocation Engine — Phase 4 (D.8).

Thin router layer — all business logic lives in AllocationService.
Follows the same patterns as the existing warehouse router.

Endpoints:
  GET    /allocation/settings       — Get allocation settings
  PUT    /allocation/settings       — Update allocation settings
  POST   /allocation/preview         — Preview allocation (no side effects)
  POST   /allocation/order           — Allocate for an entire order
  POST   /allocation/variant         — Allocate a single variant
  POST   /allocation/reallocate      — Reallocate between warehouses
  GET    /allocation/strategies      — List available strategies
  GET    /allocation/dashboard       — Allocation dashboard stats
  POST   /allocation/validate        — Validate allocation feasibility
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent, Store

from app.inventory.dependencies import get_store_for_user
from app.inventory.constants import AllocationStrategy as AllocationStrategyEnum

from app.warehouse.allocation_service import AllocationService
from app.warehouse.allocation_strategies import AllocationItem
from app.warehouse.schemas import (
    AllocationSettingsOut,
    AllocationOrderRequest, AllocationOrderResponse,
    AllocationVariantRequest, AllocationVariantResponse,
    AllocationPreviewResponse,
    AllocationReallocateRequest, AllocationReallocateResponse,
    AllocationValidateResponse, AllocationDashboardOut,
    AllocationStrategyOut, WarehouseSettingsUpdateRequest,
)
from app.warehouse.service import WarehouseService
from app.warehouse.exceptions import (
    AllocationError, AllocationFailedError,
    InvalidAllocationStrategyError,
    WarehouseNotFoundError, WarehouseInactiveError,
    WarehouseSettingsNotFoundError, WarehouseSettingsValidationError,
)
from app.inventory.exceptions import VariantNotFoundError, InvalidStoreOwnershipError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/allocation", tags=["Allocation"])


# ═══════════════════════════════════════════════════════════════════
# Error Mapping
# ═══════════════════════════════════════════════════════════════════

_EXCEPTION_TO_STATUS = {
    AllocationFailedError: status.HTTP_400_BAD_REQUEST,
    InvalidAllocationStrategyError: status.HTTP_400_BAD_REQUEST,
    WarehouseNotFoundError: status.HTTP_404_NOT_FOUND,
    WarehouseInactiveError: status.HTTP_400_BAD_REQUEST,
    VariantNotFoundError: status.HTTP_404_NOT_FOUND,
    WarehouseSettingsNotFoundError: status.HTTP_404_NOT_FOUND,
    WarehouseSettingsValidationError: status.HTTP_400_BAD_REQUEST,
    InvalidStoreOwnershipError: status.HTTP_403_FORBIDDEN,
}


def _handle_error(exc: Exception) -> None:
    """Convert a domain exception to the appropriate HTTP response."""
    status_code = _EXCEPTION_TO_STATUS.get(
        type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    detail = {"message": str(exc), "error_code": type(exc).__name__}
    if hasattr(exc, "detail") and exc.detail:
        detail["detail"] = exc.detail
    raise HTTPException(status_code=status_code, detail=detail)


# ═══════════════════════════════════════════════════════════════════
# Dependencies
# ═══════════════════════════════════════════════════════════════════


async def _get_allocation_service(
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store_for_user),
    user: RegisteredStudent = Depends(get_current_user),
) -> AllocationService:
    """Build AllocationService with resolved dependencies."""
    return AllocationService(db=db, store=store, user_id=user.id)


# ═══════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════


@router.get(
    "/settings",
    response_model=AllocationSettingsOut,
    summary="Get allocation settings",
)
async def get_allocation_settings(
    service: AllocationService = Depends(_get_allocation_service),
    warehouse_service: WarehouseService = Depends(
        lambda db=Depends(get_db), store=Depends(get_store_for_user),
               user=Depends(get_current_user): WarehouseService(db, store, user.id)
    ),
):
    """Get the current allocation configuration from WarehouseSettings."""
    try:
        settings = await warehouse_service.get_warehouse_settings()
        strategy = await service.get_strategy()
        return AllocationSettingsOut(
            **settings,
            active_strategy=strategy["name"],
            available_strategies=await service.list_strategies(),
        )
    except (WarehouseSettingsNotFoundError, WarehouseSettingsValidationError) as exc:
        _handle_error(exc)


@router.put(
    "/settings",
    response_model=AllocationSettingsOut,
    summary="Update allocation settings",
)
async def update_allocation_settings(
    payload: WarehouseSettingsUpdateRequest,
    service: AllocationService = Depends(_get_allocation_service),
    warehouse_service: WarehouseService = Depends(
        lambda db=Depends(get_db), store=Depends(get_store_for_user),
               user=Depends(get_current_user): WarehouseService(db, store, user.id)
    ),
):
    """Update allocation configuration settings."""
    try:
        settings = await warehouse_service.update_warehouse_settings(payload)
        return AllocationSettingsOut(**settings, available_strategies=await service.list_strategies())
    except (WarehouseSettingsNotFoundError, WarehouseSettingsValidationError,
            WarehouseNotFoundError, WarehouseInactiveError) as exc:
        _handle_error(exc)


@router.post(
    "/preview",
    response_model=AllocationPreviewResponse,
    summary="Preview allocation without side effects",
)
async def preview_allocation(
    payload: AllocationVariantRequest,
    service: AllocationService = Depends(_get_allocation_service),
):
    """Preview which warehouse(s) would fulfill a request — no changes made."""
    try:
        result = await service.preview_allocation(
            variant_id=payload.variant_id,
            quantity=payload.quantity,
            strategy_name=payload.strategy_name,
            warehouse_ids=payload.warehouse_ids,
        )
        return AllocationPreviewResponse(**result)
    except (VariantNotFoundError, InvalidAllocationStrategyError) as exc:
        _handle_error(exc)


@router.post(
    "/order",
    response_model=AllocationOrderResponse,
    summary="Allocate inventory for an order",
)
async def allocate_order(
    payload: AllocationOrderRequest,
    service: AllocationService = Depends(_get_allocation_service),
):
    """Allocate inventory for an entire order with optional auto-reservation."""
    try:
        items = [
            AllocationItem(variant_id=item.variant_id, quantity=item.quantity)
            for item in payload.items
        ]
        result = await service.allocate_order(
            items=items,
            order_id=payload.order_id,
            strategy_name=payload.strategy_name,
            auto_reserve=payload.auto_reserve,
        )
        return AllocationOrderResponse(**result)
    except (VariantNotFoundError, AllocationFailedError,
            InvalidAllocationStrategyError) as exc:
        _handle_error(exc)


@router.post(
    "/variant",
    response_model=AllocationVariantResponse,
    summary="Allocate a single variant",
)
async def allocate_variant(
    payload: AllocationVariantRequest,
    service: AllocationService = Depends(_get_allocation_service),
):
    """Allocate a single variant across available warehouses."""
    try:
        plan = await service.allocate_variant(
            variant_id=payload.variant_id,
            quantity=payload.quantity,
            strategy_name=payload.strategy_name,
            auto_reserve=payload.auto_reserve,
        )
        return AllocationVariantResponse(
            variant_id=str(payload.variant_id),
            requested_quantity=payload.quantity,
            fulfilled_quantity=plan.fulfilled_quantity,
            partial=plan.partial,
            fully_fulfilled=plan.is_fully_fulfilled,
            strategy=plan.strategy_name,
            allocations=[
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
        )
    except (VariantNotFoundError, AllocationFailedError,
            InvalidAllocationStrategyError) as exc:
        _handle_error(exc)


@router.post(
    "/reallocate",
    response_model=AllocationReallocateResponse,
    summary="Reallocate stock between warehouses",
)
async def reallocate_stock(
    payload: AllocationReallocateRequest,
    service: AllocationService = Depends(_get_allocation_service),
):
    """Move allocated stock from one warehouse to another."""
    try:
        result = await service.reallocate(
            variant_id=payload.variant_id,
            quantity=payload.quantity,
            from_warehouse_id=payload.from_warehouse_id,
            to_warehouse_id=payload.to_warehouse_id,
            reason=payload.reason,
        )
        return AllocationReallocateResponse(**result)
    except (WarehouseNotFoundError, WarehouseInactiveError,
            AllocationFailedError, VariantNotFoundError) as exc:
        _handle_error(exc)


@router.get(
    "/strategies",
    response_model=list[AllocationStrategyOut],
    summary="List available allocation strategies",
)
async def list_strategies(
    service: AllocationService = Depends(_get_allocation_service),
):
    """List all registered allocation strategies."""
    strategies = await service.list_strategies()
    return [AllocationStrategyOut(**s) for s in strategies]


@router.get(
    "/dashboard",
    response_model=AllocationDashboardOut,
    summary="Allocation dashboard statistics",
)
async def allocation_dashboard(
    service: AllocationService = Depends(_get_allocation_service),
):
    """Get allocation statistics for dashboards."""
    stats = await service.get_dashboard_stats()
    return AllocationDashboardOut(**stats)


@router.post(
    "/validate",
    response_model=AllocationValidateResponse,
    summary="Validate allocation feasibility",
)
async def validate_allocation(
    variant_id: uuid.UUID = Query(...),
    quantity: int = Query(..., ge=1),
    warehouse_id: uuid.UUID = Query(...),
    service: AllocationService = Depends(_get_allocation_service),
):
    """Validate that a specific warehouse can fulfill a quantity."""
    result = await service.validate_allocation(
        variant_id=variant_id,
        quantity=quantity,
        warehouse_id=warehouse_id,
    )
    return AllocationValidateResponse(**result)
