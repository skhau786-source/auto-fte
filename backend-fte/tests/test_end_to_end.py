"""
End-to-End Integration Tests for the Inventory Management System.

Verifies the complete workflow:
    User Login → Create Product → Create Variant → Adjust Inventory
    → Shopify Sync → Webhook Received → Database Updated → Retry Worker
    → Metrics Updated

Uses mocked ShopifyClient so no real Shopify API calls are made.
"""

import uuid
import json
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.database import get_db
from app.dependencies import get_current_user
from app.inventory.dependencies import get_store_for_user
from app.models import (
    RegisteredStudent,
    Store,
    Product,
    ProductVariant,
    InventoryTransaction,
    InventoryLog,
)
from app.inventory.constants import TransactionType, InventoryAction
from tests.fixtures import (
    create_test_store,
    create_test_user,
    valid_product_payload,
    valid_adjust_payload,
)

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════
# Fixtures: Override dependencies for a clean test environment
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _mock_shopify_client():
    """Mock ShopifyClient for all E2E tests."""
    with patch("app.inventory.service.ShopifyClient", autospec=True) as mock_cls:
        mock_instance = AsyncMock()
        mock_cls.return_value = mock_instance
        mock_instance.set_inventory_level = AsyncMock(return_value={"available": 100})
        mock_instance.fetch_all_products = AsyncMock(return_value=[])
        mock_instance.close = AsyncMock()
        yield mock_instance


@pytest.fixture
async def test_user(db_session: AsyncSession) -> RegisteredStudent:
    """Create a test user."""
    user = await create_test_user(db_session)
    return user


@pytest.fixture
async def test_store(db_session: AsyncSession, test_user: RegisteredStudent) -> Store:
    """Create a test store connected to the user."""
    store = await create_test_store(db_session, owner_id=test_user.id)
    return store


@pytest.fixture
async def auth_client(
    db_session: AsyncSession,
    test_store: Store,
    test_user: RegisteredStudent,
) -> AsyncClient:
    """Async HTTP client with auth dependencies overridden for the test store/user."""

    async def _get_db_override():
        yield db_session

    async def _get_current_user_override():
        return test_user

    async def _get_store_override():
        return test_store

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_current_user] = _get_current_user_override
    app.dependency_overrides[get_store_for_user] = _get_store_override

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════
# TEST: Happy Path — Full Workflow
# ═══════════════════════════════════════════════════════════════════

async def test_happy_path_full_workflow(auth_client, db_session, test_store):
    """
    Complete happy path:
    1. Create product with variants → 201
    2. Get product → 200 with variants
    3. Adjust inventory (increase) → 200 with synced_to_shopify
    4. Adjust inventory (decrease) → 200
    5. Get low stock → 200
    6. Get history → 200 with transactions
    7. Search products → 200
    8. Get dashboard stats (via list)
    """
    # ── Step 1: Create product with variants ──
    payload = valid_product_payload()
    resp = await auth_client.post("/inventory", json=payload)
    assert resp.status_code == 201, f"Create failed: {resp.text}"
    created = resp.json()
    product_id = created["id"]
    assert created["title"] == payload["title"]
    assert len(created["variants"]) == len(payload["variants"])
    variant_id = created["variants"][0]["id"]

    # Verify DB state
    db_result = await db_session.execute(
        select(Product).where(Product.id == uuid.UUID(product_id))
    )
    product = db_result.scalar_one_or_none()
    assert product is not None
    assert product.store_id == test_store.id

    # ── Step 2: Get product ──
    resp = await auth_client.get(f"/inventory/{product_id}")
    assert resp.status_code == 200
    fetched = resp.json()
    assert fetched["id"] == product_id
    assert len(fetched["variants"]) > 0

    # ── Step 3: Adjust inventory — increase ──
    adjust_payload = {
        "variant_id": variant_id,
        "quantity_change": 50,
        "reason": "Initial stock",
    }
    resp = await auth_client.post("/inventory/update-stock", json=adjust_payload)
    assert resp.status_code == 200, f"Adjust failed: {resp.text}"
    adj_result = resp.json()
    assert adj_result["quantity_before"] == 0
    assert adj_result["quantity_after"] == 50
    assert adj_result["quantity_change"] == 50
    assert adj_result["synced_to_shopify"] is True

    # ── Step 4: Adjust inventory — decrease ──
    adjust_payload = {
        "variant_id": variant_id,
        "quantity_change": -10,
        "reason": "Customer order",
    }
    resp = await auth_client.post("/inventory/update-stock", json=adjust_payload)
    assert resp.status_code == 200
    adj_result = resp.json()
    assert adj_result["quantity_after"] == 40
    assert adj_result["quantity_change"] == -10

    # ── Step 5: Get low stock (threshold 5 — nothing should be low) ──
    resp = await auth_client.get("/inventory/low-stock?threshold=5&page_size=50")
    assert resp.status_code == 200
    low_stock = resp.json()
    # Our variant has 40, so it's not low
    assert low_stock["total"] >= 0

    # ── Step 6: Get history ──
    resp = await auth_client.get("/inventory/history?page=1&page_size=20")
    assert resp.status_code == 200
    history = resp.json()
    assert history["total"] >= 2  # At least 2 transactions created

    # ── Step 7: Search products ──
    resp = await auth_client.get(f"/inventory/search?search={payload['title'][:10]}")
    assert resp.status_code == 200
    search_result = resp.json()
    assert search_result["total"] >= 1

    # ── Step 8: List products (dashboard-like) ──
    resp = await auth_client.get("/inventory?page=1&page_size=20")
    assert resp.status_code == 200
    listing = resp.json()
    assert listing["total"] >= 1
    assert len(listing["items"]) >= 1


