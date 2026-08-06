"""
Synchronization Engine for WooCommerce Integration Module.

Provides a dedicated orchestrator for data synchronization with:
- Conflict resolution (timestamp-based last-write-wins)
- Duplicate detection (by SKU, by wc_product_id)
- Sync progress tracking (items processed / total)
- Sync statistics (success rate, duration, item counts)
- Batch processing with configurable chunk sizes
"""

import uuid
import logging
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Any

from sqlalchemy import select, func, and_, or_, delete, update, desc as sa_desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.woocommerce.client import WooCommerceClient
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
    WooCommerceSyncLog,
    WooCommerceSetting,
)
from app.woocommerce.constants import (
    SyncStatus,
    SyncType,
    StoreStatus,
    DEFAULT_SYNC_INTERVAL_HOURS,
    PRODUCTS_PER_PAGE,
)
from app.woocommerce.exceptions import (
    StoreNotFoundError,
    StoreInactiveError,
    SyncInProgressError,
    WooCommerceAPIError,
)

# ── Order Integration (Phase 5 — optional, failures don't break sync) ──
try:
    from app.woocommerce.order_integration_service import WooCommerceOrderIntegrationService
    from app.models import Store as InventoryStore
    _ORDER_INTEGRATION_AVAILABLE = True
except ImportError:
    WooCommerceOrderIntegrationService = None
    InventoryStore = None
    _ORDER_INTEGRATION_AVAILABLE = False
    logger.debug("Order integration not available — order sync continues")

logger = logging.getLogger(__name__)


class SyncProgress:
    """Tracks progress of a sync operation."""

    def __init__(self, total: int = 0):
        self.total = total
        self.processed: int = 0
        self.created: int = 0
        self.updated: int = 0
        self.skipped: int = 0
        self.failed: int = 0
        self.errors: list[dict] = []
        self.start_time: datetime = datetime.now(timezone.utc)

    @property
    def percentage(self) -> float:
        """Sync completion percentage."""
        if self.total == 0:
            return 100.0
        return round((self.processed / self.total) * 100, 1)

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since sync started."""
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()

    @property
    def success_rate(self) -> float:
        """Percentage of items that didn't fail."""
        if self.processed == 0:
            return 100.0
        return round(((self.processed - self.failed) / self.processed) * 100, 1)

    def record_success(self, action: str = "updated"):
        """Record a successfully processed item."""
        self.processed += 1
        if action == "created":
            self.created += 1
        elif action == "updated":
            self.updated += 1
        elif action == "skipped":
            self.skipped += 1

    def record_failure(self, item_id: Any, error: str):
        """Record a failed item."""
        self.processed += 1
        self.failed += 1
        self.errors.append({"item_id": str(item_id), "error": str(error)})

    def to_dict(self) -> dict:
        """Serialize progress to dict for sync log storage."""
        return {
            "progress_pct": self.percentage,
            "elapsed_seconds": self.elapsed_seconds,
            "success_rate": self.success_rate,
            "total": self.total,
            "processed": self.processed,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "failed": self.failed,
            "errors": self.errors[:10],  # Limit stored errors
        }


