"""
API Router for the WooCommerce Integration Module.

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
from app.models import RegisteredStudent

from app.woocommerce.schemas import (
    StoreConnectRequest, StoreUpdateRequest, StoreOut, StoreListOut, StoreVerifyResponse,
    ProductOut, ProductListOut, ProductSearchFilters,
    InventoryAdjustRequest, InventoryAdjustResponse, LowStockListOut, InventoryHistoryOut,
    OrderOut, OrderListOut, OrderSyncRequest,
    CustomerOut, CustomerListOut,
    CategoryOut, CategoryListOut, CategoryTreeOut,
    CouponOut, CouponListOut,
    AlertOut, AlertListOut, AlertMarkRequest,
    DashboardOut, DashboardStats,
    RevenueAnalyticsOut, TopProductsOut, OrderStatusBreakdownOut,
    SettingsOut, SettingsUpdateRequest,
    SyncRequest, SyncResponse, SyncLogOut, SyncLogListOut,
    MessageResponse, BulkImportRequest, BulkImportResponse,
)
from app.woocommerce.service import WooCommerceService
from app.woocommerce.bulk_operations import bulk_import_products, bulk_update_products, parse_csv_to_items, parse_json_to_items
from app.woocommerce.exceptions import (
    WooCommerceError,
    StoreNotFoundError,
    StoreConnectionError,
    StoreAlreadyExistsError,
    StoreInactiveError,
    ProductNotFoundError,
    OrderNotFoundError,
    CustomerNotFoundError,
    CategoryNotFoundError,
    CouponNotFoundError,
    DuplicateSKUError,
    InsufficientStockError,
    InvalidStoreOwnershipError,
    SyncInProgressError,
)

from app.woocommerce.constants import SyncStatus, SyncType
from app.woocommerce.models import WooCommerceSyncLog
from sqlalchemy import func, select

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/woocommerce", tags=["WooCommerce"])


# ═══════════════════════════════════════════════════════════════════
# Error Mapping
# ═══════════════════════════════════════════════════════════════════

_EXCEPTION_TO_STATUS = {
    StoreNotFoundError: status.HTTP_404_NOT_FOUND,
    StoreConnectionError: status.HTTP_400_BAD_REQUEST,
    StoreAlreadyExistsError: status.HTTP_409_CONFLICT,
    StoreInactiveError: status.HTTP_400_BAD_REQUEST,
    ProductNotFoundError: status.HTTP_404_NOT_FOUND,
    OrderNotFoundError: status.HTTP_404_NOT_FOUND,
    CustomerNotFoundError: status.HTTP_404_NOT_FOUND,
    CategoryNotFoundError: status.HTTP_404_NOT_FOUND,
    CouponNotFoundError: status.HTTP_404_NOT_FOUND,
    DuplicateSKUError: status.HTTP_409_CONFLICT,
    InsufficientStockError: status.HTTP_400_BAD_REQUEST,
    InvalidStoreOwnershipError: status.HTTP_403_FORBIDDEN,
    SyncInProgressError: status.HTTP_409_CONFLICT,
}


async def _get_service(
    db: AsyncSession = Depends(get_db),
    user: RegisteredStudent = Depends(get_current_user),
) -> WooCommerceService:
    """Build a WooCommerceService instance with all its dependencies resolved."""
    return WooCommerceService(db=db, user=user)


def _handle_error(exc: WooCommerceError) -> None:
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
# STORE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/stores/connect",
    response_model=dict,
    summary="Connect a WooCommerce store",
    description="Connects and verifies a WooCommerce store using Consumer Key and Consumer Secret.",
    status_code=status.HTTP_201_CREATED,
)
async def connect_store(
    payload: StoreConnectRequest,
    service: WooCommerceService = Depends(_get_service),
):
    """Connect a new WooCommerce store."""
    try:
        result = await service.connect_store(payload)
        return {
            "message": result["message"],
            "store": StoreOut.model_validate(result["store"]),
            "verification": result["verification"],
        }
    except (StoreConnectionError, StoreAlreadyExistsError) as exc:
        _handle_error(exc)


@router.get("/stores", response_model=StoreListOut, summary="List all connected stores")
async def list_stores(
    service: WooCommerceService = Depends(_get_service),
):
    """List all WooCommerce stores for the authenticated user."""
    stores = await service.get_stores()
    return StoreListOut(
        items=[StoreOut.model_validate(s) for s in stores],
        total=len(stores),
    )


@router.get("/stores/{store_id}", response_model=StoreOut, summary="Get store details")
async def get_store(
    store_id: uuid.UUID,
    service: WooCommerceService = Depends(_get_service),
):
    """Get a single store by ID."""
    try:
        store = await service.get_store(store_id)
        return StoreOut.model_validate(store)
    except StoreNotFoundError as exc:
        _handle_error(exc)


@router.put("/stores/{store_id}", response_model=StoreOut, summary="Update store")
async def update_store(
    store_id: uuid.UUID,
    payload: StoreUpdateRequest,
    service: WooCommerceService = Depends(_get_service),
):
    """Update store credentials or name."""
    try:
        store = await service.update_store(store_id, payload)
        return StoreOut.model_validate(store)
    except StoreNotFoundError as exc:
        _handle_error(exc)


@router.delete("/stores/{store_id}", response_model=MessageResponse, summary="Disconnect store")
async def disconnect_store(
    store_id: uuid.UUID,
    service: WooCommerceService = Depends(_get_service),
):
    """Disconnect and deactivate a WooCommerce store."""
    try:
        result = await service.disconnect_store(store_id)
        return MessageResponse(message=result["message"])
    except StoreNotFoundError as exc:
        _handle_error(exc)


@router.post(
    "/stores/{store_id}/verify",
    response_model=StoreVerifyResponse,
    summary="Verify store connection",
)
async def verify_store(
    store_id: uuid.UUID,
    service: WooCommerceService = Depends(_get_service),
):
    """Verify a store's WooCommerce API connection."""
    try:
        result = await service.verify_store_connection(store_id)
        return StoreVerifyResponse(**result)
    except (StoreNotFoundError, StoreConnectionError) as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# PRODUCT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/stores/{store_id}/products",
    response_model=ProductListOut,
    summary="List products",
)
async def list_products(
    store_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, max_length=200),
    status: Optional[str] = Query(None),
    stock_status: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    low_stock_only: bool = Query(False),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    sort_by: str = Query("updated_at"),
    sort_order: str = Query("desc", pattern=r"^(asc|desc)$"),
    service: WooCommerceService = Depends(_get_service),
):
    """List products with filtering, search, and pagination."""
    try:
        products, total = await service.list_products(
            store_id=store_id, page=page, page_size=page_size,
            search=search, status=status, stock_status=stock_status,
            category_id=category_id, low_stock_only=low_stock_only,
            min_price=min_price, max_price=max_price,
            sort_by=sort_by, sort_order=sort_order,
        )
        return ProductListOut(
            items=[ProductOut.model_validate(p) for p in products],
            total=total, page=page, page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
        )
    except StoreNotFoundError as exc:
        _handle_error(exc)


