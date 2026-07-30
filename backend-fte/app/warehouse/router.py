"""
API Router for the Warehouse Management module.

Thin router layer — all business logic lives in the service layer.
Domain exceptions from services are caught and converted to HTTP responses.
Follows the same pattern as the Inventory module router.
"""

import uuid
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent, Store

from app.inventory.dependencies import get_store_for_user
from app.inventory.constants import WarehouseStatus, TransferStatus

from app.warehouse.service import (
    WarehouseService, WarehouseInventoryService,
    WarehouseTransferService, CapacityService,
    InventoryAggregationService,
)
from app.warehouse.schemas import (
    WarehouseCreateRequest, WarehouseUpdateRequest,
    WarehouseOut, WarehouseListOut,
    WarehouseActivateRequest,
    WarehouseInventoryOut, WarehouseInventoryListOut,
    WarehouseInventoryUpdateRequest,
    WarehouseStockAdjustRequest, WarehouseStockAdjustResponse,
    TransferCreateRequest, TransferOut, TransferListOut,
    TransferActionResponse,
    WarehouseCapacityOut,
    WarehouseAnalyticsOut, WarehouseSummaryOut,
)
from app.warehouse.exceptions import (
    WarehouseError, WarehouseNotFoundError,
    WarehouseAlreadyExistsError, WarehouseInactiveError,
    WarehouseAtCapacityError, WarehouseInventoryNotFoundError,
    TransferNotFoundError, InvalidTransferStateError,
    SameWarehouseTransferError, InsufficientWarehouseStockError,
    WarehouseSettingsNotFoundError, WarehouseSettingsValidationError,
)
from app.inventory.exceptions import VariantNotFoundError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/warehouses", tags=["Warehouse"])


# ═══════════════════════════════════════════════════════════════════
# Error Mapping
# ═══════════════════════════════════════════════════════════════════

_EXCEPTION_TO_STATUS = {
    WarehouseNotFoundError: status.HTTP_404_NOT_FOUND,
    WarehouseAlreadyExistsError: status.HTTP_409_CONFLICT,
    WarehouseInactiveError: status.HTTP_400_BAD_REQUEST,
    WarehouseAtCapacityError: status.HTTP_400_BAD_REQUEST,
    WarehouseInventoryNotFoundError: status.HTTP_404_NOT_FOUND,
    TransferNotFoundError: status.HTTP_404_NOT_FOUND,
    InvalidTransferStateError: status.HTTP_409_CONFLICT,
    SameWarehouseTransferError: status.HTTP_400_BAD_REQUEST,
    InsufficientWarehouseStockError: status.HTTP_400_BAD_REQUEST,
    VariantNotFoundError: status.HTTP_404_NOT_FOUND,
    WarehouseSettingsNotFoundError: status.HTTP_404_NOT_FOUND,
    WarehouseSettingsValidationError: status.HTTP_400_BAD_REQUEST,
}


def _handle_error(exc: WarehouseError) -> None:
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

async def _get_wh_service(
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store_for_user),
    user: RegisteredStudent = Depends(get_current_user),
) -> WarehouseService:
    return WarehouseService(db=db, store=store, user_id=user.id)


async def _get_wh_inv_service(
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store_for_user),
    user: RegisteredStudent = Depends(get_current_user),
) -> WarehouseInventoryService:
    return WarehouseInventoryService(db=db, store=store, user_id=user.id)


async def _get_transfer_service(
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store_for_user),
    user: RegisteredStudent = Depends(get_current_user),
) -> WarehouseTransferService:
    return WarehouseTransferService(db=db, store=store, user_id=user.id)


async def _get_capacity_service(
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store_for_user),
) -> CapacityService:
    return CapacityService(db=db, store=store)


async def _get_agg_service(
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store_for_user),
) -> InventoryAggregationService:
    return InventoryAggregationService(db=db, store=store)


# ═══════════════════════════════════════════════════════════════════
# WAREHOUSE CRUD ENDPOINTS (Phase 7)
# ═══════════════════════════════════════════════════════════════════

@router.get("", response_model=WarehouseListOut, summary="List all warehouses")
async def list_warehouses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[WarehouseStatus] = Query(None),
    search: Optional[str] = Query(None, max_length=200),
    is_active: Optional[bool] = Query(None),
    service: WarehouseService = Depends(_get_wh_service),
):
    """List warehouses with pagination and filtering."""
    warehouses, total = await service.list_warehouses(
        page=page, page_size=page_size,
        status=status, search=search, is_active=is_active,
    )
    return WarehouseListOut(
        items=[WarehouseOut.model_validate(w) for w in warehouses],
        total=total,
    )


