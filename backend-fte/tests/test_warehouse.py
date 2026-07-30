"""
Comprehensive tests for the Warehouse Management module.

Tests cover:
- Warehouse CRUD operations
- Warehouse activation/deactivation
- Warehouse inventory management
- Warehouse transfers (create, approve, complete, cancel)
- Stock reservation and release
- Capacity validation
- Error handling for all domain exceptions
"""

import uuid
import pytest

pytestmark = pytest.mark.asyncio

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import (
    Warehouse, WarehouseInventory, WarehouseTransfer,
    WarehouseTransferItem, Product, ProductVariant, Store,
)
from app.inventory.constants import (
    WarehouseStatus, TransferStatus, TransactionType, InventoryAction,
)
from app.inventory.exceptions import VariantNotFoundError
from app.warehouse.exceptions import (
    WarehouseNotFoundError, WarehouseAlreadyExistsError,
    WarehouseInactiveError, WarehouseAtCapacityError,
    WarehouseInventoryNotFoundError, TransferNotFoundError,
    InvalidTransferStateError, SameWarehouseTransferError,
    InsufficientWarehouseStockError,
)
from app.warehouse.service import (
    WarehouseService, WarehouseInventoryService,
    WarehouseTransferService, CapacityService,
    InventoryAggregationService,
)


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_store():
    """Create a mock store."""
    store = MagicMock(spec=Store)
    store.id = uuid.uuid4()
    store.shopify_domain = "test-store.myshopify.com"
    store.is_active = True
    return store


@pytest.fixture
def user_id():
    """Create a mock user ID."""
    return uuid.uuid4()


@pytest.fixture
def warehouse_service(mock_db, mock_store, user_id):
    """Create a WarehouseService with mocked dependencies."""
    service = WarehouseService(db=mock_db, store=mock_store, user_id=user_id)
    service.repo = AsyncMock()
    service.log_repo = AsyncMock()
    return service


@pytest.fixture
def wh_inv_service(mock_db, mock_store, user_id):
    """Create a WarehouseInventoryService with mocked dependencies."""
    service = WarehouseInventoryService(db=mock_db, store=mock_store, user_id=user_id)
    service.inv_repo = AsyncMock()
    service.wh_repo = AsyncMock()
    service.variant_repo = AsyncMock()
    service.txn_repo = AsyncMock()
    service.log_repo = AsyncMock()
    return service


@pytest.fixture
def transfer_service(mock_db, mock_store, user_id):
    """Create a WarehouseTransferService with mocked dependencies."""
    service = WarehouseTransferService(db=mock_db, store=mock_store, user_id=user_id)
    service.transfer_repo = AsyncMock()
    service.item_repo = AsyncMock()
    service.inv_repo = AsyncMock()
    service.wh_repo = AsyncMock()
    service.variant_repo = AsyncMock()
    service.txn_repo = AsyncMock()
    service.log_repo = AsyncMock()
    return service


@pytest.fixture
def mock_warehouse():
    """Create a mock warehouse."""
    wh = MagicMock(spec=Warehouse)
    wh.id = uuid.uuid4()
    wh.store_id = uuid.uuid4()
    wh.code = "WH-001"
    wh.name = "Main Warehouse"
    wh.description = "Primary storage facility"
    wh.address = "123 Warehouse Blvd"
    wh.city = "Portland"
    wh.state = "OR"
    wh.country = "USA"
    wh.postal_code = "97201"
    wh.phone = "555-0100"
    wh.email = "warehouse@example.com"
    wh.capacity = 10000
    wh.capacity_unit = "units"
    wh.status = WarehouseStatus.ACTIVE
    wh.is_active = True
    wh.created_at = datetime.now(timezone.utc)
    wh.updated_at = datetime.now(timezone.utc)
    return wh


@pytest.fixture
def mock_variant():
    """Create a mock product variant."""
    variant = MagicMock(spec=ProductVariant)
    variant.id = uuid.uuid4()
    variant.product_id = uuid.uuid4()
    variant.sku = "SKU-001"
    variant.title = "Test Variant"
    variant.price = Decimal("29.99")
    variant.inventory_quantity = 100
    variant.requires_shipping = True
    return variant