@router.get("/stores/{store_id}/products/{product_id}", response_model=ProductOut, summary="Get product")
async def get_product(
    store_id: uuid.UUID,
    product_id: uuid.UUID,
    service: WooCommerceService = Depends(_get_service),
):
    """Get a single product by ID."""
    try:
        product = await service.get_product(store_id, product_id)
        return ProductOut.model_validate(product)
    except (StoreNotFoundError, ProductNotFoundError) as exc:
        _handle_error(exc)


@router.post(
    "/stores/{store_id}/products/sync",
    response_model=dict,
    summary="Sync products from WooCommerce",
)
async def sync_products(
    store_id: uuid.UUID,
    payload: SyncRequest = SyncRequest(),
    service: WooCommerceService = Depends(_get_service),
):
    """Trigger product synchronization from WooCommerce."""
    try:
        result = await service.sync_products(
            store_id=store_id, force_full=payload.force_full
        )
        return result
    except (StoreNotFoundError, StoreInactiveError, SyncInProgressError) as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# INVENTORY ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/stores/{store_id}/inventory/adjust",
    response_model=InventoryAdjustResponse,
    summary="Adjust inventory stock",
)
async def adjust_inventory(
    store_id: uuid.UUID,
    payload: InventoryAdjustRequest,
    service: WooCommerceService = Depends(_get_service),
):
    """Adjust inventory stock for a product."""
    try:
        result = await service.adjust_inventory(
            store_id=store_id,
            wc_product_id=payload.wc_product_id,
            quantity_change=payload.quantity_change,
            reason=payload.reason,
        )
        return InventoryAdjustResponse(**result)
    except (StoreNotFoundError, ProductNotFoundError, InsufficientStockError) as exc:
        _handle_error(exc)


