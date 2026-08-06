"""
API Router for the store-centric Allocation Engine.

Thin router layer — all business logic lives in AllocationService.

Endpoints:
  GET    /allocation/settings       — Get allocation settings (store settings)
  PUT    /allocation/settings       — Update allocation settings
  POST   /allocation/preview         — Preview allocation (no side effects)
  POST   /allocation/order           — Allocate for an entire order
  POST   /allocation/variant         — Allocate a single variant
  GET    /allocation/strategies      — List available strategies
  GET    /allocation/dashboard       — Allocation dashboard stats
  POST   /allocation/validate        — Validate allocation feasibility
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent, Store

from app.inventory.dependencies import get_store_for_user
from app.inventory.allocation_service import AllocationService
from app.inventory.allocation_strategies import AllocationItem
from app.inventory.repository import StoreSettingsRepository
from app.inventory.exceptions import (
    AllocationFailedError,
    InvalidAllocationStrategyError,
    StoreSettingsNotFoundError, StoreSettingsValidationError,
    VariantNotFoundError, InvalidStoreOwnershipError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/allocation", tags=["Allocation"])


# ═══════════════════════════════════════════════════════════════════
# Schemas
# ═══════════════════════════════════════════════════════════════════

class StoreSettingsOut(BaseModel):
    store_id: str
    auto_allocate_inventory: bool = True
    allocation_strategy: str = "default"
    allow_negative_stock: bool = False
    reserve_stock_on_order: bool = True
    auto_release_cancelled_orders: bool = True
    active_strategy: str = "default"
    available_strategies: list[dict] = []


class StoreSettingsUpdateRequest(BaseModel):
    auto_allocate_inventory: Optional[bool] = None
    allocation_strategy: Optional[str] = None
    allow_negative_stock: Optional[bool] = None
    reserve_stock_on_order: Optional[bool] = None
    auto_release_cancelled_orders: Optional[bool] = None


class AllocationItemIn(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(..., ge=1)


class AllocationOrderRequest(BaseModel):
    order_id: str
    strategy_name: Optional[str] = None
    auto_reserve: bool = True
    items: list[AllocationItemIn] = Field(..., min_length=1)


class AllocationVariantRequest(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(..., ge=1)
    strategy_name: Optional[str] = None
    auto_reserve: bool = True


# ═══════════════════════════════════════════════════════════════════
# Error Mapping
# ═══════════════════════════════════════════════════════════════════

_EXCEPTION_TO_STATUS = {
    AllocationFailedError: status.HTTP_400_BAD_REQUEST,
    InvalidAllocationStrategyError: status.HTTP_400_BAD_REQUEST,
    VariantNotFoundError: status.HTTP_404_NOT_FOUND,
    StoreSettingsNotFoundError: status.HTTP_404_NOT_FOUND,
    StoreSettingsValidationError: status.HTTP_400_BAD_REQUEST,
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
    response_model=StoreSettingsOut,
    summary="Get allocation settings",
)
async def get_allocation_settings(
    service: AllocationService = Depends(_get_allocation_service),
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store_for_user),
):
    """Get the current allocation configuration from store settings."""
    settings = await StoreSettingsRepository(db).get_or_create(store.id)
    strategy = await service.get_strategy()
    return StoreSettingsOut(
        store_id=str(store.id),
        auto_allocate_inventory=settings.auto_allocate_inventory,
        allocation_strategy=settings.allocation_strategy,
        allow_negative_stock=settings.allow_negative_stock,
        reserve_stock_on_order=settings.reserve_stock_on_order,
        auto_release_cancelled_orders=settings.auto_release_cancelled_orders,
        active_strategy=strategy["name"],
        available_strategies=await service.list_strategies(),
    )


@router.put(
    "/settings",
    response_model=StoreSettingsOut,
    summary="Update allocation settings",
)
async def update_allocation_settings(
    payload: StoreSettingsUpdateRequest,
    service: AllocationService = Depends(_get_allocation_service),
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store_for_user),
):
    """Update allocation configuration settings."""
    settings_repo = StoreSettingsRepository(db)
    settings = await settings_repo.get_or_create(store.id)

    data = payload.model_dump(exclude_unset=True)
    if "allocation_strategy" in data:
        if data["allocation_strategy"] not in {
            s["name"] for s in await service.list_strategies()
        }:
            raise InvalidAllocationStrategyError(data["allocation_strategy"])

    if data:
        settings = await settings_repo.update(store.id, data)
        await db.commit()
    if settings is None:
        raise StoreSettingsNotFoundError(str(store.id))

    strategy = await service.get_strategy()
    return StoreSettingsOut(
        store_id=str(store.id),
        auto_allocate_inventory=settings.auto_allocate_inventory,
        allocation_strategy=settings.allocation_strategy,
        allow_negative_stock=settings.allow_negative_stock,
        reserve_stock_on_order=settings.reserve_stock_on_order,
        auto_release_cancelled_orders=settings.auto_release_cancelled_orders,
        active_strategy=strategy["name"],
        available_strategies=await service.list_strategies(),
    )


@router.post(
    "/preview",
    response_model=dict,
    summary="Preview allocation without side effects",
)
async def preview_allocation(
    payload: AllocationVariantRequest,
    service: AllocationService = Depends(_get_allocation_service),
):
    """Preview which stock would fulfill a request — no changes made."""
    try:
        return await service.preview_allocation(
            variant_id=payload.variant_id,
            quantity=payload.quantity,
            strategy_name=payload.strategy_name,
        )
    except (VariantNotFoundError, InvalidAllocationStrategyError) as exc:
        _handle_error(exc)


@router.post(
    "/order",
    response_model=dict,
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
        return await service.allocate_order(
            items=items,
            order_id=payload.order_id,
            strategy_name=payload.strategy_name,
            auto_reserve=payload.auto_reserve,
        )
    except (VariantNotFoundError, AllocationFailedError,
            InvalidAllocationStrategyError) as exc:
        _handle_error(exc)


@router.post(
    "/variant",
    response_model=dict,
    summary="Allocate a single variant",
)
async def allocate_variant(
    payload: AllocationVariantRequest,
    service: AllocationService = Depends(_get_allocation_service),
):
    """Allocate a single variant from the store's available stock."""
    try:
        plan = await service.allocate_variant(
            variant_id=payload.variant_id,
            quantity=payload.quantity,
            strategy_name=payload.strategy_name,
            auto_reserve=payload.auto_reserve,
        )
        result = plan.items[0] if plan.items else None
        return {
            "variant_id": str(payload.variant_id),
            "requested_quantity": payload.quantity,
            "fulfilled_quantity": result.fulfilled_quantity if result else 0,
            "available_quantity": result.available_quantity if result else 0,
            "partial": plan.partial,
            "fully_fulfilled": plan.is_fully_fulfilled,
            "strategy": plan.strategy_name,
            "allocations": [
                {
                    "location": str(payload.variant_id),
                    "quantity": result.fulfilled_quantity if result else 0,
                }
            ] if result else [],
        }
    except (VariantNotFoundError, AllocationFailedError,
            InvalidAllocationStrategyError) as exc:
        _handle_error(exc)


@router.get(
    "/strategies",
    response_model=list[dict],
    summary="List available allocation strategies",
)
async def list_strategies(
    service: AllocationService = Depends(_get_allocation_service),
):
    """List all registered allocation strategies."""
    return await service.list_strategies()


@router.get(
    "/dashboard",
    response_model=dict,
    summary="Allocation dashboard statistics",
)
async def allocation_dashboard(
    service: AllocationService = Depends(_get_allocation_service),
):
    """Get allocation statistics for dashboards."""
    return await service.get_dashboard_stats()


@router.post(
    "/validate",
    response_model=dict,
    summary="Validate allocation feasibility",
)
async def validate_allocation(
    variant_id: uuid.UUID = Query(...),
    quantity: int = Query(..., ge=1),
    service: AllocationService = Depends(_get_allocation_service),
):
    """Validate that the store can fulfill a quantity."""
    try:
        return await service.validate_allocation(
            variant_id=variant_id,
            quantity=quantity,
        )
    except VariantNotFoundError as exc:
        _handle_error(exc)
