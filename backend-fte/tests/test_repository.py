"""
Repository Layer Tests — Data access only, no business logic.

Covers every repository class and method with positive cases,
boundary values, constraint violations, and error paths.
"""

import uuid
from decimal import Decimal
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product, ProductVariant, InventoryTransaction, InventoryLog
from app.inventory.repository import (
    ProductRepository,
    VariantRepository,
    TransactionRepository,
    LogRepository,
)
from app.inventory.constants import TransactionType, InventoryAction
from tests.utils import (
    assert_product_count,
    assert_variant_count,
    assert_transaction_count,
    assert_log_count,
    assert_variant_quantity,
)

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════
# PRODUCT REPOSITORY
# ═══════════════════════════════════════════════════════════════════


class TestProductRepository:
    """ProductRepository: create, read, update, delete, list, search, paginate."""

    async def test_create_minimal(self, db_session: AsyncSession, test_store):
        """Minimal product creation succeeds."""
        repo = ProductRepository(db_session)
        prod = await repo.create(test_store.id, {"title": "Minimal Product"})
        assert prod.id is not None
        assert prod.title == "Minimal Product"
        assert str(prod.store_id) == str(test_store.id)
        await assert_product_count(db_session, 1, test_store.id)

    async def test_create_full(self, db_session: AsyncSession, test_store, test_category):
        """Product creation with all fields succeeds."""
        repo = ProductRepository(db_session)
        prod = await repo.create(
            test_store.id,
            {
                "title": "Full Product",
                "description": "Full description",
                "vendor": "Acme",
                "product_type": "Digital",
                "status": "active",
                "category_id": test_category.id,
                "featured_image_url": "https://example.com/img.jpg",
            },
        )
        assert prod.title == "Full Product"
        assert prod.description == "Full description"
        assert prod.vendor == "Acme"
        assert prod.product_type == "Digital"
        assert prod.status == "active"
        assert str(prod.category_id) == str(test_category.id)
        assert prod.featured_image_url == "https://example.com/img.jpg"

    async def test_get_by_id_found(self, db_session: AsyncSession, test_product):
        """get_by_id returns the correct product with variants eagerly loaded."""
        repo = ProductRepository(db_session)
        prod = await repo.get_by_id(test_product.id)
        assert prod is not None
        assert prod.id == test_product.id
        assert prod.title == "Test Product"
        # Variants should be loaded eagerly
        assert len(prod.variants) >= 1

    async def test_get_by_id_not_found(self, db_session: AsyncSession):
        """get_by_id returns None for a non-existent ID."""
        repo = ProductRepository(db_session)
        prod = await repo.get_by_id(uuid.uuid4())
        assert prod is None

    async def test_get_by_shopify_id(self, db_session: AsyncSession, test_store):
        """get_by_shopify_id finds a product linked to Shopify."""
        repo = ProductRepository(db_session)
        created = await repo.create(
            test_store.id,
            {"title": "Shopify Product", "shopify_product_id": 50005000},
        )
        found = await repo.get_by_shopify_id(50005000, test_store.id)
        assert found is not None
        assert found.id == created.id

    async def test_get_by_shopify_id_wrong_store(self, db_session: AsyncSession, test_store):
        """get_by_shopify_id scoped to store — wrong store returns None."""
        repo = ProductRepository(db_session)
        await repo.create(
            test_store.id,
            {"title": "Shopify Product", "shopify_product_id": 60006000},
        )
        found = await repo.get_by_shopify_id(60006000, uuid.uuid4())
        assert found is None

    async def test_update_partial(self, db_session: AsyncSession, test_product):
        """Partial update changes only provided fields."""
        repo = ProductRepository(db_session)
        updated = await repo.update(
            test_product.id,
            {"title": "Updated Title", "vendor": "New Vendor"},
        )
        assert updated is not None
        assert updated.title == "Updated Title"
        assert updated.vendor == "New Vendor"
        assert updated.description == test_product.description  # unchanged

    async def test_update_not_found(self, db_session: AsyncSession):
        """Update on non-existent ID returns None."""
        repo = ProductRepository(db_session)
        result = await repo.update(uuid.uuid4(), {"title": "Nope"})
        assert result is None

    async def test_delete_success(self, db_session: AsyncSession, test_product):
        """Delete removes the product and returns True."""
        repo = ProductRepository(db_session)
        result = await repo.delete(test_product.id)
        assert result is True
        assert await repo.get_by_id(test_product.id) is None

    async def test_delete_not_found(self, db_session: AsyncSession):
        """Delete on non-existent ID returns False."""
        repo = ProductRepository(db_session)
        result = await repo.delete(uuid.uuid4())
        assert result is False

    async def test_count_by_store(self, db_session: AsyncSession, test_store, test_product):
        """count_by_store returns the right total."""
        repo = ProductRepository(db_session)
        count = await repo.count_by_store(test_store.id)
        assert count >= 1

    # ─── List / Search / Paginate ───

    async def test_list_products_pagination(
        self, db_session: AsyncSession, test_store, test_products_batch
    ):
        """list_products returns paginated results with correct totals."""
        repo = ProductRepository(db_session)
        products, total = await repo.list_products(test_store.id, page=1, page_size=5)
        assert len(products) == 5
        assert total == 15  # 15 products created by the fixture

    async def test_list_products_page_2(self, db_session: AsyncSession, test_store, test_products_batch):
        """Second page of results."""
        repo = ProductRepository(db_session)
        products, total = await repo.list_products(test_store.id, page=2, page_size=5)
        assert len(products) == 5
        assert total == 15

    async def test_list_products_search_title(
        self, db_session: AsyncSession, test_store, test_products_batch
    ):
        """Search by product title."""
        repo = ProductRepository(db_session)
        products, total = await repo.list_products(test_store.id, search="Product 1")
        assert total >= 1
        assert all("Product 1" in p.title for p in products)

    async def test_list_products_search_sku(
        self, db_session: AsyncSession, test_store, test_products_batch
    ):
        """Search by variant SKU."""
        repo = ProductRepository(db_session)
        products, total = await repo.list_products(test_store.id, search="SKU-0005")
        assert total >= 1

    async def test_list_products_filter_by_status(
        self, db_session: AsyncSession, test_store
    ):
        """Filter products by status."""
        repo = ProductRepository(db_session)
        # Create an archived product
        await repo.create(test_store.id, {"title": "Archived Product", "status": "archived"})
        await repo.create(test_store.id, {"title": "Active Product", "status": "active"})
        active, total = await repo.list_products(test_store.id, status="active")
        assert total >= 1
        assert all(p.status == "active" for p in active)

    async def test_list_products_filter_by_vendor(
        self, db_session: AsyncSession, test_store, test_products_batch
    ):
        """Filter products by vendor."""
        repo = ProductRepository(db_session)
        products, total = await repo.list_products(test_store.id, vendor="Vendor 1")
        assert total >= 1

    async def test_list_products_filter_by_type(
        self, db_session: AsyncSession, test_store, test_products_batch
    ):
        """Filter products by product type."""
        repo = ProductRepository(db_session)
        products, total = await repo.list_products(test_store.id, product_type="Type A")
        assert total >= 1
        assert all(p.product_type == "Type A" for p in products)

    async def test_list_products_sort_by_title_asc(
        self, db_session: AsyncSession, test_store, test_products_batch
    ):
        """Sort products by title ascending."""
        repo = ProductRepository(db_session)
        products, _ = await repo.list_products(
            test_store.id, sort_by="title", sort_order="asc", page_size=5
        )
        titles = [p.title for p in products]
        assert titles == sorted(titles)

    async def test_list_products_no_results(
        self, db_session: AsyncSession, test_store
    ):
        """List with no matching products returns empty."""
        repo = ProductRepository(db_session)
        products, total = await repo.list_products(test_store.id, search="NONEXISTENT")
        assert len(products) == 0
        assert total == 0

    async def test_mark_synced(self, db_session: AsyncSession, test_product):
        """mark_synced updates shopify_product_id and last_synced_at."""
        repo = ProductRepository(db_session)
        result = await repo.mark_synced(test_product.id, 7777777)
        assert result is not None
        assert result.shopify_product_id == 7777777
        assert result.last_synced_at is not None

    async def test_mark_synced_not_found(self, db_session: AsyncSession):
        """mark_synced on non-existent product returns None."""
        repo = ProductRepository(db_session)
        result = await repo.mark_synced(uuid.uuid4(), 7777777)
        assert result is None

    # ─── Dashboard Stats ───

    async def test_dashboard_stats(
        self, db_session: AsyncSession, test_store, test_product
    ):
        """dashboard_stats returns correct aggregated data."""
        repo = ProductRepository(db_session)
        stats = await repo.dashboard_stats(test_store.id)
        assert stats["total_products"] >= 1
        assert stats["total_variants"] >= 1
        assert stats["total_inventory_units"] >= 100
        assert stats["total_value"] >= Decimal("1999.00")  # 100 * 19.99
        assert "low_stock_count" in stats
        assert "out_of_stock_count" in stats