@router.get(
    "/stores/{store_id}/inventory/low-stock",
    response_model=LowStockListOut,
    summary="Get low stock items",
)
async def get_low_stock(
    store_id: uuid.UUID,
    threshold: int = Query(10, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    service: WooCommerceService = Depends(_get_service),
):
    """Get all products with low stock."""
    try:
        items, total = await service.get_low_stock(
            store_id=store_id, threshold=threshold, page=page, page_size=page_size
        )
        return LowStockListOut(items=items, total=total)
    except StoreNotFoundError as exc:
        _handle_error(exc)


@router.get(
    "/stores/{store_id}/inventory/history",
    response_model=dict,
    summary="Get inventory change history",
)
async def get_inventory_history(
    store_id: uuid.UUID,
    product_id: Optional[uuid.UUID] = Query(None),
    action: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: WooCommerceService = Depends(_get_service),
):
    """Get inventory change history with audit trail."""
    try:
        dt_from = datetime.fromisoformat(date_from.replace("Z", "+00:00")) if date_from else None
        dt_to = datetime.fromisoformat(date_to.replace("Z", "+00:00")) if date_to else None

        logs, total = await service.get_inventory_history(
            store_id=store_id, product_id=product_id, action=action,
            date_from=dt_from, date_to=dt_to, page=page, page_size=page_size,
        )
        return {
            "items": [InventoryHistoryOut.model_validate(l) for l in logs],
            "total": total, "page": page, "page_size": page_size,
        }
    except StoreNotFoundError as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# ORDER ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/stores/{store_id}/orders",
    response_model=OrderListOut,
    summary="List orders",
)
async def list_orders(
    store_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=200),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc", pattern=r"^(asc|desc)$"),
    service: WooCommerceService = Depends(_get_service),
):
    """List orders with filtering and pagination."""
    try:
        orders, total = await service.list_orders(
            store_id=store_id, page=page, page_size=page_size,
            status=status, search=search,
            sort_by=sort_by, sort_order=sort_order,
        )
        return OrderListOut(
            items=[OrderOut.model_validate(o) for o in orders],
            total=total, page=page, page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
        )
    except StoreNotFoundError as exc:
        _handle_error(exc)


@router.get("/stores/{store_id}/orders/{order_id}", response_model=OrderOut, summary="Get order")
async def get_order(
    store_id: uuid.UUID,
    order_id: uuid.UUID,
    service: WooCommerceService = Depends(_get_service),
):
    """Get a single order by ID."""
    try:
        order = await service.get_order(store_id, order_id)
        return OrderOut.model_validate(order)
    except (StoreNotFoundError, OrderNotFoundError) as exc:
        _handle_error(exc)