@router.post(
    "", response_model=WarehouseOut, status_code=status.HTTP_201_CREATED,
    summary="Create a new warehouse",
)
async def create_warehouse(
    payload: WarehouseCreateRequest,
    service: WarehouseService = Depends(_get_wh_service),
):
    """Create a new warehouse with unique code."""
    try:
        warehouse = await service.create_warehouse(payload)
        return WarehouseOut.model_validate(warehouse)
    except (WarehouseAlreadyExistsError,) as exc:
        _handle_error(exc)


@router.get("/{warehouse_id}", response_model=WarehouseOut, summary="Get warehouse details")
async def get_warehouse(
    warehouse_id: uuid.UUID,
    service: WarehouseService = Depends(_get_wh_service),
):
    """Get a single warehouse by ID."""
    try:
        warehouse = await service.get_warehouse(warehouse_id)
        return WarehouseOut.model_validate(warehouse)
    except WarehouseNotFoundError as exc:
        _handle_error(exc)


@router.put("/{warehouse_id}", response_model=WarehouseOut, summary="Update warehouse")
async def update_warehouse(
    warehouse_id: uuid.UUID,
    payload: WarehouseUpdateRequest,
    service: WarehouseService = Depends(_get_wh_service),
):
    """Update warehouse fields."""
    try:
        warehouse = await service.update_warehouse(warehouse_id, payload)
        return WarehouseOut.model_validate(warehouse)
    except WarehouseNotFoundError as exc:
        _handle_error(exc)


@router.delete("/{warehouse_id}", summary="Delete warehouse")
async def delete_warehouse(
    warehouse_id: uuid.UUID,
    service: WarehouseService = Depends(_get_wh_service),
):
    """Delete a warehouse."""
    try:
        result = await service.delete_warehouse(warehouse_id)
        return result
    except WarehouseNotFoundError as exc:
        _handle_error(exc)


@router.post(
    "/{warehouse_id}/activate", response_model=WarehouseOut,
    summary="Activate warehouse",
)
async def activate_warehouse(
    warehouse_id: uuid.UUID,
    service: WarehouseService = Depends(_get_wh_service),
):
    """Activate a warehouse."""
    try:
        warehouse = await service.activate_warehouse(warehouse_id)
        return WarehouseOut.model_validate(warehouse)
    except WarehouseNotFoundError as exc:
        _handle_error(exc)


@router.post(
    "/{warehouse_id}/deactivate", response_model=WarehouseOut,
    summary="Deactivate warehouse",
)
async def deactivate_warehouse(
    warehouse_id: uuid.UUID,
    service: WarehouseService = Depends(_get_wh_service),
):
    """Deactivate a warehouse."""
    try:
        warehouse = await service.deactivate_warehouse(warehouse_id)
        return WarehouseOut.model_validate(warehouse)
    except WarehouseNotFoundError as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# WAREHOUSE INVENTORY ENDPOINTS (Phase 7)
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/{warehouse_id}/inventory", response_model=WarehouseInventoryListOut,
    summary="List warehouse inventory",
)
async def list_warehouse_inventory(
    warehouse_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    low_stock_only: bool = Query(False),
    search: Optional[str] = Query(None, max_length=200),
    service: WarehouseInventoryService = Depends(_get_wh_inv_service),
):
    """List inventory items at a specific warehouse."""
    try:
        items, total = await service.get_inventory(
            warehouse_id=warehouse_id, page=page, page_size=page_size,
            low_stock_only=low_stock_only, search=search,
        )
        warehouse_name = ""
        wh = await WarehouseService(service.db, service.store).get_warehouse(warehouse_id)
        warehouse_name = wh.name

        enriched = []
        for item in items:
            item_out = WarehouseInventoryOut.model_validate(item)
            item_out.total_stock = item.available_stock + item.reserved_stock
            if item.variant:
                item_out.variant_title = item.variant.title
                item_out.sku = item.variant.sku
            if item.product:
                item_out.product_title = item.product.title
            enriched.append(item_out)

        return WarehouseInventoryListOut(
            items=enriched, total=total,
            warehouse_id=warehouse_id, warehouse_name=warehouse_name,
        )
    except WarehouseNotFoundError as exc:
        _handle_error(exc)


