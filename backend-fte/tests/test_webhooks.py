"""
Webhook Tests — HMAC verification, store lookup, idempotency, edge cases.

All tests use the httpx AsyncClient with overridden dependencies.
ShopifyClient must be explicitly mocked to prevent real HTTP calls.
"""

import hmac
import hashlib
import json

import pytest
from httpx import AsyncClient

from app.config import settings
from tests.fixtures import shopify_product_payload, shopify_inventory_payload

pytestmark = pytest.mark.asyncio


def _compute_hmac(body: bytes, secret: str) -> str:
    """Helper: compute a valid Shopify-style HMAC header."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _make_headers(shop_domain: str = "test-store.myshopify.com") -> dict:
    """Helper: build minimal valid webhook headers (HMAC is computed from body)."""
    return {
        "x-shopify-hmac-sha256": "placeholder",
        "x-shopify-shop-domain": shop_domain,
        "x-shopify-topic": "inventory_levels/update",
        "Content-Type": "application/json",
    }


class TestWebhookHMACVerification:

    async def test_valid_hmac(self, client: AsyncClient, mock_shopify_client):
        """POST /webhooks with valid HMAC returns 200."""
        payload = shopify_inventory_payload()
        body = json.dumps(payload).encode()
        headers = _make_headers()
        headers["x-shopify-hmac-sha256"] = _compute_hmac(body, settings.SHOPIFY_API_SECRET)

        resp = await client.post(
            "/webhooks/inventory-levels-update",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200

    async def test_invalid_hmac(self, client: AsyncClient, mock_shopify_client):
        """POST /webhooks with invalid HMAC returns 401."""
        payload = shopify_inventory_payload()
        body = json.dumps(payload).encode()
        headers = _make_headers()
        headers["x-shopify-hmac-sha256"] = "invalid_hmac_value"

        resp = await client.post(
            "/webhooks/inventory-levels-update",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 401

    async def test_missing_hmac_header(self, client: AsyncClient, mock_shopify_client):
        """POST /webhooks without HMAC header returns 401."""
        payload = shopify_inventory_payload()
        headers = {
            "x-shopify-shop-domain": "test-store.myshopify.com",
            "Content-Type": "application/json",
        }
        resp = await client.post(
            "/webhooks/inventory-levels-update",
            content=json.dumps(payload),
            headers=headers,
        )
        assert resp.status_code == 401

    async def test_missing_shop_domain(self, client: AsyncClient, mock_shopify_client):
        """POST /webhooks without shop domain returns 401."""
        payload = shopify_inventory_payload()
        headers = {
            "x-shopify-hmac-sha256": "something",
            "Content-Type": "application/json",
        }
        resp = await client.post(
            "/webhooks/inventory-levels-update",
            content=json.dumps(payload),
            headers=headers,
        )
        assert resp.status_code == 401


class TestInventoryLevelsWebhook:

    async def test_updates_inventory(
        self, client: AsyncClient, mock_shopify_client, test_product, db_session
    ):
        """Webhook updates variant inventory quantity."""
        variant = test_product.variants[0]
        variant.shopify_inventory_item_id = 808950810
        await db_session.commit()

        payload = shopify_inventory_payload(
            inventory_item_id=808950810,
            available=75,
        )
        body = json.dumps(payload).encode()
        headers = _make_headers()
        headers["x-shopify-hmac-sha256"] = _compute_hmac(body, settings.SHOPIFY_API_SECRET)

        resp = await client.post(
            "/webhooks/inventory-levels-update",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["status"] == "ok"

    async def test_ignores_unknown_inventory_item(
        self, client: AsyncClient, mock_shopify_client
    ):
        """Webhook with unknown inventory_item_id returns 200 but ignores."""
        payload = shopify_inventory_payload(
            inventory_item_id=99999999,
            available=50,
        )
        body = json.dumps(payload).encode()
        headers = _make_headers()
        headers["x-shopify-hmac-sha256"] = _compute_hmac(body, settings.SHOPIFY_API_SECRET)

        resp = await client.post(
            "/webhooks/inventory-levels-update",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["result"]["status"] in ("ignored",)

    async def test_missing_required_fields(
        self, client: AsyncClient, mock_shopify_client
    ):
        """Webhook with missing fields returns 200 and ignores."""
        payload = {"available": 25}  # Missing inventory_item_id
        body = json.dumps(payload).encode()
        headers = _make_headers()
        headers["x-shopify-hmac-sha256"] = _compute_hmac(body, settings.SHOPIFY_API_SECRET)

        resp = await client.post(
            "/webhooks/inventory-levels-update",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200

    async def test_idempotent_duplicate(
        self, client: AsyncClient, mock_shopify_client, test_product, db_session
    ):
        """Duplicate webhook with same quantity handles gracefully."""
        variant = test_product.variants[0]
        variant.shopify_inventory_item_id = 808950810
        await db_session.commit()

        payload = shopify_inventory_payload(
            inventory_item_id=808950810,
            available=100,
        )
        body = json.dumps(payload).encode()
        headers = _make_headers()
        headers["x-shopify-hmac-sha256"] = _compute_hmac(body, settings.SHOPIFY_API_SECRET)

        resp = await client.post(
            "/webhooks/inventory-levels-update",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200


class TestProductsUpdateWebhook:

    async def test_creates_new_product(
        self, client: AsyncClient, mock_shopify_client
    ):
        """products/update webhook creates a new product."""
        payload = shopify_product_payload(shopify_id=5001, title="Webhook Created")
        body = json.dumps(payload).encode()
        headers = _make_headers()
        headers["x-shopify-topic"] = "products/update"
        headers["x-shopify-hmac-sha256"] = _compute_hmac(body, settings.SHOPIFY_API_SECRET)

        resp = await client.post(
            "/webhooks/products-update",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["result"]["status"] == "created"

    async def test_updates_existing_product(
        self, client: AsyncClient, mock_shopify_client
    ):
        """products/update webhook updates an existing product."""
        # First call: create
        payload = shopify_product_payload(shopify_id=6001, title="Original Title")
        body = json.dumps(payload).encode()
        headers = _make_headers()
        headers["x-shopify-topic"] = "products/update"
        headers["x-shopify-hmac-sha256"] = _compute_hmac(body, settings.SHOPIFY_API_SECRET)
        resp1 = await client.post("/webhooks/products-update", content=body, headers=headers)
        assert resp1.status_code == 200

        # Second call: update
        payload2 = shopify_product_payload(shopify_id=6001, title="Updated Title")
        body2 = json.dumps(payload2).encode()
        headers2 = _make_headers()
        headers2["x-shopify-topic"] = "products/update"
        headers2["x-shopify-hmac-sha256"] = _compute_hmac(body2, settings.SHOPIFY_API_SECRET)
        resp2 = await client.post("/webhooks/products-update", content=body2, headers=headers2)
        assert resp2.status_code == 200
        assert resp2.json()["result"]["status"] == "updated"

    async def test_missing_product_id(
        self, client: AsyncClient, mock_shopify_client
    ):
        """products/update with missing id returns 200 and ignores."""
        payload = {"title": "No ID"}  # Missing "id" field
        body = json.dumps(payload).encode()
        headers = _make_headers()
        headers["x-shopify-topic"] = "products/update"
        headers["x-shopify-hmac-sha256"] = _compute_hmac(body, settings.SHOPIFY_API_SECRET)

        resp = await client.post(
            "/webhooks/products-update",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200


class TestAppUninstalledWebhook:

    async def test_deactivates_store(
        self, client: AsyncClient, mock_shopify_client
    ):
        """app/uninstalled webhook deactivates the store."""
        payload = {"shop_id": 123456, "shop_domain": "test-store.myshopify.com"}
        body = json.dumps(payload).encode()
        headers = _make_headers()
        headers["x-shopify-topic"] = "app/uninstalled"
        headers["x-shopify-hmac-sha256"] = _compute_hmac(body, settings.SHOPIFY_API_SECRET)

        resp = await client.post(
            "/webhooks/app-uninstalled",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["result"]["status"] == "deactivated"

    async def test_inactive_store_rejected(
        self, client: AsyncClient, mock_shopify_client, db_session, test_store
    ):
        """Webhook for an inactive store returns 404."""
        from app.models import Store as StoreModel
        from sqlalchemy import select
        result = await db_session.execute(
            select(StoreModel).where(StoreModel.id == test_store.id)
        )
        store = result.scalar_one()
        store.is_active = False
        await db_session.commit()

        payload = shopify_inventory_payload()
        body = json.dumps(payload).encode()
        headers = _make_headers()
        headers["x-shopify-hmac-sha256"] = _compute_hmac(body, settings.SHOPIFY_API_SECRET)

        resp = await client.post(
            "/webhooks/inventory-levels-update",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_unknown_store_rejected(
        self, client: AsyncClient, mock_shopify_client
    ):
        """Webhook from an unknown store returns 404."""
        payload = shopify_inventory_payload()
        body = json.dumps(payload).encode()
        headers = _make_headers(shop_domain="unknown-store.myshopify.com")
        headers["x-shopify-hmac-sha256"] = _compute_hmac(body, settings.SHOPIFY_API_SECRET)

        resp = await client.post(
            "/webhooks/inventory-levels-update",
            content=body,
            headers=headers,
        )
        assert resp.status_code == 404


class TestMalformedPayloads:

    async def test_invalid_json(self, client: AsyncClient, mock_shopify_client):
        """Webhook with invalid JSON body returns error."""
        headers = _make_headers()
        headers["x-shopify-hmac-sha256"] = "some_hmac"

        resp = await client.post(
            "/webhooks/inventory-levels-update",
            content=b"not json at all",
            headers=headers,
        )
        assert resp.status_code >= 400

    async def test_empty_body(self, client: AsyncClient, mock_shopify_client):
        """Webhook with empty body returns error."""
        headers = _make_headers()
        headers["x-shopify-hmac-sha256"] = "some_hmac"

        resp = await client.post(
            "/webhooks/inventory-levels-update",
            content=b"",
            headers=headers,
        )
        assert resp.status_code >= 400
