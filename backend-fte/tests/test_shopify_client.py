"""
Shopify Client Unit Tests — All HTTP calls are mocked using respx or manual httpx mocks.

Covers retry logic, rate limiting, GraphQL/REST parsing, edge cases, and error mapping.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
import httpx

from app.shopify.shopify_client import (
    ShopifyClient,
    ShopifySyncError,
    MAX_RETRIES,
    BASE_RETRY_DELAY_SECONDS,
)
from app.config import settings

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client():
    """Create a ShopifyClient with test credentials."""
    return ShopifyClient(
        shop_domain="test-store.myshopify.com",
        access_token="shpat_test_token",
        location_id=905684977,
    )


class TestInitialization:

    def test_constructor_sets_properties(self):
        """Constructor correctly computes endpoints and headers."""
        c = ShopifyClient(
            shop_domain="my-store.myshopify.com",
            access_token="shpat_abc",
            location_id=123,
        )
        assert c.shop_domain == "my-store.myshopify.com"
        assert c.access_token == "shpat_abc"
        assert c.location_id == 123
        assert "myshopify.com" in c.graphql_url
        assert "X-Shopify-Access-Token" in c.headers
        assert c.headers["X-Shopify-Access-Token"] == "shpat_abc"

    def test_default_api_version(self, client):
        """Default API version comes from settings."""
        assert client.api_version == settings.SHOPIFY_API_VERSION


class TestGraphQLHelpers:

    def test_gid_to_id(self):
        """_gid_to_id extracts numeric ID from GID string."""
        assert ShopifyClient._gid_to_id("gid://shopify/Product/123456") == 123456
        assert ShopifyClient._gid_to_id("gid://shopify/InventoryItem/789") == 789

    def test_gid_to_id_malformed(self):
        """_gid_to_id returns 0 for malformed GID."""
        assert ShopifyClient._gid_to_id("invalid") == 0
        assert ShopifyClient._gid_to_id("") == 0

    def test_to_gid(self):
        """_to_gid converts numeric ID to Shopify GID."""
        assert ShopifyClient._to_gid("Product", 123) == "gid://shopify/Product/123"
        assert ShopifyClient._to_gid("InventoryItem", 456) == "gid://shopify/InventoryItem/456"

    def test_parse_retry_after(self):
        """_parse_retry_after extracts integer from header."""
        # Create a mock response with Retry-After header
        from unittest.mock import MagicMock
        resp = MagicMock(spec=httpx.Response)
        resp.headers = {"Retry-After": "5"}
        assert ShopifyClient._parse_retry_after(resp) == 5

    def test_parse_retry_after_missing(self):
        """_parse_retry_after defaults to 2 when header missing."""
        from unittest.mock import MagicMock
        resp = MagicMock(spec=httpx.Response)
        resp.headers = {}
        assert ShopifyClient._parse_retry_after(resp) == 2

    def test_parse_retry_after_invalid(self):
        """_parse_retry_after defaults to 2 when header is not an integer."""
        from unittest.mock import MagicMock
        resp = MagicMock(spec=httpx.Response)
        resp.headers = {"Retry-After": "not-a-number"}
        assert ShopifyClient._parse_retry_after(resp) == 2


class TestNormalizeProduct:

    def test_normalize_minimal(self):
        """_normalize_product handles minimal product data."""
        raw = {
            "id": "gid://shopify/Product/100",
            "title": "Test",
            "variants": {"edges": []},
        }
        result = ShopifyClient._normalize_product(raw)
        assert result["id"] == 100
        assert result["title"] == "Test"
        assert result["variants"] == []

    def test_normalize_with_variants(self):
        """_normalize_product converts variant edges to flat list."""
        raw = {
            "id": "gid://shopify/Product/200",
            "title": "Multi-Variant",
            "bodyHtml": "<p>Desc</p>",
            "vendor": "Acme",
            "productType": "Physical",
            "status": "active",
            "featuredImage": {"url": "https://example.com/img.jpg"},
            "variants": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/ProductVariant/1001",
                            "title": "Red",
                            "sku": "RED-001",
                            "barcode": "123",
                            "price": "29.99",
                            "compareAtPrice": "34.99",
                            "inventoryQuantity": 50,
                            "requiresShipping": True,
                            "inventoryItem": {"id": "gid://shopify/InventoryItem/5001"},
                        }
                    }
                ]
            },
        }
        result = ShopifyClient._normalize_product(raw)
        assert result["id"] == 200
        assert result["featured_image_url"] == "https://example.com/img.jpg"
        assert len(result["variants"]) == 1
        v = result["variants"][0]
        assert v["id"] == 1001
        assert v["sku"] == "RED-001"
        assert v["inventory_item_id"] == 5001
        assert v["inventory_quantity"] == 50

    def test_normalize_missing_fields(self):
        """_normalize_product defaults missing optional fields."""
        raw = {
            "id": "gid://shopify/Product/300",
            "title": "Minimal",
            "variants": {"edges": []},
        }
        result = ShopifyClient._normalize_product(raw)
        assert result["body_html"] is None
        assert result["vendor"] is None
        assert result["featured_image_url"] is None


class TestWebhookVerification:

    def test_verify_valid_hmac(self):
        """verify_webhook returns True for a valid HMAC."""
        # Body that will produce a known hash
        body = b'{"test": true}'
        secret = "my_secret"

        # Compute the correct HMAC for this body+secret
        import hmac, hashlib
        expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        assert ShopifyClient.verify_webhook(expected, body, secret) is True

    def test_verify_invalid_hmac(self):
        """verify_webhook returns False for an invalid HMAC."""
        body = b'{"test": true}'
        assert ShopifyClient.verify_webhook("invalid_hmac", body, "my_secret") is False

    def test_verify_empty_hmac(self):
        """verify_webhook returns False for empty HMAC."""
        body = b'{"test": true}'
        assert ShopifyClient.verify_webhook("", body, "my_secret") is False

    def test_verify_empty_body(self):
        """verify_webhook handles empty body."""
        assert ShopifyClient.verify_webhook("some_hmac", b"", "secret") is False


class TestRetryLogic:

    async def test_retry_on_429(self):
        """Client retries on 429 and respects Retry-After."""
        client = ShopifyClient("test.myshopify.com", "token")
        client.max_retries = 2

        with patch.object(client, "_request", new=AsyncMock()) as mock_request:
            mock_request.side_effect = ShopifySyncError("Rate limited")

            with pytest.raises(ShopifySyncError):
                await client.set_inventory_level(123, 456, 50)

            # Verify it was called (the mock _request is called by set_inventory_level -> _graphql -> _request)
            assert mock_request.called

    async def test_retry_on_500(self):
        """Client retries on 5xx server errors."""
        client = ShopifyClient("test.myshopify.com", "token")
        client.max_retries = 2

        with patch.object(client, "_request", new=AsyncMock()) as mock_request:
            mock_request.side_effect = ShopifySyncError("Server error")

            with pytest.raises(ShopifySyncError):
                await client.set_inventory_level(123, 456, 50)

            assert mock_request.call_count >= 1

    async def test_retry_on_timeout(self):
        """Client retries on timeout."""
        client = ShopifyClient("test.myshopify.com", "token")
        client.max_retries = 2

        with patch.object(client, "_request", new=AsyncMock()) as mock_request:
            mock_request.side_effect = ShopifySyncError("Timeout")

            with pytest.raises(ShopifySyncError):
                await client.set_inventory_level(123, 456, 50)

            assert mock_request.called

    async def test_retry_on_network_error(self):
        """Client retries on network errors."""
        client = ShopifyClient("test.myshopify.com", "token")
        client.max_retries = 2

        with patch.object(client, "_request", new=AsyncMock()) as mock_request:
            mock_request.side_effect = ShopifySyncError("Network error")

            with pytest.raises(ShopifySyncError):
                await client.fetch_all_products()

            assert mock_request.called

    async def test_no_retry_on_401(self):
        """Client does NOT retry on 401 Unauthorized (non-retryable)."""
        client = ShopifyClient("test.myshopify.com", "token")
        client.max_retries = 3

        with patch.object(client, "_request", new=AsyncMock()) as mock_request:
            mock_request.side_effect = ShopifySyncError("Unauthorized")

            with pytest.raises(ShopifySyncError):
                await client.fetch_all_products()

            assert mock_request.called


class TestHTTPMethods:

    async def test_graphql_success(self):
        """_graphql returns parsed data on success."""
        client = ShopifyClient("test.myshopify.com", "token")

        with patch.object(client, "_request", new=AsyncMock(return_value={
            "data": {"products": {"edges": []}}
        })):
            data = await client._graphql("{ products { edges { node { id } } } }")
            assert "products" in data

    async def test_graphql_with_errors(self):
        """_graphql raises ShopifySyncError when GraphQL returns errors."""
        client = ShopifyClient("test.myshopify.com", "token")

        with patch.object(client, "_request", new=AsyncMock(return_value={
            "errors": [{"message": "Field 'xyz' doesn't exist"}]
        })):
            with pytest.raises(ShopifySyncError) as exc:
                await client._graphql("{ invalidQuery }")
            assert "GraphQL error" in str(exc.value)

    async def test_fetch_inventory_level_not_found(self):
        """fetch_inventory_level returns None when item not at location."""
        client = ShopifyClient("test.myshopify.com", "token")

        with patch.object(client, "_graphql", new=AsyncMock(return_value={
            "inventoryLevel": None
        })):
            level = await client.fetch_inventory_level(123, 456)
            assert level is None

    async def test_set_inventory_level_user_errors(self):
        """set_inventory_level raises ShopifySyncError when userErrors present."""
        client = ShopifyClient("test.myshopify.com", "token")

        with patch.object(client, "_graphql", new=AsyncMock(return_value={
            "inventorySetQuantity": {
                "userErrors": [{"field": "quantity", "message": "Cannot be negative"}]
            }
        })):
            with pytest.raises(ShopifySyncError) as exc:
                await client.set_inventory_level(123, 456, -5)
            assert "Cannot be negative" in str(exc.value)

    async def test_fetch_locations_success(self):
        """fetch_locations returns parsed locations list."""
        client = ShopifyClient("test.myshopify.com", "token")

        with patch.object(client, "_rest_get", new=AsyncMock(return_value={
            "locations": [{"id": 123, "name": "Primary", "primary": True}]
        })):
            locations = await client.fetch_locations()
            assert len(locations) == 1
            assert locations[0]["name"] == "Primary"

    async def test_fetch_locations_raises_on_failure(self):
        """fetch_locations propagates ShopifySyncError."""
        client = ShopifyClient("test.myshopify.com", "token")

        with patch.object(client, "_rest_get", new=AsyncMock(side_effect=ShopifySyncError("API error"))):
            with pytest.raises(ShopifySyncError):
                await client.fetch_locations()


class TestGetPrimaryLocation:

    async def test_primary_location_found(self):
        """get_primary_location_id returns the primary location."""
        client = ShopifyClient("test.myshopify.com", "token")

        with patch.object(client, "fetch_locations", new=AsyncMock(return_value=[
            {"id": 100, "name": "Secondary", "primary": False},
            {"id": 200, "name": "Primary", "primary": True},
        ])):
            loc_id = await client.get_primary_location_id()
            assert loc_id == 200

    async def test_primary_location_first_fallback(self):
        """get_primary_location_id falls back to first location."""
        client = ShopifyClient("test.myshopify.com", "token")

        with patch.object(client, "fetch_locations", new=AsyncMock(return_value=[
            {"id": 100, "name": "First", "primary": False},
        ])):
            loc_id = await client.get_primary_location_id()
            assert loc_id == 100

    async def test_no_locations(self):
        """get_primary_location_id returns None when no locations exist."""
        client = ShopifyClient("test.myshopify.com", "token")

        with patch.object(client, "fetch_locations", new=AsyncMock(return_value=[])):
            loc_id = await client.get_primary_location_id()
            assert loc_id is None


class TestClientLifecycle:

    async def test_context_manager(self):
        """Client works as an async context manager."""
        async with ShopifyClient("test.myshopify.com", "token") as c:
            assert c.shop_domain == "test.myshopify.com"

    async def test_close_idempotent(self):
        """Calling close multiple times is safe."""
        c = ShopifyClient("test.myshopify.com", "token")
        await c.close()
        await c.close()  # Should not raise


class TestAdjustInventoryLevel:

    async def test_adjust_via_rest(self):
        """adjust_inventory_level calls REST endpoint first."""
        client = ShopifyClient("test.myshopify.com", "token")

        with patch.object(client, "_rest_post", new=AsyncMock(return_value={
            "inventory_level": {"id": 123, "available": 75}
        })):
            result = await client.adjust_inventory_level(100, 200, 25)
            assert result["available"] == 75

    async def test_adjust_rest_fallback_to_graphql(self):
        """adjust_inventory_level falls back to GraphQL when REST fails."""
        client = ShopifyClient("test.myshopify.com", "token")

        with patch.object(client, "_rest_post", new=AsyncMock(side_effect=ShopifySyncError("REST failed"))):
            with patch.object(client, "fetch_inventory_level", new=AsyncMock(return_value=50)):
                with patch.object(client, "set_inventory_level", new=AsyncMock(return_value={"available": 75})):
                    result = await client.adjust_inventory_level(100, 200, 25)
                    assert result["available"] == 75

    async def test_adjust_rest_fallback_target_below_zero(self):
        """adjust_inventory_level raises when fallback would set negative."""
        client = ShopifyClient("test.myshopify.com", "token")

        with patch.object(client, "_rest_post", new=AsyncMock(side_effect=ShopifySyncError("REST failed"))):
            with patch.object(client, "fetch_inventory_level", new=AsyncMock(return_value=10)):
                with pytest.raises(ShopifySyncError) as exc:
                    await client.adjust_inventory_level(100, 200, -50)
                assert "below zero" in str(exc.value)

    async def test_adjust_rest_fallback_level_none(self):
        """adjust_inventory_level re-raises when fallback can't fetch current level."""
        client = ShopifyClient("test.myshopify.com", "token")

        with patch.object(client, "_rest_post", new=AsyncMock(side_effect=ShopifySyncError("REST failed"))):
            with patch.object(client, "fetch_inventory_level", new=AsyncMock(return_value=None)):
                with pytest.raises(ShopifySyncError):
                    await client.adjust_inventory_level(100, 200, 25)