# ═══════════════════════════════════════════════════════════════════
# VARIANT REPOSITORY
# ═══════════════════════════════════════════════════════════════════


class TestVariantRepository:
    """VariantRepository: create, read, update, delete, low-stock queries."""

    async def test_create(self, db_session: AsyncSession, test_product):
        """Create a variant under a product."""
        repo = VariantRepository(db_session)
        variant = await repo.create(
            test_product.id,
            {"title": "New Variant", "sku": "VAR-001", "price": Decimal("14.99"), "inventory_quantity": 30},
        )
        assert variant.id is not None
        assert variant.product_id == test_product.id
        assert variant.sku == "VAR-001"
        await assert_variant_count(db_session, 2, test_product.id)  # 1 from fixture + 1 new

    async def test_get_by_id(self, db_session: AsyncSession, test_variant):
        """get_by_id returns variant with product eagerly loaded."""
        repo = VariantRepository(db_session)
        variant = await repo.get_by_id(test_variant.id)
        assert variant is not None
        assert variant.id == test_variant.id
        assert variant.product is not None  # eagerly loaded

    async def test_get_by_id_not_found(self, db_session: AsyncSession):
        """get_by_id returns None for non-existent ID."""
        repo = VariantRepository(db_session)
        variant = await repo.get_by_id(uuid.uuid4())
        assert variant is None

    async def test_get_by_shopify_id(self, db_session: AsyncSession, test_product):
        """get_by_shopify_id finds a variant linked to Shopify."""
        repo = VariantRepository(db_session)
        created = await repo.create(
            test_product.id,
            {"title": "Shopify Variant", "shopify_variant_id": 80008000},
        )
        found = await repo.get_by_shopify_id(80008000)
        assert found is not None
        assert found.id == created.id

    async def test_get_by_inventory_item_id(self, db_session: AsyncSession, test_product):
        """get_by_inventory_item_id finds variant by Shopify inventory item ID."""
        repo = VariantRepository(db_session)
        created = await repo.create(
            test_product.id,
            {
                "title": "Inventory Item Variant",
                "shopify_inventory_item_id": 90009000,
            },
        )
        found = await repo.get_by_inventory_item_id(90009000)
        assert found is not None
        assert found.id == created.id

    async def test_get_by_sku(self, db_session: AsyncSession, test_store, test_product):
        """get_by_sku finds variant by SKU scoped to store."""
        repo = VariantRepository(db_session)
        await repo.create(
            test_product.id,
            {"title": "SKU Variant", "sku": "UNIQUE-SKU-999"},
        )
        found = await repo.get_by_sku("UNIQUE-SKU-999", test_store.id)
        assert found is not None
        assert found.sku == "UNIQUE-SKU-999"

    async def test_get_by_sku_wrong_store(self, db_session: AsyncSession, test_store, test_product):
        """get_by_sku fails when SKU exists under a different store."""
        repo = VariantRepository(db_session)
        await repo.create(
            test_product.id,
            {"title": "SKU Variant", "sku": "STORE-SPECIFIC-SKU"},
        )
        found = await repo.get_by_sku("STORE-SPECIFIC-SKU", uuid.uuid4())
        assert found is None

    async def test_update(self, db_session: AsyncSession, test_variant):
        """Partial update changes only provided fields."""
        repo = VariantRepository(db_session)
        updated = await repo.update(
            test_variant.id,
            {"price": Decimal("49.99"), "inventory_quantity": 200},
        )
        assert updated is not None
        assert updated.price == Decimal("49.99")
        assert updated.inventory_quantity == 200
        assert updated.title == test_variant.title  # unchanged

    async def test_update_quantity(self, db_session: AsyncSession, test_variant):
        """update_quantity changes only the quantity field."""
        repo = VariantRepository(db_session)
        updated = await repo.update_quantity(test_variant.id, 75)
        assert updated is not None
        assert updated.inventory_quantity == 75

    async def test_delete(self, db_session: AsyncSession, test_variant):
        """Delete removes the variant and returns True."""
        repo = VariantRepository(db_session)
        result = await repo.delete(test_variant.id)
        assert result is True
        assert await repo.get_by_id(test_variant.id) is None

    async def test_delete_not_found(self, db_session: AsyncSession):
        """Delete on non-existent ID returns False."""
        repo = VariantRepository(db_session)
        result = await repo.delete(uuid.uuid4())
        assert result is False

    async def test_list_by_product(self, db_session: AsyncSession, test_product):
        """list_by_product returns all variants for a product."""
        repo = VariantRepository(db_session)
        variants = await repo.list_by_product(test_product.id)
        assert len(variants) >= 1

    async def test_get_low_stock(self, db_session: AsyncSession, test_store, test_product):
        """get_low_stock returns variants below threshold."""
        repo = VariantRepository(db_session)
        # Create a low-stock variant
        await repo.create(
            test_product.id,
            {"title": "Low Stock", "sku": "LOW-001", "inventory_quantity": 3, "low_stock_threshold": 10},
        )
        # Create a well-stocked variant
        await repo.create(
            test_product.id,
            {"title": "Well Stocked", "sku": "HIGH-001", "inventory_quantity": 500},
        )
        low, total = await repo.get_low_stock(test_store.id, threshold=10)
        assert total >= 1
        # At least one variant should have quantity <= threshold
        assert any(v.inventory_quantity <= 10 for v in low)

    async def test_get_low_stock_empty(self, db_session: AsyncSession, test_store, test_product):
        """get_low_stock returns empty when all stock is sufficient."""
        repo = VariantRepository(db_session)
        # Raise all variants well above threshold
        await repo.update(test_product.variants[0].id, {"inventory_quantity": 999})
        low, total = await repo.get_low_stock(test_store.id, threshold=5)
        assert total == 0

    async def test_mark_synced(self, db_session: AsyncSession, test_variant):
        """mark_synced sets Shopify IDs on a variant."""
        repo = VariantRepository(db_session)
        result = await repo.mark_synced(test_variant.id, 100200, 300400)
        assert result is not None
        assert result.shopify_variant_id == 100200
        assert result.shopify_inventory_item_id == 300400

    async def test_bulk_update_quantity(self, db_session: AsyncSession, test_product):
        """bulk_update_quantity updates multiple variants."""
        repo = VariantRepository(db_session)
        v1 = await repo.create(test_product.id, {"title": "B1", "inventory_quantity": 10})
        v2 = await repo.create(test_product.id, {"title": "B2", "inventory_quantity": 20})
        updated = await repo.bulk_update_quantity([(v1.id, 100), (v2.id, 200)])
        assert updated == 2
        await assert_variant_quantity(db_session, v1.id, 100)
        await assert_variant_quantity(db_session, v2.id, 200)

    async def test_delete_by_product(self, db_session: AsyncSession, test_product):
        """delete_by_product removes all variants for a product."""
        repo = VariantRepository(db_session)
        deleted = await repo.delete_by_product(test_product.id)
        assert deleted >= 1
        remaining = await repo.list_by_product(test_product.id)
        assert len(remaining) == 0


