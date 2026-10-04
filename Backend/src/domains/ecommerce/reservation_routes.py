# ═══════════════════════════════════════════════════════════════
# domains / ecommerce / reservation_routes.py
#
# PURPOSE: Stock reservation endpoints.
#
#   POST /api/v1/stores/{store_id}/reservations
#   GET  /api/v1/stores/{store_id}/reservations
#   GET  /api/v1/stores/{store_id}/reservations/stats
#   GET  /api/v1/stores/{store_id}/reservations/validate/{variant_id}
#   GET  /api/v1/stores/{store_id}/reservations/{reservation_id}
#   POST /api/v1/stores/{store_id}/reservations/{reservation_id}/commit
#   POST /api/v1/stores/{store_id}/reservations/{reservation_id}/release
#   POST /api/v1/stores/{store_id}/reservations/{reservation_id}/expire
#   POST /api/v1/stores/{store_id}/reservations/orders/{order_id}/cancel
#
# NOTE:    Ported from kulsoom (backend-fte/app/inventory/reservation_router.py).
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
from src.domains.ecommerce.reservation_service import ReservationService

router = APIRouter(prefix="/api/v1", tags=["Reservations"])


class ReservationCreate(BaseModel):
    variant_id: int
    quantity: int = Field(gt=0)
    order_id: Optional[str] = Field(default=None, max_length=255)
    order_source: str = "manual"
    expires_in_minutes: Optional[int] = Field(default=None, gt=0, le=60 * 24 * 30)
    reason: Optional[str] = Field(default=None, max_length=500)


class ReservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    store_id: int
    variant_id: int
    order_id: Optional[str]
    order_source: str
    quantity: int
    status: str
    reason: Optional[str]
    expires_at: Optional[datetime]
    committed_at: Optional[datetime]
    released_at: Optional[datetime]
    created_at: datetime


class ReservationListResponse(BaseModel):
    items: list[ReservationOut]
    total: int
    page: int
    page_size: int


class ValidateResponse(BaseModel):
    variant_id: int
    requested: int
    available: int
    sufficient: bool


def _http_error(exc: AgentError) -> HTTPException:
    return HTTPException(status_code=exc.code if exc.code in (400, 404, 409) else 400, detail=exc.message)


async def _service(store_id: int, user: User, db: AsyncSession) -> ReservationService:
    await _get_store_or_404(db, store_id, user.id)
    return ReservationService(db, store_id, user.id)


@router.post("/stores/{store_id}/reservations", response_model=ReservationOut, status_code=201)
async def create_reservation(
    store_id: int,
    payload: ReservationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = await _service(store_id, user, db)
    try:
        return await service.reserve_stock(**payload.model_dump())
    except AgentError as exc:
        await db.rollback()
        raise _http_error(exc)


@router.get("/stores/{store_id}/reservations", response_model=ReservationListResponse)
async def list_reservations(
    store_id: int,
    status: Optional[str] = None,
    variant_id: Optional[int] = None,
    order_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = await _service(store_id, user, db)
    try:
        items, total = await service.list_reservations(status, variant_id, order_id, page, page_size)
    except AgentError as exc:
        raise _http_error(exc)
    return ReservationListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/stores/{store_id}/reservations/stats")
async def reservation_stats(
    store_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await (await _service(store_id, user, db)).get_stats()


@router.get("/stores/{store_id}/reservations/validate/{variant_id}", response_model=ValidateResponse)
async def validate_stock(
    store_id: int,
    variant_id: int,
    quantity: int = Query(1, gt=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = await _service(store_id, user, db)
    try:
        return await service.validate_stock(variant_id, quantity)
    except AgentError as exc:
        raise _http_error(exc)


@router.get("/stores/{store_id}/reservations/{reservation_id}", response_model=ReservationOut)
async def get_reservation(
    store_id: int,
    reservation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = await _service(store_id, user, db)
    try:
        return await service.get_reservation(reservation_id)
    except AgentError as exc:
        raise _http_error(exc)


async def _transition(store_id: int, reservation_id: int, action: str, user: User, db: AsyncSession):
    service = await _service(store_id, user, db)
    method = {
        "commit": service.commit_stock,
        "release": service.release_stock,
        "expire": service.expire_reservation,
    }[action]
    try:
        return await method(reservation_id)
    except AgentError as exc:
        await db.rollback()
        raise _http_error(exc)


@router.post("/stores/{store_id}/reservations/{reservation_id}/commit", response_model=ReservationOut)
async def commit_reservation(
    store_id: int, reservation_id: int,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await _transition(store_id, reservation_id, "commit", user, db)


@router.post("/stores/{store_id}/reservations/{reservation_id}/release", response_model=ReservationOut)
async def release_reservation(
    store_id: int, reservation_id: int,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await _transition(store_id, reservation_id, "release", user, db)


@router.post("/stores/{store_id}/reservations/{reservation_id}/expire", response_model=ReservationOut)
async def expire_reservation(
    store_id: int, reservation_id: int,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await _transition(store_id, reservation_id, "expire", user, db)


@router.post("/stores/{store_id}/reservations/orders/{order_id}/cancel", response_model=list[ReservationOut])
async def cancel_order_reservations(
    store_id: int,
    order_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = await _service(store_id, user, db)
    try:
        return await service.cancel_order(order_id)
    except AgentError as exc:
        await db.rollback()
        raise _http_error(exc)
