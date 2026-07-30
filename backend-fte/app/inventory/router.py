"""
API Router for the Inventory Management module.

Thin router layer — all business logic lives in the service layer.
Domain exceptions from the service are caught and converted to HTTP responses.
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
from app.inventory.service import InventoryService
from app.inventory.schemas import (
    ProductCreateRequest,
    ProductUpdateRequest,
    ProductOut,
    ProductListOut,
    DeleteResponse,
    InventoryAdjustRequest,
    InventoryAdjustResponse,
    LowStockListOut,
    InventoryHistoryOut,
    InventoryTransactionOut,
    ProductSearchFilters,
)
from app.inventory.exceptions import (
    InventoryError,
    ProductNotFoundError,
    VariantNotFoundError,
    DuplicateSKUError,
    InsufficientStockError,
    InvalidStoreOwnershipError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/inventory", tags=["Inventory"])


# ═══════════════════════════════════════════════════════════════════
# Error Mapping Helper
# ═══════════════════════════════════════════════════════════════════

_EXCEPTION_TO_STATUS = {
    ProductNotFoundError: status.HTTP_404_NOT_FOUND,
    VariantNotFoundError: status.HTTP_404_NOT_FOUND,
    DuplicateSKUError: status.HTTP_409_CONFLICT,
    InsufficientStockError: status.HTTP_400_BAD_REQUEST,
    InvalidStoreOwnershipError: status.HTTP_403_FORBIDDEN,
}


async def _get_inventory_service(
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store_for_user),
    user: RegisteredStudent = Depends(get_current_user),
) -> InventoryService:
    """
    Build an InventoryService instance with all its dependencies resolved.
    The three Depends are used directly because:
    - get_db provides the async session
    - get_store_for_user provides the authenticated store
    - get_current_user provides the authenticated user ID
    FastAPI caches duplicate deps, so if get_store_for_user already called
    get_db and get_current_user, they won't be called again.
    """
    return InventoryService(db=db, store=store, user_id=user.id)


def _handle_inventory_error(exc: InventoryError) -> None:
    """
    Convert a domain exception to the appropriate HTTP response.
    Called inside except blocks in every route handler.
    """
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
# LIST PRODUCTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "",
    response_model=ProductListOut,
    summary="List products with pagination and filtering",
    description="""
    Returns a paginated list of products for the authenticated user's store.

    Supports:
    - Full-text search (product title + variant SKU)
    - Filtering by status, category, vendor, product type
    - Low-stock-only mode
    - Sorting by title, created_at, updated_at, status, vendor
    - Configurable page size (max 100)
    """,
)
async def list_products(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, max_length=200, description="Search by title or SKU"),
    status: Optional[str] = Query(None, pattern=r"^(active|archived|draft)$", description="Filter by status"),
    category_id: Optional[uuid.UUID] = Query(None, description="Filter by category"),
    vendor: Optional[str] = Query(None, max_length=255, description="Filter by vendor"),
    product_type: Optional[str] = Query(None, max_length=255, description="Filter by product type"),
    low_stock_only: bool = Query(False, description="Only show products with low-stock variants"),
    sort_by: str = Query("updated_at", description="Sort field: title, created_at, updated_at, status, vendor, product_type"),
    sort_order: str = Query("desc", pattern=r"^(asc|desc)$", description="Sort direction"),
    service: InventoryService = Depends(_get_inventory_service),
):
    """List products with search, filter, sort, and pagination."""
    products, total = await service.list_products(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        category_id=category_id,
        vendor=vendor,
        product_type=product_type,
        low_stock_only=low_stock_only,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return ProductListOut(
        items=[ProductOut.model_validate(p) for p in products],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


# ═══════════════════════════════════════════════════════════════════
# SEARCH PRODUCTS (Advanced)
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/search",
    response_model=ProductListOut,
    summary="Advanced product search",
    description="Same as GET /inventory but accepts additional query parameters for advanced filtering.",
)
async def search_products(
    filters: ProductSearchFilters = Depends(ProductSearchFilters),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("updated_at", description="Sort field"),
    sort_order: str = Query("desc", pattern=r"^(asc|desc)$", description="Sort direction"),
    service: InventoryService = Depends(_get_inventory_service),
):
    """Advanced product search with all filters applied."""
    products, total = await service.list_products(
        page=page,
        page_size=page_size,
        search=filters.search,
        status=filters.status,
        category_id=filters.category_id,
        vendor=filters.vendor,
        product_type=filters.product_type,
        low_stock_only=filters.low_stock_only,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return ProductListOut(
        items=[ProductOut.model_validate(p) for p in products],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


# ═══════════════════════════════════════════════════════════════════
# GET SINGLE PRODUCT
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/{product_id}",
    response_model=ProductOut,
    summary="Get a single product by ID",
    description="Returns a product with all its variants. Validates store ownership.",
)
async def get_product(
    product_id: uuid.UUID,
    service: InventoryService = Depends(_get_inventory_service),
):
    """Get a single product by UUID."""
    try:
        product = await service.get_product(product_id)
    except ProductNotFoundError as exc:
        _handle_inventory_error(exc)

    return ProductOut.model_validate(product)


# ═══════════════════════════════════════════════════════════════════
# CREATE PRODUCT
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "",
    response_model=ProductOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new product locally",
    description="Creates a product in PostgreSQL with optional variants. SKUs are validated for uniqueness within the store.",
)
async def create_product(
    payload: ProductCreateRequest,
    service: InventoryService = Depends(_get_inventory_service),
):
    """Create a product locally (local-first)."""
    try:
        product = await service.create_product(payload)
    except (DuplicateSKUError, ProductNotFoundError) as exc:
        _handle_inventory_error(exc)

    return ProductOut.model_validate(product)


# ═══════════════════════════════════════════════════════════════════
# UPDATE PRODUCT
# ═══════════════════════════════════════════════════════════════════

@router.put(
    "/{product_id}",
    response_model=ProductOut,
    summary="Update a product",
    description="Partially updates a product's scalar fields (PATCH semantics). Variant-level changes handled separately.",
)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdateRequest,
    service: InventoryService = Depends(_get_inventory_service),
):
    """Update a product's scalar fields."""
    try:
        product = await service.update_product(product_id, payload)
    except ProductNotFoundError as exc:
        _handle_inventory_error(exc)

    return ProductOut.model_validate(product)


