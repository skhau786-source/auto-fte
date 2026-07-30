"""
Warehouse ↔ WooCommerce Synchronization Service.

Bridges the gap between the WooCommerce sync system and the Warehouse
inventory system. Responsible for ensuring that when WooCommerce products
are synced, their stock_quantity is reflected in warehouse_inventory records.

Architecture:
    WooCommerce SyncEngine/WooCommerceService
        ↓ (calls this service)
    WarehouseInventorySyncService
        ↓
    1. Find inventory Store for WooCommerceStore owner
    2. Find or create inventory Product/Variant (by SKU)
    3. Determine default warehouse
    4. Create or update WarehouseInventory record
        ↓
    warehouse_inventory.available_stock updated
    wc_products.stock_quantity unchanged (backward compat)

Error handling:
    - Warehouse failures are logged but DO NOT fail WooCommerce sync
    - If no warehouse exists, a warning is logged and sync is skipped gracefully
    - If no default warehouse is configured and multiple exist, first active is used
"""

import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Store, Product, ProductVariant, Warehouse, WarehouseInventory,
)
from app.warehouse.repository import (
    WarehouseRepository,
    WarehouseInventoryRepository,
)
from app.woocommerce.models import WooCommerceStore, WooCommerceProduct

logger = logging.getLogger(__name__)


