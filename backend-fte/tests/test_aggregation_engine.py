"""
Tests for the store-centric Inventory Aggregation Engine.

Covers:
- Store-level aggregation structure
- Dashboard summary
- Product / variant aggregation with ownership validation
- Report data
- Cache invalidation helpers

All tests are mock-based (no PostgreSQL required).
"""

import uuid
from decimal import Decimal
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.inventory.aggregation_engine import InventoryAggregationEngine
from app.inventory.aggregation_cache import aggregation_cache
from app.inventory.exceptions import InvalidStoreOwnershipError


# ═══════════════════════════════════════════════════════════════════
# Helpers & fixtures
# ═══════════════════════════════════════════════════════════════════

def _make_store():
    store = MagicMock()
    store.id = uuid.uuid4()
    store.owner_id = uuid.uuid4()
    return store


def _make_engine(store=None):
    store = store or _make_store()
    return InventoryAggregationEngine(db=AsyncMock(), store=store)


def _store_totals(**overrides):
    totals = {
        "store_id": str(uuid.uuid4()),
        "total_available_inventory": 1000,
        "total_reserved_inventory": 50,
        "inventory_value": Decimal("19999.00"),
        "product_count": 5,
        "variant_count": 12,
        "low_stock_variant_count": 3,
        "out_of_stock_variant_count": 1,
        "active_reservations_count": 7,
        "generated_at": "2026-08-06T00:00:00+00:00",
    }
    totals.update(overrides)
    return totals


def _make_variant(store_id=None, quantity=100, price="19.99"):
    store_id = store_id or uuid.uuid4()
    variant = MagicMock()
    variant.id = uuid.uuid4()
    variant.product_id = uuid.uuid4()
    variant.sku = "SKU-1"
    variant.title = "Variant 1"
    variant.inventory_quantity = quantity
    variant.low_stock_threshold = 10
    variant.price = Decimal(price)
    product = MagicMock()
    product.store_id = store_id
    product.title = "Product"
    variant.product = product
    return variant


# ═══════════════════════════════════════════════════════════════════
# STORE AGGREGATION
# ═══════════════════════════════════════════════════════════════════

class TestStoreAggregation:
    @pytest.mark.asyncio
    async def test_get_store_structure(self):
        engine = _make_engine()
        engine._compute_store_totals = AsyncMock(return_value=_store_totals())

        result = await engine.get_store(use_cache=False)

        assert result["total_available_inventory"] == 1000
        assert result["total_reserved_inventory"] == 50
        assert result["inventory_value"] == Decimal("19999.00")
        assert result["product_count"] == 5
        assert result["variant_count"] == 12
        assert result["low_stock_variant_count"] == 3
        assert result["out_of_stock_variant_count"] == 1
        assert result["active_reservations_count"] == 7

    @pytest.mark.asyncio
    async def test_get_dashboard(self):
        engine = _make_engine()
        engine._compute_store_totals = AsyncMock(return_value=_store_totals())

        result = await engine.get_dashboard(use_cache=False)

        assert result["total_available_inventory"] == 1000
        assert result["total_reserved_inventory"] == 50
        assert result["inventory_value"] == 19999.0
        assert result["low_stock_variants"] == 3
        assert result["out_of_stock_variants"] == 1
        assert result["active_reservations"] == 7
        assert result["store_id"] == str(engine.store.id)


# ═══════════════════════════════════════════════════════════════════
# VARIANT / PRODUCT AGGREGATION
# ═══════════════════════════════════════════════════════════════════