# ═══════════════════════════════════════════════════════════════════
# WAREHOUSE SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestWarehouseService:
    """Tests for warehouse CRUD and lifecycle."""

    async def test_create_warehouse_success(self, warehouse_service, mock_warehouse):
        """Test successful warehouse creation."""
        data = MagicMock()
        data.code = "WH-002"
        data.model_dump.return_value = {
            "code": "WH-002", "name": "New Warehouse", "capacity": 5000,
        }
        warehouse_service.repo.get_by_code.return_value = None
        warehouse_service.repo.create.return_value = mock_warehouse

        result = await warehouse_service.create_warehouse(data)

        assert result is not None
        warehouse_service.repo.get_by_code.assert_called_once_with(
            "WH-002", warehouse_service.store.id
        )
        warehouse_service.repo.create.assert_called_once()

    async def test_create_warehouse_duplicate_code(self, warehouse_service, mock_warehouse):
        """Test warehouse creation with duplicate code."""
        data = MagicMock()
        data.code = "WH-001"
        warehouse_service.repo.get_by_code.return_value = mock_warehouse

        with pytest.raises(WarehouseAlreadyExistsError):
            await warehouse_service.create_warehouse(data)

    async def test_get_warehouse_success(self, warehouse_service, mock_warehouse):
        """Test successful warehouse retrieval."""
        mock_warehouse.store_id = warehouse_service.store.id
        warehouse_service.repo.get_by_id.return_value = mock_warehouse

        result = await warehouse_service.get_warehouse(mock_warehouse.id)
        assert result is not None

    async def test_get_warehouse_not_found(self, warehouse_service):
        """Test warehouse retrieval when not found."""
        warehouse_service.repo.get_by_id.return_value = None
        with pytest.raises(WarehouseNotFoundError):
            await warehouse_service.get_warehouse(uuid.uuid4())

    async def test_get_warehouse_wrong_store(self, warehouse_service, mock_warehouse):
        """Test warehouse retrieval when it belongs to another store."""
        mock_warehouse.store_id = uuid.uuid4()
        warehouse_service.repo.get_by_id.return_value = mock_warehouse
        with pytest.raises(WarehouseNotFoundError):
            await warehouse_service.get_warehouse(mock_warehouse.id)

    async def test_list_warehouses(self, warehouse_service, mock_warehouse):
        """Test listing warehouses."""
        warehouse_service.repo.list_by_store.return_value = ([mock_warehouse], 1)
        warehouses, total = await warehouse_service.list_warehouses()
        assert len(warehouses) == 1
        assert total == 1

    async def test_activate_warehouse(self, warehouse_service, mock_warehouse):
        """Test warehouse activation."""
        mock_warehouse.store_id = warehouse_service.store.id
        warehouse_service.repo.get_by_id.return_value = mock_warehouse
        warehouse_service.repo.update.return_value = mock_warehouse

        result = await warehouse_service.activate_warehouse(mock_warehouse.id)
        warehouse_service.repo.update.assert_called_once_with(
            mock_warehouse.id,
            {"is_active": True, "status": WarehouseStatus.ACTIVE},
        )

    async def test_deactivate_warehouse(self, warehouse_service, mock_warehouse):
        """Test warehouse deactivation with settings cleanup."""
        mock_warehouse.store_id = warehouse_service.store.id
        mock_warehouse.is_default = False  # Not the default
        warehouse_service.repo.get_by_id.return_value = mock_warehouse
        warehouse_service.repo.update.return_value = mock_warehouse

        with patch('app.warehouse.service.WarehouseSettingsRepository') as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo.get_or_create = AsyncMock(return_value=MagicMock(default_warehouse_id=None))
            mock_repo_cls.return_value = mock_repo

            result = await warehouse_service.deactivate_warehouse(mock_warehouse.id)

        warehouse_service.repo.update.assert_called_once_with(
            mock_warehouse.id,
            {"is_active": False, "status": WarehouseStatus.INACTIVE},
        )

    async def test_delete_warehouse(self, warehouse_service, mock_warehouse):
        """Test warehouse deletion with settings cleanup."""
        mock_warehouse.store_id = warehouse_service.store.id
        mock_warehouse.name = "Test WH"
        mock_warehouse.is_default = False
        warehouse_service.repo.get_by_id.return_value = mock_warehouse
        warehouse_service.repo.delete.return_value = True

        with patch('app.warehouse.service.WarehouseSettingsRepository') as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo.get_by_store = AsyncMock(return_value=None)  # No settings
            mock_repo_cls.return_value = mock_repo

            result = await warehouse_service.delete_warehouse(mock_warehouse.id)
            assert "deleted" in result["message"].lower()