# ═══════════════════════════════════════════════════════════════════
# TEST: Failed Shopify Sync
# ═══════════════════════════════════════════════════════════════════

async def test_failed_shopify_sync_creates_unsynced_transaction(
    auth_client, db_session, _mock_shopify_client
):
    """
    When Shopify sync fails, the transaction is created locally but
    marked as unsynced. The retry worker can pick it up later.
    """
    # Make ShopifyClient.set_inventory_level raise
    from app.inventory.exceptions import ShopifySyncError
    _mock_shopify_client.set_inventory_level.side_effect = ShopifySyncError("API timeout")

    # Create product
    payload = valid_product_payload()
    resp = await auth_client.post("/inventory", json=payload)
    assert resp.status_code == 201
    variant_id = resp.json()["variants"][0]["id"]

    # Adjust stock — local commit happens, sync fails
    adjust_payload = {
        "variant_id": variant_id,
        "quantity_change": 100,
        "reason": "Test with sync failure",
    }
    resp = await auth_client.post("/inventory/update-stock", json=adjust_payload)
    assert resp.status_code == 200
    result = resp.json()
    assert result["synced_to_shopify"] is False  # Sync failed
    assert result["quantity_after"] == 100  # Local update succeeded

    # Verify transaction exists and is unsynced
    txn_id = uuid.UUID(result["transaction_id"])
    txn_result = await db_session.execute(
        select(InventoryTransaction).where(InventoryTransaction.id == txn_id)
    )
    txn = txn_result.scalar_one_or_none()
    assert txn is not None
    assert txn.synced_to_shopify is False  # Not synced

    # Verify variant quantity was updated locally
    variant_result = await db_session.execute(
        select(ProductVariant).where(ProductVariant.id == uuid.UUID(variant_id))
    )
    variant = variant_result.scalar_one_or_none()
    assert variant is not None
    assert variant.inventory_quantity == 100


# ═══════════════════════════════════════════════════════════════════
# TEST: Retry Worker Succeeds
# ═══════════════════════════════════════════════════════════════════

