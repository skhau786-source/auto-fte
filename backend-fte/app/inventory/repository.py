"""
Repository Layer for the Inventory Management module.

Each repository encapsulates ALL database operations for its entity.
- No business logic — only SQLAlchemy queries.
- Returns ORM model instances (or scalars).
- The service layer transforms results and applies business rules.
"""

import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    select, func, and_, or_, exists, update, delete,
    desc, asc,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.models import (
    Product,
    ProductVariant,
    InventoryTransaction,
    InventoryLog,
    StoreSettings,
    TransactionType,
)


# ═══════════════════════════════════════════════════════════════════
# PRODUCT REPOSITORY
# ═══════════════════════════════════════════════════════════════════


class ProductRepository:
    """Data access for products. Every method takes an open db session."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── Create ───

    async def create(self, store_id: uuid.UUID, data: dict) -> Product:
        """Insert a new product and return it with an empty variants list loaded."""
        product = Product(store_id=store_id, **data)
        self.db.add(product)
        await self.db.flush()
        return product

    # ─── Read — Single ───

    async def get_by_id(self, product_id: uuid.UUID) -> Optional[Product]:
        """Fetch a single product by PK with variants eagerly loaded."""
        result = await self.db.execute(
            select(Product)
            .options(selectinload(Product.variants))
            .where(Product.id == product_id)
        )
        return result.scalar_one_or_none()

    async def get_by_shopify_id(self, shopify_product_id: int, store_id: uuid.UUID) -> Optional[Product]:
        """Fetch a product by its Shopify ID (scoped to a store)."""
        result = await self.db.execute(
            select(Product)
            .options(selectinload(Product.variants))
            .where(
                Product.shopify_product_id == shopify_product_id,
                Product.store_id == store_id,
            )
        )
        return result.scalar_one_or_none()

    # ─── Read — List / Search / Paginate ───

    async def list_products(
        self,
        store_id: uuid.UUID,
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
        """
        Return (products, total_count) with pagination, filtering, and sorting.

        Search matches against Product.title OR ProductVariant.sku.
        low_stock_only filters to variants where inventory <= low_stock_threshold.
        """
        # Base query with eager-loaded variants
        query = select(Product).options(selectinload(Product.variants))
        count_query = select(func.count(Product.id))

        # ── WHERE conditions ──
        conditions = [Product.store_id == store_id]

        if status:
            conditions.append(Product.status == status)

        if category_id:
            conditions.append(Product.category_id == category_id)

        if vendor:
            conditions.append(Product.vendor.ilike(f"%{vendor}%"))

        if product_type:
            conditions.append(Product.product_type.ilike(f"%{product_type}%"))

        if search:
            # Search across product title AND variant SKU
            search_pattern = f"%{search}%"
            sku_exists = (
                exists(
                    select(ProductVariant.id).where(
                        ProductVariant.product_id == Product.id,
                        ProductVariant.sku.ilike(search_pattern),
                    )
                )
            )
            conditions.append(
                or_(
                    Product.title.ilike(search_pattern),
                    sku_exists,
                )
            )

        if low_stock_only:
            # Products where at least one variant is below its threshold
            low_stock_exists = (
                exists(
                    select(ProductVariant.id).where(
                        ProductVariant.product_id == Product.id,
                        ProductVariant.inventory_quantity
                        <= func.coalesce(ProductVariant.low_stock_threshold, 10),
                    )
                )
            )
            conditions.append(low_stock_exists)

        where_clause = and_(*conditions)
        query = query.where(where_clause)
        count_query = count_query.where(where_clause)

        # ── Sorting ──
        sort_column = self._resolve_sort_column(sort_by)
        order_fn = desc if sort_order.lower() == "desc" else asc
        query = query.order_by(order_fn(sort_column))

        # ── Pagination ──
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        products = list(result.scalars().all())

        return products, total

    @staticmethod
    def _resolve_sort_column(sort_by: str):
        """Map string sort key to SQLAlchemy column."""
        column_map = {
            "title": Product.title,
            "created_at": Product.created_at,
            "updated_at": Product.updated_at,
            "status": Product.status,
            "vendor": Product.vendor,
            "product_type": Product.product_type,
        }
        return column_map.get(sort_by, Product.updated_at)

    # ─── Update ───

    async def update(self, product_id: uuid.UUID, data: dict) -> Optional[Product]:
        """
        Partially update a product. Only the keys present in *data* are changed.
        Returns the updated product (or None if not found).
        """
        product = await self.get_by_id(product_id)
        if product is None:
            return None

        for field, value in data.items():
            if hasattr(product, field):
                setattr(product, field, value)

        await self.db.flush()
        return product

    async def mark_synced(self, product_id: uuid.UUID, shopify_product_id: int) -> Optional[Product]:
        """
        Mark a local-only product as synced to Shopify.
        Sets shopify_product_id and last_synced_at.
        """
        product = await self.get_by_id(product_id)
        if product is None:
            return None

        product.shopify_product_id = shopify_product_id
        product.last_synced_at = datetime.now(timezone.utc)
        await self.db.flush()
        return product

    # ─── Delete ───

    async def delete(self, product_id: uuid.UUID) -> bool:
        """Delete a product by ID. Returns True if deleted, False if not found."""
        product = await self.get_by_id(product_id)
        if product is None:
            return False

        await self.db.delete(product)
        await self.db.flush()
        return True

    # ─── Aggregations ───

    async def count_by_store(self, store_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count(Product.id)).where(Product.store_id == store_id)
        )
        return result.scalar() or 0

    async def dashboard_stats(self, store_id: uuid.UUID) -> dict:
        """Return aggregated counts for the inventory dashboard."""
        # Total products
        total_products = await self.count_by_store(store_id)

        # Total variants & inventory units
        variant_result = await self.db.execute(
            select(
                func.count(ProductVariant.id),
                func.coalesce(func.sum(ProductVariant.inventory_quantity), 0),
            )
            .select_from(Product)
            .join(ProductVariant, ProductVariant.product_id == Product.id)
            .where(Product.store_id == store_id)
        )
        total_variants, total_units = variant_result.one()

        # Total inventory value (sum of price * quantity per variant)
        value_result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(
                        ProductVariant.price * ProductVariant.inventory_quantity
                    ),
                    0,
                )
            )
            .select_from(Product)
            .join(ProductVariant, ProductVariant.product_id == Product.id)
            .where(Product.store_id == store_id)
        )
        total_value = value_result.scalar() or Decimal("0.00")

        # Low stock & out of stock counts
        low_stock_result = await self.db.execute(
            select(func.count(ProductVariant.id))
            .select_from(Product)
            .join(ProductVariant, ProductVariant.product_id == Product.id)
            .where(
                Product.store_id == store_id,
                ProductVariant.inventory_quantity
                <= func.coalesce(ProductVariant.low_stock_threshold, 10),
                ProductVariant.inventory_quantity > 0,
            )
        )
        low_stock_count = low_stock_result.scalar() or 0

        out_of_stock_result = await self.db.execute(
            select(func.count(ProductVariant.id))
            .select_from(Product)
            .join(ProductVariant, ProductVariant.product_id == Product.id)
            .where(
                Product.store_id == store_id,
                ProductVariant.inventory_quantity == 0,
            )
        )
        out_of_stock_count = out_of_stock_result.scalar() or 0

        return {
            "total_products": total_products,
            "total_variants": total_variants,
            "total_inventory_units": total_units,
            "total_value": total_value,
            "low_stock_count": low_stock_count,
            "out_of_stock_count": out_of_stock_count,
        }


# ═══════════════════════════════════════════════════════════════════
# VARIANT REPOSITORY
# ═══════════════════════════════════════════════════════════════════


class VariantRepository:
    """Data access for product variants (the inventory-carrying entities)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── Create ───

    async def create(self, product_id: uuid.UUID, data: dict) -> ProductVariant:
        """Create a new variant under a given product."""
        variant = ProductVariant(product_id=product_id, **data)
        self.db.add(variant)
        await self.db.flush()
        return variant

    # ─── Read — Single ───

    async def get_by_id(self, variant_id: uuid.UUID) -> Optional[ProductVariant]:
        """Fetch variant by PK with its product (for store ownership checks)."""
        result = await self.db.execute(
            select(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .where(ProductVariant.id == variant_id)
            # Refresh even if the instance is already in the identity map,
            # so ``variant.product`` is always eagerly populated. Without
            # this, a stale identity-map hit would lazy-load the
            # relationship outside an async greenlet.
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_by_shopify_id(self, shopify_variant_id: int) -> Optional[ProductVariant]:
        """Fetch a variant by its Shopify variant ID."""
        result = await self.db.execute(
            select(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .where(ProductVariant.shopify_variant_id == shopify_variant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_inventory_item_id(self, inventory_item_id: int) -> Optional[ProductVariant]:
        """Fetch a variant by its Shopify inventory item ID (used in webhooks)."""
        result = await self.db.execute(
            select(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .where(ProductVariant.shopify_inventory_item_id == inventory_item_id)
        )
        return result.scalar_one_or_none()

    async def get_by_sku(self, sku: str, store_id: uuid.UUID) -> Optional[ProductVariant]:
        """Fetch a variant by SKU, scoped to a store."""
        result = await self.db.execute(
            select(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .join(Product, ProductVariant.product_id == Product.id)
            .where(ProductVariant.sku == sku, Product.store_id == store_id)
        )
        return result.scalar_one_or_none()

    # ─── Read — List / Filter ───

    async def list_by_product(self, product_id: uuid.UUID) -> list[ProductVariant]:
        """Get all variants for a given product."""
        result = await self.db.execute(
            select(ProductVariant)
            .where(ProductVariant.product_id == product_id)
            .order_by(ProductVariant.title)
        )
        return list(result.scalars().all())

    async def get_low_stock(
        self,
        store_id: uuid.UUID,
        threshold: int = 10,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ProductVariant], int]:
        """
        Find all variants where inventory_quantity <= threshold (or their
        custom low_stock_threshold, whichever is lower).
        Returns (variants, total_count).
        """
        query = (
            select(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .join(Product, ProductVariant.product_id == Product.id)
            .where(
                Product.store_id == store_id,
                ProductVariant.inventory_quantity
                <= func.coalesce(ProductVariant.low_stock_threshold, threshold),
            )
            .order_by(ProductVariant.inventory_quantity.asc())
        )
        count_query = (
            select(func.count(ProductVariant.id))
            .join(Product, ProductVariant.product_id == Product.id)
            .where(
                Product.store_id == store_id,
                ProductVariant.inventory_quantity
                <= func.coalesce(ProductVariant.low_stock_threshold, threshold),
            )
        )

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        result = await self.db.execute(query)
        variants = list(result.scalars().all())

        return variants, total

    # ─── Update ───

    async def update(self, variant_id: uuid.UUID, data: dict) -> Optional[ProductVariant]:
        """Partially update a variant."""
        variant = await self.get_by_id(variant_id)
        if variant is None:
            return None

        for field, value in data.items():
            if hasattr(variant, field):
                setattr(variant, field, value)

        await self.db.flush()
        return variant

    async def update_quantity(
        self, variant_id: uuid.UUID, new_quantity: int
    ) -> Optional[ProductVariant]:
        """Update only the inventory_quantity field. Returns the variant."""
        variant = await self.get_by_id(variant_id)
        if variant is None:
            return None

        variant.inventory_quantity = new_quantity
        await self.db.flush()
        return variant

    async def bulk_update_quantity(
        self, updates: list[tuple[uuid.UUID, int]]
    ) -> int:
        """
        Bulk-update inventory quantities for multiple variants.
        *updates* is a list of (variant_id, new_quantity) tuples.
        Returns the number of rows updated.
        """
        count = 0
        for variant_id, new_quantity in updates:
            variant = await self.update_quantity(variant_id, new_quantity)
            if variant is not None:
                count += 1
        return count

    async def mark_synced(
        self, variant_id: uuid.UUID, shopify_variant_id: int, inventory_item_id: int
    ) -> Optional[ProductVariant]:
        """Mark a local-only variant as synced, setting its Shopify IDs."""
        variant = await self.get_by_id(variant_id)
        if variant is None:
            return None

        variant.shopify_variant_id = shopify_variant_id
        variant.shopify_inventory_item_id = inventory_item_id
        await self.db.flush()
        return variant

    # ─── Delete ───

    async def delete(self, variant_id: uuid.UUID) -> bool:
        """Delete a variant by ID. Returns True if deleted."""
        result = await self.db.execute(
            select(ProductVariant).where(ProductVariant.id == variant_id)
        )
        variant = result.scalar_one_or_none()
        if variant is None:
            return False

        await self.db.delete(variant)
        await self.db.flush()
        return True

    async def delete_by_product(self, product_id: uuid.UUID) -> int:
        """Delete all variants for a product. Returns count of deleted rows."""
        result = await self.db.execute(
            delete(ProductVariant).where(ProductVariant.product_id == product_id)
        )
        await self.db.flush()
        return result.rowcount


# ═══════════════════════════════════════════════════════════════════
# TRANSACTION REPOSITORY (Audit Trail)
# ═══════════════════════════════════════════════════════════════════


class TransactionRepository:
    """Read-only after create — transactions are an immutable audit trail."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── Create ───

    async def create(
        self,
        variant_id: uuid.UUID,
        transaction_type: TransactionType,
        quantity_change: int,
        quantity_before: int,
        quantity_after: int,
        reason: Optional[str] = None,
        reference_id: Optional[str] = None,
        performed_by: Optional[uuid.UUID] = None,
    ) -> InventoryTransaction:
        """Record a single inventory transaction."""
        txn = InventoryTransaction(
            variant_id=variant_id,
            transaction_type=transaction_type,
            quantity_change=quantity_change,
            quantity_before=quantity_before,
            quantity_after=quantity_after,
            reason=reason,
            reference_id=reference_id,
            performed_by=performed_by,
        )
        self.db.add(txn)
        await self.db.flush()
        return txn

    # ─── Read — History ───

    async def list_history(
        self,
        store_id: uuid.UUID,
        variant_id: Optional[uuid.UUID] = None,
        transaction_type: Optional[TransactionType] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[InventoryTransaction], int]:
        """
        Return paginated transaction history for a store.
        Filters by variant, type, and date range when provided.
        """
        query = select(InventoryTransaction)
        count_query = select(func.count(InventoryTransaction.id))

        # Join through variant → product to scope to store
        query = query.join(
            ProductVariant, InventoryTransaction.variant_id == ProductVariant.id
        ).join(Product, ProductVariant.product_id == Product.id)

        count_query = count_query.join(
            ProductVariant, InventoryTransaction.variant_id == ProductVariant.id
        ).join(Product, ProductVariant.product_id == Product.id)

        conditions = [Product.store_id == store_id]

        if variant_id:
            conditions.append(InventoryTransaction.variant_id == variant_id)

        if transaction_type:
            conditions.append(InventoryTransaction.transaction_type == transaction_type)

        if date_from:
            conditions.append(InventoryTransaction.created_at >= date_from)

        if date_to:
            conditions.append(InventoryTransaction.created_at <= date_to)

        where_clause = and_(*conditions)
        query = query.where(where_clause).order_by(InventoryTransaction.created_at.desc())
        count_query = count_query.where(where_clause)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.db.execute(query)
        transactions = list(result.scalars().all())

        return transactions, total

    async def get_recent(
        self, store_id: uuid.UUID, limit: int = 10
    ) -> list[InventoryTransaction]:
        """Get the most recent transactions for a store (for dashboard)."""
        result = await self.db.execute(
            select(InventoryTransaction)
            .join(ProductVariant, InventoryTransaction.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(Product.store_id == store_id)
            .order_by(InventoryTransaction.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_synced(self, transaction_id: uuid.UUID) -> None:
        """Mark a transaction as synced to Shopify."""
        await self.db.execute(
            update(InventoryTransaction)
            .where(InventoryTransaction.id == transaction_id)
            .values(synced_to_shopify=True, synced_at=datetime.now(timezone.utc))
        )
        await self.db.flush()

    async def get_unsynced(self, store_id: uuid.UUID, limit: int = 50) -> list[InventoryTransaction]:
        """Get transactions that haven't been synced to Shopify yet."""
        result = await self.db.execute(
            select(InventoryTransaction)
            .join(ProductVariant, InventoryTransaction.variant_id == ProductVariant.id)
            .join(Product, ProductVariant.product_id == Product.id)
            .where(
                Product.store_id == store_id,
                InventoryTransaction.synced_to_shopify == False,  # noqa: E712
            )
            .order_by(InventoryTransaction.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════════
# LOG REPOSITORY  (Activity Log)
# ═══════════════════════════════════════════════════════════════════


class LogRepository:
    """Append-only activity log. Once written, rows are never modified."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        variant_id: uuid.UUID,
        action: str,
        details: Optional[dict] = None,
        performed_by: Optional[uuid.UUID] = None,
    ) -> InventoryLog:
        """Write a log entry for a variant event."""
        log = InventoryLog(
            variant_id=variant_id,
            action=action,
            details=details or {},
            performed_by=performed_by,
        )
        self.db.add(log)
        await self.db.flush()
        return log

    async def list_by_variant(
        self,
        variant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[InventoryLog], int]:
        """Get paginated logs for a specific variant."""
        query = (
            select(InventoryLog)
            .where(InventoryLog.variant_id == variant_id)
            .order_by(InventoryLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        count_query = select(func.count(InventoryLog.id)).where(
            InventoryLog.variant_id == variant_id
        )

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        result = await self.db.execute(query)
        logs = list(result.scalars().all())

        return logs, total


# ═══════════════════════════════════════════════════════════════════
# STORE SETTINGS REPOSITORY (SaaS store configuration)
# ═══════════════════════════════════════════════════════════════════


class StoreSettingsRepository:
    """Data access for per-store inventory/fulfillment settings."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_store(self, store_id: uuid.UUID) -> Optional[StoreSettings]:
        """Fetch settings for a store (one-to-one)."""
        result = await self.db.execute(
            select(StoreSettings).where(StoreSettings.store_id == store_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, store_id: uuid.UUID) -> StoreSettings:
        """Return existing settings or create defaults for the store."""
        settings = await self.get_by_store(store_id)
        if settings is not None:
            return settings

        settings = StoreSettings(store_id=store_id)
        self.db.add(settings)
        await self.db.flush()
        return settings

    async def update(self, store_id: uuid.UUID, data: dict) -> Optional[StoreSettings]:
        """Partially update settings for a store."""
        settings = await self.get_by_store(store_id)
        if settings is None:
            return None

        for field, value in data.items():
            if hasattr(settings, field):
                setattr(settings, field, value)

        await self.db.flush()
        return settings