@router.post(
    "/inventory/adjust", response_model=WarehouseStockAdjustResponse,
    summary="Adjust stock at warehouse",
)
async def adjust_warehouse_stock(
    payload: WarehouseStockAdjustRequest,
    service: WarehouseInventoryService = Depends(_get_wh_inv_service),
):
    """Adjust stock for a variant at a specific warehouse."""
    try:
        result = await service.adjust_stock(
            warehouse_id=payload.warehouse_id,
            variant_id=payload.variant_id,
            quantity_change=payload.quantity_change,
            reason=payload.reason,
        )
        return WarehouseStockAdjustResponse(**result)
    except (
        WarehouseNotFoundError, WarehouseInactiveError,
        VariantNotFoundError, InsufficientWarehouseStockError,
    ) as exc:
        _handle_error(exc)


@router.put(
    "/{warehouse_id}/inventory/{variant_id}",
    response_model=WarehouseInventoryOut,
    summary="Update warehouse inventory metadata",
)
async def update_warehouse_inventory(
    warehouse_id: uuid.UUID,
    variant_id: uuid.UUID,
    payload: WarehouseInventoryUpdateRequest,
    service: WarehouseInventoryService = Depends(_get_wh_inv_service),
):
    """Update inventory thresholds, bin location, shelf, etc."""
    try:
        inv = await service.update_inventory(warehouse_id, variant_id, payload)
        return WarehouseInventoryOut.model_validate(inv)
    except WarehouseInventoryNotFoundError as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# WAREHOUSE TRANSFER ENDPOINTS (Phase 7)
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/transfers", response_model=TransferOut, status_code=status.HTTP_201_CREATED,
    summary="Create a warehouse transfer",
)
async def create_transfer(
    payload: TransferCreateRequest,
    service: WarehouseTransferService = Depends(_get_transfer_service),
):
    """Create a transfer between warehouses."""
    try:
        transfer = await service.create_transfer(payload)
        return _enrich_transfer(transfer)
    except (
        WarehouseNotFoundError, WarehouseInactiveError,
        SameWarehouseTransferError, InsufficientWarehouseStockError,
    ) as exc:
        _handle_error(exc)


@router.get(
    "/transfers", response_model=TransferListOut,
    summary="List warehouse transfers",
)
async def list_transfers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[TransferStatus] = Query(None),
    source_warehouse_id: Optional[uuid.UUID] = Query(None),
    destination_warehouse_id: Optional[uuid.UUID] = Query(None),
    search: Optional[str] = Query(None, max_length=200),
    service: WarehouseTransferService = Depends(_get_transfer_service),
):
    """List transfers with filtering and pagination."""
    transfers, total = await service.list_transfers(
        page=page, page_size=page_size,
        status=status,
        source_warehouse_id=source_warehouse_id,
        destination_warehouse_id=destination_warehouse_id,
        search=search,
    )
    enriched = [_enrich_transfer(t) for t in transfers]
    return TransferListOut(
        items=enriched, total=total,
        page=page, page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
    )


@router.get(
    "/transfers/{transfer_id}", response_model=TransferOut,
    summary="Get transfer details",
)
async def get_transfer(
    transfer_id: uuid.UUID,
    service: WarehouseTransferService = Depends(_get_transfer_service),
):
    """Get a single transfer by ID."""
    try:
        transfer = await service.get_transfer(transfer_id)
        return _enrich_transfer(transfer)
    except TransferNotFoundError as exc:
        _handle_error(exc)


@router.post(
    "/transfers/{transfer_id}/submit", response_model=TransferActionResponse,
    summary="Submit transfer for approval",
)
async def submit_transfer(
    transfer_id: uuid.UUID,
    service: WarehouseTransferService = Depends(_get_transfer_service),
):
    """Submit a draft transfer for approval."""
    try:
        transfer = await service.submit_transfer(transfer_id)
        return TransferActionResponse(
            transfer_id=transfer.id,
            transfer_number=transfer.transfer_number,
            status=transfer.status,
            message=f"Transfer {transfer.transfer_number} submitted for approval",
        )
    except (TransferNotFoundError, InvalidTransferStateError) as exc:
        _handle_error(exc)


@router.post(
    "/transfers/{transfer_id}/approve", response_model=TransferActionResponse,
    summary="Approve a transfer",
)
async def approve_transfer(
    transfer_id: uuid.UUID,
    service: WarehouseTransferService = Depends(_get_transfer_service),
):
    """Approve a pending transfer."""
    try:
        transfer = await service.approve_transfer(transfer_id)
        return TransferActionResponse(
            transfer_id=transfer.id,
            transfer_number=transfer.transfer_number,
            status=transfer.status,
            message=f"Transfer {transfer.transfer_number} approved",
        )
    except (TransferNotFoundError, InvalidTransferStateError) as exc:
        _handle_error(exc)


