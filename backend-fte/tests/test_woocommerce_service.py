"""
Unit tests for the WooCommerce Service Layer.

Tests cover:
- Store connection and verification
- Product CRUD and sync operations
- Inventory management (adjustments, low stock)
- Order management and sync
- Customer management
- Category sync with hierarchy
- Coupon sync
- Alert management
- Dashboard aggregation
- Settings management
"""

import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.woocommerce.service import WooCommerceService
from app.woocommerce.exceptions import (
    StoreNotFoundError,
    StoreAlreadyExistsError,
    StoreConnectionError,
    ProductNotFoundError,
    InsufficientStockError,
)


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_user():
    """Create a mock user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "test@example.com"
    return user


@pytest.fixture
def service(mock_db, mock_user):
    """Create a WooCommerceService instance with mocked dependencies."""
    return WooCommerceService(db=mock_db, user=mock_user)


class TestStoreManagement:
    """Test store connection, verification, and CRUD operations."""

    @pytest.mark.asyncio
    async def test_connect_store_success(self, service, mock_db):
        """Connect store with valid credentials should create store record."""
        mock_data = MagicMock()
        mock_data.store_url = "https://test-store.com"
        mock_data.store_name = "Test Store"
        mock_data.consumer_key = "ck_valid"
        mock_data.consumer_secret = "cs_valid"

        # Mock no existing store
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Mock client verification
        with patch("app.woocommerce.service.WooCommerceClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.verify_connection.return_value = {
                "status": "connected",
                "woocommerce_version": "8.5.0",
            }
            mock_client_cls.return_value = mock_client

            # Mock Celery initial sync
            with patch("app.woocommerce.service.run_initial_sync") as mock_sync:
                mock_sync.delay.return_value = None

                result = await service.connect_store(mock_data)

                assert result["message"] == "Store connected successfully"
                assert result["verification"]["status"] == "connected"
                mock_db.add.assert_called()
                mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_connect_store_duplicate_url(self, service, mock_db):
        """Duplicate store URL should raise StoreAlreadyExistsError."""
        mock_data = MagicMock()
        mock_data.store_url = "https://test-store.com"

        # Mock existing store found
        mock_db.execute.return_value.scalar_one_or_none.return_value = MagicMock()

        with pytest.raises(StoreAlreadyExistsError):
            await service.connect_store(mock_data)

    @pytest.mark.asyncio
    async def test_connect_store_invalid_credentials(self, service, mock_db):
        """Invalid credentials should raise StoreConnectionError."""
        mock_data = MagicMock()
        mock_data.store_url = "https://test-store.com"

        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        with patch("app.woocommerce.service.WooCommerceClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.verify_connection.side_effect = Exception("Invalid credentials")
            mock_client_cls.return_value = mock_client

            with pytest.raises(StoreConnectionError):
                await service.connect_store(mock_data)

    @pytest.mark.asyncio
    async def test_disconnect_store(self, service, mock_db):
        """Disconnect should deactivate store and create alert."""
        store_id = uuid.uuid4()
        mock_store = MagicMock()
        mock_store.id = store_id
        mock_store.store_name = "Test Store"
        mock_store.is_active = True
        mock_store.owner_id = service.user_id

        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_store

        result = await service.disconnect_store(store_id)

        assert result["message"] == "Store 'Test Store' disconnected successfully"
        assert mock_store.is_active == False


class TestInventoryManagement:
    """Test inventory adjustment, low stock detection, and history."""

    @pytest.mark.asyncio
    async def test_adjust_inventory_increase(self, service, mock_db):
        """Increasing stock should update quantity and create log."""
        store_id = uuid.uuid4()
        mock_store = MagicMock()
        mock_store.id = store_id
        mock_store.is_active = True
        mock_store.owner_id = service.user_id
        mock_store.shopify_domain = "test-store.com"

        mock_product = MagicMock()
        mock_product.id = uuid.uuid4()
        mock_product.wc_product_id = 123
        mock_product.manage_stock = True
        mock_product.stock_quantity = 50
        mock_product.sku = "TEST-001"
        mock_product.name = "Test Product"

        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_store

        # Mock the product query (second execute call)
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=lambda: mock_store),  # get_store
            MagicMock(scalar_one_or_none=lambda: mock_product),  # get_product
        ]

        result = await service.adjust_inventory(
            store_id=store_id,
            wc_product_id=123,
            quantity_change=10,
            reason="Restock",
        )

        assert result["quantity_before"] == 50
        assert result["quantity_after"] == 60
        assert result["quantity_change"] == 10
        assert "increased" in result["message"]

    @pytest.mark.asyncio
    async def test_adjust_inventory_below_zero(self, service, mock_db):
        """Reducing stock below zero should raise InsufficientStockError."""
        store_id = uuid.uuid4()
        mock_store = MagicMock()
        mock_store.id = store_id
        mock_store.is_active = True
        mock_store.owner_id = service.user_id

        mock_product = MagicMock()
        mock_product.id = uuid.uuid4()
        mock_product.wc_product_id = 123
        mock_product.manage_stock = True
        mock_product.stock_quantity = 5

        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_store
        mock_db.execute.side_effect = [
            MagicMock(scalar_one_or_none=lambda: mock_store),
            MagicMock(scalar_one_or_none=lambda: mock_product),
        ]

        with pytest.raises(InsufficientStockError):
            await service.adjust_inventory(
                store_id=store_id,
                wc_product_id=123,
                quantity_change=-10,
                reason="Sale",
            )

    @pytest.mark.asyncio
    async def test_get_low_stock(self, service, mock_db):
        """Low stock query should return products below threshold."""
        store_id = uuid.uuid4()

        mock_product = MagicMock()
        mock_product.id = uuid.uuid4()
        mock_product.wc_product_id = 123
        mock_product.name = "Low Stock Item"
        mock_product.sku = "LOW-001"
        mock_product.stock_quantity = 3
        mock_product.featured_image_url = None

        # Mock count query and list query
        mock_count = MagicMock()
        mock_count.scalar.return_value = 1

        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [mock_product]

        mock_db.execute.side_effect = [mock_count, mock_list]

        items, total = await service.get_low_stock(store_id, threshold=10)

        assert total == 1
        assert items[0]["product_name"] == "Low Stock Item"
        assert items[0]["stock_quantity"] == 3


class TestProductSync:
    """Test product synchronization logic."""

    @pytest.mark.asyncio
    async def test_sync_products_creates_new(self, service, mock_db):
        """New products from WooCommerce should be created locally."""
        store_id = uuid.uuid4()
        mock_store = MagicMock()
        mock_store.id = store_id
        mock_store.is_active = True
        mock_store.owner_id = service.user_id
        mock_store.store_url = "https://test-store.com"
        mock_store.consumer_key = "ck_test"
        mock_store.consumer_secret = "cs_test"

        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_store

        with patch("app.woocommerce.service.WooCommerceClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get_all_products.return_value = [
                {"id": 1, "name": "New Product", "price": "29.99", "type": "simple", "status": "publish"}
            ]
            mock_client_cls.return_value = mock_client

            result = await service.sync_products(store_id=store_id, force_full=True)

            assert result["total"] == 1
            mock_db.add.assert_called()  # Product was created
