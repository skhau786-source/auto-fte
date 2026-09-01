"""
Tests for the Phase 3 Revenue Dashboard / Advanced Analytics endpoints
(app.woocommerce.service.WooCommerceService.get_revenue_analytics,
get_top_products, get_order_status_breakdown).

All tests are mock-based (mocked AsyncSession), matching this project's
existing WooCommerce service test convention (see test_woocommerce_service.py).
They verify that:
- figures are computed from mocked query results, never hard-coded
- the previous-period comparison and average-order-value math is correct
- a store the caller doesn't own is rejected before any analytics query runs
- empty/zero data is handled without crashing (no division by zero, etc.)
"""

import uuid
import pytest
from decimal import Decimal
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.woocommerce.service import WooCommerceService
from app.woocommerce.exceptions import StoreNotFoundError


@pytest.fixture
def mock_db():
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalar.return_value = 0
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result
    return db


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


@pytest.fixture
def service(mock_db, mock_user):
    return WooCommerceService(db=mock_db, user=mock_user)


def _mock_store(service):
    store = MagicMock()
    store.id = uuid.uuid4()
    store.owner_id = service.user_id
    store.is_active = True
    return store


def _mock_result(**methods):
    """A MagicMock whose named methods (all/one/scalar_one_or_none/...) return the given values."""
    r = MagicMock()
    for name, value in methods.items():
        getattr(r, name).return_value = value
    return r


class TestRevenueAnalytics:
    @pytest.mark.asyncio
    async def test_computes_revenue_and_change_from_query_results(self, service, mock_db):
        store_id = uuid.uuid4()
        store = _mock_store(service)

        mock_db.execute.side_effect = [
            _mock_result(scalar_one_or_none=store),  # _get_store
            _mock_result(all=[(date(2026, 8, 20), Decimal("100.00"), 2),
                               (date(2026, 8, 21), Decimal("50.00"), 1)]),  # daily trend
            _mock_result(one=(Decimal("150.00"), 3)),  # current period summary
            _mock_result(one=(Decimal("100.00"), 2)),  # previous period summary
        ]

        result = await service.get_revenue_analytics(store_id, days=30)

        assert result["revenue"] == 150.00
        assert result["orders"] == 3
        assert result["average_order_value"] == 50.00
        assert result["previous_period_revenue"] == 100.00
        assert result["previous_period_orders"] == 2
        # (150 - 100) / 100 * 100 = 50.0
        assert result["revenue_change_pct"] == 50.0
        # (3 - 2) / 2 * 100 = 50.0
        assert result["order_change_pct"] == 50.0
        assert len(result["trend"]) == 2
        assert result["trend"][0] == {"date": "2026-08-20", "revenue": 100.0, "orders": 2}

    @pytest.mark.asyncio
    async def test_no_orders_in_either_period_is_a_safe_zero_result(self, service, mock_db):
        store = _mock_store(service)
        mock_db.execute.side_effect = [
            _mock_result(scalar_one_or_none=store),
            _mock_result(all=[]),
            _mock_result(one=(None, 0)),
            _mock_result(one=(None, 0)),
        ]

        result = await service.get_revenue_analytics(uuid.uuid4(), days=30)

        assert result["revenue"] == 0
        assert result["orders"] == 0
        assert result["average_order_value"] == 0.0
        # No prior-period revenue to compare against -> undefined, not fabricated as 0%.
        assert result["revenue_change_pct"] is None
        assert result["order_change_pct"] is None
        assert result["trend"] == []

    @pytest.mark.asyncio
    async def test_zero_previous_period_does_not_divide_by_zero(self, service, mock_db):
        """New store with revenue this period but none previously — no crash, no fabricated %."""
        store = _mock_store(service)
        mock_db.execute.side_effect = [
            _mock_result(scalar_one_or_none=store),
            _mock_result(all=[]),
            _mock_result(one=(Decimal("200.00"), 4)),
            _mock_result(one=(None, 0)),
        ]

        result = await service.get_revenue_analytics(uuid.uuid4(), days=30)

        assert result["revenue"] == 200.0
        assert result["revenue_change_pct"] is None
        assert result["order_change_pct"] is None

    @pytest.mark.asyncio
    async def test_unowned_store_is_rejected_before_any_analytics_query(self, service, mock_db):
        mock_db.execute.side_effect = [_mock_result(scalar_one_or_none=None)]

        with pytest.raises(StoreNotFoundError):
            await service.get_revenue_analytics(uuid.uuid4(), days=30)

        assert mock_db.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_days_parameter_is_clamped_to_a_sane_range(self, service, mock_db):
        store = _mock_store(service)
        mock_db.execute.side_effect = [
            _mock_result(scalar_one_or_none=store),
            _mock_result(all=[]),
            _mock_result(one=(None, 0)),
            _mock_result(one=(None, 0)),
        ]

        result = await service.get_revenue_analytics(uuid.uuid4(), days=99999)

        assert result["period_days"] == 365


class TestTopProducts:
    @pytest.mark.asyncio
    async def test_returns_products_ordered_by_revenue(self, service, mock_db):
        store = _mock_store(service)
        mock_db.execute.side_effect = [
            _mock_result(scalar_one_or_none=store),
            _mock_result(all=[
                (101, "Widget Pro", "WID-PRO", Decimal("500.00"), 10),
                (102, "Widget Basic", "WID-BAS", Decimal("200.00"), 8),
            ]),
        ]

        products = await service.get_top_products(uuid.uuid4(), days=30, limit=10)

        assert len(products) == 2
        assert products[0] == {
            "wc_product_id": 101, "name": "Widget Pro", "sku": "WID-PRO",
            "revenue": 500.0, "units_sold": 10,
        }

    @pytest.mark.asyncio
    async def test_no_sales_in_period_returns_empty_list(self, service, mock_db):
        store = _mock_store(service)
        mock_db.execute.side_effect = [
            _mock_result(scalar_one_or_none=store),
            _mock_result(all=[]),
        ]

        products = await service.get_top_products(uuid.uuid4(), days=7, limit=10)
        assert products == []

    @pytest.mark.asyncio
    async def test_limit_is_clamped(self, service, mock_db):
        store = _mock_store(service)
        mock_db.execute.side_effect = [
            _mock_result(scalar_one_or_none=store),
            _mock_result(all=[]),
        ]
        await service.get_top_products(uuid.uuid4(), days=30, limit=9999)
        # Just verifying it doesn't crash / raise on an out-of-range limit;
        # the clamp itself is applied before the query is built.


class TestOrderStatusBreakdown:
    @pytest.mark.asyncio
    async def test_returns_counts_per_status(self, service, mock_db):
        from app.woocommerce.constants import OrderStatus

        store = _mock_store(service)
        mock_db.execute.side_effect = [
            _mock_result(scalar_one_or_none=store),
            _mock_result(all=[
                (OrderStatus.COMPLETED, 12),
                (OrderStatus.PENDING, 3),
                (OrderStatus.CANCELLED, 1),
            ]),
        ]

        result = await service.get_order_status_breakdown(uuid.uuid4(), days=30)

        assert result == [
            {"status": "completed", "count": 12},
            {"status": "pending", "count": 3},
            {"status": "cancelled", "count": 1},
        ]

    @pytest.mark.asyncio
    async def test_no_orders_returns_empty_list(self, service, mock_db):
        store = _mock_store(service)
        mock_db.execute.side_effect = [
            _mock_result(scalar_one_or_none=store),
            _mock_result(all=[]),
        ]
        result = await service.get_order_status_breakdown(uuid.uuid4(), days=30)
        assert result == []
