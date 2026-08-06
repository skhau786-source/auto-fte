"""
API Router for the Shopify Integration Module.

Thin router layer — all business logic lives in the service layer
(InventoryService) or the Shopify client (ShopifyClient).
Domain exceptions from the services are caught and converted to HTTP responses.

Follows the same architecture and conventions as the WooCommerce module
(app.woocommerce.router).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.inventory.dependencies import get_store_for_user
from app.inventory.exceptions import (
    InvalidStoreOwnershipError,
    InventoryError,
    ShopifySyncError,
    StoreNotFoundError,
)
from app.inventory.schemas import (
    ProductListOut,
    ProductOut,
    StoreOut,
    SyncRequest,
)
from app.inventory.service import InventoryService
from app.models import RegisteredStudent, Store
from app.shopify.shopify_client import ShopifyClient
from app.shopify.webhook_registration import register_webhooks

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/shopify", tags=["Shopify"])


# ═══════════════════════════════════════════════════════════════════
# Request Schemas
# ═══════════════════════════════════════════════════════════════════


class ShopifyConnectRequest(BaseModel):
    """Request body for POST /shopify/connect."""

    shop_domain: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="The store's myshopify.com domain (e.g. my-store.myshopify.com).",
    )
    access_token: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="Shopify API access token (typically starts with 'shpat_').",
    )
    shopify_store_id: int | None = Field(
        None, description="Optional Shopify numeric store ID."
    )
    location_id: int | None = Field(
        None, description="Optional Shopify location ID. Auto-detected if omitted."
    )
    app_base_url: str | None = Field(
        None,
        max_length=512,
        description=(
            "Public base URL of the app (e.g. https://app.example.com). "
            "If provided, required webhooks are registered automatically."
        ),
    )

    @field_validator("shop_domain")
    @classmethod
    def normalize_shop_domain(cls, v: str) -> str:
        """Strip scheme/www and normalize to a bare domain."""
        domain = v.strip().lower().rstrip("/")
        if "://" in domain or domain.startswith("www."):
            raise ValueError(
                "shop_domain must be a bare domain (e.g. my-store.myshopify.com)"
            )
        return domain

    @field_validator("app_base_url")
    @classmethod
    def normalize_app_base_url(cls, v: str | None) -> str | None:
        """Remove trailing slashes from the public base URL."""
        if v is None:
            return v
        return v.strip().rstrip("/")


# ═══════════════════════════════════════════════════════════════════
# Error Mapping
# ═══════════════════════════════════════════════════════════════════

_EXCEPTION_TO_STATUS = {
    StoreNotFoundError: status.HTTP_404_NOT_FOUND,
    ShopifySyncError: status.HTTP_502_BAD_GATEWAY,
    InvalidStoreOwnershipError: status.HTTP_403_FORBIDDEN,
}


def _handle_error(exc: InventoryError) -> None:
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


async def _get_inventory_service(
    db: AsyncSession = Depends(get_db),
    store: Store = Depends(get_store_for_user),
    user: RegisteredStudent = Depends(get_current_user),
) -> InventoryService:
    """Build an InventoryService instance with all its dependencies resolved."""
    return InventoryService(db=db, store=store, user_id=user.id)


# ═══════════════════════════════════════════════════════════════════
# CONNECT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/connect",
    response_model=dict,
    summary="Connect a Shopify store",
    description="""
    Connects and verifies a Shopify store using an access token.

    - Verifies connectivity by querying the Shopify Locations API
    - Creates or updates the Store record for the authenticated user
    - Auto-detects the primary location when no location_id is provided
    - Optionally registers required webhooks when app_base_url is provided
    """,
    status_code=status.HTTP_201_CREATED,
)
async def connect_shopify_store(
    payload: ShopifyConnectRequest,
    db: AsyncSession = Depends(get_db),
    user: RegisteredStudent = Depends(get_current_user),
):
    """Connect a new (or re-connect an existing) Shopify store."""
    # ── Verify connectivity ──
    client = ShopifyClient(
        shop_domain=payload.shop_domain,
        access_token=payload.access_token,
        location_id=payload.location_id,
    )
    try:
        locations = await client.fetch_locations()
        location_id = payload.location_id
        if location_id is None and locations:
            location_id = await client.get_primary_location_id()
    except ShopifySyncError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": f"Shopify connection failed: {exc.message}",
                "error_code": "SHOPIFY_CONNECTION_ERROR",
            },
        )
    finally:
        await client.close()

    # ── Upsert the Store record ──
    result = await db.execute(
        select(Store).where(Store.shopify_domain == payload.shop_domain)
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        if existing.owner_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "This Shopify store is already connected to another account",
                    "error_code": "STORE_ALREADY_EXISTS",
                },
            )
        existing.access_token = payload.access_token
        if payload.shopify_store_id is not None:
            existing.shopify_store_id = payload.shopify_store_id
        if location_id is not None:
            existing.shopify_location_id = location_id
        existing.is_active = True
        store = existing
    else:
        store = Store(
            owner_id=user.id,
            shopify_domain=payload.shop_domain,
            access_token=payload.access_token,
            shopify_store_id=payload.shopify_store_id,
            shopify_location_id=location_id,
            is_active=True,
        )
        db.add(store)

    await db.commit()
    await db.refresh(store)

    # ── Optional: register webhooks ──
    webhook_results = None
    if payload.app_base_url:
        webhook_results = await register_webhooks(
            shop_domain=store.shopify_domain,
            access_token=store.access_token,
            app_base_url=payload.app_base_url,
        )

    return {
        "message": "Shopify store connected successfully",
        "store": StoreOut.model_validate(store),
        "verification": {
            "status": "connected",
            "locations_found": len(locations),
            "location_id": location_id,
        },
        "webhooks": webhook_results,
    }


# ═══════════════════════════════════════════════════════════════════
# STATUS ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/status",
    response_model=dict,
    summary="Get Shopify store connection status",
    description="Returns the connection details of the authenticated user's active Shopify store.",
)
async def get_status(
    store: Store = Depends(get_store_for_user),
):
    """Get the current Shopify store connection status."""
    return {
        "connected": store.is_active,
        "shopify_domain": store.shopify_domain,
        "shopify_store_id": store.shopify_store_id,
        "shopify_location_id": store.shopify_location_id,
        "created_at": store.created_at.isoformat() if store.created_at else None,
        "updated_at": store.updated_at.isoformat() if store.updated_at else None,
    }


# ═══════════════════════════════════════════════════════════════════
# SYNC ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/sync",
    response_model=dict,
    summary="Sync products and inventory from Shopify",
    description="Triggers a full product/variant/inventory synchronization from Shopify into the local database.",
)
async def sync_products(
    payload: SyncRequest = SyncRequest(),
    service: InventoryService = Depends(_get_inventory_service),
):
    """Trigger product synchronization from Shopify."""
    try:
        result = await service.sync_from_shopify(force_full=payload.force_full)
    except (ShopifySyncError, StoreNotFoundError) as exc:
        _handle_error(exc)

    return {
        "status": "completed",
        "store_id": str(service.store.id),
        "results": result,
    }


# ═══════════════════════════════════════════════════════════════════
# PRODUCT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/products",
    response_model=ProductListOut,
    summary="List synced products",
    description="Returns a paginated list of locally synced products for the authenticated store.",
)
async def list_products(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: str | None = Query(None, max_length=200, description="Search by title or SKU"),
    status: str | None = Query(None, pattern=r"^(active|archived|draft)$", description="Filter by status"),
    low_stock_only: bool = Query(False, description="Only show products with low-stock variants"),
    sort_by: str = Query("updated_at", description="Sort field: title, created_at, updated_at, status, vendor, product_type"),
    sort_order: str = Query("desc", pattern=r"^(asc|desc)$", description="Sort direction"),
    service: InventoryService = Depends(_get_inventory_service),
):
    """List locally synced products with filtering and pagination."""
    products, total = await service.list_products(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
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
# INVENTORY ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/inventory",
    response_model=dict,
    summary="Get inventory snapshot",
    description="Returns aggregate inventory metrics and sync health for the authenticated store.",
)
async def get_inventory_snapshot(
    store: Store = Depends(get_store_for_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an aggregate inventory snapshot for the store."""
    from app.dashboard.dashboard_service import DashboardService

    dashboard = await DashboardService(db=db, store=store).get_dashboard()
    summary = dashboard.inventory_summary
    sync_health = dashboard.sync_health
    webhook_health = dashboard.webhook_health

    return {
        "total_products": summary.total_products,
        "total_variants": summary.total_variants,
        "total_inventory_units": summary.total_inventory_units,
        "total_inventory_value": str(summary.total_inventory_value),
        "low_stock_count": summary.low_stock_count,
        "out_of_stock_count": summary.out_of_stock_count,
        "pending_syncs": sync_health.pending_syncs,
        "failed_syncs": sync_health.failed_syncs,
        "last_sync_at": sync_health.last_sync_at.isoformat() if sync_health.last_sync_at else None,
        "last_sync_status": sync_health.last_sync_status,
        "webhooks_registered": webhook_health.webhooks_registered,
    }


