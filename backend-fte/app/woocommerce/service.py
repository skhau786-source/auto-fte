"""
Service Layer for the WooCommerce Integration Module.

All business logic lives here. Repositories handle data access;
the service orchestrates, validates, and coordinates transactions.

The service NEVER raises HTTPException — it raises domain exceptions
(from exceptions.py) that the router layer catches and converts to HTTP.
"""

import uuid
import logging
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

from sqlalchemy import select, func, and_, or_, delete, update, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.config import settings
from app.models import RegisteredStudent
from app.woocommerce.models import (
    WooCommerceStore,
    WooCommerceProduct,
    WooCommerceCategory,
    WooCommerceTag,
    WooCommerceOrder,
    WooCommerceOrderItem,
    WooCommerceCustomer,
    WooCommerceCoupon,
    WooCommerceInventoryLog,
    WooCommerceAlert,
    WooCommerceSyncLog,
    WooCommerceSetting,
)
from app.woocommerce.client import WooCommerceClient
from app.woocommerce.constants import (
    SyncStatus,
    SyncType,
    StockStatus,
    AlertType,
    AlertSeverity,
    StoreStatus,
    REVENUE_ORDER_STATUSES,
    DEFAULT_LOW_STOCK_THRESHOLD,
    DEFAULT_SYNC_INTERVAL_HOURS,
)
from app.woocommerce.exceptions import (
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
    WooCommerceAPIError,
    SyncInProgressError,
)
from app.woocommerce.encryption import encrypt_value, decrypt_value, mask_credential

logger = logging.getLogger(__name__)