@router.post(
    "/transfers/{transfer_id}/start", response_model=TransferActionResponse,
    summary="Start transfer (in transit)",
)
async def start_transfer(
    transfer_id: uuid.UUID,
    service: WarehouseTransferService = Depends(_get_transfer_service),
):
    """Mark transfer as in transit and reserve stock."""
    try:
        transfer = await service.start_transfer(transfer_id)
        return TransferActionResponse(
            transfer_id=transfer.id,
            transfer_number=transfer.transfer_number,
            status=transfer.status,
            message=f"Transfer {transfer.transfer_number} is in transit",
        )
    except (TransferNotFoundError, InvalidTransferStateError) as exc:
        _handle_error(exc)


@router.post(
    "/transfers/{transfer_id}/complete", response_model=TransferActionResponse,
    summary="Complete a transfer",
)
async def complete_transfer(
    transfer_id: uuid.UUID,
    service: WarehouseTransferService = Depends(_get_transfer_service),
):
    """Complete a transfer — moves stock from source to destination."""
    try:
        transfer = await service.complete_transfer(transfer_id)
        return TransferActionResponse(
            transfer_id=transfer.id,
            transfer_number=transfer.transfer_number,
            status=transfer.status,
            message=f"Transfer {transfer.transfer_number} completed",
        )
    except (TransferNotFoundError, InvalidTransferStateError) as exc:
        _handle_error(exc)


@router.post(
    "/transfers/{transfer_id}/cancel", response_model=TransferActionResponse,
    summary="Cancel a transfer",
)
async def cancel_transfer(
    transfer_id: uuid.UUID,
    service: WarehouseTransferService = Depends(_get_transfer_service),
):
    """Cancel a transfer and release reserved stock."""
    try:
        transfer = await service.cancel_transfer(transfer_id)
        return TransferActionResponse(
            transfer_id=transfer.id,
            transfer_number=transfer.transfer_number,
            status=transfer.status,
            message=f"Transfer {transfer.transfer_number} cancelled",
        )
    except (TransferNotFoundError, InvalidTransferStateError) as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# CAPACITY ENDPOINTS (Phase 7)
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/{warehouse_id}/capacity", response_model=WarehouseCapacityOut,
    summary="Get warehouse capacity",
)
async def get_warehouse_capacity(
    warehouse_id: uuid.UUID,
    service: CapacityService = Depends(_get_capacity_service),
):
    """Get capacity information for a warehouse."""
    try:
        cap = await service.get_capacity(warehouse_id)
        return WarehouseCapacityOut(**cap)
    except WarehouseNotFoundError as exc:
        _handle_error(exc)


@router.get(
    "/capacity/summary", response_model=WarehouseSummaryOut,
    summary="Get warehouse capacity summary",
)
async def get_capacity_summary(
    service: CapacityService = Depends(_get_capacity_service),
):
    """Get high-level capacity summary across all warehouses."""
    summary = await service.get_summary()
    return WarehouseSummaryOut(**summary)


# ═══════════════════════════════════════════════════════════════════
# ANALYTICS / DASHBOARD ENDPOINTS (Phase 9)
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/{warehouse_id}/analytics", response_model=WarehouseAnalyticsOut,
    summary="Get warehouse analytics",
)
async def get_warehouse_analytics(
    warehouse_id: uuid.UUID,
    service: InventoryAggregationService = Depends(_get_agg_service),
    cap_service: CapacityService = Depends(_get_capacity_service),
):
    """Get comprehensive analytics for a warehouse."""
    try:
        summaries = await service.get_all_warehouse_summaries()
        wh_summary = next(
            (s for s in summaries if str(s["warehouse_id"]) == str(warehouse_id)),
            None,
        )
        if not wh_summary:
            raise WarehouseNotFoundError(str(warehouse_id))

        capacity = await cap_service.get_capacity(warehouse_id)
        transfer_service = WarehouseTransferService(
            service.db, service.store, None,
        )
        pending_out, _ = await transfer_service.list_transfers(
            source_warehouse_id=warehouse_id,
            status=TransferStatus.PENDING,
        )
        pending_in, _ = await transfer_service.list_transfers(
            destination_warehouse_id=warehouse_id,
            status=TransferStatus.PENDING,
        )

        return WarehouseAnalyticsOut(
            warehouse_id=wh_summary["warehouse_id"],
            warehouse_name=wh_summary["warehouse_name"],
            total_products=wh_summary["total_products"],
            total_variants=wh_summary["total_products"],
            total_available_stock=wh_summary["total_available_stock"],
            total_reserved_stock=wh_summary["total_reserved_stock"],
            total_incoming_stock=0,
            total_damaged_stock=0,
            capacity_usage=WarehouseCapacityOut(**capacity) if capacity else None,
            low_stock_count=wh_summary["low_stock_count"],
            out_of_stock_count=wh_summary["out_of_stock_count"],
            pending_transfers_in=len(pending_in),
            pending_transfers_out=len(pending_out),
        )
    except WarehouseNotFoundError as exc:
        _handle_error(exc)


