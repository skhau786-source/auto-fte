"""
Service Layer for the Inventory Management module.

All business logic lives here. Repositories handle data access;
the service orchestrates, validates, and coordinates transactions.

The service NEVER raises HTTPException — it raises domain exceptions
(from exceptions.py) that the router layer catches and converts to HTTP.
"""

import uuid
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Store,
    Product,
    ProductVariant,
    InventoryTransaction,
)
from app.inventory.constants import TransactionType, InventoryAction
from app.inventory.repository import (
    ProductRepository,
    VariantRepository,
    TransactionRepository,
    LogRepository,
)
from app.inventory.exceptions import (
    ProductNotFoundError,
    VariantNotFoundError,
    DuplicateSKUError,
    InsufficientStockError,
    InvalidStoreOwnershipError,
    ShopifySyncError,
)
from app.shopify.shopify_client import ShopifyClient
from app.inventory.aggregation_cache import aggregation_cache


class InventoryService:
    """
    Orchestrates inventory operations.

    Usage:
        service = InventoryService(db=db, store=store, user_id=current_user.id)
        product = await service.create_product(data)
    """

    def __init__(
        self,
        db: AsyncSession,
        store: Store,
        user_id: Optional[uuid.UUID] = None,
    ):
        self.db = db
        self.store = store
        self.user_id = user_id

        # Repositories
        self.product_repo = ProductRepository(db)
        self.variant_repo = VariantRepository(db)
        self.transaction_repo = TransactionRepository(db)
        self.log_repo = LogRepository(db)

        # Logger
        self.logger = logging.getLogger(f"{__name__}.InventoryService")

    # ═══════════════════════════════════════════════════════════════
    # PRODUCT CRUD
    # ═══════════════════════════════════════════════════════════════

    async def create_product(self, data) -> Product:
        """
        Create a product locally with its variants.

        Validates:
        - No duplicate SKU within the store
        - At least basic fields are present (title)
        """
        # ── Validate SKU uniqueness (across all variants) ──
        for v_data in data.variants:
            if v_data.sku:
                existing = await self.variant_repo.get_by_sku(v_data.sku, self.store.id)
                if existing:
                    raise DuplicateSKUError(v_data.sku)

        # ── Create product ──
        product_data = data.model_dump(exclude={"variants"}, exclude_unset=True)
        product = await self.product_repo.create(self.store.id, product_data)

        # ── Create variants ──
        for v_data in data.variants:
            variant_data = v_data.model_dump(exclude_unset=True)
            await self.variant_repo.create(product.id, variant_data)

        # Refresh the product including its variants relationship so
        # ``product.variants`` is populated (avoids async lazy-load).
        await self.db.refresh(product, attribute_names=["variants"])

        # ── Log (only if variants exist — log FK references product_variants) ──
        if product.variants:
            await self.log_repo.create(
                variant_id=product.variants[0].id,
                action=InventoryAction.CREATED.value,
                details={
                    "product_id": str(product.id),
                    "title": product.title,
                    "variants_count": len(data.variants),
                },
                performed_by=self.user_id,
            )

        await self.db.commit()
        await self.db.refresh(product, attribute_names=["variants"])
        return product

    async def get_product(self, product_id: uuid.UUID) -> Product:
        """Fetch a product by ID. Validates store ownership."""
        product = await self.product_repo.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(str(product_id))

        self._ensure_store_owns_product(product)
        return product

    async def update_product(self, product_id: uuid.UUID, data) -> Product:
        """
        Partially update a product's scalar fields (title, description, vendor, etc.).

        Only the fields sent in the request are changed (PATCH semantics).
        Uses model_dump(exclude_unset=True) to detect which fields were provided.

        Note: Variant-level changes (quantity, price, SKU) are handled via
        dedicated endpoints (adjust_inventory, etc.) to keep operations atomic.
        """
        product = await self.product_repo.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(str(product_id))

        self._ensure_store_owns_product(product)

        # ── Update product fields only (exclude variants) ──
        update_data = data.model_dump(exclude={"variants"}, exclude_unset=True)
        if update_data:
            product = await self.product_repo.update(product_id, update_data)
            if product is None:
                raise ProductNotFoundError(str(product_id))

            # ── Log product-level changes (only if variants exist) ──
            if product.variants:
                await self.log_repo.create(
                    variant_id=product.variants[0].id,
                    action=InventoryAction.UPDATED.value,
                    details={
                        "product_id": str(product.id),
                        "updated_fields": list(update_data.keys()),
                    },
                    performed_by=self.user_id,
                )

        await self.db.commit()
        await self.db.refresh(product, attribute_names=["variants"])
        return product

    async def delete_product(self, product_id: uuid.UUID) -> dict:
        """Delete a product and cascade all related data (variants, txns, logs)."""
        product = await self.product_repo.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(str(product_id))

        self._ensure_store_owns_product(product)

        # Capture info for the response before deletion
        title = product.title
        deleted = await self.product_repo.delete(product_id)
        if not deleted:
            raise ProductNotFoundError(str(product_id))

        # ── Log (we no longer have the product, so use a generic log) ──
        # Since the product is deleted, we skip variant-level log.
        # The service caller can know deletion happened.

        await self.db.commit()
        return {
            "message": f"Product '{title}' deleted successfully",
            "deleted_product_id": product_id,
        }

    # ═══════════════════════════════════════════════════════════════
    # PRODUCT LISTING / SEARCH
    # ═══════════════════════════════════════════════════════════════

    async def list_products(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        status: Optional[str] = None,
        category_id: Optional[uuid.UUID] = None,
        vendor: Optional[str] = None,
        product_type: Optional[str] = None,
        low_stock_only: bool = False,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> tuple[list[Product], int]:
        """List products with search, filter, sort, and pagination."""
        return await self.product_repo.list_products(
            store_id=self.store.id,
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

    # ═══════════════════════════════════════════════════════════════
    # INVENTORY ADJUSTMENTS
    # ═══════════════════════════════════════════════════════════════

    async def adjust_inventory(
        self,
        variant_id: uuid.UUID,
        quantity_change: int,
        reason: Optional[str] = None,
        commit: bool = True,
    ) -> dict:
        """
        Adjust inventory quantity for a single variant.

        This is the core inventory operation:
        1. Validate variant exists and belongs to store
        2. Validate stock won't go negative
        3. Update the quantity
        4. Record transaction (immutable audit trail)
        5. Log the event
        6. Commit local changes FIRST (before any external API call)
        7. Attempt Shopify sync (best-effort — local state already persisted)
        8. If sync succeeded, persist the synced flag

        When *commit* is False, the caller must commit explicitly.
        This is used by bulk_adjust_inventory to keep the batch atomic.
        """
        variant = await self.variant_repo.get_by_id(variant_id)
        if variant is None:
            raise VariantNotFoundError(str(variant_id))

        self._ensure_store_owns_variant(variant)

        # ── Validate stock ──
        quantity_before = variant.inventory_quantity
        quantity_after = quantity_before + quantity_change

        if quantity_after < 0:
            raise InsufficientStockError(
                variant_id=str(variant_id),
                current_quantity=quantity_before,
                requested_change=quantity_change,
            )

        # ── Update quantity ──
        variant.inventory_quantity = quantity_after

        # ── Create transaction (immutable audit record) ──
        txn = await self.transaction_repo.create(
            variant_id=variant_id,
            transaction_type=TransactionType.ADJUSTMENT,
            quantity_change=quantity_change,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            reason=reason,
            performed_by=self.user_id,
        )

        # ── Log ──
        await self.log_repo.create(
            variant_id=variant_id,
            action=InventoryAction.INVENTORY_ADJUSTED.value,
            details={
                "quantity_before": quantity_before,
                "quantity_after": quantity_after,
                "change": quantity_change,
                "reason": reason,
            },
            performed_by=self.user_id,
        )

        # ── Commit local changes FIRST (before any external API call) ──
        if commit:
            await self.db.commit()

        # ── Attempt Shopify sync (best-effort — local state is already persisted) ──
        try:
            synced_to_shopify = await self._try_shopify_sync(variant, txn)
        except ShopifySyncError:
            synced_to_shopify = False
            self.logger.warning(
                "Local inventory updated for variant %s but Shopify sync failed",
                variant_id,
            )

        # ── If sync succeeded, persist the synced flag ──
        if synced_to_shopify:
            if commit:
                # After first commit — ORM objects are expired, use explicit UPDATE
                try:
                    await self.transaction_repo.mark_synced(txn.id)
                    await self.db.commit()
                except Exception as exc:
                    self.logger.error(
                        "Shopify sync succeeded for variant %s but failed to "
                        "persist synced flag: %s. Transaction %s left unsynced for retry.",
                        variant_id,
                        exc,
                        txn.id,
                    )
                    synced_to_shopify = False
            else:
                # No prior commit — ORM objects are still active, set directly
                txn.synced_to_shopify = True
                txn.synced_at = datetime.now(timezone.utc)

        return {
            "variant_id": variant_id,
            "quantity_before": quantity_before,
            "quantity_after": quantity_after,
            "quantity_change": quantity_change,
            "transaction_id": txn.id,
            "synced_to_shopify": synced_to_shopify,
            "message": f"Stock {'increased' if quantity_change > 0 else 'decreased'} by {abs(quantity_change)}",
        }

    async def bulk_adjust_inventory(
        self, adjustments: list
    ) -> list[dict]:
        """
        Process multiple inventory adjustments in a single transaction.

        Unlike calling adjust_inventory() in a loop (which commits per item),
        this method passes commit=False so that all adjustments are finalized
        with a single commit at the end. If ANY adjustment fails with an
        unexpected error, the ENTIRE batch is rolled back.

        Expected errors (validation, ownership, stock) are collected per item
        and do NOT roll back the rest of the batch.
        """
        results = []

        for adj in adjustments:
            try:
                result = await self.adjust_inventory(
                    variant_id=adj.variant_id,
                    quantity_change=adj.quantity_change,
                    reason=adj.reason,
                    commit=False,  # Defer commit to the single batch commit below
                )
                results.append({**result, "success": True})
            except (VariantNotFoundError, InsufficientStockError, InvalidStoreOwnershipError) as e:
                results.append({
                    "variant_id": adj.variant_id,
                    "error": e.message,
                    "success": False,
                })

        # Single commit for all successful adjustments in the batch
        await self.db.commit()

        return results

    # ═══════════════════════════════════════════════════════════════
    # LOW STOCK
    # ═══════════════════════════════════════════════════════════════

    async def get_low_stock(
        self, threshold: int = 10, page: int = 1, page_size: int = 50
    ) -> tuple[list[dict], int]:
        """
        Find all variants where inventory <= threshold.
        Returns enriched data with product titles.
        """
        variants, total = await self.variant_repo.get_low_stock(
            store_id=self.store.id,
            threshold=threshold,
            page=page,
            page_size=page_size,
        )

        items = []
        for v in variants:
            items.append({
                "variant_id": v.id,
                "variant_title": v.title,
                "sku": v.sku,
                "product_title": v.product.title if v.product else "N/A",
                "product_id": v.product.id if v.product else None,
                "inventory_quantity": v.inventory_quantity,
                "low_stock_threshold": v.low_stock_threshold or threshold,
                "days_until_out": None,  # Requires velocity data — future enhancement
            })

        return items, total

    async def set_low_stock_threshold(
        self, variant_id: uuid.UUID, threshold: int
    ) -> ProductVariant:
        """Set or clear the custom low-stock threshold for a variant."""
        variant = await self.variant_repo.get_by_id(variant_id)
        if variant is None:
            raise VariantNotFoundError(str(variant_id))

        self._ensure_store_owns_variant(variant)

        variant.low_stock_threshold = threshold if threshold > 0 else None

        await self.log_repo.create(
            variant_id=variant_id,
            action=InventoryAction.THRESHOLD_UPDATED.value,
            details={
                "new_threshold": threshold,
            },
            performed_by=self.user_id,
        )

        await self.db.commit()
        return variant

    # ═══════════════════════════════════════════════════════════════
    # HISTORY / AUDIT TRAIL
    # ═══════════════════════════════════════════════════════════════

    async def get_history(
        self,
        variant_id: Optional[uuid.UUID] = None,
        transaction_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[InventoryTransaction], int]:
        """Get paginated inventory transaction history for the store."""
        # Convert string to enum if provided
        txn_type_enum = None
        if transaction_type:
            try:
                txn_type_enum = TransactionType(transaction_type)
            except ValueError:
                pass  # Invalid type — will filter to zero results

        return await self.transaction_repo.list_history(
            store_id=self.store.id,
            variant_id=variant_id,
            transaction_type=txn_type_enum,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )

    # ═══════════════════════════════════════════════════════════════
    # DASHBOARD
    # ═══════════════════════════════════════════════════════════════

    async def get_dashboard(self) -> dict:
        """Aggregated dashboard data for the store."""
        stats = await self.product_repo.dashboard_stats(self.store.id)
        recent_txns = await self.transaction_repo.get_recent(self.store.id, limit=10)
        low_stock_items, _ = await self.variant_repo.get_low_stock(
            self.store.id, threshold=10, page=1, page_size=5
        )

        return {
            **stats,
            "recent_transactions": recent_txns,
            "top_low_stock": [
                {
                    "variant_id": v.id,
                    "variant_title": v.title,
                    "sku": v.sku,
                    "product_title": v.product.title if v.product else "N/A",
                    "product_id": v.product.id if v.product else None,
                    "inventory_quantity": v.inventory_quantity,
                    "low_stock_threshold": v.low_stock_threshold or 10,
                }
                for v in low_stock_items
            ],
        }

    # ═══════════════════════════════════════════════════════════════
    # SHOPIFY SYNC
    # ═══════════════════════════════════════════════════════════════

    async def sync_from_shopify(self, force_full: bool = False) -> dict:
        """
        Fetch products from Shopify and upsert them into the local database.

        Flow:
        1. Create ShopifyClient from store credentials
        2. Fetch ALL products with variants via paginated GraphQL
        3. For each product: create or update locally (upsert by shopify_product_id)
        4. For each variant: create or update locally (upsert by shopify_variant_id)
        5. Update inventory quantities from Shopify
        6. Store raw shopify_data as JSONB snapshot
        7. Return accurate sync summary
        """
        if not self.store.shopify_domain or not self.store.access_token:
            raise ShopifySyncError("Store is not connected to Shopify")

        if not self.store.shopify_location_id:
            self.logger.warning(
                "Store %s has no location_id — inventory levels will not be synced",
                self.store.shopify_domain,
            )

        self.logger.info(
            "Starting Shopify sync for store %s (force_full=%s)",
            self.store.shopify_domain,
            force_full,
        )

        client = ShopifyClient(
            shop_domain=self.store.shopify_domain,
            access_token=self.store.access_token,
            location_id=self.store.shopify_location_id,
        )

        try:
            self.logger.info("Fetching products from Shopify...")
            shopify_products = await client.fetch_all_products()
            self.logger.info("Fetched %d products from Shopify", len(shopify_products))
        except Exception as exc:
            raise ShopifySyncError(str(exc))
        finally:
            await client.close()

        stats = {
            "products_created": 0,
            "products_updated": 0,
            "variants_created": 0,
            "variants_updated": 0,
            "inventory_updated": 0,
        }

        for sp in shopify_products:
            # ── Upsert product ──
            existing_product = await self.product_repo.get_by_shopify_id(
                sp["id"], self.store.id
            )

            product_fields = {
                "title": sp.get("title", ""),
                "description": sp.get("body_html"),
                "vendor": sp.get("vendor"),
                "product_type": sp.get("product_type"),
                "status": (sp.get("status") or "active").lower(),
                "featured_image_url": sp.get("featured_image_url"),
                "shopify_data": sp,
            }

            if existing_product:
                updated = await self.product_repo.update(existing_product.id, product_fields)
                if updated:
                    stats["products_updated"] += 1
                product_id = existing_product.id
            else:
                product_fields["shopify_product_id"] = sp["id"]
                new_product = await self.product_repo.create(self.store.id, product_fields)
                stats["products_created"] += 1
                product_id = new_product.id

            # ── Upsert variants ──
            for sv in sp.get("variants", []):
                existing_variant = await self.variant_repo.get_by_shopify_id(sv["id"])

                variant_fields = {
                    "title": sv.get("title", ""),
                    "sku": sv.get("sku"),
                    "barcode": sv.get("barcode"),
                    "price": Decimal(str(sv.get("price", "0.00"))),
                    "compare_at_price": Decimal(str(sv["compare_at_price"])) if sv.get("compare_at_price") else None,
                    "inventory_quantity": sv.get("inventory_quantity", 0),
                    "requires_shipping": sv.get("requires_shipping", True),
                    "shopify_inventory_item_id": sv.get("inventory_item_id"),
                    "shopify_data": sv,
                }

                if existing_variant:
                    await self.variant_repo.update(existing_variant.id, variant_fields)
                    stats["variants_updated"] += 1
                else:
                    variant_fields["shopify_variant_id"] = sv["id"]
                    await self.variant_repo.create(product_id, variant_fields)
                    stats["variants_created"] += 1

                stats["inventory_updated"] += 1

        await self.db.commit()

        # Invalidate aggregation cache after Shopify sync
        try:
            await aggregation_cache.invalidate_store(self.store.id)
        except Exception as cache_exc:
            self.logger.warning(
                "Cache invalidation failed after Shopify sync: %s", cache_exc,
            )

        stats["message"] = (
            f"Synced {stats['products_created'] + stats['products_updated']} "
            f"products and {stats['variants_created'] + stats['variants_updated']} variants from Shopify"
        )
        self.logger.info("Shopify sync completed: %s", stats)
        return stats

    # ═══════════════════════════════════════════════════════════════
    # WEBHOOK HANDLERS
    # ═══════════════════════════════════════════════════════════════

    async def update_inventory_from_webhook(
        self,
        inventory_item_id: int,
        location_id: int,
        new_quantity: int,
    ) -> dict:
        """
        Update local inventory from a Shopify webhook.

        Unlike adjust_inventory(), this method does NOT push the change
        back to Shopify — the change originated FROM Shopify.
        Syncing back would create a circular loop.

        Args:
            inventory_item_id: Shopify inventory item ID.
            location_id: Shopify location where the change occurred.
            new_quantity: The new available quantity from Shopify.

        Returns:
            Dict with status and variant_id.
        """
        variant = await self.variant_repo.get_by_inventory_item_id(inventory_item_id)
        if variant is None:
            self.logger.info(
                "Inventory webhook: variant not found for inventory_item_id=%d",
                inventory_item_id,
            )
            return {"status": "ignored", "reason": "variant_not_found"}

        self._ensure_store_owns_variant(variant)

        # ── Log warning if webhook location differs from the store's primary location ──
        if self.store.shopify_location_id and location_id != self.store.shopify_location_id:
            self.logger.warning(
                "Inventory webhook: variant %s updated at location %d, "
                "but store's primary location is %d. "
                "Multi-location inventory may be out of sync.",
                variant.id,
                location_id,
                self.store.shopify_location_id,
            )

        quantity_before = variant.inventory_quantity
        quantity_change = new_quantity - quantity_before

        if quantity_change == 0:
            return {
                "status": "unchanged",
                "variant_id": str(variant.id),
                "quantity": quantity_before,
            }

        # ── Update quantity directly (NO sync back to Shopify) ──
        variant.inventory_quantity = new_quantity

        # ── Record transaction (audit trail) ──
        txn = await self.transaction_repo.create(
            variant_id=variant.id,
            transaction_type=TransactionType.SHOPIFY_SYNC,
            quantity_change=quantity_change,
            quantity_before=quantity_before,
            quantity_after=new_quantity,
            reason="Webhook: inventory_levels/update",
        )

        # Mark as synced — the change came FROM Shopify
        txn.synced_to_shopify = True
        txn.synced_at = datetime.now(timezone.utc)

        # ── Log the event ──
        await self.log_repo.create(
            variant_id=variant.id,
            action=InventoryAction.WEBHOOK_UPDATED.value,
            details={
                "inventory_item_id": inventory_item_id,
                "location_id": location_id,
                "quantity_before": quantity_before,
                "quantity_after": new_quantity,
            },
            performed_by=None,  # Webhook — no authenticated user
        )

        await self.db.commit()

        # Invalidate aggregation cache after webhook inventory update
        try:
            await aggregation_cache.invalidate_store(self.store.id)
        except Exception as cache_exc:
            self.logger.warning(
                "Cache invalidation failed after webhook: %s", cache_exc,
            )

        self.logger.info(
            "Inventory webhook: variant %s updated %d → %d (delta=%d)",
            variant.id,
            quantity_before,
            new_quantity,
            quantity_change,
        )

        return {
            "status": "updated",
            "variant_id": str(variant.id),
            "product_id": str(variant.product_id),
            "quantity_before": quantity_before,
            "quantity_after": new_quantity,
            "quantity_change": quantity_change,
            "transaction_id": str(txn.id),
        }

    async def update_product_from_webhook(self, shopify_data: dict) -> dict:
        """
        Upsert a product and its variants from a Shopify webhook payload.

        This handles both products/create and products/update webhooks.
        Uses the full Shopify product JSON sent by the webhook to keep
        the local database in sync.

        Args:
            shopify_data: The full Shopify product JSON payload.

        Returns:
            Dict with status and product_id.
        """
        shopify_product_id = shopify_data["id"]

        # ── Upsert product ──
        existing = await self.product_repo.get_by_shopify_id(
            shopify_product_id, self.store.id
        )

        # Normalize Shopify status to lowercase
        raw_status = shopify_data.get("status", "active")
        normalized_status = raw_status.lower() if raw_status else "active"

        product_fields = {
            "title": shopify_data.get("title", ""),
            "description": shopify_data.get("body_html"),
            "vendor": shopify_data.get("vendor"),
            "product_type": shopify_data.get("product_type"),
            "status": normalized_status,
            "featured_image_url": (
                shopify_data.get("image", {}).get("src")
                if shopify_data.get("image")
                else None
            ),
            "shopify_data": shopify_data,
            "last_synced_at": datetime.now(timezone.utc),
        }

        if existing:
            await self.product_repo.update(existing.id, product_fields)
            product_id = existing.id
            action = "updated"
        else:
            product_fields["shopify_product_id"] = shopify_product_id
            new_product = await self.product_repo.create(self.store.id, product_fields)
            product_id = new_product.id
            action = "created"

        # ── Upsert variants ──
        variants_processed = 0
        for sv in shopify_data.get("variants", []):
            existing_v = await self.variant_repo.get_by_shopify_id(sv["id"])

            variant_fields = {
                "title": sv.get("title", ""),
                "sku": sv.get("sku"),
                "barcode": sv.get("barcode"),
                "price": Decimal(str(sv.get("price", "0.00"))),
                "compare_at_price": (
                    Decimal(str(sv["compare_at_price"]))
                    if sv.get("compare_at_price")
                    else None
                ),
                "inventory_quantity": sv.get("inventory_quantity", 0),
                "requires_shipping": sv.get("requires_shipping", True),
                "shopify_inventory_item_id": sv.get("inventory_item_id"),
                "shopify_data": sv,
            }

            if existing_v:
                await self.variant_repo.update(existing_v.id, variant_fields)
            else:
                variant_fields["shopify_variant_id"] = sv["id"]
                await self.variant_repo.create(product_id, variant_fields)

            variants_processed += 1

        await self.db.commit()

        # Invalidate aggregation cache after product webhook update
        try:
            await aggregation_cache.invalidate_store(self.store.id)
        except Exception as cache_exc:
            self.logger.warning(
                "Cache invalidation failed after product webhook: %s", cache_exc,
            )

        self.logger.info(
            "Product webhook: product %d %s with %d variants",
            shopify_product_id,
            action,
            variants_processed,
        )

        return {
            "status": action,
            "product_id": shopify_product_id,
            "variants_processed": variants_processed,
        }

    async def deactivate_store(self) -> dict:
        """
        Mark the current store as inactive (app/uninstalled webhook).

        This stops the system from consuming API quota for this store.
        The store's data is preserved for possible re-activation.
        """
        self.store.is_active = False
        await self.db.commit()

        self.logger.info(
            "Store %s deactivated (app/uninstalled webhook)",
            self.store.shopify_domain,
        )

        return {
            "status": "deactivated",
            "shopify_domain": self.store.shopify_domain,
            "store_id": str(self.store.id),
        }

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ═══════════════════════════════════════════════════════════════

    def _ensure_store_owns_product(self, product: Product) -> None:
        """Raise if the product does not belong to the current store."""
        if str(product.store_id) != str(self.store.id):
            raise InvalidStoreOwnershipError("Product", str(product.id))

    def _ensure_store_owns_variant(self, variant: ProductVariant) -> None:
        """Raise if the variant's product does not belong to the current store."""
        if variant.product and str(variant.product.store_id) != str(self.store.id):
            raise InvalidStoreOwnershipError("Variant", str(variant.id))

    async def _try_shopify_sync(
        self,
        variant: ProductVariant,
        transaction: InventoryTransaction,
    ) -> bool:
        """
        Push an inventory change to Shopify via the Admin API.

        This is a pure integration method — it does NOT mutate ORM objects.
        The caller (adjust_inventory) handles persisting the sync result
        via transaction_repo.mark_synced() after a successful API call.

        Uses the GraphQL `inventorySetQuantity` mutation (preferred method).
        Falls back to REST `inventory_levels/adjust` if needed (handled by client).

        Args:
            variant: The variant whose inventory changed (used for IDs only).
            transaction: The transaction record (used for variant_id in logs only).

        Returns:
            True if synced successfully.

        Raises:
            ShopifySyncError: If the Shopify API call fails.
        """
        if not variant.shopify_inventory_item_id or not self.store.shopify_location_id:
            self.logger.debug(
                "Skipping Shopify sync for variant %s (missing inventory_item_id or location_id)",
                variant.id,
            )
            return False

        client = ShopifyClient(
            shop_domain=self.store.shopify_domain,
            access_token=self.store.access_token,
            location_id=self.store.shopify_location_id,
        )

        try:
            self.logger.info(
                "Syncing variant %s to Shopify: inventory_item=%d, location=%d, qty=%d",
                variant.id,
                variant.shopify_inventory_item_id,
                self.store.shopify_location_id,
                variant.inventory_quantity,
            )

            await client.set_inventory_level(
                inventory_item_id=variant.shopify_inventory_item_id,
                location_id=self.store.shopify_location_id,
                quantity=variant.inventory_quantity,
            )

            # Log the success event (audit trail only — no ORM mutations)
            await self.log_repo.create(
                variant_id=variant.id,
                action=InventoryAction.SYNCED.value,
                details={
                    "inventory_item_id": variant.shopify_inventory_item_id,
                    "location_id": self.store.shopify_location_id,
                    "quantity": variant.inventory_quantity,
                    "method": "inventorySetQuantity",
                },
                performed_by=self.user_id,
            )

            self.logger.info("Shopify sync succeeded for variant %s", variant.id)
            return True

        except Exception as exc:
            self.logger.error(
                "Shopify sync failed for variant %s: %s",
                variant.id,
                exc,
            )
            await self.log_repo.create(
                variant_id=variant.id,
                action=InventoryAction.SHOPIFY_SYNC_FAILED.value,
                details={"error": str(exc)},
                performed_by=self.user_id,
            )
            raise ShopifySyncError(str(exc))

        finally:
            await client.close()