# ═══════════════════════════════════════════════════════════════════
# TRANSACTION REPOSITORY (Audit Trail)
# ═══════════════════════════════════════════════════════════════════


class TestTransactionRepository:
    """TransactionRepository: create, history, recent, mark_synced, get_unsynced."""

    async def test_create(self, db_session: AsyncSession, test_variant):
        """Create an inventory transaction."""
        repo = TransactionRepository(db_session)
        txn = await repo.create(
            variant_id=test_variant.id,
            transaction_type=TransactionType.ADJUSTMENT,
            quantity_change=5,
            quantity_before=100,
            quantity_after=105,
            reason="Test",
        )
        assert txn.id is not None
        assert txn.transaction_type == TransactionType.ADJUSTMENT
        assert txn.quantity_change == 5
        assert txn.quantity_before == 100
        assert txn.quantity_after == 105
        assert txn.synced_to_shopify is False
        await assert_transaction_count(db_session, 1)

    async def test_create_with_performer(self, db_session: AsyncSession, test_variant, test_user):
        """Create a transaction with a performer."""
        repo = TransactionRepository(db_session)
        txn = await repo.create(
            variant_id=test_variant.id,
            transaction_type=TransactionType.ADJUSTMENT,
            quantity_change=10,
            quantity_before=50,
            quantity_after=60,
            reason="Performed by user",
            performed_by=test_user.id,
        )
        assert txn.performed_by == test_user.id

    async def test_list_history_pagination(
        self, db_session: AsyncSession, test_variant
    ):
        """list_history returns paginated results."""
        repo = TransactionRepository(db_session)
        # Create multiple transactions
        for i in range(5):
            await repo.create(
                variant_id=test_variant.id,
                transaction_type=TransactionType.ADJUSTMENT,
                quantity_change=i,
                quantity_before=100,
                quantity_after=100 + i,
            )
        # The variant's product has store_id on Product model
        transactions, total = await repo.list_history(
            store_id=test_variant.product.store_id,
            page=1,
            page_size=2,
        )
        assert len(transactions) == 2
        assert total == 5

    async def test_list_history_filter_by_variant(
        self, db_session: AsyncSession, test_product, test_variant
    ):
        """list_history filters by variant_id."""
        repo = TransactionRepository(db_session)
        # Create another variant
        v2 = await VariantRepository(db_session).create(
            test_product.id, {"title": "V2", "inventory_quantity": 50}
        )
        # Create transactions for both variants
        for _ in range(3):
            await repo.create(
                variant_id=test_variant.id,
                transaction_type=TransactionType.ADJUSTMENT,
                quantity_change=1,
                quantity_before=100,
                quantity_after=101,
            )
        for _ in range(2):
            await repo.create(
                variant_id=v2.id,
                transaction_type=TransactionType.ADJUSTMENT,
                quantity_change=1,
                quantity_before=50,
                quantity_after=51,
            )
        # Filter by test_variant
        txns, total = await repo.list_history(
            store_id=test_variant.product.store_id,
            variant_id=test_variant.id,
        )
        assert total == 3

    async def test_list_history_filter_by_type(
        self, db_session: AsyncSession, test_variant
    ):
        """list_history filters by transaction type."""
        repo = TransactionRepository(db_session)
        await repo.create(
            variant_id=test_variant.id,
            transaction_type=TransactionType.ADJUSTMENT,
            quantity_change=5,
            quantity_before=100,
            quantity_after=105,
        )
        await repo.create(
            variant_id=test_variant.id,
            transaction_type=TransactionType.SALE,
            quantity_change=-5,
            quantity_before=105,
            quantity_after=100,
        )
        txns, total = await repo.list_history(
            store_id=test_variant.product.store_id,
            transaction_type=TransactionType.SALE,
        )
        assert total == 1

    async def test_list_history_filter_by_date_range(
        self, db_session: AsyncSession, test_variant
    ):
        """list_history filters by date range."""
        repo = TransactionRepository(db_session)
        txn = await repo.create(
            variant_id=test_variant.id,
            transaction_type=TransactionType.ADJUSTMENT,
            quantity_change=5,
            quantity_before=100,
            quantity_after=105,
        )
        # Filter by a range that includes the transaction
        from datetime import timedelta
        date_from = txn.created_at - timedelta(hours=1)
        date_to = txn.created_at + timedelta(hours=1)
        txns, total = await repo.list_history(
            store_id=test_variant.product.store_id,
            date_from=date_from,
            date_to=date_to,
        )
        assert total >= 1

    async def test_get_recent(
        self, db_session: AsyncSession, test_variant
    ):
        """get_recent returns the most recent transactions."""
        repo = TransactionRepository(db_session)
        for i in range(5):
            await repo.create(
                variant_id=test_variant.id,
                transaction_type=TransactionType.ADJUSTMENT,
                quantity_change=i,
                quantity_before=100,
                quantity_after=100 + i,
            )
        recent = await repo.get_recent(
            store_id=test_variant.product.store_id,
            limit=3,
        )
        assert len(recent) <= 3

    async def test_mark_synced(
        self, db_session: AsyncSession, test_variant
    ):
        """mark_synced sets synced_to_shopify and synced_at via explicit UPDATE."""
        repo = TransactionRepository(db_session)
        txn = await repo.create(
            variant_id=test_variant.id,
            transaction_type=TransactionType.ADJUSTMENT,
            quantity_change=5,
            quantity_before=100,
            quantity_after=105,
        )
        await repo.mark_synced(txn.id)
        # Re-fetch to verify
        from sqlalchemy import select
        result = await db_session.execute(
            select(InventoryTransaction).where(InventoryTransaction.id == txn.id)
        )
        updated = result.scalar_one()
        assert updated.synced_to_shopify is True
        assert updated.synced_at is not None

    async def test_get_unsynced(
        self, db_session: AsyncSession, test_variant
    ):
        """get_unsynced returns only transactions not yet synced to Shopify."""
        repo = TransactionRepository(db_session)
        # Create an unsynced transaction
        txn1 = await repo.create(
            variant_id=test_variant.id,
            transaction_type=TransactionType.ADJUSTMENT,
            quantity_change=5,
            quantity_before=100,
            quantity_after=105,
        )
        # Create a synced transaction
        txn2 = await repo.create(
            variant_id=test_variant.id,
            transaction_type=TransactionType.ADJUSTMENT,
            quantity_change=10,
            quantity_before=105,
            quantity_after=115,
        )
        await repo.mark_synced(txn2.id)

        unsynced = await repo.get_unsynced(
            store_id=test_variant.product.store_id
        )
        unsynced_ids = [t.id for t in unsynced]
        assert txn1.id in unsynced_ids
        assert txn2.id not in unsynced_ids