# ═══════════════════════════════════════════════════════════════════
# DELETE PRODUCT
# ═══════════════════════════════════════════════════════════════════

@router.delete(
    "/{product_id}",
    response_model=DeleteResponse,
    summary="Delete a product",
    description="Deletes a product and all its related data (variants, transactions, logs). Irreversible.",
)
async def delete_product(
    product_id: uuid.UUID,
    service: InventoryService = Depends(_get_inventory_service),
):
    """Delete a product by UUID."""
    try:
        result = await service.delete_product(product_id)
    except ProductNotFoundError as exc:
        _handle_inventory_error(exc)

    return DeleteResponse(**result)


# ═══════════════════════════════════════════════════════════════════
# ADJUST INVENTORY STOCK
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/update-stock",
    response_model=InventoryAdjustResponse,
    summary="Adjust inventory stock for a single variant",
    description="""
    Adjust stock quantity for a single variant.

    - Positive quantity_change = add stock
    - Negative quantity_change = remove stock
    - Will not allow stock to go below zero
    - Creates an immutable audit trail (transaction + log)
    - Attempts to sync the change to Shopify (best-effort)
    """,
)
async def update_stock(
    payload: InventoryAdjustRequest,
    service: InventoryService = Depends(_get_inventory_service),
):
    """Adjust inventory quantity for a single variant."""
    try:
        result = await service.adjust_inventory(
            variant_id=payload.variant_id,
            quantity_change=payload.quantity_change,
            reason=payload.reason,
        )
    except (VariantNotFoundError, InsufficientStockError, InvalidStoreOwnershipError) as exc:
        _handle_inventory_error(exc)

    return InventoryAdjustResponse(**result)


# ═══════════════════════════════════════════════════════════════════
# LOW STOCK
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/low-stock",
    response_model=LowStockListOut,
    summary="Get low stock items",
    description="Returns all variants where inventory quantity is at or below the threshold.",
)
async def get_low_stock(
    threshold: int = Query(10, ge=0, description="Low-stock threshold"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    service: InventoryService = Depends(_get_inventory_service),
):
    """Get all variants with low stock."""
    items, total = await service.get_low_stock(
        threshold=threshold,
        page=page,
        page_size=page_size,
    )
    return LowStockListOut(items=items, total=total)


# ═══════════════════════════════════════════════════════════════════
# TRANSACTION HISTORY
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/history",
    response_model=InventoryHistoryOut,
    summary="Get inventory transaction history",
    description="Returns a paginated audit trail of all inventory changes for the store.",
)
async def get_history(
    variant_id: Optional[uuid.UUID] = Query(None, description="Filter by variant"),
    transaction_type: Optional[str] = Query(None, description="Filter by type (adjustment, sale, purchase, return, transfer, shopify_sync)"),
    date_from: Optional[str] = Query(None, description="Start date (ISO 8601, e.g. 2026-01-01T00:00:00Z)"),
    date_to: Optional[str] = Query(None, description="End date (ISO 8601)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    service: InventoryService = Depends(_get_inventory_service),
):
    """Get paginated inventory transaction history."""
    # Parse ISO date strings to datetime if provided
    dt_from = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
    dt_to = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None

    transactions, total = await service.get_history(
        variant_id=variant_id,
        transaction_type=transaction_type,
        date_from=dt_from,
        date_to=dt_to,
        page=page,
        page_size=page_size,
    )
    return InventoryHistoryOut(
        items=[InventoryTransactionOut.model_validate(t) for t in transactions],
        total=total,
        page=page,
        page_size=page_size,
    )