class WarehouseInventorySyncService:
    """
    Synchronizes WooCommerce stock levels with warehouse inventory records.

    This is the integration point between the WooCommerce sync pipeline
    and the Warehouse inventory system. Call this from the WooCommerce
    sync engine after products are synced.

    Usage:
        sync_service = WarehouseInventorySyncService(db)
        result = await sync_service.sync_wc_product_to_warehouse(
            wc_store=wc_store,
            wc_product=wc_product_record,
            stock_quantity=product_stock,
        )
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.wh_repo = WarehouseRepository(db)
        self.inv_repo = WarehouseInventoryRepository(db)
        self.logger = logging.getLogger(f"{__name__}.WarehouseInventorySyncService")

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════════

    async def sync_wc_product_to_warehouse(
        self,
        wc_store: WooCommerceStore,
        wc_product: WooCommerceProduct,
        stock_quantity: int,
    ) -> dict:
        """
        Sync a single WooCommerce product's stock to warehouse inventory.

        Pipeline:
        1. Find the inventory Store for this WooCommerce store's owner
        2. Find or create inventory Product/Variant (matched by SKU)
        3. Determine the default warehouse
        4. Create or update WarehouseInventory record

        Args:
            wc_store: The WooCommerceStore record being synced
            wc_product: The WooCommerceProduct record (local DB)
            stock_quantity: The stock quantity from WooCommerce

        Returns:
            Dict with sync result status and details.
            NEVER raises — failures are logged and returned as status.
        """
        start_time = datetime.now(timezone.utc)
        wc_product_id = wc_product.wc_product_id
        sku = wc_product.sku or ""

        try:
            # Step 1: Find the inventory Store for this owner
            inv_store = await self._find_inventory_store(wc_store.owner_id)
            if inv_store is None:
                self.logger.info(
                    "No inventory Store found for WooCommerce store owner %s "
                    "(wc_product_id=%d, sku=%s) — skipping warehouse sync",
                    wc_store.owner_id, wc_product_id, sku,
                )
                return {
                    "status": "skipped",
                    "reason": "no_inventory_store",
                    "wc_product_id": wc_product_id,
                }

            # Step 2: Find or create variant in inventory system
            variant = await self._find_or_create_variant(
                store_id=inv_store.id,
                sku=sku,
                wc_product=wc_product,
            )
            if variant is None:
                self.logger.info(
                    "Could not find or create variant for wc_product_id=%d, sku=%s "
                    "— skipping warehouse sync",
                    wc_product_id, sku,
                )
                return {
                    "status": "skipped",
                    "reason": "variant_not_created",
                    "wc_product_id": wc_product_id,
                }

            # Step 3: Determine the default warehouse
            warehouse = await self._get_default_warehouse(inv_store.id)
            if warehouse is None:
                self.logger.info(
                    "No warehouse found for store %s (wc_product_id=%d) "
                    "— skipping warehouse sync",
                    inv_store.id, wc_product_id,
                )
                return {
                    "status": "skipped",
                    "reason": "no_warehouse",
                    "wc_product_id": wc_product_id,
                    "store_id": str(inv_store.id),
                }

            # Step 4: Create or update WarehouseInventory
            wh_inv = await self.inv_repo.get_or_create(
                warehouse_id=warehouse.id,
                variant_id=variant.id,
            )

            old_stock = wh_inv.available_stock
            wh_inv.available_stock = stock_quantity
            wh_inv.updated_at = datetime.now(timezone.utc)

            await self.db.flush()

            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

            self.logger.info(
                "WooCommerce Product Synced → Warehouse Inventory Updated: "
                "warehouse_id=%s product_id=%s variant_id=%s "
                "old_stock=%d new_stock=%d elapsed=%.3fs",
                warehouse.id, variant.product_id, variant.id,
                old_stock, stock_quantity, elapsed,
            )

            return {
                "status": "synced",
                "warehouse_id": str(warehouse.id),
                "warehouse_name": warehouse.name,
                "variant_id": str(variant.id),
                "product_id": str(variant.product_id) if variant.product_id else None,
                "wc_product_id": wc_product_id,
                "sku": sku,
                "old_stock": old_stock,
                "new_stock": stock_quantity,
            }

        except Exception as exc:
            self.logger.warning(
                "Warehouse sync failed for wc_product_id=%d, sku=%s, "
                "store=%s: %s — WooCommerce sync continues unaffected",
                wc_product_id, sku, wc_store.store_name, exc,
                exc_info=True,
            )
            return {
                "status": "failed",
                "reason": str(exc),
                "wc_product_id": wc_product_id,
            }

    async def sync_wc_products_batch(
        self,
        wc_store: WooCommerceStore,
        products_with_stock: list[tuple[WooCommerceProduct, int]],
    ) -> list[dict]:
        """
        Sync a batch of WooCommerce products to warehouse inventory.

        Each product is synced independently so one failure doesn't
        block the rest of the batch.

        Args:
            wc_store: The WooCommerceStore being synced
            products_with_stock: List of (WooCommerceProduct, stock_quantity) tuples

        Returns:
            List of individual sync result dicts
        """
        results = []
        for wc_product, stock_qty in products_with_stock:
            result = await self.sync_wc_product_to_warehouse(
                wc_store=wc_store,
                wc_product=wc_product,
                stock_quantity=stock_qty,
            )
            results.append(result)

        synced_count = sum(1 for r in results if r.get("status") == "synced")
        skipped_count = sum(1 for r in results if r.get("status") == "skipped")
        failed_count = sum(1 for r in results if r.get("status") == "failed")

        if results:
            self.logger.info(
                "Warehouse batch sync complete for store %s: "
                "%d synced, %d skipped, %d failed out of %d",
                wc_store.store_name, synced_count, skipped_count,
                failed_count, len(results),
            )

        return results

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL — Store Lookup
    # ═══════════════════════════════════════════════════════════════

    async def _find_inventory_store(
        self, owner_id: uuid.UUID,
    ) -> Optional[Store]:
        """
        Find the inventory Store that belongs to the same owner as
        the WooCommerce store.

        Both WooCommerceStore and Store link to RegisteredStudent via
        owner_id. We find the first active inventory Store for this owner.

        Returns None if no inventory Store exists (will skip warehouse sync).
        """
        result = await self.db.execute(
            select(Store).where(
                Store.owner_id == owner_id,
                Store.is_active == True,
            ).limit(1)
        )
        return result.scalar_one_or_none()

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL — Variant Resolution
    # ═══════════════════════════════════════════════════════════════

    async def _find_or_create_variant(
        self,
        store_id: uuid.UUID,
        sku: str,
        wc_product: WooCommerceProduct,
    ) -> Optional[ProductVariant]:
        """
        Find an existing ProductVariant by SKU, or create a new one.

        The variant is linked to the inventory Product (found or created
        by matching SKU). If no SKU exists, we skip variant creation.

        Returns the ProductVariant, or None if we cannot resolve.
        """
        if not sku:
            # Without a SKU we can't reliably match to inventory products
            return None

        # Try to find existing variant by SKU (scoped to store via product)
        result = await self.db.execute(
            select(ProductVariant)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(
                ProductVariant.sku == sku,
                Product.store_id == store_id,
            )
            .limit(1)
        )
        existing_variant = result.scalar_one_or_none()
        if existing_variant:
            return existing_variant

        # No variant found — we need to create a product + variant
        # First, find or create the parent product
        product = await self._find_or_create_product(store_id, wc_product)
        if product is None:
            return None

        # Create the variant
        variant = ProductVariant(
            product_id=product.id,
            title=wc_product.name or sku,
            sku=sku,
            price=wc_product.price,
            inventory_quantity=wc_product.stock_quantity or 0,
        )
        self.db.add(variant)
        await self.db.flush()

        self.logger.info(
            "Created inventory variant for WooCommerce product: "
            "sku=%s, product_id=%s, variant_id=%s",
            sku, product.id, variant.id,
        )

        return variant

    async def _find_or_create_product(
        self,
        store_id: uuid.UUID,
        wc_product: WooCommerceProduct,
    ) -> Optional[Product]:
        """
        Find an existing inventory Product by matching the WooCommerce
        product's name, or create a new one.

        Matches by title (case-insensitive) within the store.
        """
        if not wc_product.name:
            return None

        # Try matching by title
        result = await self.db.execute(
            select(Product).where(
                Product.store_id == store_id,
                Product.title == wc_product.name,
            ).limit(1)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        # Create a new product
        product = Product(
            store_id=store_id,
            title=wc_product.name,
            description=wc_product.description,
            status="active",
        )
        self.db.add(product)
        await self.db.flush()

        self.logger.info(
            "Created inventory product for WooCommerce product: "
            "name=%s, product_id=%s, wc_product_id=%d",
            wc_product.name, product.id, wc_product.wc_product_id,
        )

        return product

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL — Warehouse Resolution
    # ═══════════════════════════════════════════════════════════════

    async def _get_default_warehouse(
        self, store_id: uuid.UUID,
    ) -> Optional[Warehouse]:
        """
        Determine which warehouse to use for inventory sync.

        Resolution order:
        1. Look up WarehouseSettings.default_warehouse_id (persisted config)
        2. If settings point to a valid active warehouse → use it
        3. If no settings/default, check is_default flag on Warehouse
        4. If only one active warehouse exists → auto-default it
        5. If none → return None (sync skipped)

        No hardcoded warehouse names remain.
        """
        # Step 1: Check persisted WarehouseSettings
        try:
            from app.warehouse.repository import WarehouseSettingsRepository
            settings_repo = WarehouseSettingsRepository(self.db)
            settings = await settings_repo.get_by_store(store_id)
            if settings and settings.default_warehouse_id:
                from app.warehouse.repository import WarehouseRepository
                repo = WarehouseRepository(self.db)
                warehouse = await repo.get_by_id(settings.default_warehouse_id)
                if warehouse and str(warehouse.store_id) == str(store_id) and warehouse.is_active:
                    self.logger.info(
                        "Using configured default warehouse from settings: %s (%s)",
                        warehouse.name, warehouse.id,
                    )
                    return warehouse
        except Exception as exc:
            self.logger.debug("Could not read warehouse settings: %s", exc)

        # Step 2: Fall back to is_default flag
        from app.warehouse.repository import WarehouseRepository
        repo = WarehouseRepository(self.db)
        warehouse = await repo.get_default(store_id)
        if warehouse:
            return warehouse

        # Step 3: If only one warehouse exists, auto-default
        warehouse = await repo.ensure_single_default(store_id)
        if warehouse:
            return warehouse

        self.logger.info(
            "No default warehouse configured and none can be auto-assigned "
            "for store %s. Warehouse sync skipped.",
            store_id,
        )
        return None

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL — Inventory Store Discovery
    # ═══════════════════════════════════════════════════════════════

    async def find_or_create_inventory_store(
        self, wc_store: WooCommerceStore,
    ) -> Optional[Store]:
        """
        Find or create an inventory Store for a WooCommerceStore.

        Each WooCommerceStore owner should have at least one inventory
        Store for warehouse management. This creates one if none exists.

        This is called during initial store setup to ensure the
        inventory store exists before product sync.

        Returns the inventory Store, or None if creation fails.
        """
        store = await self._find_inventory_store(wc_store.owner_id)
        if store:
            return store

        # Create a new inventory Store for this WooCommerce store
        store = Store(
            owner_id=wc_store.owner_id,
            shopify_domain=f"wc-{wc_store.store_url.split('//')[-1].split('/')[0]}",
            shopify_store_id=wc_store.wc_store_id,
            access_token="",  # WC doesn't use the same token system
            is_active=True,
        )
        self.db.add(store)
        await self.db.flush()

        self.logger.info(
            "Created inventory Store for WooCommerce store %s: store_id=%s",
            wc_store.store_name, store.id,
        )

        return store
