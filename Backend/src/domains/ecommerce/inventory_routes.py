# ═══════════════════════════════════════════════════════════════
# domains / ecommerce / inventory_routes.py
#
# PURPOSE: Stock adjustment + movement history endpoints.
#
#   POST /api/v1/stores/{store_id}/inventory/adjust
#   POST /api/v1/stores/{store_id}/inventory/adjust/bulk
#   GET  /api/v1/stores/{store_id}/inventory/history
#
# NOTE:    Ported from kulsoom (backend-fte/app/inventory/router.py
#          update-stock + history).
# ═══════════════════════════════════════════════════════════════

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.sdk.database import get_db
from src.sdk.exceptions import AgentError
from src.domains.auth.models import User
from src.domains.auth.service import get_current_user
from src.domains.ecommerce.routes import _get_store_or_404
from src.domains.ecommerce.inventory_service import InventoryService

router = APIRouter(prefix="/api/v1", tags=["Inventory"])


class AdjustRequest(BaseModel):
    variant_id: int
    quantity_change: int = Field(description="Positive = add stock, negative = remove")
    reason: Optional[str] = Field(default=None, max_length=500)


class BulkAdjustRequest(BaseModel):
    adjustments: list[AdjustRequest] = Field(min_length=1, max_length=100)


class AdjustResult(BaseModel):
    variant_id: int
    movement_id: int
    quantity_before: int
    quantity_after: int
    quantity_change: int


class BulkAdjustItem(BaseModel):
    variant_id: int
    success: bool
    movement_id: Optional[int] = None
    quantity_before: Optional[int] = None
    quantity_after: Optional[int] = None
    quantity_change: Optional[int] = None
    error: Optional[str] = None


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    variant_id: int
    movement_type: str
    quantity_change: int
    quantity_before: int
    quantity_after: int
    reason: Optional[str]
    reference_id: Optional[str]
    performed_by: Optional[int]
    created_at: datetime


class HistoryResponse(BaseModel):
    items: list[MovementOut]
    total: int
    page: int
    page_size: int


def _http_error(exc: AgentError) -> HTTPException:
    return HTTPException(status_code=exc.code if exc.code in (400, 404, 409) else 400, detail=exc.message)


@router.post("/stores/{store_id}/inventory/adjust", response_model=AdjustResult)
async def adjust_stock(
    store_id: int,
    payload: AdjustRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_store_or_404(db, store_id, user.id)
    try:
        return await InventoryService(db, store_id, user.id).adjust_stock(
            variant_id=payload.variant_id,
            quantity_change=payload.quantity_change,
            reason=payload.reason,
        )
    except AgentError as exc:
        await db.rollback()
        raise _http_error(exc)


@router.post("/stores/{store_id}/inventory/adjust/bulk", response_model=list[BulkAdjustItem])
async def bulk_adjust_stock(
    store_id: int,
    payload: BulkAdjustRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_store_or_404(db, store_id, user.id)
    return await InventoryService(db, store_id, user.id).bulk_adjust(
        [a.model_dump() for a in payload.adjustments]
    )


@router.get("/stores/{store_id}/inventory/history", response_model=HistoryResponse)
async def stock_history(
    store_id: int,
    variant_id: Optional[int] = None,
    movement_type: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_store_or_404(db, store_id, user.id)
    items, total = await InventoryService(db, store_id, user.id).get_history(
        variant_id=variant_id,
        movement_type=movement_type,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return HistoryResponse(items=items, total=total, page=page, page_size=page_size)
