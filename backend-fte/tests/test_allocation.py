"""
Tests for the store-centric Allocation Engine.

Covers:
- AllocationItem / AllocationPlan helpers
- allocate_for_woocommerce: full, partial, out-of-stock
- Reservation failures don't crash allocation
- preview / validate
- strategies and dashboard stats

All tests are mock-based (no PostgreSQL required).
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.inventory.allocation_strategies import (
    AllocationItem,
    AllocationItemResult,
    AllocationPlan,
)
from app.inventory.allocation_service import AllocationService
from app.inventory.exceptions import (
    InvalidAllocationStrategyError,
    VariantNotFoundError,
)


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _make_variant(store_id=None, quantity=100, variant_id=None):
    store_id = store_id or uuid.uuid4()
    variant = MagicMock()
    variant.id = variant_id or uuid.uuid4()
    variant.product_id = uuid.uuid4()
    variant.inventory_quantity = quantity
    product = MagicMock()
    product.store_id = store_id
    variant.product = product
    return variant


def _make_store():
    store = MagicMock()
    store.id = uuid.uuid4()
    return store


def _make_reservation(variant_id):
    res = MagicMock()
    res.id = uuid.uuid4()
    res.variant_id = variant_id
    return res


def _make_service(store=None, variant=None):
    store = store or _make_store()
    service = AllocationService(db=AsyncMock(), store=store)
    service._get_variant = AsyncMock(return_value=variant)
    service.reservation_service.reserve_stock = AsyncMock(
        return_value=_make_reservation(variant.id if variant else uuid.uuid4())
    )
    return service


# ═══════════════════════════════════════════════════════════════════
# Models
# ═══════════════════════════════════════════════════════════════════

class TestAllocationModels:
    def test_item_result_status_fulfilled(self):
        r = AllocationItemResult(
            variant_id=uuid.uuid4(), requested_quantity=5, fulfilled_quantity=5,
        )
        assert r.status == "fulfilled"

    def test_item_result_status_partial(self):
        r = AllocationItemResult(
            variant_id=uuid.uuid4(), requested_quantity=10, fulfilled_quantity=3,
        )
        assert r.status == "partial"

    def test_item_result_status_out_of_stock(self):
        r = AllocationItemResult(variant_id=uuid.uuid4(), requested_quantity=10)
        assert r.status == "out_of_stock"

    def test_plan_properties(self):
        plan = AllocationPlan(strategy_name="default", items=[
            AllocationItemResult(variant_id=uuid.uuid4(), requested_quantity=5, fulfilled_quantity=5),
            AllocationItemResult(variant_id=uuid.uuid4(), requested_quantity=5, fulfilled_quantity=2),
        ])
        assert plan.total_requested == 10
        assert plan.total_fulfilled == 7
        assert plan.total_unfulfilled == 3
        assert plan.partial is True
        assert plan.is_fully_fulfilled is False
        assert plan.status == "partially_allocated"


# ═══════════════════════════════════════════════════════════════════
# AllocationService — order allocation
# ═══════════════════════════════════════════════════════════════════

class TestAllocateForWoocommerce:
    @pytest.mark.asyncio
    async def test_full_allocation(self):
        store = _make_store()
        variant = _make_variant(store_id=store.id, quantity=100)
        service = _make_service(store=store, variant=variant)

        result = await service.allocate_for_woocommerce(
            items=[AllocationItem(variant_id=variant.id, quantity=10)],
            order_id="WC-1",
        )

        assert result["total_requested"] == 10
        assert result["total_fulfilled"] == 10
        assert result["fully_fulfilled"] is True
        assert result["status"] == "fully_allocated"
        assert len(result["reservation_ids"]) == 1
        service.reservation_service.reserve_stock.assert_awaited()

    @pytest.mark.asyncio
    async def test_partial_allocation(self):
        store = _make_store()
        variant = _make_variant(store_id=store.id, quantity=5)
        service = _make_service(store=store, variant=variant)

        result = await service.allocate_for_woocommerce(
            items=[AllocationItem(variant_id=variant.id, quantity=10)],
            order_id="WC-1",
        )

        assert result["total_fulfilled"] == 5
        assert result["partial"] is True
        assert result["status"] == "partially_allocated"

    @pytest.mark.asyncio
    async def test_out_of_stock(self):
        store = _make_store()
        variant = _make_variant(store_id=store.id, quantity=0)
        service = _make_service(store=store, variant=variant)

        result = await service.allocate_for_woocommerce(
            items=[AllocationItem(variant_id=variant.id, quantity=10)],
            order_id="WC-1",
        )

        assert result["total_fulfilled"] == 0
        assert result["status"] == "out_of_stock"
        assert result["reservation_ids"] == []

    @pytest.mark.asyncio
    async def test_unknown_variant_item(self):
        store = _make_store()
        service = _make_service(store=store, variant=None)

        result = await service.allocate_for_woocommerce(
            items=[AllocationItem(variant_id=uuid.uuid4(), quantity=5)],
            order_id="WC-1",
        )

        assert result["total_fulfilled"] == 0
        assert result["items"][0]["status"] == "out_of_stock"

    @pytest.mark.asyncio
    async def test_reservation_failure_does_not_crash(self):
        store = _make_store()
        variant = _make_variant(store_id=store.id, quantity=100)
        service = _make_service(store=store, variant=variant)
        service.reservation_service.reserve_stock = AsyncMock(
            side_effect=Exception("DB error")
        )

        result = await service.allocate_for_woocommerce(
            items=[AllocationItem(variant_id=variant.id, quantity=10)],
            order_id="WC-1",
        )

        # Item reported as unfulfilled, but the call itself did not raise
        assert result["total_fulfilled"] == 0
        assert result["status"] == "out_of_stock"


# ═══════════════════════════════════════════════════════════════════
# AllocationService — preview / validate / strategies / dashboard
# ═══════════════════════════════════════════════════════════════════

class TestAllocationHelpers:
    @pytest.mark.asyncio
    async def test_preview_allocation(self):
        store = _make_store()
        variant = _make_variant(store_id=store.id, quantity=50)
        service = _make_service(store=store, variant=variant)

        result = await service.preview_allocation(variant.id, 10)
        assert result["fulfilled_quantity"] == 10
        assert result["status"] == "fulfilled"

    @pytest.mark.asyncio
    async def test_preview_unknown_variant(self):
        service = _make_service(variant=None)
        with pytest.raises(VariantNotFoundError):
            await service.preview_allocation(uuid.uuid4(), 10)

    @pytest.mark.asyncio
    async def test_validate_allocation(self):
        store = _make_store()
        variant = _make_variant(store_id=store.id, quantity=50)
        service = _make_service(store=store, variant=variant)

        assert (await service.validate_allocation(variant.id, 10))["sufficient"] is True
        assert (await service.validate_allocation(variant.id, 100))["sufficient"] is False

    @pytest.mark.asyncio
    async def test_list_strategies(self):
        service = _make_service()
        strategies = await service.list_strategies()
        names = {s["name"] for s in strategies}
        assert "default" in names
        assert "manual" in names

    @pytest.mark.asyncio
    async def test_unknown_strategy_rejected(self):
        service = _make_service()
        with pytest.raises(InvalidAllocationStrategyError):
            await service.allocate_for_woocommerce(
                items=[AllocationItem(variant_id=uuid.uuid4(), quantity=1)],
                order_id="WC-1",
                strategy_name="black_magic",
            )

    @pytest.mark.asyncio
    async def test_dashboard_stats(self):
        store = _make_store()
        service = _make_service(store=store)
        service._get_active_strategy = AsyncMock(return_value="default")
        db = service.db
        db.execute.return_value = MagicMock()
        db.execute.return_value.scalar.return_value = 5

        stats = await service.get_dashboard_stats()
        assert stats["allocation_strategy"] == "default"
        assert stats["total_allocated_units"] == 5
        assert stats["orders_allocated"] == 5

    @pytest.mark.asyncio
    async def test_get_strategy(self):
        store = _make_store()
        service = _make_service(store=store)
        service._get_active_strategy = AsyncMock(return_value="default")

        strategy = await service.get_strategy()
        assert strategy["name"] == "default"
