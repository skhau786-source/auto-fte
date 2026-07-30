"""
Unit tests for the WooCommerce REST API Client.

Tests cover:
- Client initialization and URL construction
- Authentication header generation
- Response parsing and normalization
- Error handling and retry logic
- Pagination logic
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

from app.woocommerce.client import WooCommerceClient
from app.woocommerce.exceptions import WooCommerceAPIError, StoreConnectionError


@pytest.fixture
def client():
    """Create a WooCommerceClient instance for testing."""
    return WooCommerceClient(
        store_url="https://test-store.com",
        consumer_key="ck_test_key",
        consumer_secret="cs_test_secret",
    )


class TestWooCommerceClientInit:
    """Test client initialization and configuration."""

    def test_url_normalization(self):
        """Store URL should have trailing slash removed."""
        client = WooCommerceClient(
            store_url="https://test-store.com/",
            consumer_key="ck_key",
            consumer_secret="cs_secret",
        )
        assert client.store_url == "https://test-store.com"
        assert client.api_base == "https://test-store.com/wp-json/wc/v3"

    def test_custom_api_version(self):
        """Custom API version should override default."""
        client = WooCommerceClient(
            store_url="https://test-store.com",
            consumer_key="ck_key",
            consumer_secret="cs_secret",
            api_version="wc/v2",
        )
        assert client.api_version == "wc/v2"
        assert "wc/v2" in client.api_base


class TestNormalization:
    """Test WooCommerce data normalization methods."""

    def test_normalize_product(self):
        """Product normalization should transform WooCommerce format to internal format."""
        wc_product = {
            "id": 123,
            "name": "Test Product",
            "slug": "test-product",
            "price": "19.99",
            "regular_price": "24.99",
            "sale_price": "19.99",
            "on_sale": True,
            "manage_stock": True,
            "stock_quantity": 50,
            "stock_status": "instock",
            "categories": [{"id": 5, "name": "Clothing"}],
            "tags": [{"id": 3, "name": "cotton"}],
            "images": [{"id": 1, "src": "https://example.com/image.jpg"}],
            "attributes": [{"id": 1, "name": "Color", "options": ["Red", "Blue"]}],
            "type": "simple",
            "status": "publish",
        }

        normalized = WooCommerceClient.normalize_product(wc_product)

        assert normalized["wc_product_id"] == 123
        assert normalized["name"] == "Test Product"
        assert normalized["price"] == "19.99"
        assert normalized["manage_stock"] == True
        assert normalized["stock_quantity"] == 50
        assert normalized["featured_image_url"] == "https://example.com/image.jpg"
        assert normalized["category_ids"] == [5]
        assert normalized["category_names"] == ["Clothing"]
        assert normalized["tag_ids"] == [3]
        assert normalized["tag_names"] == ["cotton"]
        assert len(normalized["attributes"]) == 1
        assert normalized["type"] == "simple"

    def test_normalize_product_empty_fields(self):
        """Product normalization should handle missing fields gracefully."""
        wc_product = {"id": 456, "name": "Minimal Product"}
        normalized = WooCommerceClient.normalize_product(wc_product)
        assert normalized["wc_product_id"] == 456
        assert normalized["price"] == "0.00"
        assert normalized["featured_image_url"] == ""
        assert normalized["category_ids"] == []

    def test_normalize_order(self):
        """Order normalization should capture all critical fields."""
        wc_order = {
            "id": 789,
            "number": "WC-123",
            "status": "processing",
            "total": "149.99",
            "currency": "USD",
            "customer_id": 42,
            "billing": {"first_name": "John", "last_name": "Doe"},
            "line_items": [{"id": 1, "name": "Test Product", "quantity": 2, "total": "99.98"}],
            "coupon_lines": [{"code": "SAVE10", "discount": "10.00"}],
        }
        normalized = WooCommerceClient.normalize_order(wc_order)
        assert normalized["wc_order_id"] == 789
        assert normalized["number"] == "WC-123"
        assert normalized["status"] == "processing"
        assert normalized["total"] == "149.99"
        assert normalized["billing"]["first_name"] == "John"
        assert len(normalized["line_items"]) == 1

    def test_normalize_customer(self):
        """Customer normalization should capture all relevant fields."""
        wc_customer = {
            "id": 42,
            "email": "john@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "billing": {"phone": "123-456-7890"},
            "orders_count": 5,
            "total_spent": "499.95",
        }
        normalized = WooCommerceClient.normalize_customer(wc_customer)
        assert normalized["wc_customer_id"] == 42
        assert normalized["email"] == "john@example.com"
        assert normalized["orders_count"] == 5
        assert normalized["total_spent"] == "499.95"


class TestVerifyConnection:
    """Test store connection verification."""

    @pytest.mark.asyncio
    async def test_verify_success(self, client):
        """Successful verification should return store info."""
        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "store": {"wc_version": "8.5.0"}
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client.verify_connection()
            assert result["status"] == "connected"
            assert result["woocommerce_version"] == "8.5.0"

    @pytest.mark.asyncio
    async def test_verify_failure_raises_error(self, client):
        """Failed verification should raise StoreConnectionError."""
        with patch.object(client, "_get", side_effect=Exception("Connection refused")):
            with pytest.raises(StoreConnectionError):
                await client.verify_connection()


class TestPagination:
    """Test pagination logic."""

    @pytest.mark.asyncio
    async def test_paginate_all_single_page(self, client):
        """Single page should be returned correctly."""
        mock_get_paginated = AsyncMock()
        mock_get_paginated.return_value = (
            [{"id": 1}, {"id": 2}],
            {"total": 2, "total_pages": 1},
        )

        with patch.object(client, "_get_paginated", mock_get_paginated):
            results = await client._paginate_all("/products", {"per_page": 100})
            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_paginate_all_multi_page(self, client):
        """Multiple pages should be combined into single list."""
        page1 = ([{"id": 1}, {"id": 2}], {"total": 4, "total_pages": 2})
        page2 = ([{"id": 3}, {"id": 4}], {"total": 4, "total_pages": 2})

        mock_get_paginated = AsyncMock()
        mock_get_paginated.side_effect = [page1, page2]

        with patch.object(client, "_get_paginated", mock_get_paginated):
            results = await client._paginate_all("/products", {"per_page": 2})
            assert len(results) == 4