@router.post(
    "/stores/{store_id}/orders/sync",
    response_model=dict,
    summary="Sync orders from WooCommerce",
)
async def sync_orders(
    store_id: uuid.UUID,
    payload: OrderSyncRequest = OrderSyncRequest(),
    service: WooCommerceService = Depends(_get_service),
):
    """Trigger order synchronization from WooCommerce."""
    try:
        result = await service.sync_orders(
            store_id=store_id,
            date_after=payload.date_after,
            status=payload.status,
        )
        return result
    except (StoreNotFoundError, StoreInactiveError) as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# CUSTOMER ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/stores/{store_id}/customers",
    response_model=CustomerListOut,
    summary="List customers",
)
async def list_customers(
    store_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, max_length=200),
    service: WooCommerceService = Depends(_get_service),
):
    """List customers with pagination."""
    try:
        customers, total = await service.list_customers(
            store_id=store_id, page=page, page_size=page_size, search=search
        )
        return CustomerListOut(
            items=[CustomerOut.model_validate(c) for c in customers],
            total=total, page=page, page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total > 0 else 0,
        )
    except StoreNotFoundError as exc:
        _handle_error(exc)


@router.get("/stores/{store_id}/customers/{customer_id}", response_model=CustomerOut, summary="Get customer")
async def get_customer(
    store_id: uuid.UUID,
    customer_id: uuid.UUID,
    service: WooCommerceService = Depends(_get_service),
):
    """Get a single customer by ID."""
    try:
        customer = await service.get_customer(store_id, customer_id)
        return CustomerOut.model_validate(customer)
    except (StoreNotFoundError, CustomerNotFoundError) as exc:
        _handle_error(exc)


@router.post(
    "/stores/{store_id}/customers/sync",
    response_model=dict,
    summary="Sync customers from WooCommerce",
)
async def sync_customers(
    store_id: uuid.UUID,
    service: WooCommerceService = Depends(_get_service),
):
    """Trigger customer synchronization from WooCommerce."""
    try:
        result = await service.sync_customers(store_id=store_id)
        return result
    except (StoreNotFoundError, StoreInactiveError) as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# CATEGORY ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/stores/{store_id}/categories",
    response_model=CategoryListOut,
    summary="List categories",
)
async def list_categories(
    store_id: uuid.UUID,
    service: WooCommerceService = Depends(_get_service),
):
    """List all categories for a store."""
    try:
        categories = await service.list_categories(store_id=store_id)
        return CategoryListOut(
            items=[CategoryOut.model_validate(c) for c in categories],
            total=len(categories),
        )
    except StoreNotFoundError as exc:
        _handle_error(exc)


@router.get(
    "/stores/{store_id}/categories/tree",
    response_model=list[CategoryTreeOut],
    summary="Get category tree",
)
async def get_category_tree(
    store_id: uuid.UUID,
    service: WooCommerceService = Depends(_get_service),
):
    """Get hierarchical category tree."""
    try:
        tree = await service.get_category_tree(store_id=store_id)
        return tree
    except StoreNotFoundError as exc:
        _handle_error(exc)


@router.post(
    "/stores/{store_id}/categories/sync",
    response_model=dict,
    summary="Sync categories from WooCommerce",
)
async def sync_categories(
    store_id: uuid.UUID,
    service: WooCommerceService = Depends(_get_service),
):
    """Trigger category synchronization from WooCommerce."""
    try:
        result = await service.sync_categories(store_id=store_id)
        return result
    except (StoreNotFoundError, StoreInactiveError) as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# COUPON ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/stores/{store_id}/coupons",
    response_model=CouponListOut,
    summary="List coupons",
)
async def list_coupons(
    store_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: WooCommerceService = Depends(_get_service),
):
    """List coupons with pagination."""
    try:
        coupons, total = await service.list_coupons(
            store_id=store_id, page=page, page_size=page_size
        )
        return CouponListOut(
            items=[CouponOut.model_validate(c) for c in coupons],
            total=total,
        )
    except StoreNotFoundError as exc:
        _handle_error(exc)


