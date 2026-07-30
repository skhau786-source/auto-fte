"""
API Router for the Reservation Engine (Phase 3).

All endpoints require authentication and store ownership validation.
Business logic lives in ReservationService — this is a thin router layer.

Endpoints:
  POST   /reservations              — Reserve stock
  GET    /reservations              — List reservations
  GET    /reservations/{id}         — Get reservation details
  POST   /reservations/{id}/commit  — Commit a reservation
  POST   /reservations/{id}/release — Release a reservation
  POST   /reservations/{id}/expire  — Expire a reservation
  DELETE /reservations/{id}         — Cancel a reservation
  GET    /orders/{order_id}/reservations  — Get reservations by order
  GET    /reservations/dashboard    — Reservation dashboard stats
"""

import uuid
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent, Store

from app.inventory.dependencies import get_store_for_user
from app.inventory.constants import ReservationSource

from app.warehouse.reservation_service import ReservationService
from app.warehouse.schemas import (
    ReservationCreateRequest, ReservationReleaseRequest,
    ReservationOut, ReservationListOut,
    ReservationActionResponse, ReservationDashboardOut,
)
from app.warehouse.exceptions import (
    ReservationError, ReservationNotFoundError,
    InsufficientStockForReservationError, InvalidReservationStateError,
    DuplicateReservationError,
    WarehouseNotFoundError, WarehouseInactiveError,
)
from app.inventory.exceptions import VariantNotFoundError, InvalidStoreOwnershipError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reservations", tags=["Reservations"])


# ═══════════════════════════════════════════════════════════════════
# Error Mapping
# ═══════════════════════════════════════════════════════════════════

_EXCEPTION_TO_STATUS = {
    ReservationNotFoundError: status.HTTP_404_NOT_FOUND,
    InsufficientStockForReservationError: status.HTTP_400_BAD_REQUEST,
    InvalidReservationStateError: status.HTTP_409_CONFLICT,
    DuplicateReservationError: status.HTTP_409_CONFLICT,
    WarehouseNotFoundError: status.HTTP_404_NOT_FOUND,
    WarehouseInactiveError: status.HTTP_400_BAD_REQUEST,
    VariantNotFoundError: status.HTTP_404_NOT_FOUND,
    InvalidStoreOwnershipError: status.HTTP_403_FORBIDDEN,
}


def _handle_error(exc: ReservationError) -> None:
    """Convert a domain exception to the appropriate HTTP response."""
    status_code = _EXCEPTION_TO_STATUS.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    raise HTTPException(
        status_code=status_code,
        detail={
            "message": exc.message,
            "error_code": type(exc).__name__,
            **exc.detail,
        },
    )


# ═══════════════════════════════════════════════════════════════════
# Dependencies
# ═══════════════════════════════════════════════════════════════════

async def _get_reservation_service(
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store_for_user),
    user: RegisteredStudent = Depends(get_current_user),
) -> ReservationService:
    """Build a ReservationService with resolved dependencies."""
    return ReservationService(db=db, store=store, user_id=user.id)


def _serialize_reservation(res) -> dict:
    """Serialize a reservation ORM instance to a dict."""

    def _to_iso(val):
        return val.isoformat() if hasattr(val, "isoformat") else val

    return {
        "id": res.id,
        "store_id": res.store_id,
        "warehouse_id": res.warehouse_id,
        "inventory_id": res.inventory_id,
        "product_id": res.product_id,
        "variant_id": res.variant_id,
        "order_id": res.order_id,
        "order_source": (
            res.order_source.value
            if hasattr(res.order_source, "value")
            else str(res.order_source)
        ),
        "quantity": res.quantity,
        "status": (
            res.status.value
            if hasattr(res.status, "value")
            else str(res.status)
        ),
        "expires_at": _to_iso(res.expires_at),
        "created_at": _to_iso(res.created_at),
        "updated_at": _to_iso(res.updated_at),
        "released_at": _to_iso(res.released_at),
        "committed_at": _to_iso(res.committed_at),
        "metadata": (
            res.meta_data
            if hasattr(res, "meta_data")
            else (res.metadata if hasattr(res, "metadata") else {})
        ),
    }


# ═══════════════════════════════════════════════════════════════════
# RESERVATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "",
    response_model=ReservationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Reserve stock at a warehouse",
)
async def create_reservation(
    payload: ReservationCreateRequest,
    service: ReservationService = Depends(_get_reservation_service),
):
    """Reserve stock at a specific warehouse using FOR UPDATE locking."""
    try:
        # Map order_source string to enum
        source = ReservationSource.MANUAL
        if payload.order_source:
            try:
                source = ReservationSource(payload.order_source.lower())
            except ValueError:
                pass

        reservation = await service.reserve_stock(
            warehouse_id=payload.warehouse_id,
            variant_id=payload.variant_id,
            quantity=payload.quantity,
            order_id=payload.order_id,
            order_source=source,
            expires_in_minutes=payload.expires_in_minutes,
            reason=payload.reason,
        )
        return _serialize_reservation(reservation)
    except (
        WarehouseNotFoundError, WarehouseInactiveError,
        VariantNotFoundError, InsufficientStockForReservationError,
        DuplicateReservationError,
    ) as exc:
        _handle_error(exc)


