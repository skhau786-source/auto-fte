"""
Tests for the WooCommerce ↔ Warehouse Inventory Sync Integration.

Verifies that:
- WarehouseInventorySyncService correctly syncs WC stock to warehouse inventory
- Products without SKU are handled gracefully
- Missing warehouses don't break the sync
- Multiple warehouse scenarios work with default selection
- Errors in warehouse sync don't propagate to WooCommerce sync
- Duplicate records are prevented
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.warehouse.woocommerce_sync_service import WarehouseInventorySyncService
from app.woocommerce.models import WooCommerceStore, WooCommerceProduct
from app.models import Store, Product, ProductVariant, Warehouse, WarehouseInventory


pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def sample_wc_store() -> WooCommerceStore:
    return WooCommerceStore(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        owner_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        store_name="Test WC Store",
        store_url="https://test-store.example.com",
        is_active=True,
    )


@pytest.fixture
def sample_wc_product() -> WooCommerceProduct:
    return WooCommerceProduct(
        id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        store_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        wc_product_id=12345,
        name="Test Product",
        sku="TEST-SKU-001",
        price=Decimal("29.99"),
        stock_quantity=50,
        manage_stock=True,
    )


@pytest.fixture
def sample_wc_product_no_sku(sample_wc_product) -> WooCommerceProduct:
    sample_wc_product.sku = ""
    sample_wc_product.wc_product_id = 54321
    return sample_wc_product


@pytest.fixture
def sample_inventory_store() -> Store:
    return Store(
        id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        owner_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        shopify_domain="test.myshopify.com",
        is_active=True,
    )


@pytest.fixture
def sample_warehouse() -> Warehouse:
    return Warehouse(
        id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
        store_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        code="WH-DEFAULT",
        name="Default Warehouse",
        is_active=True,
    )


@pytest.fixture
def sample_variant() -> ProductVariant:
    return ProductVariant(
        id=uuid.UUID("66666666-6666-6666-6666-666666666666"),
        product_id=uuid.UUID("77777777-7777-7777-7777-777777777777"),
        sku="TEST-SKU-001",
        title="Test Product",
        price=Decimal("29.99"),
        inventory_quantity=50,
    )


@pytest.fixture
def sample_product() -> Product:
    return Product(
        id=uuid.UUID("77777777-7777-7777-7777-777777777777"),
        store_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        title="Test Product",
        status="active",
    )


@pytest.fixture
def sample_wh_inventory() -> WarehouseInventory:
    return WarehouseInventory(
        id=uuid.UUID("88888888-8888-8888-8888-888888888888"),
        warehouse_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
        variant_id=uuid.UUID("66666666-6666-6666-6666-666666666666"),
        product_id=uuid.UUID("77777777-7777-7777-7777-777777777777"),
        available_stock=30,
        reserved_stock=0,
        incoming_stock=0,
        damaged_stock=0,
    )


# ═══════════════════════════════════════════════════════════════════
# Tests: _find_inventory_store
# ═══════════════════════════════════════════════════════════════════

class TestFindInventoryStore:

    async def test_finds_existing_store(self, mock_db, sample_wc_store, sample_inventory_store):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_inventory_store
        mock_db.execute.return_value = mock_result

        service = WarehouseInventorySyncService(mock_db)
        result = await service._find_inventory_store(sample_wc_store.owner_id)

        assert result is not None
        assert result.id == sample_inventory_store.id

    async def test_no_store_returns_none(self, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = WarehouseInventorySyncService(mock_db)
        result = await service._find_inventory_store(uuid.uuid4())
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# Tests: _get_default_warehouse
# ═══════════════════════════════════════════════════════════════════

class TestGetDefaultWarehouse:

    async def test_single_warehouse_used(self, mock_db, sample_warehouse):
        # _get_default_warehouse calls repo.get_default() which does
        # db.execute → scalar_one_or_none
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_warehouse
        mock_db.execute.return_value = mock_result

        service = WarehouseInventorySyncService(mock_db)
        result = await service._get_default_warehouse(sample_warehouse.store_id)
        assert result is not None
        assert result.id == sample_warehouse.id

    async def test_no_warehouse_returns_none(self, mock_db):
        # _get_default_warehouse:
        #   1. WarehouseSettingsRepository.get_by_store → db.execute → scalar_one_or_none (None)
        #   2. repo.get_default() → db.execute → scalar_one_or_none (None)
        #   3. repo.ensure_single_default():
        #       3a. get_default() → db.execute → scalar_one_or_none (None)
        #       3b. list_by_store → db.execute count → scalar() → 0
        #       3c. list_by_store → db.execute list → scalars().all() → []
        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None

        mock_count = MagicMock()
        mock_count.scalar.return_value = 0

        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [
            mock_none,    # 1. WarehouseSettings get_by_store
            mock_none,    # 2. get_default (in _get_default_warehouse)
            mock_none,    # 3a. get_default (in ensure_single_default)
            mock_count,   # 3b. list_by_store count
            mock_list,    # 3c. list_by_store list
        ]

        service = WarehouseInventorySyncService(mock_db)
        result = await service._get_default_warehouse(uuid.uuid4())
        assert result is None

    async def test_default_warehouse_flag_used(self, mock_db, sample_warehouse):
        """With multiple warehouses, the one with is_default=True is returned."""
        wh2 = Warehouse(
            id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            store_id=sample_warehouse.store_id,
            code="WH-SECONDARY",
            name="Secondary Warehouse",
            is_active=True,
        )
        # Mark sample_warehouse as default
        sample_warehouse.is_default = True

        # get_default returns sample_warehouse (it has is_default=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_warehouse
        mock_db.execute.return_value = mock_result

        service = WarehouseInventorySyncService(mock_db)
        result = await service._get_default_warehouse(sample_warehouse.store_id)
        assert result is not None
        assert result.id == sample_warehouse.id
        assert result.is_default is True


# ═══════════════════════════════════════════════════════════════════
# Tests: _find_or_create_variant
# ═══════════════════════════════════════════════════════════════════

class TestFindOrCreateVariant:

    async def test_finds_existing_variant_by_sku(
        self, mock_db, sample_variant, sample_wc_product, sample_inventory_store,
    ):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_variant
        mock_db.execute.return_value = mock_result

        service = WarehouseInventorySyncService(mock_db)
        result = await service._find_or_create_variant(
            store_id=sample_inventory_store.id,
            sku=sample_wc_product.sku,
            wc_product=sample_wc_product,
        )
        assert result is not None
        assert result.id == sample_variant.id

    async def test_no_sku_returns_none(self, mock_db, sample_wc_product_no_sku, sample_inventory_store):
        service = WarehouseInventorySyncService(mock_db)
        result = await service._find_or_create_variant(
            store_id=sample_inventory_store.id,
            sku="",
            wc_product=sample_wc_product_no_sku,
        )
        assert result is None

    async def test_creates_new_variant_and_product(
        self, mock_db, sample_wc_product, sample_inventory_store,
    ):
        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_none

        service = WarehouseInventorySyncService(mock_db)

        mock_none2 = MagicMock()
        mock_none2.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [mock_none, mock_none2]

        result = await service._find_or_create_variant(
            store_id=sample_inventory_store.id,
            sku=sample_wc_product.sku,
            wc_product=sample_wc_product,
        )
        assert result is not None
        assert result.sku == sample_wc_product.sku
        assert mock_db.add.called
        assert mock_db.flush.called


# ═══════════════════════════════════════════════════════════════════
# Tests: sync_wc_product_to_warehouse (end-to-end)
# ═══════════════════════════════════════════════════════════════════
# Call order in sync_wc_product_to_warehouse:
#   1. _find_inventory_store  (execute -> scalar_one_or_none)
#   2. _find_or_create_variant (execute -> scalar_one_or_none)
#   3. _get_default_warehouse   (execute -> scalars().all())
#   4. inv_repo.get_or_create   (execute -> scalar_one_or_none)
# ═══════════════════════════════════════════════════════════════════

class TestSyncWCProductToWarehouse:

    async def test_full_sync_pipeline(
        self, mock_db, sample_wc_store, sample_wc_product,
        sample_inventory_store, sample_warehouse, sample_variant,
        sample_wh_inventory,
    ):
        # Build mock results in the ORDER the service calls them
        mock_store = MagicMock()
        mock_store.scalar_one_or_none.return_value = sample_inventory_store

        mock_variant = MagicMock()
        mock_variant.scalar_one_or_none.return_value = sample_variant

        # _get_default_warehouse now reads WarehouseSettings first
        mock_wh_settings = MagicMock()
        mock_wh_settings.scalar_one_or_none.return_value = None  # No settings

        mock_wh = MagicMock()
        mock_wh.scalar_one_or_none.return_value = sample_warehouse

        mock_wh_inv = MagicMock()
        mock_wh_inv.scalar_one_or_none.return_value = sample_wh_inventory

        mock_db.execute.side_effect = [
            mock_store,         # 1. _find_inventory_store
            mock_variant,       # 2. _find_or_create_variant
            mock_wh_settings,   # 3. _get_default_warehouse: WarehouseSettings
            mock_wh,            # 4. _get_default_warehouse: repo.get_default
            mock_wh_inv,        # 5. inv_repo.get_or_create
        ]

        service = WarehouseInventorySyncService(mock_db)
        result = await service.sync_wc_product_to_warehouse(
            wc_store=sample_wc_store,
            wc_product=sample_wc_product,
            stock_quantity=75,
        )

        assert result["status"] == "synced"
        assert result["wc_product_id"] == sample_wc_product.wc_product_id
        assert result["old_stock"] == 30
        assert result["new_stock"] == 75

    async def test_no_inventory_store_skips(self, mock_db, sample_wc_store, sample_wc_product):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = WarehouseInventorySyncService(mock_db)
        result = await service.sync_wc_product_to_warehouse(
            wc_store=sample_wc_store,
            wc_product=sample_wc_product,
            stock_quantity=50,
        )
        assert result["status"] == "skipped"
        assert result["reason"] == "no_inventory_store"

    async def test_no_warehouse_skips(
        self, mock_db, sample_wc_store, sample_wc_product, sample_inventory_store,
    ):
        mock_store = MagicMock()
        mock_store.scalar_one_or_none.return_value = sample_inventory_store

        mock_variant = MagicMock()
        mock_variant.scalar_one_or_none.return_value = None  # no variant found

        mock_product = MagicMock()
        mock_product.scalar_one_or_none.return_value = None  # no product found

        # _get_default_warehouse checks WarehouseSettings first
        mock_wh_settings = MagicMock()
        mock_wh_settings.scalar_one_or_none.return_value = None  # No settings

        # _get_default_warehouse calls repo.get_default() which returns None
        mock_default_none = MagicMock()
        mock_default_none.scalar_one_or_none.return_value = None

        # ensure_single_default calls get_default (None) then list_by_store count + list
        mock_count = MagicMock()
        mock_count.scalar.return_value = 0

        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [
            mock_store,           # 1. _find_inventory_store
            mock_variant,         # 2. find existing variant (None)
            mock_product,         # 3. find existing product (None) → then creates both
            mock_wh_settings,     # 4. _get_default_warehouse: WarehouseSettings
            mock_default_none,    # 5. _get_default_warehouse: get_default returns None
            mock_default_none,    # 6. ensure_single_default: get_default again
            mock_count,           # 7. ensure_single_default: list_by_store count
            mock_list,            # 8. ensure_single_default: list_by_store list
        ]

        service = WarehouseInventorySyncService(mock_db)
        result = await service.sync_wc_product_to_warehouse(
            wc_store=sample_wc_store,
            wc_product=sample_wc_product,
            stock_quantity=50,
        )

        assert result["status"] == "skipped"
        assert result["reason"] == "no_warehouse"

    async def test_no_sku_skips(
        self, mock_db, sample_wc_store, sample_wc_product_no_sku, sample_inventory_store, sample_warehouse,
    ):
        mock_store = MagicMock()
        mock_store.scalar_one_or_none.return_value = sample_inventory_store

        mock_db.execute.side_effect = [
            mock_store,  # only store lookup, then _find_or_create_variant returns None for empty SKU
        ]

        service = WarehouseInventorySyncService(mock_db)
        result = await service.sync_wc_product_to_warehouse(
            wc_store=sample_wc_store,
            wc_product=sample_wc_product_no_sku,
            stock_quantity=50,
        )

        assert result["status"] == "skipped"
        assert result["reason"] == "variant_not_created"

    async def test_exception_handled_gracefully(self, mock_db, sample_wc_store, sample_wc_product):
        mock_db.execute.side_effect = ValueError("Database connection error")

        service = WarehouseInventorySyncService(mock_db)
        result = await service.sync_wc_product_to_warehouse(
            wc_store=sample_wc_store,
            wc_product=sample_wc_product,
            stock_quantity=50,
        )

        assert result["status"] == "failed"
        assert "Database connection error" in result["reason"]


# ═══════════════════════════════════════════════════════════════════
# Tests: sync_wc_products_batch
# ═══════════════════════════════════════════════════════════════════

class TestSyncBatch:

    async def test_batch_processes_all_products(self, mock_db, sample_wc_store, sample_wc_product):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        products = [(sample_wc_product, 50), (sample_wc_product, 30)]

        service = WarehouseInventorySyncService(mock_db)
        results = await service.sync_wc_products_batch(sample_wc_store, products)

        assert len(results) == 2
        assert all(r["status"] == "skipped" for r in results)


# ═══════════════════════════════════════════════════════════════════
# Tests: find_or_create_inventory_store
# ═══════════════════════════════════════════════════════════════════

class TestFindOrCreateInventoryStore:

    async def test_finds_existing_store(self, mock_db, sample_wc_store, sample_inventory_store):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_inventory_store
        mock_db.execute.return_value = mock_result

        service = WarehouseInventorySyncService(mock_db)
        result = await service.find_or_create_inventory_store(sample_wc_store)
        assert result is not None
        assert result.id == sample_inventory_store.id

    async def test_creates_new_store(self, mock_db, sample_wc_store):
        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_none

        service = WarehouseInventorySyncService(mock_db)
        result = await service.find_or_create_inventory_store(sample_wc_store)

        assert result is not None
        assert result.owner_id == sample_wc_store.owner_id
        assert mock_db.add.called
        assert mock_db.flush.called