@router.get("/stores/{store_id}/coupons/{coupon_id}", response_model=CouponOut, summary="Get coupon")
async def get_coupon(
    store_id: uuid.UUID,
    coupon_id: uuid.UUID,
    service: WooCommerceService = Depends(_get_service),
):
    """Get a single coupon by ID."""
    try:
        coupon = await service.get_coupon(store_id, coupon_id)
        return CouponOut.model_validate(coupon)
    except (StoreNotFoundError, CouponNotFoundError) as exc:
        _handle_error(exc)


@router.post(
    "/stores/{store_id}/coupons/sync",
    response_model=dict,
    summary="Sync coupons from WooCommerce",
)
async def sync_coupons(
    store_id: uuid.UUID,
    service: WooCommerceService = Depends(_get_service),
):
    """Trigger coupon synchronization from WooCommerce."""
    try:
        result = await service.sync_coupons(store_id=store_id)
        return result
    except (StoreNotFoundError, StoreInactiveError) as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# DASHBOARD ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/stores/{store_id}/dashboard",
    response_model=DashboardOut,
    summary="Get dashboard data",
)
async def get_dashboard(
    store_id: uuid.UUID,
    service: WooCommerceService = Depends(_get_service),
):
    """Get comprehensive dashboard data for a store."""
    try:
        data = await service.get_dashboard(store_id=store_id)
        return DashboardOut(**data)
    except StoreNotFoundError as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# ANALYTICS ENDPOINTS (Revenue Dashboard / Advanced Analytics)
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/stores/{store_id}/analytics/revenue",
    response_model=RevenueAnalyticsOut,
    summary="Get revenue trend and summary analytics",
)
async def get_revenue_analytics(
    store_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365, description="Size of the analysis period, in days"),
    service: WooCommerceService = Depends(_get_service),
):
    """Revenue trend (daily) + summary for `days` days, compared to the prior period of equal length."""
    try:
        data = await service.get_revenue_analytics(store_id=store_id, days=days)
        return RevenueAnalyticsOut(**data)
    except (StoreNotFoundError, StoreInactiveError) as exc:
        _handle_error(exc)


@router.get(
    "/stores/{store_id}/analytics/top-products",
    response_model=TopProductsOut,
    summary="Get top products by realized revenue",
)
async def get_top_products_analytics(
    store_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    service: WooCommerceService = Depends(_get_service),
):
    """Top products by realized order-item revenue over `days` days."""
    try:
        products = await service.get_top_products(store_id=store_id, days=days, limit=limit)
        return TopProductsOut(products=products)
    except (StoreNotFoundError, StoreInactiveError) as exc:
        _handle_error(exc)


@router.get(
    "/stores/{store_id}/analytics/order-status",
    response_model=OrderStatusBreakdownOut,
    summary="Get order counts grouped by status",
)
async def get_order_status_analytics(
    store_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365),
    service: WooCommerceService = Depends(_get_service),
):
    """Order counts grouped by status over `days` days (operational health view)."""
    try:
        breakdown = await service.get_order_status_breakdown(store_id=store_id, days=days)
        return OrderStatusBreakdownOut(period_days=days, breakdown=breakdown)
    except (StoreNotFoundError, StoreInactiveError) as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# ALERT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/stores/{store_id}/alerts",
    response_model=AlertListOut,
    summary="List alerts",
)
async def list_alerts(
    store_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
    unresolved_only: bool = Query(False),
    alert_type: Optional[str] = Query(None),
    service: WooCommerceService = Depends(_get_service),
):
    """List alerts with filtering and pagination."""
    try:
        alerts, total, unread_count = await service.list_alerts(
            store_id=store_id, page=page, page_size=page_size,
            unread_only=unread_only, unresolved_only=unresolved_only,
            alert_type=alert_type,
        )
        return AlertListOut(
            items=[AlertOut.model_validate(a) for a in alerts],
            total=total, unread_count=unread_count,
        )
    except StoreNotFoundError as exc:
        _handle_error(exc)