# ═══════════════════════════════════════════════════════════════════
# LOCATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/locations",
    response_model=dict,
    summary="List Shopify locations",
    description="Fetches the live list of locations from the Shopify API for the authenticated store.",
)
async def get_locations(
    store: Store = Depends(get_store_for_user),
):
    """Fetch the store's locations directly from Shopify."""
    client = ShopifyClient(
        shop_domain=store.shopify_domain,
        access_token=store.access_token,
        location_id=store.shopify_location_id,
    )
    try:
        locations = await client.fetch_locations()
    except ShopifySyncError as exc:
        _handle_error(exc)
    finally:
        await client.close()

    return {"locations": locations, "total": len(locations)}


# ═══════════════════════════════════════════════════════════════════
# WEBHOOK REGISTRATION
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/register-webhooks",
    response_model=dict,
    summary="Register Shopify webhooks",
    description="""
    Registers all required Shopify webhooks (products/update, inventory_levels/update,
    app/uninstalled) for the authenticated store using the public app base URL.
    """,
)
async def register_webhooks_endpoint(
    app_base_url: str = Query(
        ...,
        min_length=1,
        max_length=512,
        description="Public base URL of the app (e.g. https://app.example.com).",
    ),
    store: Store = Depends(get_store_for_user),
):
    """Register all required webhooks with Shopify."""
    try:
        results = await register_webhooks(
            shop_domain=store.shopify_domain,
            access_token=store.access_token,
            app_base_url=app_base_url,
        )
    except ShopifySyncError as exc:
        _handle_error(exc)

    return {
        "message": "Webhook registration completed",
        "results": results,
        "total": len(results),
        "succeeded": sum(1 for v in results.values() if not str(v).startswith("error")),
        "failed": sum(1 for v in results.values() if str(v).startswith("error")),
    }