# ═══════════════════════════════════════════════════════════════════
# WAREHOUSE INVENTORY SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestWarehouseInventoryService:
    """Tests for warehouse inventory management."""

    async def test_adjust_stock_success(self, wh_inv_service, mock_warehouse, mock_variant):
        """Test successful stock adjustment at a warehouse."""
        mock_warehouse.store_id = wh_inv_service.store.id
        mock_warehouse.is_active = True
        wh_inv_service.wh_repo.get_by_id.return_value = mock_warehouse
        wh_inv_service.variant_repo.get_by_id.return_value = mock_variant

        mock_inv = MagicMock(spec=WarehouseInventory)
        mock_inv.available_stock = 50
        wh_inv_service.inv_repo.get_or_create.return_value = mock_inv

        mock_txn = MagicMock()
        mock_txn.id = uuid.uuid4()
        wh_inv_service.txn_repo.create.return_value = mock_txn

        result = await wh_inv_service.adjust_stock(
            warehouse_id=mock_warehouse.id,
            variant_id=mock_variant.id,
            quantity_change=10,
            reason="Restock",
        )

        assert result["quantity_change"] == 10
        assert result["available_after"] == 60
        assert "increased" in result["message"]

    async def test_adjust_stock_negative_insufficient(self, wh_inv_service, mock_warehouse, mock_variant):
        """Test stock adjustment that would go negative."""
        mock_warehouse.store_id = wh_inv_service.store.id
        mock_warehouse.is_active = True
        wh_inv_service.wh_repo.get_by_id.return_value = mock_warehouse
        wh_inv_service.variant_repo.get_by_id.return_value = mock_variant

        mock_inv = MagicMock(spec=WarehouseInventory)
        mock_inv.available_stock = 5
        wh_inv_service.inv_repo.get_or_create.return_value = mock_inv

        with pytest.raises(InsufficientWarehouseStockError):
            await wh_inv_service.adjust_stock(
                warehouse_id=mock_warehouse.id,
                variant_id=mock_variant.id,
                quantity_change=-10,
                reason="Over-deduction",
            )

    async def test_adjust_stock_inactive_warehouse(self, wh_inv_service, mock_warehouse, mock_variant):
        """Test stock adjustment on inactive warehouse."""
        mock_warehouse.store_id = wh_inv_service.store.id
        mock_warehouse.is_active = False
        wh_inv_service.wh_repo.get_by_id.return_value = mock_warehouse

        with pytest.raises(WarehouseInactiveError):
            await wh_inv_service.adjust_stock(
                warehouse_id=mock_warehouse.id,
                variant_id=mock_variant.id,
                quantity_change=5,
            )

    async def test_reserve_stock_success(self, wh_inv_service):
        """Test successful stock reservation."""
        warehouse_id = uuid.uuid4()
        variant_id = uuid.uuid4()

        mock_inv = MagicMock(spec=WarehouseInventory)
        mock_inv.available_stock = 100
        mock_inv.reserved_stock = 0
        wh_inv_service.inv_repo.get_or_create.return_value = mock_inv

        result = await wh_inv_service.reserve_stock(
            warehouse_id=warehouse_id,
            variant_id=variant_id,
            quantity=20,
            reason="Order fulfillment",
        )

        assert mock_inv.available_stock == 80
        assert mock_inv.reserved_stock == 20
        wh_inv_service.log_repo.create.assert_called_once()

    async def test_reserve_stock_insufficient(self, wh_inv_service):
        """Test reservation when not enough stock."""
        warehouse_id = uuid.uuid4()
        variant_id = uuid.uuid4()

        mock_inv = MagicMock(spec=WarehouseInventory)
        mock_inv.available_stock = 5
        wh_inv_service.inv_repo.get_or_create.return_value = mock_inv

        with pytest.raises(InsufficientWarehouseStockError):
            await wh_inv_service.reserve_stock(
                warehouse_id=warehouse_id,
                variant_id=variant_id,
                quantity=20,
            )

    async def test_release_reservation(self, wh_inv_service):
        """Test releasing a reservation."""
        warehouse_id = uuid.uuid4()
        variant_id = uuid.uuid4()

        mock_inv = MagicMock(spec=WarehouseInventory)
        mock_inv.available_stock = 50
        mock_inv.reserved_stock = 30
        wh_inv_service.inv_repo.get_or_create.return_value = mock_inv

        await wh_inv_service.release_reservation(
            warehouse_id=warehouse_id,
            variant_id=variant_id,
            quantity=15,
            reason="Order cancelled",
        )

        assert mock_inv.available_stock == 65
        assert mock_inv.reserved_stock == 15