@router.post(
    "/stores/{store_id}/alerts/mark",
    response_model=MessageResponse,
    summary="Mark alerts as read/resolved",
)
async def mark_alerts(
    store_id: uuid.UUID,
    payload: AlertMarkRequest,
    service: WooCommerceService = Depends(_get_service),
):
    """Mark alerts as read or resolved."""
    try:
        await service.mark_alerts(
            store_id=store_id,
            alert_ids=payload.alert_ids,
            mark_as_read=payload.mark_as_read,
            mark_as_resolved=payload.mark_as_resolved,
        )
        return MessageResponse(message=f"{len(payload.alert_ids)} alert(s) updated")
    except StoreNotFoundError as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# SETTINGS ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/stores/{store_id}/settings",
    response_model=SettingsOut,
    summary="Get store settings",
)
async def get_settings(
    store_id: uuid.UUID,
    service: WooCommerceService = Depends(_get_service),
):
    """Get store-specific settings."""
    try:
        settings = await service.get_settings(store_id=store_id)
        return SettingsOut.model_validate(settings)
    except StoreNotFoundError as exc:
        _handle_error(exc)


@router.put(
    "/stores/{store_id}/settings",
    response_model=SettingsOut,
    summary="Update store settings",
)
async def update_settings(
    store_id: uuid.UUID,
    payload: SettingsUpdateRequest,
    service: WooCommerceService = Depends(_get_service),
):
    """Update store-specific settings."""
    try:
        settings = await service.update_settings(store_id=store_id, data=payload)
        return SettingsOut.model_validate(settings)
    except StoreNotFoundError as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# SYNC ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/stores/{store_id}/sync",
    response_model=dict,
    summary="Sync all resources from WooCommerce",
)
async def sync_all(
    store_id: uuid.UUID,
    payload: SyncRequest = SyncRequest(),
    service: WooCommerceService = Depends(_get_service),
):
    """Trigger synchronization of all selected resources."""
    try:
        results = {}
        for resource in payload.resources:
            if resource == "products":
                results[resource] = await service.sync_products(store_id, force_full=payload.force_full)
            elif resource == "orders":
                results[resource] = await service.sync_orders(store_id)
            elif resource == "customers":
                results[resource] = await service.sync_customers(store_id)
            elif resource == "categories":
                results[resource] = await service.sync_categories(store_id)
            elif resource == "coupons":
                results[resource] = await service.sync_coupons(store_id)

        return {
            "status": "completed",
            "store_id": str(store_id),
            "results": results,
        }
    except (StoreNotFoundError, StoreInactiveError) as exc:
        _handle_error(exc)


@router.get(
    "/stores/{store_id}/sync-logs",
    response_model=SyncLogListOut,
    summary="Get sync logs",
)
async def get_sync_logs(
    store_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    resource: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    service: WooCommerceService = Depends(_get_service),
):
    """Get sync operation history."""
    try:
        from app.woocommerce.sync_service import get_sync_logs
        logs, total = await get_sync_logs(service, store_id, page, page_size, resource, status)
        return SyncLogListOut(
            items=[SyncLogOut.model_validate(l) for l in logs],
            total=total,
        )
    except StoreNotFoundError as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# WEBHOOK REGISTRATION
# ═══════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════
# STORE HEALTH ENDPOINT
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/stores/{store_id}/health",
    response_model=dict,
    summary="Get store health status",
    description="""
    Runs a comprehensive health check on a WooCommerce store connection.

    Checks:
    - Store status (active/inactive)
    - WooCommerce API connectivity
    - Sync freshness (last sync time)
    - Last sync status
    - Data freshness (stale products)
    - Webhook registration status
    - Failed syncs in last 24h

    Returns an overall status ('pass', 'warn', 'fail') and recommendations.
    """,
)
async def get_store_health(
    store_id: uuid.UUID,
    service: WooCommerceService = Depends(_get_service),
):
    """Run comprehensive health check on a store."""
    try:
        from app.woocommerce.health import get_store_health as health_check
        result = await health_check(
            db=service.db,
            store_id=store_id,
            user_id=service.user_id,
        )
        return result
    except StoreNotFoundError as exc:
        _handle_error(exc)