class WooCommerceService:
    """
    Orchestrates WooCommerce integration operations.
    Single point of coordination for all WooCommerce-related business logic.
    """

    def __init__(self, db: AsyncSession, user: Optional[RegisteredStudent] = None):
        self.db = db
        self.user = user
        self.user_id = user.id if user else None
        self.logger = logging.getLogger(f"{__name__}.WooCommerceService")

    # ═══════════════════════════════════════════════════════════════
    # STORE MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def connect_store(self, data) -> dict:
        """Connect and verify a new WooCommerce store."""
        # Check for duplicate URL
        existing = await self.db.execute(
            select(WooCommerceStore).where(
                WooCommerceStore.store_url == data.store_url.rstrip("/"),
                WooCommerceStore.owner_id == self.user_id,
                WooCommerceStore.is_active == True,
            )
        )
        if existing.scalar_one_or_none():
            raise StoreAlreadyExistsError(data.store_url)

        # Verify credentials against WooCommerce API
        # Use plaintext credentials for verification (before encryption)
        client = WooCommerceClient(
            store_url=data.store_url,
            consumer_key=data.consumer_key,
            consumer_secret=data.consumer_secret,
        )

        try:
            verification = await client.verify_connection()
            self.logger.info(
                "Verified WooCommerce connection for '%s': version=%s",
                data.store_name,
                verification.get("woocommerce_version", "unknown"),
            )
        except Exception as exc:
            raise StoreConnectionError(str(exc))
        finally:
            await client.close()

        # Encrypt credentials before storing
        encrypted_key = encrypt_value(data.consumer_key)
        encrypted_secret = encrypt_value(data.consumer_secret)

        self.logger.info(
            "Storing encrypted credentials for store '%s': key=%s, secret=%s",
            data.store_name,
            mask_credential(data.consumer_key),
            mask_credential(data.consumer_secret),
        )

        # Create store record
        store = WooCommerceStore(
            owner_id=self.user_id,
            store_name=data.store_name,
            store_url=data.store_url.rstrip("/"),
            consumer_key=encrypted_key,
            consumer_secret=encrypted_secret,
            wc_version=verification.get("woocommerce_version"),
            status=StoreStatus.CONNECTED,
            is_active=True,
        )
        self.db.add(store)
        await self.db.flush()

        # Create default settings
        settings = WooCommerceSetting(store_id=store.id)
        self.db.add(settings)

        await self.db.commit()
        await self.db.refresh(store)

        # Trigger initial sync in background (via Celery)
        from app.woocommerce.tasks import run_initial_sync
        try:
            run_initial_sync.delay(str(store.id), str(self.user_id))
        except Exception as exc:
            self.logger.warning("Failed to trigger initial sync for store %s: %s", store.id, exc)

        return {
            "message": "Store connected successfully",
            "store": store,
            "verification": verification,
        }

    async def disconnect_store(self, store_id: uuid.UUID) -> dict:
        """Disconnect and deactivate a WooCommerce store."""
        store = await self._get_store(store_id)
        store.is_active = False
        store.status = StoreStatus.DISCONNECTED

        # Create alert
        alert = WooCommerceAlert(
            store_id=store.id,
            alert_type=AlertType.STORE_DISCONNECTED,
            severity=AlertSeverity.INFO,
            title="Store Disconnected",
            message=f"Store '{store.store_name}' has been disconnected.",
        )
        self.db.add(alert)
        await self.db.commit()

        return {"message": f"Store '{store.store_name}' disconnected successfully"}

    async def get_stores(self) -> list[WooCommerceStore]:
        """Get all stores for the current user."""
        result = await self.db.execute(
            select(WooCommerceStore)
            .where(WooCommerceStore.owner_id == self.user_id)
            .order_by(WooCommerceStore.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_store(self, store_id: uuid.UUID) -> WooCommerceStore:
        """Get a single store by ID with ownership check."""
        return await self._get_store(store_id)

    async def update_store(self, store_id: uuid.UUID, data) -> WooCommerceStore:
        """Update store credentials or name."""
        store = await self._get_store(store_id)

        if data.store_name is not None:
            store.store_name = data.store_name
        if data.consumer_key is not None:
            store.consumer_key = encrypt_value(data.consumer_key)
            self.logger.info("Updated encrypted consumer_key for store %s", store.store_name)
        if data.consumer_secret is not None:
            store.consumer_secret = encrypt_value(data.consumer_secret)
            self.logger.info("Updated encrypted consumer_secret for store %s", store.store_name)

        await self.db.commit()
        await self.db.refresh(store)
        return store

    async def _get_decrypted_store(self, store_id: uuid.UUID) -> WooCommerceStore:
        """
        Get a store and decrypt its API credentials for use with WooCommerceClient.

        Returns the store with consumer_key and consumer_secret decrypted in-place.
        Does NOT persist the decrypted values back to the database.

        If decryption fails (e.g., legacy plaintext data from before encryption was
        introduced), the raw value is used as-is. Failures are logged at DEBUG level.
        """
        store = await self._get_store(store_id)
        try:
            store.consumer_key = decrypt_value(store.consumer_key)
        except Exception as exc:
            # Already plaintext (legacy data before encryption was introduced)
            self.logger.debug(
                "Consumer key for store %s is plaintext (decryption skipped): %s",
                store.store_name, exc,
            )
        try:
            store.consumer_secret = decrypt_value(store.consumer_secret)
        except Exception as exc:
            self.logger.debug(
                "Consumer secret for store %s is plaintext (decryption skipped): %s",
                store.store_name, exc,
            )
        return store

    async def verify_store_connection(self, store_id: uuid.UUID) -> dict:
        """Verify a store's WooCommerce API connection."""
        store = await self._get_decrypted_store(store_id)

        client = WooCommerceClient(
            store_url=store.store_url,
            consumer_key=store.consumer_key,
            consumer_secret=store.consumer_secret,
        )

        try:
            result = await client.verify_connection()
            store.status = StoreStatus.CONNECTED
            store.error_message = None
            await self.db.commit()
            return result
        except Exception as exc:
            store.status = StoreStatus.ERROR
            store.error_message = str(exc)
            await self.db.commit()
            raise StoreConnectionError(str(exc))
        finally:
            await client.close()

    # ═══════════════════════════════════════════════════════════════
    # PRODUCT MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def list_products(
        self,
        store_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        status: Optional[str] = None,
        stock_status: Optional[str] = None,
        category_id: Optional[int] = None,
        low_stock_only: bool = False,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> tuple[list[WooCommerceProduct], int]:
        """List products with filtering, search, and pagination."""
        query = select(WooCommerceProduct).where(WooCommerceProduct.store_id == store_id)
        count_query = select(func.count(WooCommerceProduct.id)).where(WooCommerceProduct.store_id == store_id)

        # Filters
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    WooCommerceProduct.name.ilike(pattern),
                    WooCommerceProduct.sku.ilike(pattern),
                )
            )
            count_query = count_query.where(
                or_(
                    WooCommerceProduct.name.ilike(pattern),
                    WooCommerceProduct.sku.ilike(pattern),
                )
            )

        if status:
            query = query.where(WooCommerceProduct.status == status)
            count_query = count_query.where(WooCommerceProduct.status == status)

        if stock_status:
            query = query.where(WooCommerceProduct.stock_status == stock_status)
            count_query = count_query.where(WooCommerceProduct.stock_status == stock_status)

        if category_id:
            query = query.where(WooCommerceProduct.category_ids.contains([category_id]))
            count_query = count_query.where(WooCommerceProduct.category_ids.contains([category_id]))

        if low_stock_only:
            threshold = DEFAULT_LOW_STOCK_THRESHOLD
            condition = and_(
                WooCommerceProduct.manage_stock == True,
                WooCommerceProduct.stock_quantity <= threshold,
                WooCommerceProduct.stock_quantity > 0,
            )
            query = query.where(condition)
            count_query = count_query.where(condition)

        if min_price is not None:
            query = query.where(WooCommerceProduct.price >= min_price)
            count_query = count_query.where(WooCommerceProduct.price >= min_price)

        if max_price is not None:
            query = query.where(WooCommerceProduct.price <= max_price)
            count_query = count_query.where(WooCommerceProduct.price <= max_price)

        # Sort
        sort_map = {
            "name": WooCommerceProduct.name,
            "price": WooCommerceProduct.price,
            "created_at": WooCommerceProduct.created_at,
            "updated_at": WooCommerceProduct.updated_at,
            "stock_quantity": WooCommerceProduct.stock_quantity,
            "total_sales": WooCommerceProduct.total_sales,
        }
        sort_col = sort_map.get(sort_by, WooCommerceProduct.updated_at)
        order_fn = desc if sort_order.lower() == "desc" else asc
        query = query.order_by(order_fn(sort_col))

        # Pagination
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        products = list(result.scalars().all())

        return products, total

    async def get_product(self, store_id: uuid.UUID, product_id: uuid.UUID) -> WooCommerceProduct:
        """Get a single product by ID."""
        result = await self.db.execute(
            select(WooCommerceProduct).where(
                WooCommerceProduct.id == product_id,
                WooCommerceProduct.store_id == store_id,
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            raise ProductNotFoundError(str(product_id))
        return product

    async def sync_products(
        self, store_id: uuid.UUID, force_full: bool = False
    ) -> dict:
        """Sync products from WooCommerce to local database."""
        store = await self._get_decrypted_store(store_id)

        # Check for existing sync
        if not force_full:
            existing = await self.db.execute(
                select(WooCommerceSyncLog).where(
                    WooCommerceSyncLog.store_id == store_id,
                    WooCommerceSyncLog.resource == "products",
                    WooCommerceSyncLog.status == SyncStatus.IN_PROGRESS,
                )
            )
            if existing.scalar_one_or_none():
                raise SyncInProgressError(str(store_id), "products")

        # Create sync log
        sync_log = WooCommerceSyncLog(
            store_id=store_id,
            sync_type=SyncType.MANUAL if force_full else SyncType.INCREMENTAL,
            resource="products",
            status=SyncStatus.IN_PROGRESS,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(sync_log)
        await self.db.flush()

        client = WooCommerceClient(
            store_url=store.store_url,
            consumer_key=store.consumer_key,
            consumer_secret=store.consumer_secret,
        )

        stats = {"created": 0, "updated": 0, "failed": 0, "skipped": 0, "total": 0}

        try:
            # Fetch all products from WooCommerce
            wc_products = await client.get_all_products()
            stats["total"] = len(wc_products)

            for wc_product in wc_products:
                try:
                    normalized = WooCommerceClient.normalize_product(wc_product)
                    product_id = normalized["wc_product_id"]

                    # Check if product exists locally
                    existing_product = await self.db.execute(
                        select(WooCommerceProduct).where(
                            WooCommerceProduct.store_id == store_id,
                            WooCommerceProduct.wc_product_id == product_id,
                        )
                    )
                    existing = existing_product.scalar_one_or_none()

                    if existing:
                        # Update existing product
                        for key, value in normalized.items():
                            if key != "wc_raw_data" and hasattr(existing, key):
                                setattr(existing, key, value)
                        existing.last_synced_at = datetime.now(timezone.utc)
                        stats["updated"] += 1
                    else:
                        # Create new product
                        product = WooCommerceProduct(
                            store_id=store_id,
                            **{k: v for k, v in normalized.items() if hasattr(WooCommerceProduct, k) and k != "wc_raw_data"},
                            raw_data=wc_product,
                            last_synced_at=datetime.now(timezone.utc),
                        )
                        self.db.add(product)
                        stats["created"] += 1

                except Exception as exc:
                    self.logger.error("Failed to sync product %s: %s", wc_product.get("id"), exc)
                    stats["failed"] += 1

            # Update store's last_sync_at
            store.last_sync_at = datetime.now(timezone.utc)

            # Update sync log
            sync_log.status = SyncStatus.COMPLETED
            sync_log.completed_at = datetime.now(timezone.utc)
            sync_log.total_items = stats["total"]
            sync_log.created_items = stats["created"]
            sync_log.updated_items = stats["updated"]
            sync_log.failed_items = stats["failed"]
            sync_log.duration_seconds = (
                datetime.now(timezone.utc) - sync_log.started_at
            ).total_seconds() if sync_log.started_at else 0

            await self.db.commit()

            self.logger.info(
                "Product sync completed for store %s: %d created, %d updated, %d failed",
                store.store_name, stats["created"], stats["updated"], stats["failed"],
            )

            return {
                **stats,
                "sync_id": str(sync_log.id),
                "message": f"Synced {stats['created'] + stats['updated']} products",
            }

        except Exception as exc:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = str(exc)
            sync_log.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            self.logger.error("Product sync failed for store %s: %s", store.store_name, exc)
            raise
        finally:
            await client.close()

    # ═══════════════════════════════════════════════════════════════
    # INVENTORY MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def adjust_inventory(
        self,
        store_id: uuid.UUID,
        wc_product_id: int,
        quantity_change: int,
        reason: Optional[str] = None,
        sync_to_wc: bool = True,
    ) -> dict:
        """Adjust inventory stock for a product."""
        store = await self._get_decrypted_store(store_id)

        # Find product
        result = await self.db.execute(
            select(WooCommerceProduct).where(
                WooCommerceProduct.store_id == store_id,
                WooCommerceProduct.wc_product_id == wc_product_id,
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            raise ProductNotFoundError(str(wc_product_id))

        if not product.manage_stock:
            return {
                "message": "Product does not use stock management",
                "product_id": str(product.id),
                "wc_product_id": wc_product_id,
            }

        # Calculate new quantity
        quantity_before = product.stock_quantity or 0
        quantity_after = quantity_before + quantity_change

        if quantity_after < 0:
            raise InsufficientStockError(
                variant_id=str(product.id),
                current_quantity=quantity_before,
                requested_change=quantity_change,
            )

        # Update local stock
        product.stock_quantity = quantity_after
        product.stock_status = (
            StockStatus.IN_STOCK if quantity_after > 0 else StockStatus.OUT_OF_STOCK
        )

        # Create inventory log
        log = WooCommerceInventoryLog(
            store_id=store_id,
            product_id=product.id,
            wc_product_id=wc_product_id,
            sku=product.sku,
            action="adjustment",
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            quantity_change=quantity_change,
            reason=reason,
            source="manual",
            performed_by=self.user_id,
        )
        self.db.add(log)

        await self.db.commit()

        # Sync to WooCommerce (async)
        if sync_to_wc and store.is_active:
            try:
                client = WooCommerceClient(
                    store_url=store.store_url,
                    consumer_key=store.consumer_key,
                    consumer_secret=store.consumer_secret,
                )
                await client.update_product(wc_product_id, {
                    "stock_quantity": quantity_after,
                    "stock_status": "instock" if quantity_after > 0 else "outofstock",
                })
                await client.close()
            except Exception as exc:
                self.logger.warning(
                    "Failed to sync inventory to WooCommerce for product %s: %s",
                    wc_product_id, exc,
                )

        # Check for low stock alert
        settings_result = await self.db.execute(
            select(WooCommerceSetting).where(WooCommerceSetting.store_id == store_id)
        )
        settings = settings_result.scalar_one_or_none()
        threshold = settings.low_stock_threshold if settings else DEFAULT_LOW_STOCK_THRESHOLD

        if quantity_after <= threshold and quantity_after > 0 and settings and settings.low_stock_alerts:
            await self._create_alert(
                store_id=store_id,
                alert_type=AlertType.LOW_STOCK,
                severity=AlertSeverity.WARNING,
                title=f"Low Stock: {product.name}",
                message=f"Product '{product.name}' (SKU: {product.sku}) has only {quantity_after} units remaining.",
                resource_type="product",
                resource_id=str(product.wc_product_id),
            )

        return {
            "product_id": str(product.id),
            "wc_product_id": wc_product_id,
            "sku": product.sku,
            "quantity_before": quantity_before,
            "quantity_after": quantity_after,
            "quantity_change": quantity_change,
            "message": f"Stock {'increased' if quantity_change > 0 else 'decreased'} by {abs(quantity_change)}",
        }

    async def get_low_stock(
        self, store_id: uuid.UUID, threshold: int = DEFAULT_LOW_STOCK_THRESHOLD, page: int = 1, page_size: int = 50
    ) -> tuple[list[dict], int]:
        """Get all products with low stock."""
        query = select(WooCommerceProduct).where(
            WooCommerceProduct.store_id == store_id,
            WooCommerceProduct.manage_stock == True,
            WooCommerceProduct.stock_quantity <= threshold,
            WooCommerceProduct.stock_quantity > 0,
        )
        count_query = select(func.count(WooCommerceProduct.id)).where(
            WooCommerceProduct.store_id == store_id,
            WooCommerceProduct.manage_stock == True,
            WooCommerceProduct.stock_quantity <= threshold,
            WooCommerceProduct.stock_quantity > 0,
        )

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.order_by(WooCommerceProduct.stock_quantity.asc()).offset(offset).limit(page_size)
        result = await self.db.execute(query)
        products = list(result.scalars().all())

        items = [
            {
                "product_id": p.id,
                "wc_product_id": p.wc_product_id,
                "product_name": p.name,
                "sku": p.sku,
                "stock_quantity": p.stock_quantity or 0,
                "low_stock_threshold": threshold,
                "featured_image_url": p.featured_image_url,
            }
            for p in products
        ]

        return items, total

    async def get_inventory_history(
        self,
        store_id: uuid.UUID,
        product_id: Optional[uuid.UUID] = None,
        action: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[WooCommerceInventoryLog], int]:
        """Get inventory change history."""
        query = select(WooCommerceInventoryLog).where(WooCommerceInventoryLog.store_id == store_id)
        count_query = select(func.count(WooCommerceInventoryLog.id)).where(WooCommerceInventoryLog.store_id == store_id)

        if product_id:
            query = query.where(WooCommerceInventoryLog.product_id == product_id)
            count_query = count_query.where(WooCommerceInventoryLog.product_id == product_id)

        if action:
            query = query.where(WooCommerceInventoryLog.action == action)
            count_query = count_query.where(WooCommerceInventoryLog.action == action)

        if date_from:
            query = query.where(WooCommerceInventoryLog.created_at >= date_from)
            count_query = count_query.where(WooCommerceInventoryLog.created_at >= date_from)

        if date_to:
            query = query.where(WooCommerceInventoryLog.created_at <= date_to)
            count_query = count_query.where(WooCommerceInventoryLog.created_at <= date_to)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(WooCommerceInventoryLog.created_at.desc())
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        logs = list(result.scalars().all())

        return logs, total

    # ═══════════════════════════════════════════════════════════════
    # ORDER MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def list_orders(
        self,
        store_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
        search: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[WooCommerceOrder], int]:
        """List orders with filtering and pagination."""
        query = select(WooCommerceOrder).options(
            selectinload(WooCommerceOrder.items)
        ).where(WooCommerceOrder.store_id == store_id)
        count_query = select(func.count(WooCommerceOrder.id)).where(WooCommerceOrder.store_id == store_id)

        if status:
            query = query.where(WooCommerceOrder.status == status)
            count_query = count_query.where(WooCommerceOrder.status == status)

        if customer_id:
            query = query.where(WooCommerceOrder.customer_id == customer_id)
            count_query = count_query.where(WooCommerceOrder.customer_id == customer_id)

        if search:
            pattern = f"%{search}%"
            query = query.where(WooCommerceOrder.number.ilike(pattern))
            count_query = count_query.where(WooCommerceOrder.number.ilike(pattern))

        sort_map = {
            "created_at": WooCommerceOrder.created_at,
            "total": WooCommerceOrder.total,
            "status": WooCommerceOrder.status,
        }
        sort_col = sort_map.get(sort_by, WooCommerceOrder.created_at)
        order_fn = desc if sort_order.lower() == "desc" else asc
        query = query.order_by(order_fn(sort_col))

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        orders = list(result.scalars().all())

        return orders, total

    async def get_order(self, store_id: uuid.UUID, order_id: uuid.UUID) -> WooCommerceOrder:
        """Get a single order by ID."""
        result = await self.db.execute(
            select(WooCommerceOrder)
            .options(selectinload(WooCommerceOrder.items))
            .where(WooCommerceOrder.id == order_id, WooCommerceOrder.store_id == store_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            raise OrderNotFoundError(str(order_id))
        return order

    async def sync_orders(
        self,
        store_id: uuid.UUID,
        date_after: Optional[str] = None,
        status: Optional[str] = None,
    ) -> dict:
        """Sync orders from WooCommerce."""
        store = await self._get_decrypted_store(store_id)

        sync_log = WooCommerceSyncLog(
            store_id=store_id,
            sync_type=SyncType.INCREMENTAL,
            resource="orders",
            status=SyncStatus.IN_PROGRESS,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(sync_log)
        await self.db.flush()

        client = WooCommerceClient(
            store_url=store.store_url,
            consumer_key=store.consumer_key,
            consumer_secret=store.consumer_secret,
        )

        stats = {"created": 0, "updated": 0, "failed": 0, "total": 0}

        try:
            wc_orders = await client.get_all_orders(after=date_after, status=status)
            stats["total"] = len(wc_orders)

            for wc_order in wc_orders:
                try:
                    normalized = WooCommerceClient.normalize_order(wc_order)
                    order_id = normalized["wc_order_id"]

                    existing_result = await self.db.execute(
                        select(WooCommerceOrder).where(
                            WooCommerceOrder.store_id == store_id,
                            WooCommerceOrder.wc_order_id == order_id,
                        )
                    )
                    existing = existing_result.scalar_one_or_none()

                    line_items = normalized.pop("line_items", [])

                    if existing:
                        for key, value in normalized.items():
                            if key != "wc_raw_data" and hasattr(existing, key):
                                setattr(existing, key, value)
                        existing.last_synced_at = datetime.now(timezone.utc)
                        stats["updated"] += 1
                        # Update items
                        await self._sync_order_items(existing.id, line_items, store_id)
                    else:
                        order = WooCommerceOrder(
                            store_id=store_id,
                            **{k: v for k, v in normalized.items() if hasattr(WooCommerceOrder, k) and k != "wc_raw_data"},
                            raw_data=wc_order,
                            last_synced_at=datetime.now(timezone.utc),
                        )
                        self.db.add(order)
                        await self.db.flush()
                        await self._sync_order_items(order.id, line_items, store_id)
                        stats["created"] += 1

                except Exception as exc:
                    self.logger.error("Failed to sync order %s: %s", wc_order.get("id"), exc)
                    stats["failed"] += 1

            sync_log.status = SyncStatus.COMPLETED
            sync_log.completed_at = datetime.now(timezone.utc)
            sync_log.total_items = stats["total"]
            sync_log.created_items = stats["created"]
            sync_log.updated_items = stats["updated"]
            sync_log.failed_items = stats["failed"]
            sync_log.duration_seconds = (
                datetime.now(timezone.utc) - sync_log.started_at
            ).total_seconds() if sync_log.started_at else 0

            store.last_sync_at = datetime.now(timezone.utc)
            await self.db.commit()

            return {**stats, "sync_id": str(sync_log.id)}

        except Exception as exc:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = str(exc)
            await self.db.commit()
            raise
        finally:
            await client.close()

    async def _sync_order_items(self, order_uuid: uuid.UUID, line_items: list, store_id: uuid.UUID):
        """Sync order line items."""
        # Delete existing items
        await self.db.execute(
            delete(WooCommerceOrderItem).where(WooCommerceOrderItem.order_id == order_uuid)
        )

        for item in line_items:
            wc_product_id = item.get("product_id", 0)

            # Find local product reference
            product_result = await self.db.execute(
                select(WooCommerceProduct).where(
                    WooCommerceProduct.store_id == store_id,
                    WooCommerceProduct.wc_product_id == wc_product_id,
                )
            )
            local_product = product_result.scalar_one_or_none()

            order_item = WooCommerceOrderItem(
                order_id=order_uuid,
                wc_order_item_id=item.get("id", 0),
                wc_product_id=wc_product_id,
                name=item.get("name", ""),
                sku=item.get("sku", ""),
                product_id=local_product.id if local_product else None,
                quantity=item.get("quantity", 1),
                price=Decimal(str(item.get("price", "0.00"))),
                subtotal=Decimal(str(item.get("subtotal", "0.00"))),
                subtotal_tax=Decimal(str(item.get("subtotal_tax", "0.00"))),
                total=Decimal(str(item.get("total", "0.00"))),
                total_tax=Decimal(str(item.get("total_tax", "0.00"))),
                meta_data=item.get("meta_data"),
                raw_data=item,
            )
            self.db.add(order_item)

    # ═══════════════════════════════════════════════════════════════
    # CUSTOMER MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def list_customers(
        self,
        store_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
    ) -> tuple[list[WooCommerceCustomer], int]:
        """List customers with pagination."""
        query = select(WooCommerceCustomer).where(WooCommerceCustomer.store_id == store_id)
        count_query = select(func.count(WooCommerceCustomer.id)).where(WooCommerceCustomer.store_id == store_id)

        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    WooCommerceCustomer.first_name.ilike(pattern),
                    WooCommerceCustomer.last_name.ilike(pattern),
                    WooCommerceCustomer.email.ilike(pattern),
                )
            )
            count_query = count_query.where(
                or_(
                    WooCommerceCustomer.first_name.ilike(pattern),
                    WooCommerceCustomer.last_name.ilike(pattern),
                    WooCommerceCustomer.email.ilike(pattern),
                )
            )

        query = query.order_by(WooCommerceCustomer.created_at.desc())

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        customers = list(result.scalars().all())

        return customers, total

    async def get_customer(self, store_id: uuid.UUID, customer_id: uuid.UUID) -> WooCommerceCustomer:
        """Get a single customer."""
        result = await self.db.execute(
            select(WooCommerceCustomer).where(
                WooCommerceCustomer.id == customer_id,
                WooCommerceCustomer.store_id == store_id,
            )
        )
        customer = result.scalar_one_or_none()
        if not customer:
            raise CustomerNotFoundError(str(customer_id))
        return customer

    async def sync_customers(self, store_id: uuid.UUID) -> dict:
        """Sync customers from WooCommerce."""
        store = await self._get_decrypted_store(store_id)

        sync_log = WooCommerceSyncLog(
            store_id=store_id, sync_type=SyncType.INCREMENTAL,
            resource="customers", status=SyncStatus.IN_PROGRESS,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(sync_log)
        await self.db.flush()

        client = WooCommerceClient(
            store_url=store.store_url,
            consumer_key=store.consumer_key,
            consumer_secret=store.consumer_secret,
        )

        stats = {"created": 0, "updated": 0, "failed": 0, "total": 0}

        try:
            wc_customers = await client.get_all_customers()
            stats["total"] = len(wc_customers)

            for wc_customer in wc_customers:
                try:
                    normalized = WooCommerceClient.normalize_customer(wc_customer)
                    customer_id = normalized["wc_customer_id"]

                    existing_result = await self.db.execute(
                        select(WooCommerceCustomer).where(
                            WooCommerceCustomer.store_id == store_id,
                            WooCommerceCustomer.wc_customer_id == customer_id,
                        )
                    )
                    existing = existing_result.scalar_one_or_none()

                    if existing:
                        for key, value in normalized.items():
                            if key != "wc_raw_data" and hasattr(existing, key):
                                setattr(existing, key, value)
                        existing.last_synced_at = datetime.now(timezone.utc)
                        stats["updated"] += 1
                    else:
                        customer = WooCommerceCustomer(
                            store_id=store_id,
                            **{k: v for k, v in normalized.items() if hasattr(WooCommerceCustomer, k) and k != "wc_raw_data"},
                            raw_data=wc_customer,
                            last_synced_at=datetime.now(timezone.utc),
                        )
                        self.db.add(customer)
                        stats["created"] += 1

                except Exception as exc:
                    self.logger.error("Failed to sync customer %s: %s", wc_customer.get("id"), exc)
                    stats["failed"] += 1

            sync_log.status = SyncStatus.COMPLETED
            sync_log.completed_at = datetime.now(timezone.utc)
            sync_log.total_items = stats["total"]
            sync_log.created_items = stats["created"]
            sync_log.updated_items = stats["updated"]
            sync_log.failed_items = stats["failed"]
            await self.db.commit()

            return {**stats, "sync_id": str(sync_log.id)}

        except Exception as exc:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = str(exc)
            await self.db.commit()
            raise
        finally:
            await client.close()

    # ═══════════════════════════════════════════════════════════════
    # CATEGORY MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def list_categories(self, store_id: uuid.UUID) -> list[WooCommerceCategory]:
        """List all categories for a store."""
        result = await self.db.execute(
            select(WooCommerceCategory)
            .where(WooCommerceCategory.store_id == store_id)
            .order_by(WooCommerceCategory.menu_order, WooCommerceCategory.name)
        )
        return list(result.scalars().all())

    async def get_category_tree(self, store_id: uuid.UUID) -> list[dict]:
        """Build hierarchical category tree."""
        categories = await self.list_categories(store_id)

        # Build adjacency map
        category_map = {}
        for cat in categories:
            category_map[cat.id] = {
                "id": cat.id,
                "wc_category_id": cat.wc_category_id,
                "name": cat.name,
                "slug": cat.slug,
                "description": cat.description,
                "parent_id": cat.parent_id,
                "product_count": cat.product_count,
                "children": [],
            }

        # Build tree
        roots = []
        for cat_id, cat_data in category_map.items():
            parent_id = cat_data["parent_id"]
            if parent_id and parent_id in category_map:
                category_map[parent_id]["children"].append(cat_data)
            else:
                roots.append(cat_data)

        return roots

    async def sync_categories(self, store_id: uuid.UUID) -> dict:
        """Sync categories from WooCommerce."""
        store = await self._get_decrypted_store(store_id)

        sync_log = WooCommerceSyncLog(
            store_id=store_id, sync_type=SyncType.INCREMENTAL,
            resource="categories", status=SyncStatus.IN_PROGRESS,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(sync_log)
        await self.db.flush()

        client = WooCommerceClient(
            store_url=store.store_url,
            consumer_key=store.consumer_key,
            consumer_secret=store.consumer_secret,
        )

        stats = {"created": 0, "updated": 0, "total": 0}

        try:
            wc_categories = await client.get_all_categories()
            stats["total"] = len(wc_categories)

            # First pass: create all categories
            cat_id_map = {}  # wc_category_id -> local UUID
            for wc_cat in wc_categories:
                normalized = WooCommerceClient.normalize_category(wc_cat)
                cat_id = normalized["wc_category_id"]

                existing_result = await self.db.execute(
                    select(WooCommerceCategory).where(
                        WooCommerceCategory.store_id == store_id,
                        WooCommerceCategory.wc_category_id == cat_id,
                    )
                )
                existing = existing_result.scalar_one_or_none()

                if existing:
                    for key, value in normalized.items():
                        if key != "wc_raw_data" and hasattr(existing, key) and value is not None:
                            setattr(existing, key, value)
                    cat_id_map[cat_id] = existing.id
                    stats["updated"] += 1
                else:
                    category = WooCommerceCategory(
                        store_id=store_id,
                        **{k: v for k, v in normalized.items() if hasattr(WooCommerceCategory, k) and k != "wc_raw_data"},
                        raw_data=wc_cat,
                    )
                    self.db.add(category)
                    await self.db.flush()
                    cat_id_map[cat_id] = category.id
                    stats["created"] += 1

            # Second pass: set parent relationships
            for wc_cat in wc_categories:
                wc_parent_id = wc_cat.get("parent", 0)
                if wc_parent_id and wc_parent_id in cat_id_map:
                    local_cat_id = cat_id_map.get(wc_cat["id"])
                    local_parent_id = cat_id_map[wc_parent_id]
                    if local_cat_id and local_parent_id:
                        await self.db.execute(
                            update(WooCommerceCategory)
                            .where(WooCommerceCategory.id == local_cat_id)
                            .values(parent_id=local_parent_id)
                        )

            sync_log.status = SyncStatus.COMPLETED
            sync_log.completed_at = datetime.now(timezone.utc)
            sync_log.total_items = stats["total"]
            sync_log.created_items = stats["created"]
            sync_log.updated_items = stats["updated"]
            await self.db.commit()

            return {**stats, "sync_id": str(sync_log.id)}

        except Exception as exc:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = str(exc)
            await self.db.commit()
            raise
        finally:
            await client.close()

    # ═══════════════════════════════════════════════════════════════
    # COUPON MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def list_coupons(
        self, store_id: uuid.UUID, page: int = 1, page_size: int = 20
    ) -> tuple[list[WooCommerceCoupon], int]:
        """List coupons with pagination."""
        query = select(WooCommerceCoupon).where(WooCommerceCoupon.store_id == store_id)
        count_query = select(func.count(WooCommerceCoupon.id)).where(WooCommerceCoupon.store_id == store_id)

        query = query.order_by(WooCommerceCoupon.created_at.desc())

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        coupons = list(result.scalars().all())

        return coupons, total

    async def get_coupon(self, store_id: uuid.UUID, coupon_id: uuid.UUID) -> WooCommerceCoupon:
        """Get a single coupon."""
        result = await self.db.execute(
            select(WooCommerceCoupon).where(
                WooCommerceCoupon.id == coupon_id,
                WooCommerceCoupon.store_id == store_id,
            )
        )
        coupon = result.scalar_one_or_none()
        if not coupon:
            raise CouponNotFoundError(str(coupon_id))
        return coupon

    async def sync_coupons(self, store_id: uuid.UUID) -> dict:
        """Sync coupons from WooCommerce."""
        store = await self._get_decrypted_store(store_id)

        sync_log = WooCommerceSyncLog(
            store_id=store_id, sync_type=SyncType.INCREMENTAL,
            resource="coupons", status=SyncStatus.IN_PROGRESS,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(sync_log)
        await self.db.flush()

        client = WooCommerceClient(
            store_url=store.store_url,
            consumer_key=store.consumer_key,
            consumer_secret=store.consumer_secret,
        )

        stats = {"created": 0, "updated": 0, "failed": 0, "total": 0}

        try:
            wc_coupons = await client.get_all_coupons()
            stats["total"] = len(wc_coupons)

            for wc_coupon in wc_coupons:
                try:
                    normalized = WooCommerceClient.normalize_coupon(wc_coupon)
                    coupon_id = normalized["wc_coupon_id"]

                    existing_result = await self.db.execute(
                        select(WooCommerceCoupon).where(
                            WooCommerceCoupon.store_id == store_id,
                            WooCommerceCoupon.wc_coupon_id == coupon_id,
                        )
                    )
                    existing = existing_result.scalar_one_or_none()

                    if existing:
                        for key, value in normalized.items():
                            if key != "wc_raw_data" and hasattr(existing, key):
                                setattr(existing, key, value)
                        existing.last_synced_at = datetime.now(timezone.utc)
                        stats["updated"] += 1
                    else:
                        coupon = WooCommerceCoupon(
                            store_id=store_id,
                            **{k: v for k, v in normalized.items() if hasattr(WooCommerceCoupon, k) and k != "wc_raw_data"},
                            raw_data=wc_coupon,
                            last_synced_at=datetime.now(timezone.utc),
                        )
                        self.db.add(coupon)
                        stats["created"] += 1

                except Exception as exc:
                    self.logger.error("Failed to sync coupon %s: %s", wc_coupon.get("id"), exc)
                    stats["failed"] += 1

            sync_log.status = SyncStatus.COMPLETED
            sync_log.completed_at = datetime.now(timezone.utc)
            sync_log.total_items = stats["total"]
            sync_log.created_items = stats["created"]
            sync_log.updated_items = stats["updated"]
            sync_log.failed_items = stats["failed"]
            await self.db.commit()

            return {**stats, "sync_id": str(sync_log.id)}

        except Exception as exc:
            sync_log.status = SyncStatus.FAILED
            sync_log.error_message = str(exc)
            await self.db.commit()
            raise
        finally:
            await client.close()

    # ═══════════════════════════════════════════════════════════════
    # ALERTS
    # ═══════════════════════════════════════════════════════════════

    async def list_alerts(
        self,
        store_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        unread_only: bool = False,
        unresolved_only: bool = False,
        alert_type: Optional[str] = None,
    ) -> tuple[list[WooCommerceAlert], int, int]:
        """List alerts with filtering and pagination."""
        query = select(WooCommerceAlert).where(WooCommerceAlert.store_id == store_id)
        count_query = select(func.count(WooCommerceAlert.id)).where(WooCommerceAlert.store_id == store_id)
        unread_query = select(func.count(WooCommerceAlert.id)).where(
            WooCommerceAlert.store_id == store_id,
            WooCommerceAlert.is_read == False,
        )

        if unread_only:
            query = query.where(WooCommerceAlert.is_read == False)
            count_query = count_query.where(WooCommerceAlert.is_read == False)

        if unresolved_only:
            query = query.where(WooCommerceAlert.is_resolved == False)
            count_query = count_query.where(WooCommerceAlert.is_resolved == False)

        if alert_type:
            query = query.where(WooCommerceAlert.alert_type == alert_type)
            count_query = count_query.where(WooCommerceAlert.alert_type == alert_type)

        query = query.order_by(WooCommerceAlert.created_at.desc())

        unread_result = await self.db.execute(unread_query)
        unread_count = unread_result.scalar() or 0

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        alerts = list(result.scalars().all())

        return alerts, total, unread_count

    async def mark_alerts(self, store_id: uuid.UUID, alert_ids: list[uuid.UUID], mark_as_read: bool, mark_as_resolved: bool):
        """Mark alerts as read/resolved."""
        for alert_id in alert_ids:
            result = await self.db.execute(
                select(WooCommerceAlert).where(
                    WooCommerceAlert.id == alert_id,
                    WooCommerceAlert.store_id == store_id,
                )
            )
            alert = result.scalar_one_or_none()
            if alert:
                if mark_as_read:
                    alert.is_read = True
                if mark_as_resolved:
                    alert.is_resolved = True
                    alert.resolved_at = datetime.now(timezone.utc)

        await self.db.commit()

    # ═══════════════════════════════════════════════════════════════
    # DASHBOARD
    # ═══════════════════════════════════════════════════════════════

    async def get_dashboard(self, store_id: uuid.UUID) -> dict:
        """Get comprehensive dashboard data."""
        store = await self._get_store(store_id)

        # Product counts
        prod_total = await self.db.execute(
            select(func.count(WooCommerceProduct.id)).where(WooCommerceProduct.store_id == store_id)
        )
        total_products = prod_total.scalar() or 0

        # Low stock count
        low_stock = await self.db.execute(
            select(func.count(WooCommerceProduct.id)).where(
                WooCommerceProduct.store_id == store_id,
                WooCommerceProduct.manage_stock == True,
                WooCommerceProduct.stock_quantity <= DEFAULT_LOW_STOCK_THRESHOLD,
                WooCommerceProduct.stock_quantity > 0,
            )
        )

        # Out of stock
        out_stock = await self.db.execute(
            select(func.count(WooCommerceProduct.id)).where(
                WooCommerceProduct.store_id == store_id,
                WooCommerceProduct.manage_stock == True,
                WooCommerceProduct.stock_quantity <= 0,
            )
        )

        # Order counts
        order_total = await self.db.execute(
            select(func.count(WooCommerceOrder.id)).where(WooCommerceOrder.store_id == store_id)
        )
        total_orders = order_total.scalar() or 0

        # Revenue
        revenue_result = await self.db.execute(
            select(func.coalesce(func.sum(WooCommerceOrder.total), 0)).where(WooCommerceOrder.store_id == store_id)
        )
        total_revenue = Decimal(str(revenue_result.scalar() or 0))

        # Customer count
        cust_total = await self.db.execute(
            select(func.count(WooCommerceCustomer.id)).where(WooCommerceCustomer.store_id == store_id)
        )
        total_customers = cust_total.scalar() or 0

        # Category count
        cat_total = await self.db.execute(
            select(func.count(WooCommerceCategory.id)).where(WooCommerceCategory.store_id == store_id)
        )
        total_categories = cat_total.scalar() or 0

        # Coupon count
        coup_total = await self.db.execute(
            select(func.count(WooCommerceCoupon.id)).where(WooCommerceCoupon.store_id == store_id)
        )
        total_coupons = coup_total.scalar() or 0

        # Active alerts
        alert_total = await self.db.execute(
            select(func.count(WooCommerceAlert.id)).where(
                WooCommerceAlert.store_id == store_id,
                WooCommerceAlert.is_resolved == False,
            )
        )
        active_alerts = alert_total.scalar() or 0

        # Recent orders
        recent_orders_result = await self.db.execute(
            select(WooCommerceOrder)
            .options(selectinload(WooCommerceOrder.items))
            .where(WooCommerceOrder.store_id == store_id)
            .order_by(WooCommerceOrder.created_at.desc())
            .limit(10)
        )
        recent_orders = list(recent_orders_result.scalars().all())

        # Low stock items
        low_stock_items, _ = await self.get_low_stock(store_id, page=1, page_size=5)

        # Recent alerts
        alerts_result = await self.db.execute(
            select(WooCommerceAlert)
            .where(WooCommerceAlert.store_id == store_id, WooCommerceAlert.is_resolved == False)
            .order_by(WooCommerceAlert.created_at.desc())
            .limit(5)
        )
        recent_alerts = list(alerts_result.scalars().all())

        # Recent sync logs
        syncs_result = await self.db.execute(
            select(WooCommerceSyncLog)
            .where(WooCommerceSyncLog.store_id == store_id)
            .order_by(WooCommerceSyncLog.created_at.desc())
            .limit(5)
        )
        recent_syncs = list(syncs_result.scalars().all())

        return {
            "stats": {
                "total_products": total_products,
                "total_orders": total_orders,
                "total_customers": total_customers,
            "total_categories": total_categories,
            "total_coupons": total_coupons,
                "total_revenue": total_revenue,
                "low_stock_count": low_stock.scalar() or 0,
                "out_of_stock_count": out_stock.scalar() or 0,
                "active_alerts": active_alerts,
                "last_sync_at": store.last_sync_at,
                "sync_status": store.status.value,
            },
            "recent_orders": recent_orders,
            "low_stock_items": low_stock_items,
            "recent_alerts": recent_alerts,
            "recent_syncs": recent_syncs,
        }

    # ═══════════════════════════════════════════════════════════════
    # ANALYTICS (Revenue Dashboard / Advanced Analytics)
    # ═══════════════════════════════════════════════════════════════
    #
    # Every figure below is computed directly from WooCommerceOrder /
    # WooCommerceOrderItem rows already synced for this store — nothing
    # here is estimated, hard-coded, or fabricated. "Revenue" only
    # counts orders in REVENUE_ORDER_STATUSES (processing/on-hold/
    # completed); pending, cancelled, refunded, failed, trash, and
    # draft orders are excluded — see constants.py for why.

    async def get_revenue_analytics(self, store_id: uuid.UUID, days: int = 30) -> dict:
        """
        Revenue trend + summary for the last `days` days, compared
        against the immediately preceding period of equal length
        (e.g. last 30 days vs. the 30 days before that).
        """
        await self._get_store(store_id)
        days = max(1, min(days, 365))

        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=days)
        previous_period_start = period_start - timedelta(days=days)

        daily_result = await self.db.execute(
            select(
                func.date(WooCommerceOrder.created_at),
                func.coalesce(func.sum(WooCommerceOrder.total), 0),
                func.count(WooCommerceOrder.id),
            )
            .where(
                WooCommerceOrder.store_id == store_id,
                WooCommerceOrder.status.in_(REVENUE_ORDER_STATUSES),
                WooCommerceOrder.created_at >= period_start,
            )
            .group_by(func.date(WooCommerceOrder.created_at))
            .order_by(func.date(WooCommerceOrder.created_at))
        )
        trend = [
            {"date": str(day), "revenue": float(revenue or 0), "orders": order_count or 0}
            for day, revenue, order_count in daily_result.all()
        ]

        current_result = await self.db.execute(
            select(
                func.coalesce(func.sum(WooCommerceOrder.total), 0),
                func.count(WooCommerceOrder.id),
            ).where(
                WooCommerceOrder.store_id == store_id,
                WooCommerceOrder.status.in_(REVENUE_ORDER_STATUSES),
                WooCommerceOrder.created_at >= period_start,
            )
        )
        cur_revenue, cur_orders = current_result.one()
        cur_revenue = float(cur_revenue or 0)
        cur_orders = cur_orders or 0

        previous_result = await self.db.execute(
            select(
                func.coalesce(func.sum(WooCommerceOrder.total), 0),
                func.count(WooCommerceOrder.id),
            ).where(
                WooCommerceOrder.store_id == store_id,
                WooCommerceOrder.status.in_(REVENUE_ORDER_STATUSES),
                WooCommerceOrder.created_at >= previous_period_start,
                WooCommerceOrder.created_at < period_start,
            )
        )
        prev_revenue, prev_orders = previous_result.one()
        prev_revenue = float(prev_revenue or 0)
        prev_orders = prev_orders or 0

        revenue_change_pct = (
            round((cur_revenue - prev_revenue) / prev_revenue * 100, 1)
            if prev_revenue > 0 else None
        )
        order_change_pct = (
            round((cur_orders - prev_orders) / prev_orders * 100, 1)
            if prev_orders > 0 else None
        )
        avg_order_value = round(cur_revenue / cur_orders, 2) if cur_orders > 0 else 0.0

        return {
            "period_days": days,
            "period_start": period_start,
            "period_end": now,
            "revenue": round(cur_revenue, 2),
            "orders": cur_orders,
            "average_order_value": avg_order_value,
            "previous_period_revenue": round(prev_revenue, 2),
            "previous_period_orders": prev_orders,
            "revenue_change_pct": revenue_change_pct,
            "order_change_pct": order_change_pct,
            "trend": trend,
        }

    async def get_top_products(
        self, store_id: uuid.UUID, days: int = 30, limit: int = 10,
    ) -> list[dict]:
        """
        Top products by realized revenue over the last `days` days,
        computed from actual order line items (WooCommerceOrderItem.total)
        — not WooCommerceProduct.total_sales, which is a lifetime
        WooCommerce counter unrelated to the selected period.
        """
        await self._get_store(store_id)
        days = max(1, min(days, 365))
        limit = max(1, min(limit, 50))
        period_start = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.db.execute(
            select(
                WooCommerceOrderItem.wc_product_id,
                WooCommerceOrderItem.name,
                WooCommerceOrderItem.sku,
                func.coalesce(func.sum(WooCommerceOrderItem.total), 0).label("revenue"),
                func.coalesce(func.sum(WooCommerceOrderItem.quantity), 0).label("units_sold"),
            )
            .join(WooCommerceOrder, WooCommerceOrderItem.order_id == WooCommerceOrder.id)
            .where(
                WooCommerceOrder.store_id == store_id,
                WooCommerceOrder.status.in_(REVENUE_ORDER_STATUSES),
                WooCommerceOrder.created_at >= period_start,
            )
            .group_by(
                WooCommerceOrderItem.wc_product_id,
                WooCommerceOrderItem.name,
                WooCommerceOrderItem.sku,
            )
            .order_by(desc("revenue"))
            .limit(limit)
        )

        return [
            {
                "wc_product_id": row[0],
                "name": row[1],
                "sku": row[2],
                "revenue": float(row[3] or 0),
                "units_sold": int(row[4] or 0),
            }
            for row in result.all()
        ]

    async def get_order_status_breakdown(self, store_id: uuid.UUID, days: int = 30) -> list[dict]:
        """
        Count of orders per status over the last `days` days — every
        status, unfiltered (this is an operational health view, not a
        revenue view, so pending/cancelled/etc. are deliberately included).
        """
        await self._get_store(store_id)
        days = max(1, min(days, 365))
        period_start = datetime.now(timezone.utc) - timedelta(days=days)

        result = await self.db.execute(
            select(WooCommerceOrder.status, func.count(WooCommerceOrder.id))
            .where(
                WooCommerceOrder.store_id == store_id,
                WooCommerceOrder.created_at >= period_start,
            )
            .group_by(WooCommerceOrder.status)
        )
        return [
            {"status": status.value if hasattr(status, "value") else status, "count": count}
            for status, count in result.all()
        ]

    # ═══════════════════════════════════════════════════════════════
    # SETTINGS
    # ═══════════════════════════════════════════════════════════════

    async def get_settings(self, store_id: uuid.UUID) -> WooCommerceSetting:
        """Get store settings."""
        result = await self.db.execute(
            select(WooCommerceSetting).where(WooCommerceSetting.store_id == store_id)
        )
        settings = result.scalar_one_or_none()
        if not settings:
            # Create default settings
            settings = WooCommerceSetting(store_id=store_id)
            self.db.add(settings)
            await self.db.commit()
            await self.db.refresh(settings)
        return settings

    async def update_settings(self, store_id: uuid.UUID, data) -> WooCommerceSetting:
        """Update store settings."""
        settings = await self.get_settings(store_id)

        update_fields = [
            "auto_sync_enabled", "sync_interval_hours", "sync_products",
            "sync_orders", "sync_customers", "sync_categories", "sync_coupons",
            "low_stock_threshold", "low_stock_alerts", "sync_failure_alerts",
            "email_alerts", "alert_email", "retention_days",
        ]

        for field in update_fields:
            value = getattr(data, field, None)
            if value is not None:
                setattr(settings, field, value)

        await self.db.commit()
        await self.db.refresh(settings)
        return settings

    # ═══════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════

    async def _get_store(self, store_id: uuid.UUID) -> WooCommerceStore:
        """Get a store by ID with ownership check."""
        result = await self.db.execute(
            select(WooCommerceStore).where(
                WooCommerceStore.id == store_id,
                WooCommerceStore.owner_id == self.user_id,
            )
        )
        store = result.scalar_one_or_none()
        if not store:
            raise StoreNotFoundError(str(store_id))
        if not store.is_active:
            raise StoreInactiveError(str(store_id))
        return store

    async def _create_alert(
        self,
        store_id: uuid.UUID,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        message: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ):
        """Create a system alert."""
        # Check for duplicate unresolved alerts
        existing = await self.db.execute(
            select(WooCommerceAlert).where(
                WooCommerceAlert.store_id == store_id,
                WooCommerceAlert.alert_type == alert_type,
                WooCommerceAlert.resource_id == resource_id,
                WooCommerceAlert.is_resolved == False,
            )
        )
        if existing.scalar_one_or_none():
            return  # Skip duplicate

        alert = WooCommerceAlert(
            store_id=store_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        self.db.add(alert)
        await self.db.flush()