@router.get(
    "",
    response_model=ReservationListOut,
    summary="List reservations",
)
async def list_reservations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    warehouse_id: Optional[uuid.UUID] = Query(None),
    variant_id: Optional[uuid.UUID] = Query(None),
    service: ReservationService = Depends(_get_reservation_service),
):
    """List active reservations with pagination and optional filters."""
    items, total, active_count = await service.get_reservations(
        page=page,
        page_size=page_size,
        warehouse_id=warehouse_id,
        variant_id=variant_id,
    )
    return ReservationListOut(
        items=[_serialize_reservation(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
        active_count=active_count,
    )


@router.get(
    "/dashboard",
    response_model=ReservationDashboardOut,
    summary="Reservation dashboard stats",
)
async def get_reservation_dashboard(
    service: ReservationService = Depends(_get_reservation_service),
):
    """Get reservation statistics for dashboards."""
    stats = await service.get_dashboard_stats()
    return ReservationDashboardOut(**stats)


@router.get(
    "/{reservation_id}",
    response_model=ReservationOut,
    summary="Get reservation details",
)
async def get_reservation(
    reservation_id: uuid.UUID,
    service: ReservationService = Depends(_get_reservation_service),
):
    """Get a single reservation by ID with ownership validation."""
    try:
        reservation = await service.get_reservation(reservation_id)
        return _serialize_reservation(reservation)
    except ReservationNotFoundError as exc:
        _handle_error(exc)


@router.post(
    "/{reservation_id}/commit",
    response_model=ReservationActionResponse,
    summary="Commit a reservation",
)
async def commit_reservation(
    reservation_id: uuid.UUID,
    service: ReservationService = Depends(_get_reservation_service),
):
    """Commit a reservation — finalize stock movement."""
    try:
        reservation = await service.commit_stock(reservation_id)
        return ReservationActionResponse(
            reservation_id=reservation.id,
            status=reservation.status.value,
            quantity=reservation.quantity,
            message=f"Reservation {reservation_id} committed",
        )
    except (ReservationNotFoundError, InvalidReservationStateError) as exc:
        _handle_error(exc)


@router.post(
    "/{reservation_id}/release",
    response_model=ReservationActionResponse,
    summary="Release a reservation",
)
async def release_reservation(
    reservation_id: uuid.UUID,
    payload: ReservationReleaseRequest = None,
    service: ReservationService = Depends(_get_reservation_service),
):
    """Release a reservation — return stock to available."""
    try:
        qty = payload.quantity if payload else None
        reservation = await service.release_stock(reservation_id, quantity=qty)
        return ReservationActionResponse(
            reservation_id=reservation.id,
            status=reservation.status.value,
            quantity=reservation.quantity,
            message=f"Reservation {reservation_id} released",
        )
    except (ReservationNotFoundError, InvalidReservationStateError) as exc:
        _handle_error(exc)


@router.post(
    "/{reservation_id}/expire",
    response_model=ReservationActionResponse,
    summary="Expire a reservation",
)
async def expire_reservation(
    reservation_id: uuid.UUID,
    service: ReservationService = Depends(_get_reservation_service),
):
    """Expire a reservation — release stock with expired status."""
    try:
        reservation = await service.expire_reservation(reservation_id)
        return ReservationActionResponse(
            reservation_id=reservation.id,
            status=reservation.status.value,
            quantity=reservation.quantity,
            message=f"Reservation {reservation_id} expired",
        )
    except (ReservationNotFoundError, InvalidReservationStateError) as exc:
        _handle_error(exc)


@router.delete(
    "/{reservation_id}",
    response_model=ReservationActionResponse,
    summary="Cancel a reservation",
)
async def cancel_reservation(
    reservation_id: uuid.UUID,
    service: ReservationService = Depends(_get_reservation_service),
):
    """Cancel a reservation — same as release."""
    try:
        reservation = await service.release_stock(reservation_id)
        return ReservationActionResponse(
            reservation_id=reservation.id,
            status=reservation.status.value,
            quantity=reservation.quantity,
            message=f"Reservation {reservation_id} cancelled",
        )
    except (ReservationNotFoundError, InvalidReservationStateError) as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# ORDER-BASED RESERVATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/order/{order_id}",
    response_model=list[ReservationOut],
    summary="Get reservations by order",
)
async def get_order_reservations(
    order_id: str,
    service: ReservationService = Depends(_get_reservation_service),
):
    """Get all reservations for a specific order."""
    reservations = await service.get_order_reservations(order_id)
    return [_serialize_reservation(r) for r in reservations]


# ═══════════════════════════════════════════════════════════════════
# STOCK VALIDATION ENDPOINT
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/validate/{warehouse_id}/{variant_id}",
    summary="Validate stock availability for reservation",
)
async def validate_stock(
    warehouse_id: uuid.UUID,
    variant_id: uuid.UUID,
    quantity: int = Query(..., ge=1),
    service: ReservationService = Depends(_get_reservation_service),
):
    """Check if sufficient stock is available for a reservation."""
    return await service.validate_stock(
        warehouse_id=warehouse_id,
        variant_id=variant_id,
        requested_quantity=quantity,
    )
