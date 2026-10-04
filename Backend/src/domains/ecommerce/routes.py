# ═══════════════════════════════════════════════════════════════
# src / domains / ecommerce / routes.py
#
# PURPOSE: REST API router — MULTI-PLATFORM STORE CONNECT.
#          Stores user-scoped hain (JWT auth via get_current_user).
# ═══════════════════════════════════════════════════════════════

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.sdk.database import get_db
from src.sdk.config import get_settings
from src.sdk.models.base import Store, Product, Variant, Order, OrderItem, LowStockAlert
from src.sdk.platforms import PlatformRegistry, PlatformAuth
from src.sdk.oauth.tokens import TokenManager

from src.dependencies import get_event_bus
from src.domains.ecommerce.event_publisher import EventPublisher
from src.domains.auth.service import get_current_user
from src.domains.auth.models import User

limiter = Limiter(key_func=get_remote_address)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Multi-Platform"])

token_mgr = TokenManager()


# --- Helper: Get store or return 404 (user-scoped) ---

async def _get_store_or_404(db: AsyncSession, store_id: int, user_id: int) -> Store:
    result = await db.execute(
        select(Store).where(Store.id == store_id, Store.user_id == user_id)
    )
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


# --- Pydantic Models ---

class StoreConnectRequest(BaseModel):
    platform: str = "shopify"          # "shopify", "woocommerce", "amazon", "daraz", etc.
    name: str = ""                     # Human-readable store name
    api_key: str = ""                  # For WooCommerce-style (consumer key)
    api_secret: str = ""               # For WooCommerce-style (consumer secret)
    access_token: str = ""             # For direct token entry (Shopify)
    shop_name: str = ""                # Legacy Shopify shop name
    store_url: str = ""                # For self-hosted (WooCommerce)
    redirect_uri: str = ""             # OAuth callback override


class StoreResponse(BaseModel):
    id: int
    name: str
    platform: str
    platform_store_id: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncSummary(BaseModel):
    status: str = "accepted"
    message: str = "Sync queued - agent will process asynchronously"


class StoreStats(BaseModel):
    store: str
    platform: str
    total_products: int
    total_orders: int
    last_sync: Optional[datetime] = None
    low_stock_count: int


# ================================================================
# STORE MANAGEMENT
# ================================================================