# ═══════════════════════════════════════════════════════════════════
# WAREHOUSE TRANSFER SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestWarehouseTransferService:
    """Tests for warehouse transfers."""

    async def test_create_transfer_success(self, transfer_service):
        """Test successful transfer creation."""
        source_id = uuid.uuid4()
        dest_id = uuid.uuid4()
        variant_id = uuid.uuid4()

        mock_source = MagicMock(spec=Warehouse)
        mock_source.store_id = transfer_service.store.id
        mock_source.is_active = True
        mock_source.id = source_id

        mock_dest = MagicMock(spec=Warehouse)
        mock_dest.store_id = transfer_service.store.id
        mock_dest.is_active = True
        mock_dest.id = dest_id

        transfer_service.wh_repo.get_by_id.side_effect = lambda id: {
            source_id: mock_source, dest_id: mock_dest,
        }.get(id)

        mock_inv = MagicMock(spec=WarehouseInventory)
        mock_inv.available_stock = 100
        transfer_service.inv_repo.get_by_variant_and_warehouse.return_value = mock_inv

        mock_transfer = MagicMock(spec=WarehouseTransfer)
        mock_transfer.id = uuid.uuid4()
        mock_transfer.transfer_number = "TRF-20260727-ABC123"
        mock_transfer.status = TransferStatus.DRAFT
        transfer_service.transfer_repo.create.return_value = mock_transfer

        mock_item = MagicMock(spec=WarehouseTransferItem)
        mock_item.variant_id = variant_id
        transfer_service.item_repo.create.return_value = mock_item

        mock_variant_obj = MagicMock(spec=ProductVariant)
        mock_variant_obj.product_id = uuid.uuid4()
        transfer_service.variant_repo.get_by_id.return_value = mock_variant_obj

        mock_full_transfer = MagicMock(spec=WarehouseTransfer)
        mock_full_transfer.id = mock_transfer.id
        mock_full_transfer.transfer_number = "TRF-20260727-ABC123"
        mock_full_transfer.status = TransferStatus.DRAFT
        mock_full_transfer.items = [mock_item]
        transfer_service.transfer_repo.get_by_id.return_value = mock_full_transfer

        data = MagicMock()
        data.source_warehouse_id = source_id
        data.destination_warehouse_id = dest_id
        data.notes = "Test transfer"
        data.transfer_date = None

        item_data = MagicMock()
        item_data.variant_id = variant_id
        item_data.quantity = 10
        item_data.reason = "Stock redistribution"
        data.items = [item_data]

        result = await transfer_service.create_transfer(data)
        assert result is not None

    async def test_create_transfer_same_warehouse(self, transfer_service):
        """Test transfer with same source and destination."""
        wh_id = uuid.uuid4()
        data = MagicMock()
        data.source_warehouse_id = wh_id
        data.destination_warehouse_id = wh_id

        with pytest.raises(SameWarehouseTransferError):
            await transfer_service.create_transfer(data)

    async def test_create_transfer_insufficient_stock(self, transfer_service):
        """Test transfer with insufficient source stock."""
        source_id = uuid.uuid4()
        dest_id = uuid.uuid4()
        variant_id = uuid.uuid4()

        mock_source = MagicMock(spec=Warehouse)
        mock_source.store_id = transfer_service.store.id
        mock_source.is_active = True

        mock_dest = MagicMock(spec=Warehouse)
        mock_dest.store_id = transfer_service.store.id
        mock_dest.is_active = True

        transfer_service.wh_repo.get_by_id.side_effect = lambda id: {
            source_id: mock_source, dest_id: mock_dest,
        }.get(id)

        mock_inv = MagicMock(spec=WarehouseInventory)
        mock_inv.available_stock = 5
        transfer_service.inv_repo.get_by_variant_and_warehouse.return_value = mock_inv

        data = MagicMock()
        data.source_warehouse_id = source_id
        data.destination_warehouse_id = dest_id
        data.notes = None
        data.transfer_date = None

        item_data = MagicMock()
        item_data.variant_id = variant_id
        item_data.quantity = 100
        data.items = [item_data]

        with pytest.raises(InsufficientWarehouseStockError):
            await transfer_service.create_transfer(data)

    async def test_complete_transfer(self, transfer_service):
        """Test completing a transfer."""
        transfer_id = uuid.uuid4()
        source_id = uuid.uuid4()
        dest_id = uuid.uuid4()
        variant_id = uuid.uuid4()

        mock_item = MagicMock(spec=WarehouseTransferItem)
        mock_item.variant_id = variant_id
        mock_item.quantity = 10
        mock_item.received_quantity = None

        mock_transfer = MagicMock(spec=WarehouseTransfer)
        mock_transfer.id = transfer_id
        mock_transfer.store_id = transfer_service.store.id
        mock_transfer.transfer_number = "TRF-001"
        mock_transfer.status = TransferStatus.IN_TRANSIT
        mock_transfer.source_warehouse_id = source_id
        mock_transfer.destination_warehouse_id = dest_id
        mock_transfer.items = [mock_item]

        transfer_service.transfer_repo.get_by_id.return_value = mock_transfer

        mock_source_inv = MagicMock(spec=WarehouseInventory)
        mock_source_inv.available_stock = 100
        mock_source_inv.reserved_stock = 10

        mock_dest_inv = MagicMock(spec=WarehouseInventory)
        mock_dest_inv.available_stock = 50

        transfer_service.inv_repo.get_or_create.side_effect = [
            mock_source_inv, mock_dest_inv,
        ]

        mock_txn = MagicMock()
        transfer_service.txn_repo.create.return_value = mock_txn

        result = await transfer_service.complete_transfer(transfer_id)
        assert result.status == TransferStatus.COMPLETED
        assert result.completed_date is not None
        assert mock_item.received_quantity == 10