@router.post(
    "/stores/{store_id}/webhooks/register",
    response_model=dict,
    summary="Register WooCommerce webhooks",
)
async def register_webhooks(
    store_id: uuid.UUID,
    callback_url: str = Query(..., description="Public callback URL for webhooks"),
    service: WooCommerceService = Depends(_get_service),
):
    """Register all required webhooks with WooCommerce."""
    try:
        store = await service.get_store(store_id)
        from app.woocommerce.client import WooCommerceClient
        client = WooCommerceClient(
            store_url=store.store_url,
            consumer_key=store.consumer_key,
            consumer_secret=store.consumer_secret,
        )
        results = await client.register_required_webhooks(callback_url)
        await client.close()

        store.webhooks_registered = True
        await service.db.commit()

        return {
            "message": "Webhook registration completed",
            "results": results,
            "total": len(results),
            "succeeded": sum(1 for r in results if r["status"] == "created"),
            "failed": sum(1 for r in results if r["status"] == "failed"),
        }
    except (StoreNotFoundError, StoreConnectionError) as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# BULK IMPORT / UPDATE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/stores/{store_id}/products/bulk-import",
    response_model=BulkImportResponse,
    summary="Bulk import products",
    description="""
    Import or update multiple products at once.

    Accepts JSON array of products. Matches existing products by SKU or wc_product_id.
    Creates new products if no match is found. Supports up to 5000 products per request.

    Required fields per item: name, and either sku or wc_product_id.
    Optional fields: price, regular_price, sale_price, stock_quantity, stock_status,
                     manage_stock, description, short_description, weight, barcode,
                     status, type, featured_image_url, tax_status, tax_class, backorders.
    """,
)
async def bulk_import_products_endpoint(
    store_id: uuid.UUID,
    payload: BulkImportRequest,
    service: WooCommerceService = Depends(_get_service),
):
    """Bulk import or update products."""
    try:
        # Parse items from request
        if payload.raw_data:
            if payload.format == "csv":
                items = parse_csv_to_items(payload.raw_data)
            else:
                items = parse_json_to_items(payload.raw_data)
        else:
            items = [item.model_dump(exclude_none=True) for item in payload.items]

        result = await bulk_import_products(
            db=service.db,
            store_id=store_id,
            items=items,
            user_id=service.user_id,
        )
        return BulkImportResponse(**result.to_dict())

    except (StoreNotFoundError, StoreInactiveError, ValueError) as exc:
        if isinstance(exc, (StoreNotFoundError, StoreInactiveError)):
            _handle_error(exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/stores/{store_id}/products/bulk-update",
    response_model=BulkImportResponse,
    summary="Bulk update products",
    description="""
    Update multiple existing products at once. Only updates fields provided.
    Matches by SKU or wc_product_id. Does NOT create new products.

    Supports up to 5000 products per request.
    """,
)
async def bulk_update_products_endpoint(
    store_id: uuid.UUID,
    payload: BulkImportRequest,
    service: WooCommerceService = Depends(_get_service),
):
    """Bulk update existing products."""
    try:
        # Parse items
        if payload.raw_data:
            if payload.format == "csv":
                items = parse_csv_to_items(payload.raw_data)
            else:
                items = parse_json_to_items(payload.raw_data)
        else:
            items = [item.model_dump(exclude_none=True) for item in payload.items]

        result = await bulk_update_products(
            db=service.db,
            store_id=store_id,
            items=items,
            user_id=service.user_id,
        )
        return BulkImportResponse(**result.to_dict())

    except (StoreNotFoundError, StoreInactiveError, ValueError) as exc:
        if isinstance(exc, (StoreNotFoundError, StoreInactiveError)):
            _handle_error(exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