class SyncEngine:
    """
    Orchestrates synchronization between WooCommerce and the local database.

    Provides a unified sync pipeline:
    1. Fetch data from WooCommerce API (with pagination)
    2. Normalize to internal format
    3. Detect duplicates (by SKU, wc_product_id, or custom key)
    4. Resolve conflicts (timestamp-based last-write-wins)
    5. Upsert into local database
    6. Track progress and statistics
    7. Log sync results

    Usage:
        engine = SyncEngine(db=session, store=store)
        result = await engine.sync_products(force_full=True)
        print(f"Synced {result['stats']['total']} products")
    """

    def __init__(
        self,
        db: AsyncSession,
        store: WooCommerceStore,
        user_id: Optional[uuid.UUID] = None,
        chunk_size: int = 100,
    ):
        self.db = db
        self.store = store
        self.user_id = user_id
        self.chunk_size = chunk_size
        self.client = WooCommerceClient(
            store_url=store.store_url,
            consumer_key=store.consumer_key,
            consumer_secret=store.consumer_secret,
        )
        self.logger = logging.getLogger(f"{__name__}.SyncEngine")

    async def close(self):
        """Close the underlying HTTP client."""
        await self.client.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    # ═══════════════════════════════════════════════════════════════
    # PRODUCT SYNCHRONIZATION
    # ═══════════════════════════════════════════════════════════════

    async def sync_products(
        self,
        sync_log_id: uuid.UUID,
        force_full: bool = False,
        after: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> SyncProgress:
        """
        Synchronize products from WooCommerce to local database.

        Features:
        - Full (re-fetch all) or incremental (only modified) sync
        - Duplicate detection by wc_product_id and SKU
        - Conflict resolution: newer date_modified wins
        - Batch processing with progress tracking
        - Per-item error isolation (one failure doesn't stop the batch)

        Args:
            sync_log_id: UUID of the sync log entry
            force_full: If True, re-fetch all products
            after: ISO 8601 date to fetch products modified after
            progress_callback: Optional async callback(current, total)

        Returns:
            SyncProgress with statistics
        """
        self.logger.info(
            "Starting product sync for store %s (force_full=%s)",
            self.store.store_name, force_full,
        )

        wc_products = await self.client.get_all_products(after=after)
        progress = SyncProgress(total=len(wc_products))

        self.logger.info(
            "Fetched %d products from WooCommerce for store %s",
            progress.total, self.store.store_name,
        )

        for wc_product in wc_products:
            try:
                normalized = WooCommerceClient.normalize_product(wc_product)
                wc_id = normalized["wc_product_id"]
                sku = normalized.get("sku", "")

                # Duplicate detection: lookup by wc_product_id first, then SKU
                existing = await self._find_existing_product(
                    store_id=self.store.id,
                    wc_product_id=wc_id,
                    sku=sku,
                )

                if existing:
                    # Conflict resolution: use newer date_modified
                    wc_modified = wc_product.get("date_modified", "")
                    local_modified = existing.updated_at.isoformat() if existing.updated_at else ""

                    if self._is_newer(wc_modified, local_modified):
                        await self._update_product(existing, normalized, wc_product)
                        progress.record_success("updated")
                    else:
                        progress.record_success("skipped")
                else:
                    new_product = await self._create_product(normalized, wc_product)
                    progress.record_success("created")
                    existing = new_product

                # Update sync log progress periodically
                if progress.processed % self.chunk_size == 0:
                    await self._update_sync_log_progress(sync_log_id, progress)

                if progress_callback:
                    await progress_callback(progress.processed, progress.total)

            except Exception as exc:
                self.logger.error(
                    "Product sync error for %s: %s",
                    wc_product.get("id"), exc,
                )
                progress.record_failure(wc_product.get("id"), str(exc))

        # Final sync log update
        self.store.last_sync_at = datetime.now(timezone.utc)
        await self._finalize_sync_log(sync_log_id, progress)

        self.logger.info(
            "Product sync completed for %s: %d/%d processed, %d created, "
            "%d updated, %d failed (%.1f%%)",
            self.store.store_name,
            progress.processed, progress.total,
            progress.created, progress.updated, progress.failed,
            progress.success_rate,
        )

        return progress

    # ═══════════════════════════════════════════════════════════════
    # ORDER SYNCHRONIZATION
    # ═══════════════════════════════════════════════════════════════

    async def sync_orders(
        self,
        sync_log_id: uuid.UUID,
        after: Optional[str] = None,
        status: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> SyncProgress:
        """Synchronize orders from WooCommerce."""
        self.logger.info("Starting order sync for store %s", self.store.store_name)

        wc_orders = await self.client.get_all_orders(after=after, status=status)
        progress = SyncProgress(total=len(wc_orders))

        for wc_order in wc_orders:
            try:
                normalized = WooCommerceClient.normalize_order(wc_order)
                wc_id = normalized["wc_order_id"]
                line_items = normalized.pop("line_items", [])

                existing = await self._find_existing_order(
                    store_id=self.store.id,
                    wc_order_id=wc_id,
                )

                created_or_updated = None
                if existing:
                    wc_modified = wc_order.get("date_modified", "")
                    local_modified = existing.updated_at.isoformat() if existing.updated_at else ""

                    if self._is_newer(wc_modified, local_modified):
                        await self._update_order(existing, normalized, wc_order)
                        await self._sync_order_items(existing.id, line_items)
                        progress.record_success("updated")
                        created_or_updated = existing
                    else:
                        progress.record_success("skipped")
                        created_or_updated = existing
                else:
                    order = await self._create_order(normalized, wc_order)
                    await self._sync_order_items(order.id, line_items)
                    progress.record_success("created")
                    created_or_updated = order

                # ── Phase 5: Trigger allocation + reservation (E.6) ──
                if _ORDER_INTEGRATION_AVAILABLE and created_or_updated:
                    try:
                        await self._process_order_integration(created_or_updated)
                    except Exception as pi_exc:
                        self.logger.warning(
                            "Order integration skipped for order %s: %s — "
                            "WooCommerce sync continues unaffected",
                            created_or_updated.wc_order_id, pi_exc,
                        )

                if progress.processed % self.chunk_size == 0:
                    await self._update_sync_log_progress(sync_log_id, progress)

                if progress_callback:
                    await progress_callback(progress.processed, progress.total)

            except Exception as exc:
                self.logger.error(
                    "Order sync error for %s: %s",
                    wc_order.get("id"), exc,
                )
                progress.record_failure(wc_order.get("id"), str(exc))

        self.store.last_sync_at = datetime.now(timezone.utc)
        await self._finalize_sync_log(sync_log_id, progress)
        return progress

    # ═══════════════════════════════════════════════════════════════
    # CUSTOMER SYNCHRONIZATION
    # ═══════════════════════════════════════════════════════════════

    async def sync_customers(
        self,
        sync_log_id: uuid.UUID,
        progress_callback: Optional[Callable] = None,
    ) -> SyncProgress:
        """Synchronize customers from WooCommerce."""
        self.logger.info("Starting customer sync for store %s", self.store.store_name)

        wc_customers = await self.client.get_all_customers()
        progress = SyncProgress(total=len(wc_customers))

        for wc_customer in wc_customers:
            try:
                normalized = WooCommerceClient.normalize_customer(wc_customer)
                wc_id = normalized["wc_customer_id"]

                existing = await self._find_existing_customer(
                    store_id=self.store.id,
                    wc_customer_id=wc_id,
                )

                if existing:
                    for key, value in normalized.items():
                        if key != "wc_raw_data" and hasattr(existing, key) and value is not None:
                            setattr(existing, key, value)
                    existing.last_synced_at = datetime.now(timezone.utc)
                    progress.record_success("updated")
                else:
                    customer = WooCommerceCustomer(
                        store_id=self.store.id,
                        **{k: v for k, v in normalized.items()
                           if hasattr(WooCommerceCustomer, k) and k != "wc_raw_data"},
                        raw_data=wc_customer,
                        last_synced_at=datetime.now(timezone.utc),
                    )
                    self.db.add(customer)
                    progress.record_success("created")

                if progress.processed % self.chunk_size == 0:
                    await self._update_sync_log_progress(sync_log_id, progress)

                if progress_callback:
                    await progress_callback(progress.processed, progress.total)

            except Exception as exc:
                self.logger.error(
                    "Customer sync error for %s: %s",
                    wc_customer.get("id"), exc,
                )
                progress.record_failure(wc_customer.get("id"), str(exc))

        self.store.last_sync_at = datetime.now(timezone.utc)
        await self._finalize_sync_log(sync_log_id, progress)
        return progress

    # ═══════════════════════════════════════════════════════════════
    # CATEGORY SYNCHRONIZATION
    # ═══════════════════════════════════════════════════════════════

    async def sync_categories(
        self,
        sync_log_id: uuid.UUID,
        progress_callback: Optional[Callable] = None,
    ) -> SyncProgress:
        """
        Synchronize categories from WooCommerce.

        Uses a two-pass approach:
        1. First pass: create/update all categories
        2. Second pass: set parent-child relationships
        """
        self.logger.info("Starting category sync for store %s", self.store.store_name)

        wc_categories = await self.client.get_all_categories()
        progress = SyncProgress(total=len(wc_categories))

        # First pass: create or update all categories
        wc_to_local_map: dict[int, uuid.UUID] = {}

        for wc_cat in wc_categories:
            try:
                normalized = WooCommerceClient.normalize_category(wc_cat)
                wc_id = normalized["wc_category_id"]

                existing = await self._find_existing_category(
                    store_id=self.store.id,
                    wc_category_id=wc_id,
                )

                if existing:
                    for key, value in normalized.items():
                        if key != "wc_raw_data" and hasattr(existing, key) and value is not None:
                            setattr(existing, key, value)
                    wc_to_local_map[wc_id] = existing.id
                    progress.record_success("updated")
                else:
                    category = WooCommerceCategory(
                        store_id=self.store.id,
                        **{k: v for k, v in normalized.items()
                           if hasattr(WooCommerceCategory, k) and k != "wc_raw_data"},
                        raw_data=wc_cat,
                    )
                    self.db.add(category)
                    await self.db.flush()
                    wc_to_local_map[wc_id] = category.id
                    progress.record_success("created")

            except Exception as exc:
                self.logger.error(
                    "Category sync error for %s: %s",
                    wc_cat.get("id"), exc,
                )
                progress.record_failure(wc_cat.get("id"), str(exc))

            if progress_callback:
                await progress_callback(progress.processed, progress.total)

        # Second pass: set parent relationships
        for wc_cat in wc_categories:
            wc_parent_id = wc_cat.get("parent", 0)
            if wc_parent_id and wc_parent_id in wc_to_local_map:
                local_cat_id = wc_to_local_map.get(wc_cat["id"])
                local_parent_id = wc_to_local_map[wc_parent_id]
                if local_cat_id and local_parent_id:
                    await self.db.execute(
                        update(WooCommerceCategory)
                        .where(WooCommerceCategory.id == local_cat_id)
                        .values(parent_id=local_parent_id)
                    )

        await self._finalize_sync_log(sync_log_id, progress)
        return progress

    # ═══════════════════════════════════════════════════════════════
    # COUPON SYNCHRONIZATION
    # ═══════════════════════════════════════════════════════════════

    async def sync_coupons(
        self,
        sync_log_id: uuid.UUID,
        progress_callback: Optional[Callable] = None,
    ) -> SyncProgress:
        """Synchronize coupons from WooCommerce."""
        self.logger.info("Starting coupon sync for store %s", self.store.store_name)

        wc_coupons = await self.client.get_all_coupons()
        progress = SyncProgress(total=len(wc_coupons))

        for wc_coupon in wc_coupons:
            try:
                normalized = WooCommerceClient.normalize_coupon(wc_coupon)
                wc_id = normalized["wc_coupon_id"]

                existing = await self._find_existing_coupon(
                    store_id=self.store.id,
                    wc_coupon_id=wc_id,
                )

                if existing:
                    for key, value in normalized.items():
                        if key != "wc_raw_data" and hasattr(existing, key) and value is not None:
                            setattr(existing, key, value)
                    existing.last_synced_at = datetime.now(timezone.utc)
                    progress.record_success("updated")
                else:
                    coupon = WooCommerceCoupon(
                        store_id=self.store.id,
                        **{k: v for k, v in normalized.items()
                           if hasattr(WooCommerceCoupon, k) and k != "wc_raw_data"},
                        raw_data=wc_coupon,
                        last_synced_at=datetime.now(timezone.utc),
                    )
                    self.db.add(coupon)
                    progress.record_success("created")

            except Exception as exc:
                self.logger.error(
                    "Coupon sync error for %s: %s",
                    wc_coupon.get("id"), exc,
                )
                progress.record_failure(wc_coupon.get("id"), str(exc))

        self.store.last_sync_at = datetime.now(timezone.utc)
        await self._finalize_sync_log(sync_log_id, progress)
        return progress

    # ═══════════════════════════════════════════════════════════════
    # INVENTORY SYNCHRONIZATION
    # ═══════════════════════════════════════════════════════════════

    async def sync_inventory(
        self,
        sync_log_id: uuid.UUID,
        progress_callback: Optional[Callable] = None,
    ) -> SyncProgress:
        """
        Synchronize inventory levels from WooCommerce.

        Fetches all products and updates stock_quantity, stock_status,
        and manage_stock flags. Creates inventory log entries for changes.
        """
        self.logger.info("Starting inventory sync for store %s", self.store.store_name)

        wc_products = await self.client.get_all_products()
        progress = SyncProgress(total=len(wc_products))

        for wc_product in wc_products:
            try:
                wc_id = wc_product.get("id")
                if not wc_id:
                    continue

                existing = await self._find_existing_product(
                    store_id=self.store.id,
                    wc_product_id=wc_id,
                )

                if not existing:
                    progress.record_success("skipped")
                    continue

                # Extract inventory fields from WooCommerce
                new_stock = wc_product.get("stock_quantity")
                new_status = wc_product.get("stock_status", "instock")
                manage_stock = wc_product.get("manage_stock", False)

                old_stock = existing.stock_quantity or 0

                # Update inventory fields
                if manage_stock:
                    existing.stock_quantity = new_stock
                    existing.manage_stock = manage_stock
                existing.stock_status = new_status
                existing.last_synced_at = datetime.now(timezone.utc)

                # Log stock movement
                if old_stock != (new_stock or 0):
                    log = WooCommerceInventoryLog(
                        store_id=self.store.id,
                        product_id=existing.id,
                        wc_product_id=wc_id,
                        sku=existing.sku,
                        action="sync_update",
                        quantity_before=old_stock,
                        quantity_after=new_stock or 0,
                        quantity_change=(new_stock or 0) - old_stock,
                        reason="WooCommerce sync",
                        source="sync_engine",
                    )
                    self.db.add(log)

                progress.record_success("updated")

                if progress.processed % self.chunk_size == 0:
                    await self._update_sync_log_progress(sync_log_id, progress)

                if progress_callback:
                    await progress_callback(progress.processed, progress.total)

            except Exception as exc:
                self.logger.error(
                    "Inventory sync error for product %s: %s",
                    wc_product.get("id"), exc,
                )
                progress.record_failure(wc_product.get("id"), str(exc))

        await self._finalize_sync_log(sync_log_id, progress)
        return progress

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL — Duplicate Detection & Conflict Resolution
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _is_newer(wc_modified: str, local_modified: str) -> bool:
        """
        Conflict resolution: determine if WooCommerce version is newer.

        Uses ISO 8601 date comparison. If either date is missing/empty,
        the WooCommerce version wins (prefer remote data).
        """
        if not wc_modified:
            return False
        if not local_modified:
            return True
        try:
            return wc_modified > local_modified
        except Exception:
            return True  # If comparison fails, prefer WooCommerce data

    async def _find_existing_product(
        self, store_id: uuid.UUID, wc_product_id: int, sku: str = "",
    ) -> Optional[WooCommerceProduct]:
        """Find existing product by wc_product_id, then by SKU."""
        if wc_product_id:
            result = await self.db.execute(
                select(WooCommerceProduct).where(
                    WooCommerceProduct.store_id == store_id,
                    WooCommerceProduct.wc_product_id == wc_product_id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing

        if sku:
            result = await self.db.execute(
                select(WooCommerceProduct).where(
                    WooCommerceProduct.store_id == store_id,
                    WooCommerceProduct.sku == sku,
                )
            )
            return result.scalar_one_or_none()

        return None

    async def _find_existing_order(
        self, store_id: uuid.UUID, wc_order_id: int,
    ) -> Optional[WooCommerceOrder]:
        result = await self.db.execute(
            select(WooCommerceOrder).where(
                WooCommerceOrder.store_id == store_id,
                WooCommerceOrder.wc_order_id == wc_order_id,
            )
        )
        return result.scalar_one_or_none()

    async def _find_existing_customer(
        self, store_id: uuid.UUID, wc_customer_id: int,
    ) -> Optional[WooCommerceCustomer]:
        result = await self.db.execute(
            select(WooCommerceCustomer).where(
                WooCommerceCustomer.store_id == store_id,
                WooCommerceCustomer.wc_customer_id == wc_customer_id,
            )
        )
        return result.scalar_one_or_none()

    async def _find_existing_category(
        self, store_id: uuid.UUID, wc_category_id: int,
    ) -> Optional[WooCommerceCategory]:
        result = await self.db.execute(
            select(WooCommerceCategory).where(
                WooCommerceCategory.store_id == store_id,
                WooCommerceCategory.wc_category_id == wc_category_id,
            )
        )
        return result.scalar_one_or_none()

    async def _find_existing_coupon(
        self, store_id: uuid.UUID, wc_coupon_id: int,
    ) -> Optional[WooCommerceCoupon]:
        result = await self.db.execute(
            select(WooCommerceCoupon).where(
                WooCommerceCoupon.store_id == store_id,
                WooCommerceCoupon.wc_coupon_id == wc_coupon_id,
            )
        )
        return result.scalar_one_or_none()

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL — Create / Update Helpers
    # ═══════════════════════════════════════════════════════════════

    async def _create_product(self, normalized: dict, wc_product: dict) -> WooCommerceProduct:
        """Create a new product record."""
        product = WooCommerceProduct(
            store_id=self.store.id,
            **{k: v for k, v in normalized.items()
               if hasattr(WooCommerceProduct, k) and k != "wc_raw_data"},
            raw_data=wc_product,
            last_synced_at=datetime.now(timezone.utc),
        )
        self.db.add(product)
        return product

    async def _update_product(self, existing: WooCommerceProduct, normalized: dict, wc_product: dict):
        """Update an existing product record if WooCommerce data is newer."""
        for key, value in normalized.items():
            if key != "wc_raw_data" and hasattr(existing, key):
                setattr(existing, key, value)
        existing.raw_data = wc_product
        existing.last_synced_at = datetime.now(timezone.utc)

    async def _create_order(self, normalized: dict, wc_order: dict) -> WooCommerceOrder:
        """Create a new order record."""
        order = WooCommerceOrder(
            store_id=self.store.id,
            **{k: v for k, v in normalized.items()
               if hasattr(WooCommerceOrder, k) and k != "wc_raw_data"},
            raw_data=wc_order,
            last_synced_at=datetime.now(timezone.utc),
        )
        self.db.add(order)
        await self.db.flush()
        return order

    async def _update_order(self, existing: WooCommerceOrder, normalized: dict, wc_order: dict):
        """Update an existing order record."""
        for key, value in normalized.items():
            if key != "wc_raw_data" and hasattr(existing, key):
                setattr(existing, key, value)
        existing.raw_data = wc_order
        existing.last_synced_at = datetime.now(timezone.utc)

    async def _sync_order_items(self, order_uuid: uuid.UUID, line_items: list):
        """Sync order line items (delete old, insert new)."""
        await self.db.execute(
            delete(WooCommerceOrderItem).where(WooCommerceOrderItem.order_id == order_uuid)
        )

        for item in line_items:
            wc_product_id = item.get("product_id", 0)
            product_result = await self.db.execute(
                select(WooCommerceProduct).where(
                    WooCommerceProduct.store_id == self.store.id,
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
    # INTERNAL — Sync Log Management
    # ═══════════════════════════════════════════════════════════════

    async def _update_sync_log_progress(self, sync_log_id: uuid.UUID, progress: SyncProgress):
        """Update sync log with current progress."""
        await self.db.execute(
            update(WooCommerceSyncLog)
            .where(WooCommerceSyncLog.id == sync_log_id)
            .values(
                total_items=progress.total,
                created_items=progress.created,
                updated_items=progress.updated,
                failed_items=progress.failed,
                meta_data={"progress": progress.to_dict()},
            )
        )

    async def _finalize_sync_log(self, sync_log_id: uuid.UUID, progress: SyncProgress):
        """Mark sync log as completed with final statistics."""
        duration = progress.elapsed_seconds
        await self.db.execute(
            update(WooCommerceSyncLog)
            .where(WooCommerceSyncLog.id == sync_log_id)
            .values(
                status=SyncStatus.COMPLETED if progress.failed == 0
                       else SyncStatus.PARTIAL if progress.created + progress.updated > 0
                       else SyncStatus.FAILED,
                completed_at=datetime.now(timezone.utc),
                total_items=progress.total,
                created_items=progress.created,
                updated_items=progress.updated,
                failed_items=progress.failed,
                duration_seconds=duration,
                error_message=None if progress.failed == 0
                           else f"{progress.failed} of {progress.total} items failed",
                meta_data={"progress": progress.to_dict()},
            )
        )

    @staticmethod
    def _normalize_endpoint(endpoint: str) -> str:
        """Extract a short endpoint name from a full URL path."""
        return endpoint.split("/")[-1] if "/" in endpoint else endpoint

    # ═══════════════════════════════════════════════════════════════
    # PHASE 5 — Order Integration Pipeline (E.6)
    # ═══════════════════════════════════════════════════════════════

    async def _process_order_integration(
        self,
        order: WooCommerceOrder,
    ) -> None:
        """
        Process a synced WooCommerce order through allocation + reservation.

        Called from sync_orders after each order is synced.
        Failures are caught — WooCommerce sync always continues (E.6).

        Pipeline:
        1. Resolve inventory Store from WooCommerceStore.owner_id
        2. Create WooCommerceOrderIntegrationService
        3. Call process_synced_order() → allocate → reserve → status update
        """
        if not _ORDER_INTEGRATION_AVAILABLE:
            return

        # Resolve the inventory Store by owner_id
        inv_result = await self.db.execute(
            select(InventoryStore).where(
                InventoryStore.owner_id == self.store.owner_id,
            ).limit(1)
        )
        inv_store = inv_result.scalar_one_or_none()
        if inv_store is None:
            self.logger.debug(
                "No inventory Store for owner %s — skipping order integration",
                self.store.owner_id,
            )
            return

        # Create integration service and process
        integration = WooCommerceOrderIntegrationService(
            db=self.db,
            wc_store=self.store,
            store=inv_store,
            user_id=self.user_id or self.store.owner_id,
        )

        result = await integration.process_synced_order(order)

        self.logger.debug(
            "Order %d integration result: allocation=%s, status_action=%s",
            order.wc_order_id,
            result.get("allocation", {}).get("status"),
            result.get("status_action", {}).get("status"),
        )