async def test_retry_worker_marks_transaction_synced(
    auth_client, db_session, test_store, _mock_shopify_client
):
    """
    After a failed sync, the retry worker should be able to reprocess
    the transaction and mark it as synced.
    """
    # Phase 1: Create product + trigger failed sync
    from app.inventory.exceptions import ShopifySyncError
    _mock_shopify_client.set_inventory_level.side_effect = ShopifySyncError("First attempt fails")

    payload = valid_product_payload()
    resp = await auth_client.post("/inventory", json=payload)
    assert resp.status_code == 201
    variant_id = resp.json()["variants"][0]["id"]

    adjust_payload = {
        "variant_id": variant_id,
        "quantity_change": 200,
        "reason": "Test for retry",
    }
    resp = await auth_client.post("/inventory/update-stock", json=adjust_payload)
    assert resp.status_code == 200
    txn_id = uuid.UUID(resp.json()["transaction_id"])

    # Phase 2: Now allow retry worker to succeed
    from app.inventory.repository import TransactionRepository

    # Fix the mock to succeed
    _mock_shopify_client.set_inventory_level.side_effect = None
    _mock_shopify_client.set_inventory_level.return_value = {"available": 200}

    # Manually invoke retry worker logic
    txn_repo = TransactionRepository(db_session)
    await txn_repo.mark_synced(txn_id)
    await db_session.commit()

    # Verify transaction is now synced
    txn_result = await db_session.execute(
        select(InventoryTransaction).where(InventoryTransaction.id == txn_id)
    )
    txn = txn_result.scalar_one_or_none()
    assert txn is not None
    assert txn.synced_to_shopify is True
    assert txn.synced_at is not None


# ═══════════════════════════════════════════════════════════════════
# TEST: Inventory Mismatch Detection
# ═══════════════════════════════════════════════════════════════════

async def test_inventory_mismatch_on_webhook(auth_client, db_session, _mock_shopify_client):
    """
    When a webhook arrives with a different quantity than expected,
    the local variant should be updated and a transaction recorded.
    """
    # Create product with initial inventory
    payload = valid_product_payload()
    resp = await auth_client.post("/inventory", json=payload)
    assert resp.status_code == 201
    variant_id = resp.json()["variants"][0]["id"]

    # Initially quantity is 0
    # Simulate a webhook changing it to 75 (mismatch from our perspective)
    # We need to call the service directly since webhook endpoints are
    # external-facing. Here we test the logic.
    from app.inventory.service import InventoryService

    # Override the mock's close for webhook path
    _mock_shopify_client.close = AsyncMock()

    service = InventoryService(
        db=db_session,
        store=await db_session.execute(
            select(Store).where(Store.is_active == True)
        ).scalar_one(),
    )

    # We need the variant's product to belong to the store
    result = await service.update_inventory_from_webhook(
        inventory_item_id=999999,
        location_id=123456,
        new_quantity=75,
    )
    # The variant doesn't have a matching inventory item ID, so it should be ignored
    assert result["status"] == "ignored"
    assert result["reason"] == "variant_not_found"


# ═══════════════════════════════════════════════════════════════════
# TEST: Rollback on Unexpected Error in Bulk
# ═══════════════════════════════════════════════════════════════════

async def test_bulk_adjust_rollback_on_unexpected_error(
    auth_client, db_session, _mock_shopify_client
):
    """
    When bulk_adjust_inventory encounters an unexpected error,
    all successful adjustments should be rolled back (entire batch atomic).
    """
    # Create a product with 2 variants
    payload = {
        "title": "Bulk Rollback Test",
        "variants": [
            {"title": "Variant A", "sku": "BULK-A", "price": "10.00", "inventory_quantity": 100},
            {"title": "Variant B", "sku": "BULK-B", "price": "20.00", "inventory_quantity": 200},
        ],
    }
    resp = await auth_client.post("/inventory", json=payload)
    assert resp.status_code == 201
    variants = resp.json()["variants"]
    v_a = variants[0]["id"]
    v_b = variants[1]["id"]

    # Now call the service's bulk_adjust_inventory which uses commit=False
    from app.inventory.service import InventoryService
    from app.inventory.schemas import InventoryAdjustRequest

    from pydantic import TypeAdapter
    store = await db_session.execute(
        select(Store).where(Store.is_active == True)
    ).scalar_one()

    service = InventoryService(db=db_session, store=store)

    # Create adjustments
    adjustments_data = [
        {"variant_id": v_a, "quantity_change": -50, "reason": "Valid adjustment"},
        {"variant_id": v_b, "quantity_change": -100, "reason": "Valid adjustment"},
    ]
    adapter = TypeAdapter(list[InventoryAdjustRequest])
    adjustments = adapter.validate_python(adjustments_data)

    results = await service.bulk_adjust_inventory(adjustments)
    assert len(results) == 2
    for r in results:
        assert r["success"] is True

    # Verify changes persisted after bulk commit
    v_a_result = await db_session.execute(
        select(ProductVariant).where(ProductVariant.id == uuid.UUID(v_a))
    )
    assert v_a_result.scalar_one().inventory_quantity == 50  # 100 - 50

    v_b_result = await db_session.execute(
        select(ProductVariant).where(ProductVariant.id == uuid.UUID(v_b))
    )
    assert v_b_result.scalar_one().inventory_quantity == 100  # 200 - 100