# ═══════════════════════════════════════════════════════════════════
# CAPACITY SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestCapacityService:
    """Tests for capacity management."""

    async def test_get_capacity_with_limit(self, mock_db, mock_store):
        """Test getting capacity for a warehouse with a capacity limit.
        
        Note: get_capacity now uses SQL aggregate (db.execute) instead of
        loading ORM items into memory.
        """
        service = CapacityService(db=mock_db, store=mock_store)
        service.wh_repo = AsyncMock()

        warehouse_id = uuid.uuid4()
        mock_warehouse = MagicMock(spec=Warehouse)
        mock_warehouse.store_id = mock_store.id
        mock_warehouse.name = "Test WH"
        mock_warehouse.code = "WH-TEST"
        mock_warehouse.capacity = 10000
        mock_warehouse.capacity_unit = "units"
        service.wh_repo.get_by_id.return_value = mock_warehouse

        # Mock the SQL aggregate query: db.execute returns a result
        # The capacity query returns a scalar value
        usage_result = MagicMock()
        usage_result.scalar.return_value = 7750  # Sum of all stock

        mock_db.execute.return_value = usage_result

        result = await service.get_capacity(warehouse_id)

        assert result["capacity"] == 10000
        assert result["current_usage"] == 7750
        assert result["usage_percentage"] is not None
        assert result["status"] in ("normal", "warning", "critical")

    async def test_get_capacity_no_limit(self, mock_db, mock_store):
        """Test getting capacity for a warehouse without a capacity limit."""
        service = CapacityService(db=mock_db, store=mock_store)
        service.wh_repo = AsyncMock()

        warehouse_id = uuid.uuid4()
        mock_warehouse = MagicMock(spec=Warehouse)
        mock_warehouse.store_id = mock_store.id
        mock_warehouse.name = "Test WH"
        mock_warehouse.code = "WH-TEST"
        mock_warehouse.capacity = None
        mock_warehouse.capacity_unit = "units"
        service.wh_repo.get_by_id.return_value = mock_warehouse

        # Mock SQL aggregate returning 0 usage
        usage_result = MagicMock()
        usage_result.scalar.return_value = 0
        mock_db.execute.return_value = usage_result

        result = await service.get_capacity(warehouse_id)

        assert result["capacity"] is None
        assert result["status"] == "normal"

    async def test_validate_capacity_ok(self, mock_db, mock_store):
        """Test capacity validation when there's room."""
        service = CapacityService(db=mock_db, store=mock_store)
        service.get_capacity = AsyncMock(return_value={
            "capacity": 1000, "current_usage": 500,
        })

        result = await service.validate_capacity(uuid.uuid4(), additional_units=200)
        assert result is True

    async def test_validate_capacity_exceeded(self, mock_db, mock_store):
        """Test capacity validation when capacity would be exceeded."""
        service = CapacityService(db=mock_db, store=mock_store)
        service.get_capacity = AsyncMock(return_value={
            "capacity": 1000, "current_usage": 900,
        })

        with pytest.raises(WarehouseAtCapacityError):
            await service.validate_capacity(uuid.uuid4(), additional_units=200)