# ═══════════════════════════════════════════════════════════════════
# LOG REPOSITORY (Activity Log)
# ═══════════════════════════════════════════════════════════════════


class TestLogRepository:
    """LogRepository: append-only activity log."""

    async def test_create(self, db_session: AsyncSession, test_variant):
        """Create a log entry."""
        repo = LogRepository(db_session)
        log = await repo.create(
            variant_id=test_variant.id,
            action=InventoryAction.CREATED.value,
            details={"key": "value"},
        )
        assert log.id is not None
        assert log.action == "created"
        assert log.details == {"key": "value"}
        await assert_log_count(db_session, 1)

    async def test_create_with_performer(
        self, db_session: AsyncSession, test_variant, test_user
    ):
        """Create a log entry with a performer."""
        repo = LogRepository(db_session)
        log = await repo.create(
            variant_id=test_variant.id,
            action=InventoryAction.UPDATED.value,
            performed_by=test_user.id,
        )
        assert log.performed_by == test_user.id

    async def test_list_by_variant(
        self, db_session: AsyncSession, test_variant
    ):
        """list_by_variant returns paginated logs for a variant."""
        repo = LogRepository(db_session)
        for i in range(5):
            await repo.create(
                variant_id=test_variant.id,
                action=InventoryAction.CREATED.value,
                details={"index": i},
            )
        logs, total = await repo.list_by_variant(test_variant.id, page=1, page_size=2)
        assert len(logs) == 2
        assert total == 5

    async def test_list_by_variant_empty(
        self, db_session: AsyncSession, test_variant
    ):
        """list_by_variant returns empty for a variant with no logs."""
        repo = LogRepository(db_session)
        logs, total = await repo.list_by_variant(test_variant.id)
        assert len(logs) == 0
        assert total == 0