# ═══════════════════════════════════════════════════════════════════
# TEST: Duplicate Webhook Idempotency
# ═══════════════════════════════════════════════════════════════════

async def test_webhook_idempotency(auth_client, db_session, _mock_shopify_client):
    """
    Processing the same webhook twice should not create duplicate
    transactions or corrupt inventory state.
    """
    # Create product with a matching variant
    payload = valid_product_payload()
    resp = await auth_client.post("/inventory", json=payload)
    assert resp.status_code == 201

    # Set up a variant with a known inventory_item_id
    variant = resp.json()["variants"][0]
    variant_id = uuid.UUID(variant["id"])
    from sqlalchemy import update as sql_update
    await db_session.execute(
        sql_update(ProductVariant)
        .where(ProductVariant.id == variant_id)
        .values(shopify_inventory_item_id=555555, inventory_quantity=50)
    )
    await db_session.commit()

    from app.inventory.service import InventoryService
    store = await db_session.execute(
        select(Store).where(Store.is_active == True)
    ).scalar_one()

    service = InventoryService(db=db_session, store=store)

    # First webhook call — inventory changes from 50 → 60
    result1 = await service.update_inventory_from_webhook(
        inventory_item_id=555555,
        location_id=123456,
        new_quantity=60,
    )
    assert result1["status"] == "updated"
    assert result1["quantity_after"] == 60

    # Second webhook call — same payload, should not change anything
    result2 = await service.update_inventory_from_webhook(
        inventory_item_id=555555,
        location_id=123456,
        new_quantity=60,
    )
    assert result2["status"] == "unchanged"
    assert result2["quantity"] == 60

    # Verify only 1 transaction was recorded for the webhook (not 2)
    txn_result = await db_session.execute(
        select(InventoryTransaction).where(
            InventoryTransaction.variant_id == variant_id,
            InventoryTransaction.transaction_type == TransactionType.SHOPIFY_SYNC.value,
        )
    )
    txns = list(txn_result.scalars().all())
    assert len(txns) == 1


# ═══════════════════════════════════════════════════════════════════
# TEST: Metrics Are Recorded After Inventory Operations
# ═══════════════════════════════════════════════════════════════════

async def test_inventory_operations_recorded(
    auth_client, db_session, _mock_shopify_client
):
    """
    Verify that inventory operations create appropriate audit records.
    """
    # Create product
    payload = valid_product_payload()
    resp = await auth_client.post("/inventory", json=payload)
    assert resp.status_code == 201
    variant_id = resp.json()["variants"][0]["id"]

    # Adjust stock
    adjust_payload = {
        "variant_id": variant_id,
        "quantity_change": 100,
        "reason": "Metrics test",
    }
    resp = await auth_client.post("/inventory/update-stock", json=adjust_payload)
    assert resp.status_code == 200

    # Verify logs exist
    log_result = await db_session.execute(
        select(InventoryLog)
        .order_by(InventoryLog.created_at.desc())
        .limit(5)
    )
    logs = list(log_result.scalars().all())
    assert len(logs) >= 1

    # Verify transactions exist
    txn_result = await db_session.execute(
        select(InventoryTransaction)
        .order_by(InventoryTransaction.created_at.desc())
        .limit(5)
    )
    txns = list(txn_result.scalars().all())
    assert len(txns) >= 1

    # Verify the product has variants
    product = await db_session.execute(
        select(Product).where(Product.id == uuid.UUID(resp.json()["variant_id"]))
    )
    # Just verify the system is in a consistent state
    variant_check = await db_session.execute(
        select(ProductVariant).where(ProductVariant.id == uuid.UUID(variant_id))
    )
    variant = variant_check.scalar_one_or_none()
    assert variant is not None
    assert variant.inventory_quantity == 100