# ═══════════════════════════════════════════════════════════════════
# AGGREGATION SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestInventoryAggregationService:
    """Tests for inventory aggregation across warehouses."""

    async def test_get_all_warehouse_summaries(self, mock_db, mock_store):
        """Test getting summaries for all warehouses."""
        service = InventoryAggregationService(db=mock_db, store=mock_store)
        service.wh_repo = AsyncMock()
        service.inv_repo = AsyncMock()

        mock_warehouses = []
        for i in range(3):
            wh = MagicMock(spec=Warehouse)
            wh.id = uuid.uuid4()
            wh.name = f"Warehouse {i+1}"
            wh.code = f"WH-00{i+1}"
            mock_warehouses.append(wh)

        service.wh_repo.list_by_store.return_value = (mock_warehouses, len(mock_warehouses))

        mock_items = []
        for i in range(5):
            item = MagicMock(spec=WarehouseInventory)
            item.available_stock = 100 * (i + 1)
            item.reserved_stock = 10 * (i + 1)
            item.reorder_point = 50
            item.incoming_stock = 20
            item.damaged_stock = 5
            mock_items.append(item)

        # Each warehouse calls list_by_warehouse twice (count + full data)
        # Use a default return for all calls, with enough items for side_effect
        mock_full_items = mock_items.copy()
        full_list = (mock_full_items, len(mock_full_items))

        # Provide enough return values for all 3 warehouses * 2 calls each = 6
        service.inv_repo.list_by_warehouse.side_effect = [
            full_list, full_list,  # Warehouse 1
            (mock_items[:2], 2), (mock_items[:2], 2),  # Warehouse 2
            full_list, full_list,  # Warehouse 3
        ]

        summaries = await service.get_all_warehouse_summaries()
        assert len(summaries) == 3
        for s in summaries:
            assert "warehouse_name" in s
            assert "total_products" in s
            assert "total_available_stock" in s
            assert "total_reserved_stock" in s