@router.post("/stores/connect", response_model=StoreResponse)
async def connect_store(
    body: StoreConnectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Connect ANY e-commerce store.

    Supported platforms: shopify, woocommerce, bigcommerce, amazon, daraz
    User provides platform + credentials -> system validates -> saves.
    """
    platform = body.platform.lower().strip()

    if not PlatformRegistry.is_supported(platform):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported platform '{platform}'. Supported: {PlatformRegistry.list_platforms()}"
        )

    auth = PlatformAuth(
        platform=platform,
        store_id=0,
        access_token=body.access_token,
        api_key=body.api_key,
        api_secret=body.api_secret,
        store_url=body.store_url,
    )

    try:
        connector = PlatformRegistry.get_connector(platform)
        valid = await connector.verify_credentials(auth)
        if not valid:
            raise HTTPException(status_code=401, detail=f"Invalid credentials for {platform}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Credential check failed for {platform}: {e}")
        raise HTTPException(status_code=502, detail=f"Could not verify {platform} credentials")

    platform_store_id = body.store_url or body.shop_name
    store_name = body.name or platform_store_id or f"{platform}-store"

    existing = None
    if platform_store_id:
        result = await db.execute(
            select(Store).where(
                Store.platform == platform,
                Store.platform_store_id == platform_store_id,
                Store.user_id == current_user.id,
            )
        )
        existing = result.scalar_one_or_none()

    if existing:
        existing.access_token = token_mgr.encrypt(body.access_token)
        if body.api_key:
            existing.refresh_token = token_mgr.encrypt(body.api_key)
        existing.is_active = True
        existing.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
        return existing

    settings = get_settings()
    store = Store(
        user_id=current_user.id,
        platform=platform,
        name=store_name,
        platform_store_id=platform_store_id,
        access_token=token_mgr.encrypt(body.access_token) if body.access_token else "",
        shop_name=body.shop_name or store_name,
        shop_domain=f"{body.shop_name}.myshopify.com" if body.shop_name and platform == "shopify" else None,
    )
    db.add(store)
    await db.commit()
    await db.refresh(store)
    logger.info(f"Store connected: {store_name} ({platform}, id={store.id}, user={current_user.id})")
    return store


@router.get("/stores", response_model=list[StoreResponse])
async def list_stores(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all active connected stores for the logged-in user."""
    result = await db.execute(
        select(Store).where(Store.is_active == True, Store.user_id == current_user.id)
    )
    return result.scalars().all()


@router.get("/stores/{store_id}", response_model=StoreResponse)
async def get_store(
    store_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single store by ID."""
    return await _get_store_or_404(db, store_id, current_user.id)


@router.get("/platforms")
async def list_platforms():
    """List all supported e-commerce platforms."""
    return {
        "platforms": PlatformRegistry.list_platforms(),
        "count": len(PlatformRegistry.list_platforms()),
    }


@router.delete("/stores/{store_id}")
async def disconnect_store(
    store_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete a store (is_active=False)."""
    store = await _get_store_or_404(db, store_id, current_user.id)
    store.is_active = False
    await db.commit()
    return {"status": "disconnected", "platform": store.platform}


# ================================================================
# SYNC ACTIONS (Async via Event Bus)
# ================================================================

@router.post("/stores/{store_id}/sync", status_code=202, response_model=SyncSummary)
@limiter.limit("10/minute")
async def trigger_full_sync(
    request: Request,
    store_id: int,
    db: AsyncSession = Depends(get_db),
    bus=Depends(get_event_bus),
    current_user: User = Depends(get_current_user),
):
    """Request full sync - queued for async processing."""
    store = await _get_store_or_404(db, store_id, current_user.id)
    publisher = EventPublisher(bus)
    await publisher.publish_sync_request(store_id, "full")
    logger.info(f"Full sync queued for store {store_id} ({store.platform})")
    return SyncSummary()


@router.post("/stores/{store_id}/sync/products", status_code=202, response_model=SyncSummary)
@limiter.limit("10/minute")
async def sync_products(
    request: Request,
    store_id: int,
    db: AsyncSession = Depends(get_db),
    bus=Depends(get_event_bus),
    current_user: User = Depends(get_current_user),
):
    """Request product-only sync."""
    await _get_store_or_404(db, store_id, current_user.id)
    publisher = EventPublisher(bus)
    await publisher.publish_sync_request(store_id, "products")
    return SyncSummary()


@router.post("/stores/{store_id}/sync/orders", status_code=202, response_model=SyncSummary)
@limiter.limit("10/minute")
async def sync_orders(
    request: Request,
    store_id: int,
    since_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    bus=Depends(get_event_bus),
    current_user: User = Depends(get_current_user),
):
    """Request orders sync."""
    await _get_store_or_404(db, store_id, current_user.id)
    publisher = EventPublisher(bus)
    await publisher.publish_sync_request(store_id, "orders", since_days)
    return SyncSummary()


# ================================================================
# STATS
# ================================================================

@router.get("/stores/{store_id}/stats", response_model=StoreStats)
async def get_stats(
    store_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregated store statistics."""
    store = await _get_store_or_404(db, store_id, current_user.id)

    prod_count = (await db.execute(
        select(func.count(Product.id)).where(Product.store_id == store_id)
    )).scalar() or 0

    order_count = (await db.execute(
        select(func.count(Order.id)).where(Order.store_id == store_id)
    )).scalar() or 0

    low_count = (await db.execute(
        select(func.count(LowStockAlert.id)).where(
            LowStockAlert.store_id == store_id,
            LowStockAlert.is_resolved == False,
        )
    )).scalar() or 0

    return StoreStats(
        store=store.name or store.platform_store_id or store.shop_domain or "",
        platform=store.platform,
        total_products=prod_count,
        total_orders=order_count,
        last_sync=store.updated_at,
        low_stock_count=low_count,
    )


# ================================================================
# PRODUCTS
# ================================================================

class VariantOut(BaseModel):
    id: int
    platform_variant_id: Optional[str] = None
    title: str
    sku: str
    price: float
    compare_at_price: Optional[float] = None
    inventory_quantity: int
    low_stock_threshold: int
    model_config = ConfigDict(from_attributes=True)


class ProductOut(BaseModel):
    id: int
    platform_product_id: Optional[str] = None
    title: str
    description: str
    vendor: str
    product_type: str
    status: str
    image_url: str
    extra_data: Optional[dict] = None
    created_at: datetime
    updated_at: datetime
    variants: list[VariantOut] = []
    model_config = ConfigDict(from_attributes=True)


class ProductListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: list[ProductOut]


@router.get("/stores/{store_id}/products", response_model=ProductListResponse)
async def list_products(
    store_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=250),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paginated product list with optional status/search filters."""
    await _get_store_or_404(db, store_id, current_user.id)
    query = select(Product).where(Product.store_id == store_id)
    count_query = select(func.count(Product.id)).where(Product.store_id == store_id)
    if status:
        query = query.where(Product.status == status)
        count_query = count_query.where(Product.status == status)
    if search:
        like = f"%{search}%"
        query = query.where(Product.title.ilike(like))
        count_query = count_query.where(Product.title.ilike(like))
    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * limit
    # selectinload: variants ek saath load hote hain (async mein lazy load MissingGreenlet deta tha)
    result = await db.execute(
        query.options(selectinload(Product.variants)).order_by(Product.id).offset(offset).limit(limit)
    )
    items = list(result.scalars().all())
    return ProductListResponse(total=total, page=page, limit=limit, items=items)


@router.get("/stores/{store_id}/products/{platform_product_id}", response_model=ProductOut)
async def get_product(
    store_id: int,
    platform_product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get single product with variants by platform product ID."""
    await _get_store_or_404(db, store_id, current_user.id)
    result = await db.execute(
        select(Product)
        .where(Product.store_id == store_id, Product.platform_product_id == platform_product_id)
        .options(selectinload(Product.variants))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


# ================================================================
# ORDERS
# ================================================================

class OrderItemOut(BaseModel):
    id: int
    variant_id: int
    quantity: int
    price: float
    model_config = ConfigDict(from_attributes=True)


class OrderOut(BaseModel):
    id: int
    platform_order_id: Optional[str] = None
    order_number: str
    customer_email: str
    total_price: float
    currency: str
    financial_status: str
    fulfillment_status: Optional[str] = None
    ordered_at: datetime
    extra_data: Optional[dict] = None
    items: list[OrderItemOut] = []
    model_config = ConfigDict(from_attributes=True)


class OrderListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: list[OrderOut]


@router.get("/stores/{store_id}/orders", response_model=OrderListResponse)
async def list_orders(
    store_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=250),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paginated orders list with optional financial_status filter."""
    await _get_store_or_404(db, store_id, current_user.id)
    query = select(Order).where(Order.store_id == store_id)
    count_query = select(func.count(Order.id)).where(Order.store_id == store_id)
    if status:
        query = query.where(Order.financial_status == status)
        count_query = count_query.where(Order.financial_status == status)
    query = query.order_by(Order.ordered_at.desc())
    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * limit
    result = await db.execute(
        query.options(selectinload(Order.items)).offset(offset).limit(limit)
    )
    items = list(result.scalars().all())
    return OrderListResponse(total=total, page=page, limit=limit, items=items)


# ================================================================
# LOW STOCK ALERTS
# ================================================================

class LowStockAlertOut(BaseModel):
    id: int
    variant_id: int
    product_title: str
    variant_title: str
    sku: str
    current_stock: int
    threshold: int
    is_resolved: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AlertListResponse(BaseModel):
    total: int
    items: list[LowStockAlertOut]


@router.get("/stores/{store_id}/alerts/low-stock", response_model=AlertListResponse)
async def get_low_stock_alerts(
    store_id: int,
    resolved: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List low stock alerts, optionally filtered by resolved status."""
    await _get_store_or_404(db, store_id, current_user.id)
    stmt = select(LowStockAlert).where(
        LowStockAlert.store_id == store_id,
        LowStockAlert.is_resolved == resolved,
    ).order_by(LowStockAlert.created_at.desc())
    result = await db.execute(stmt)
    alerts = result.scalars().all()
    return AlertListResponse(total=len(alerts), items=alerts)


@router.post("/stores/{store_id}/alerts/{alert_id}/resolve")
async def resolve_alert(
    store_id: int,
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a low stock alert as resolved."""
    await _get_store_or_404(db, store_id, current_user.id)
    result = await db.execute(
        select(LowStockAlert).where(
            LowStockAlert.id == alert_id,
            LowStockAlert.store_id == store_id,
        )
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_resolved = True
    alert.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "resolved"}