class TestVariantAggregation:
    @pytest.mark.asyncio
    async def test_get_variant(self):
        engine = _make_engine()
        variant = _make_variant(store_id=engine.store.id, quantity=25, price="10.00")
        engine._get_variant = AsyncMock(return_value=variant)
        engine._reserved_units_for_variants = AsyncMock(return_value=5)
        engine._committed_units_for_variants = AsyncMock(return_value=2)

        result = await engine.get_variant(variant.id, use_cache=False)

        assert result["available_quantity"] == 25
        assert result["reserved_quantity"] == 5
        assert result["committed_quantity"] == 2
        assert result["total_quantity"] == 32
        assert result["status"] == "in_stock"
        assert result["inventory_value"] == 250.0

    @pytest.mark.asyncio
    async def test_get_variant_low_stock_status(self):
        engine = _make_engine()
        variant = _make_variant(store_id=engine.store.id, quantity=3)
        engine._get_variant = AsyncMock(return_value=variant)
        engine._reserved_units_for_variants = AsyncMock(return_value=0)
        engine._committed_units_for_variants = AsyncMock(return_value=0)

        result = await engine.get_variant(variant.id, use_cache=False)
        assert result["status"] == "low_stock"

    @pytest.mark.asyncio
    async def test_get_variant_out_of_stock_status(self):
        engine = _make_engine()
        variant = _make_variant(store_id=engine.store.id, quantity=0)
        engine._get_variant = AsyncMock(return_value=variant)
        engine._reserved_units_for_variants = AsyncMock(return_value=0)
        engine._committed_units_for_variants = AsyncMock(return_value=0)

        result = await engine.get_variant(variant.id, use_cache=False)
        assert result["status"] == "out_of_stock"

    @pytest.mark.asyncio
    async def test_get_variant_cross_store_ownership(self):
        engine = _make_engine()
        variant = _make_variant(store_id=uuid.uuid4())
        engine._get_variant = AsyncMock(return_value=variant)

        with pytest.raises(InvalidStoreOwnershipError):
            await engine.get_variant(variant.id, use_cache=False)

    @pytest.mark.asyncio
    async def test_get_product(self):
        engine = _make_engine()
        product = MagicMock()
        product.id = uuid.uuid4()
        product.store_id = engine.store.id
        product.title = "Product A"
        v1 = _make_variant(store_id=engine.store.id, quantity=10, price="5.00")
        v2 = _make_variant(store_id=engine.store.id, quantity=20, price="10.00")
        product.variants = [v1, v2]

        engine._get_product = AsyncMock(return_value=product)
        engine._reserved_units_for_variants = AsyncMock(return_value=3)
        engine._committed_units_for_variants = AsyncMock(return_value=1)
        engine._reserved_units_by_variant = AsyncMock(return_value={str(v1.id): 2, str(v2.id): 1})

        result = await engine.get_product(product.id, use_cache=False)

        assert result["total_available_inventory"] == 30
        assert result["total_reserved_inventory"] == 3
        assert result["variant_count"] == 2
        assert result["inventory_value"] == 250.0
        assert len(result["variants"]) == 2


# ═══════════════════════════════════════════════════════════════════
# REPORTS
# ═══════════════════════════════════════════════════════════════════

class TestReports:
    @pytest.mark.asyncio
    async def test_get_report_data(self):
        engine = _make_engine()
        engine._compute_store_totals = AsyncMock(return_value=_store_totals())

        v1 = _make_variant(store_id=engine.store.id, quantity=100)
        v2 = _make_variant(store_id=engine.store.id, quantity=5)
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [v1, v2]
        engine.db.execute = AsyncMock(return_value=result_mock)

        report = await engine.get_report_data(use_cache=False)

        assert report["total_inventory_value"] == 19999.0
        assert report["total_available_inventory"] == 1000
        assert report["dead_stock_count"] == 0
        assert len(report["fast_movers"]) == 2
        assert len(report["slow_movers"]) == 2


# ═══════════════════════════════════════════════════════════════════
# CACHE
# ═══════════════════════════════════════════════════════════════════

class TestCache:
    @pytest.mark.asyncio
    async def test_store_cache_key(self):
        store_id = uuid.uuid4()
        assert aggregation_cache.key_store(store_id) == f"agg:store:{store_id}"

    @pytest.mark.asyncio
    async def test_invalidate_store_clears_entries(self):
        store_id = uuid.uuid4()
        await aggregation_cache.clear()
        await aggregation_cache.set(f"agg:store:{store_id}", {"data": 1})
        await aggregation_cache.set(f"agg:variant:{store_id}:{uuid.uuid4()}", {"data": 2})

        count = await aggregation_cache.invalidate_store(store_id)
        assert count >= 1
        assert await aggregation_cache.get(f"agg:store:{store_id}") is None