@router.get(
    "/analytics/summary", response_model=WarehouseSummaryOut,
    summary="Get warehouse summary",
)
async def get_warehouse_summary(
    agg_service: InventoryAggregationService = Depends(_get_agg_service),
    cap_service: CapacityService = Depends(_get_capacity_service),
):
    """Get high-level warehouse summary for dashboards."""
    summary = await cap_service.get_summary()
    return WarehouseSummaryOut(**summary)


# ═══════════════════════════════════════════════════════════════════
# DEFAULT WAREHOUSE & SETTINGS ENDPOINTS (Phase 2 — Part B)
# ═══════════════════════════════════════════════════════════════════

from app.warehouse.schemas import (
    DefaultWarehouseResponse, DefaultWarehouseSetResponse,
    WarehouseSettingsOut, WarehouseSettingsUpdateRequest,
)


@router.get(
    "/default",
    response_model=DefaultWarehouseResponse,
    summary="Get the default warehouse",
)
async def get_default_warehouse(
    service: WarehouseService = Depends(_get_wh_service),
):
    """Get the default warehouse for the current store."""
    settings = await service.get_warehouse_settings()
    return DefaultWarehouseResponse(**settings)


@router.post(
    "/{warehouse_id}/set-default",
    response_model=DefaultWarehouseSetResponse,
    summary="Set warehouse as default",
)
async def set_default_warehouse(
    warehouse_id: uuid.UUID,
    service: WarehouseService = Depends(_get_wh_service),
):
    """Set a warehouse as the default for the current store."""
    try:
        warehouse = await service.set_default_warehouse(warehouse_id)
        return DefaultWarehouseSetResponse(
            warehouse_id=str(warehouse.id),
            warehouse_name=warehouse.name,
            message=f"Warehouse '{warehouse.name}' is now the default",
        )
    except (WarehouseNotFoundError, WarehouseInactiveError) as exc:
        _handle_error(exc)


@router.delete(
    "/default",
    response_model=dict,
    summary="Clear the default warehouse",
)
async def clear_default_warehouse(
    service: WarehouseService = Depends(_get_wh_service),
):
    """Clear the default warehouse setting for the current store."""
    return await service.clear_default_warehouse()


@router.get(
    "/settings",
    response_model=WarehouseSettingsOut,
    summary="Get warehouse configuration settings",
)
async def get_warehouse_settings(
    service: WarehouseService = Depends(_get_wh_service),
):
    """Get warehouse configuration settings for the current store."""
    settings = await service.get_warehouse_settings()
    return WarehouseSettingsOut(**settings)


@router.put(
    "/settings",
    response_model=WarehouseSettingsOut,
    summary="Update warehouse configuration settings",
)
async def update_warehouse_settings(
    payload: WarehouseSettingsUpdateRequest,
    service: WarehouseService = Depends(_get_wh_service),
):
    """
    Update warehouse configuration settings.

    Supports PATCH semantics — only provided fields are updated.
    Validates:
    - default_warehouse_id belongs to this store and is active
    - allocation_strategy is a valid strategy
    """
    try:
        settings = await service.update_warehouse_settings(payload)
        return WarehouseSettingsOut(**settings)
    except (
        WarehouseNotFoundError, WarehouseInactiveError,
        WarehouseSettingsValidationError, WarehouseSettingsNotFoundError,
    ) as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════

def _enrich_transfer(transfer) -> TransferOut:
    """Enrich a transfer with warehouse names and item details."""
    out = TransferOut.model_validate(transfer)
    if transfer.source_warehouse_rel:
        out.source_warehouse_name = transfer.source_warehouse_rel.name
    if transfer.destination_warehouse_rel:
        out.destination_warehouse_name = transfer.destination_warehouse_rel.name
    if transfer.requested_by:
        out.requested_by_name = transfer.requested_by.full_name
    if transfer.approved_by:
        out.approved_by_name = transfer.approved_by.full_name

    out.total_items = len(transfer.items) if transfer.items else 0
    out.total_quantity = sum(item.quantity for item in (transfer.items or []))

    # Enrich items
    if transfer.items:
        for item in transfer.items:
            if hasattr(item, "variant") and item.variant:
                item.variant_title = item.variant.title
                item.sku = item.variant.sku
            if hasattr(item, "product") and item.product:
                item.product_title = item.product.title

    return out
