"""
API Router Tests — Full integration with dependency overrides.

Uses httpx.AsyncClient with ASGITransport so all FastAPI middleware,
dependency injection, and error handling are exercised end-to-end.
ShopifyClient must be mocked for endpoints that trigger inventory sync.
"""

import uuid

import pytest
from httpx import AsyncClient

from tests.utils import (
    assert_product_out,
    assert_list_response,
    assert_adjust_response,
)

pytestmark = pytest.mark.asyncio


class TestListProducts:

    async def test_list_empty(self, client: AsyncClient, mock_shopify_client):
        """GET /inventory returns empty list when no products exist."""
        resp = await client.get("/inventory")
        assert resp.status_code == 200
        data = resp.json()
        assert_list_response(data, expected_total=0)
        assert data["items"] == []

    async def test_list_with_data(self, client: AsyncClient, test_products_batch, mock_shopify_client):
        """GET /inventory returns paginated products."""
        resp = await client.get("/inventory?page=1&page_size=5")
        assert resp.status_code == 200
        data = resp.json()
        assert_list_response(data, expected_total=15)
        assert len(data["items"]) == 5

    async def test_list_with_search(self, client: AsyncClient, test_products_batch, mock_shopify_client):
        """GET /inventory?search= filters by title or SKU."""
        resp = await client.get("/inventory?search=Product+1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    async def test_list_with_search_by_sku(self, client: AsyncClient, test_products_batch, mock_shopify_client):
        """GET /inventory?search= finds products via variant SKU."""
        resp = await client.get("/inventory?search=SKU-0005")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    async def test_list_with_filters(self, client: AsyncClient, test_products_batch, mock_shopify_client):
        """GET /inventory?status= filters correctly."""
        resp = await client.get("/inventory?status=active")
        assert resp.status_code == 200

    async def test_list_with_sorting(self, client: AsyncClient, test_products_batch, mock_shopify_client):
        """GET /inventory sorts by specified field."""
        resp = await client.get("/inventory?sort_by=title&sort_order=asc&page_size=5")
        assert resp.status_code == 200
        data = resp.json()
        titles = [item["title"] for item in data["items"]]
        assert titles == sorted(titles)

    async def test_list_page_size_validation(self, client: AsyncClient, mock_shopify_client):
        """GET /inventory rejects invalid page_size."""
        resp = await client.get("/inventory?page_size=200")
        assert resp.status_code == 422


class TestSearchProducts:

    async def test_search_endpoint(self, client: AsyncClient, test_products_batch, mock_shopify_client):
        """GET /inventory/search works like list with filters."""
        resp = await client.get("/inventory/search?search=Product")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    async def test_search_no_results(self, client: AsyncClient, mock_shopify_client):
        """GET /inventory/search with no matches returns empty."""
        resp = await client.get("/inventory/search?search=NONEXISTENT_XYZ")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []


class TestGetProduct:

    async def test_get_found(self, client: AsyncClient, test_product, mock_shopify_client):
        """GET /inventory/{id} returns the product."""
        resp = await client.get(f"/inventory/{test_product.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert_product_out(data, expected_title="Test Product")
        assert len(data["variants"]) >= 1

    async def test_get_not_found(self, client: AsyncClient, mock_shopify_client):
        """GET /inventory/{id} returns 404 for non-existent ID."""
        resp = await client.get(f"/inventory/{uuid.uuid4()}")
        assert resp.status_code == 404
        data = resp.json()
        assert "detail" in data

    async def test_get_invalid_uuid(self, client: AsyncClient, mock_shopify_client):
        """GET /inventory/{id} returns 422 for invalid UUID."""
        resp = await client.get("/inventory/not-a-uuid")
        assert resp.status_code == 422


class TestCreateProduct:

    async def test_create_minimal(self, client: AsyncClient, mock_shopify_client):
        """POST /inventory creates a product with just a title."""
        payload = {"title": "API Created Product"}
        resp = await client.post("/inventory", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert_product_out(data, expected_title="API Created Product")
        assert len(data["variants"]) == 0

    async def test_create_with_variants(self, client: AsyncClient, mock_shopify_client):
        """POST /inventory creates a product with variants."""
        payload = {
            "title": "Multi-Variant",
            "variants": [
                {"title": "Size S", "sku": "API-SKU-S", "price": 19.99, "inventory_quantity": 10},
                {"title": "Size M", "sku": "API-SKU-M", "price": 24.99, "inventory_quantity": 20},
            ],
        }
        resp = await client.post("/inventory", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["variants"]) == 2

    async def test_create_duplicate_sku(self, client: AsyncClient, test_product, mock_shopify_client):
        """POST /inventory with duplicate SKU returns 409."""
        payload = {
            "title": "Duplicate SKU",
            "variants": [{"title": "V1", "sku": "TEST-SKU-001"}],
        }
        resp = await client.post("/inventory", json=payload)
        assert resp.status_code == 409

    async def test_create_missing_title(self, client: AsyncClient, mock_shopify_client):
        """POST /inventory without title returns 422."""
        resp = await client.post("/inventory", json={})
        assert resp.status_code == 422

    async def test_create_invalid_status(self, client: AsyncClient, mock_shopify_client):
        """POST /inventory with invalid status returns 422."""
        payload = {"title": "Bad Status", "status": "invalid_status"}
        resp = await client.post("/inventory", json=payload)
        assert resp.status_code == 422


class TestUpdateProduct:

    async def test_update_title(self, client: AsyncClient, test_product, mock_shopify_client):
        """PUT /inventory/{id} updates title."""
        resp = await client.put(
            f"/inventory/{test_product.id}",
            json={"title": "Updated via API"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Updated via API"

    async def test_update_not_found(self, client: AsyncClient, mock_shopify_client):
        """PUT /inventory/{id} on non-existent ID returns 404."""
        resp = await client.put(f"/inventory/{uuid.uuid4()}", json={"title": "Nope"})
        assert resp.status_code == 404

    async def test_update_invalid_uuid(self, client: AsyncClient, mock_shopify_client):
        """PUT /inventory/{id} with invalid UUID returns 422."""
        resp = await client.put("/inventory/bad-uuid", json={"title": "Nope"})
        assert resp.status_code == 422

    async def test_update_empty_payload(self, client: AsyncClient, test_product, mock_shopify_client):
        """PUT /inventory/{id} with empty payload succeeds (no-op)."""
        resp = await client.put(f"/inventory/{test_product.id}", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test Product"


class TestDeleteProduct:

    async def test_delete_success(self, client: AsyncClient, test_product, mock_shopify_client):
        """DELETE /inventory/{id} returns success message."""
        resp = await client.delete(f"/inventory/{test_product.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "deleted successfully" in data["message"]

    async def test_delete_not_found(self, client: AsyncClient, mock_shopify_client):
        """DELETE /inventory/{id} on non-existent ID returns 404."""
        resp = await client.delete(f"/inventory/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_delete_then_get_returns_404(self, client: AsyncClient, test_product, mock_shopify_client):
        """After delete, GET returns 404."""
        await client.delete(f"/inventory/{test_product.id}")
        resp = await client.get(f"/inventory/{test_product.id}")
        assert resp.status_code == 404


class TestUpdateStock:

    async def test_increase_stock(self, client: AsyncClient, test_variant, mock_shopify_client):
        """POST /inventory/update-stock increases stock."""
        resp = await client.post(
            "/inventory/update-stock",
            json={"variant_id": str(test_variant.id), "quantity_change": 25},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert_adjust_response(data, expected_change=25)

    async def test_decrease_stock(self, client: AsyncClient, test_variant, mock_shopify_client):
        """POST /inventory/update-stock decreases stock."""
        resp = await client.post(
            "/inventory/update-stock",
            json={"variant_id": str(test_variant.id), "quantity_change": -30},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["quantity_change"] == -30
        assert data["quantity_after"] == 70

    async def test_insufficient_stock(self, client: AsyncClient, test_variant, mock_shopify_client):
        """POST /inventory/update-stock returns 400 when stock goes below zero."""
        resp = await client.post(
            "/inventory/update-stock",
            json={"variant_id": str(test_variant.id), "quantity_change": -999},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "insufficient" in str(data).lower()

    async def test_update_stock_variant_not_found(self, client: AsyncClient, mock_shopify_client):
        """POST /inventory/update-stock on non-existent variant returns 404."""
        resp = await client.post(
            "/inventory/update-stock",
            json={"variant_id": str(uuid.uuid4()), "quantity_change": 10},
        )
        assert resp.status_code == 404

    async def test_update_stock_zero_change(self, client: AsyncClient, test_variant, mock_shopify_client):
        """POST /inventory/update-stock with zero change returns 422."""
        resp = await client.post(
            "/inventory/update-stock",
            json={"variant_id": str(test_variant.id), "quantity_change": 0},
        )
        assert resp.status_code == 422

    async def test_update_stock_invalid_variant_id(self, client: AsyncClient, mock_shopify_client):
        """POST /inventory/update-stock with invalid UUID returns 422."""
        resp = await client.post(
            "/inventory/update-stock",
            json={"variant_id": "not-a-uuid", "quantity_change": 10},
        )
        assert resp.status_code == 422


class TestLowStock:

    async def test_get_low_stock_empty(self, client: AsyncClient, mock_shopify_client):
        """GET /inventory/low-stock returns empty when all stock is sufficient."""
        resp = await client.get("/inventory/low-stock?threshold=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    async def test_get_low_stock_with_items(
        self, client: AsyncClient, db_session, test_product, mock_shopify_client
    ):
        """GET /inventory/low-stock finds items below threshold."""
        from tests.fixtures import create_variant
        await create_variant(
            db_session, test_product.id,
            title="Low", sku="LOW-API",
            inventory_quantity=3, low_stock_threshold=10,
        )
        resp = await client.get("/inventory/low-stock?threshold=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    async def test_low_stock_default_threshold(self, client: AsyncClient, mock_shopify_client):
        """GET /inventory/low-stock uses default threshold of 10."""
        resp = await client.get("/inventory/low-stock")
        assert resp.status_code == 200

    async def test_low_stock_invalid_threshold(self, client: AsyncClient, mock_shopify_client):
        """GET /inventory/low-stock with negative threshold returns 422."""
        resp = await client.get("/inventory/low-stock?threshold=-1")
        assert resp.status_code == 422


class TestHistory:

    async def test_get_history_empty(self, client: AsyncClient, mock_shopify_client):
        """GET /inventory/history returns empty when no transactions."""
        resp = await client.get("/inventory/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    async def test_get_history_with_data(
        self, client: AsyncClient, test_variant, mock_shopify_client
    ):
        """GET /inventory/history returns transactions."""
        await client.post(
            "/inventory/update-stock",
            json={"variant_id": str(test_variant.id), "quantity_change": 15},
        )
        resp = await client.get("/inventory/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1

    async def test_get_history_filter_by_variant(
        self, client: AsyncClient, test_variant, mock_shopify_client
    ):
        """GET /inventory/history?variant_id= filters correctly."""
        await client.post(
            "/inventory/update-stock",
            json={"variant_id": str(test_variant.id), "quantity_change": 5},
        )
        resp = await client.get(f"/inventory/history?variant_id={test_variant.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    async def test_get_history_invalid_date(self, client: AsyncClient, mock_shopify_client):
        """GET /inventory/history with invalid date returns 422."""
        resp = await client.get("/inventory/history?date_from=not-a-date")
        assert resp.status_code == 422


class TestHealth:

    async def test_health_endpoint(self, client: AsyncClient, mock_shopify_client):
        """GET /health returns OK."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════
# Input Validation & Security Tests
# ═══════════════════════════════════════════════════════════════════

class TestInputValidation:

    async def test_invalid_uuid_returns_422(self, client: AsyncClient, mock_shopify_client):
        """All endpoints with UUID params reject invalid UUIDs with 422."""
        for method in ["get", "put", "delete"]:
            resp = await getattr(client, method)("/inventory/not-a-uuid")
            assert resp.status_code == 422

    async def test_invalid_payload_returns_422(self, client: AsyncClient, mock_shopify_client):
        """Endpoints reject invalid payloads with 422."""
        # Missing required title
        resp = await client.post("/inventory", json={})
        assert resp.status_code == 422

        # Missing required variant title
        resp = await client.post(
            "/inventory",
            json={"title": "Test", "variants": [{}]},
        )
        assert resp.status_code == 422

    async def test_title_max_length(self, client: AsyncClient, mock_shopify_client):
        """String fields enforce max_length constraints."""
        resp = await client.post("/inventory", json={"title": "A" * 300})
        assert resp.status_code == 422

    async def test_invalid_status_regex(self, client: AsyncClient, mock_shopify_client):
        """Status field enforces regex pattern (active|archived|draft)."""
        resp = await client.post(
            "/inventory",
            json={"title": "Test", "status": "invalid_status"},
        )
        assert resp.status_code == 422

    async def test_negative_stock_quantity(self, client: AsyncClient, mock_shopify_client):
        """Creating a variant with negative stock is rejected."""
        resp = await client.post(
            "/inventory",
            json={
                "title": "Test",
                "variants": [{"title": "V1", "inventory_quantity": -5}],
            },
        )
        assert resp.status_code == 422

    async def test_negative_price(self, client: AsyncClient, mock_shopify_client):
        """Creating a variant with negative price is rejected."""
        resp = await client.post(
            "/inventory",
            json={
                "title": "Test",
                "variants": [{"title": "V1", "price": -10}],
            },
        )
        assert resp.status_code == 422

    async def test_too_many_variants(self, client: AsyncClient, mock_shopify_client):
        """Creating a product with too many variants is rejected."""
        variants = [{"title": f"V{i}"} for i in range(25)]  # max is 20
        resp = await client.post(
            "/inventory",
            json={"title": "Too Many Variants", "variants": variants},
        )
        assert resp.status_code == 422

    async def test_sort_order_validation(self, client: AsyncClient, mock_shopify_client):
        """Sort order must be asc or desc."""
        resp = await client.get("/inventory?sort_order=invalid")
        assert resp.status_code == 422
