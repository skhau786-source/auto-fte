"""
Tests for the store-centric Reservation Engine.

Covers:
- ReservationRepository queries
- reserve_stock: success, insufficient stock, unknown variant, duplicates
- commit / release / expire lifecycle
- cancel_order
- validate_stock and dashboard stats

All tests are mock-based (no PostgreSQL required).
"""

import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.inventory.reservation_service import (
    ReservationService,
    ReservationRepository,
)
from app.inventory.constants import ReservationStatus, ReservationSource
from app.inventory.exceptions import (
    ReservationNotFoundError,
    InsufficientStockForReservationError,
    InvalidReservationStateError,
    DuplicateReservationError,
    VariantNotFoundError,
    InvalidStoreOwnershipError,
)


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _make_mock_db(variant=None):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = variant
    db.execute.return_value = result
    return db


def _db_with_sequential(*scalar_values):
    """db.execute returns each result in order (scalar_one_or_none)."""
    db = AsyncMock()
    results = []
    for value in scalar_values:
        r = MagicMock()
        r.scalar_one_or_none.return_value = value
        results.append(r)
    db.execute.side_effect = results
    return db


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


def _make_reservation(store_id=None, status=ReservationStatus.ACTIVE, quantity=5):
    res = MagicMock()
    res.id = uuid.uuid4()
    res.store_id = store_id or uuid.uuid4()
    res.variant_id = uuid.uuid4()
    res.product_id = uuid.uuid4()
    res.quantity = quantity
    res.order_id = "ORDER-1"
    res.order_source = ReservationSource.MANUAL
    res.status = status
    res.meta_data = {}
    return res


# ═══════════════════════════════════════════════════════════════════
# ReservationRepository
# ═══════════════════════════════════════════════════════════════════

def _db_execute_mock():
    """db whose execute() returns a plain MagicMock (scalar/scalars are sync)."""
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    return db


class TestReservationRepository:
    @pytest.mark.asyncio
    async def test_get_by_id(self):
        db = _db_execute_mock()
        repo = ReservationRepository(db)
        res = _make_reservation()
        db.execute.return_value.scalar_one_or_none.return_value = res

        result = await repo.get_by_id(res.id)
        assert result is res

    @pytest.mark.asyncio
    async def test_get_by_order(self):
        db = _db_execute_mock()
        repo = ReservationRepository(db)
        db.execute.return_value.scalars.return_value.all.return_value = [MagicMock()]

        result = await repo.get_by_order(uuid.uuid4(), "ORDER-1")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list(self):
        db = _db_execute_mock()
        repo = ReservationRepository(db)
        db.execute.return_value.scalar.return_value = 2
        db.execute.return_value.scalars.return_value.all.return_value = [MagicMock()]

        items, total, active = await repo.list(uuid.uuid4(), page=1, page_size=10)
        assert total == 2
        assert len(items) == 1
        assert active == 2


# ═══════════════════════════════════════════════════════════════════
# ReservationService — reserve_stock
# ═══════════════════════════════════════════════════════════════════

class TestReserveStock:
    @pytest.mark.asyncio
    async def test_reserve_success(self):
        store = _make_store()
        variant = _make_variant(store_id=store.id, quantity=100)
        # Call 1: locked variant; Call 2: duplicate check returns None
        db = _db_with_sequential(variant, None)
        service = ReservationService(db=db, store=store)

        reservation = await service.reserve_stock(
            variant_id=variant.id,
            quantity=10,
            order_id="ORDER-1",
        )

        assert reservation.store_id == store.id
        assert reservation.quantity == 10
        assert reservation.status == ReservationStatus.ACTIVE
        assert variant.inventory_quantity == 90  # decremented
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_reserve_insufficient_stock(self):
        store = _make_store()
        variant = _make_variant(store_id=store.id, quantity=5)
        db = _make_mock_db(variant=variant)
        service = ReservationService(db=db, store=store)

        with pytest.raises(InsufficientStockForReservationError):
            await service.reserve_stock(
                variant_id=variant.id,
                quantity=10,
            )

    @pytest.mark.asyncio
    async def test_reserve_variant_not_found(self):
        store = _make_store()
        db = _make_mock_db(variant=None)
        service = ReservationService(db=db, store=store)

        with pytest.raises(VariantNotFoundError):
            await service.reserve_stock(
                variant_id=uuid.uuid4(),
                quantity=5,
            )

    @pytest.mark.asyncio
    async def test_reserve_cross_store_variant(self):
        store = _make_store()
        variant = _make_variant(store_id=uuid.uuid4(), quantity=50)
        db = _make_mock_db(variant=variant)
        service = ReservationService(db=db, store=store)

        with pytest.raises(InvalidStoreOwnershipError):
            await service.reserve_stock(
                variant_id=variant.id,
                quantity=5,
            )

    @pytest.mark.asyncio
    async def test_reserve_duplicate_active_reservation(self):
        store = _make_store()
        variant = _make_variant(store_id=store.id, quantity=50)
        # Call 1: locked variant; Call 2: duplicate check finds an existing reservation
        existing = _make_reservation(store_id=store.id)
        db = _db_with_sequential(variant, existing)
        service = ReservationService(db=db, store=store)

        with pytest.raises(DuplicateReservationError):
            await service.reserve_stock(
                variant_id=variant.id,
                quantity=5,
                order_id="ORDER-1",
            )

    @pytest.mark.asyncio
    async def test_reserve_expiry_set(self):
        store = _make_store()
        variant = _make_variant(store_id=store.id, quantity=50)
        db = _make_mock_db(variant=variant)
        service = ReservationService(db=db, store=store)

        reservation = await service.reserve_stock(
            variant_id=variant.id,
            quantity=5,
            expires_in_minutes=30,
        )
        assert reservation.expires_at is not None


# ═══════════════════════════════════════════════════════════════════
# ReservationService — lifecycle
# ═══════════════════════════════════════════════════════════════════

class TestLifecycle:
    @pytest.mark.asyncio
    async def test_commit_stock(self):
        store = _make_store()
        res = _make_reservation(store_id=store.id, status=ReservationStatus.ACTIVE)
        db = _make_mock_db()
        db.execute.return_value.scalar_one_or_none.return_value = res
        service = ReservationService(db=db, store=store)

        result = await service.commit_stock(res.id)
        assert result.status == ReservationStatus.COMMITTED
        assert result.committed_at is not None

    @pytest.mark.asyncio
    async def test_commit_invalid_state(self):
        store = _make_store()
        res = _make_reservation(store_id=store.id, status=ReservationStatus.RELEASED)
        db = _make_mock_db()
        db.execute.return_value.scalar_one_or_none.return_value = res
        service = ReservationService(db=db, store=store)

        with pytest.raises(InvalidReservationStateError):
            await service.commit_stock(res.id)

    @pytest.mark.asyncio
    async def test_release_restores_stock(self):
        store = _make_store()
        res = _make_reservation(store_id=store.id, status=ReservationStatus.ACTIVE, quantity=5)
        variant = _make_variant(store_id=store.id, quantity=20)
        # Call 1: reservation lookup; Call 2: variant lookup (stock restored)
        db = _db_with_sequential(res, variant)
        service = ReservationService(db=db, store=store)

        result = await service.release_stock(res.id)
        assert result.status == ReservationStatus.RELEASED
        assert variant.inventory_quantity == 25

    @pytest.mark.asyncio
    async def test_expire_reservation(self):
        store = _make_store()
        res = _make_reservation(store_id=store.id, status=ReservationStatus.ACTIVE, quantity=5)
        variant = _make_variant(store_id=store.id, quantity=20)
        # Call 1: reservation lookup; Call 2: variant lookup (stock restored)
        db = _db_with_sequential(res, variant)
        service = ReservationService(db=db, store=store)

        result = await service.expire_reservation(res.id)
        assert result.status == ReservationStatus.EXPIRED
        assert variant.inventory_quantity == 25

    @pytest.mark.asyncio
    async def test_reservation_not_found(self):
        store = _make_store()
        db = _make_mock_db(variant=None)
        db.execute.return_value.scalar_one_or_none.return_value = None
        service = ReservationService(db=db, store=store)

        with pytest.raises(ReservationNotFoundError):
            await service.get_reservation(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cancel_order_releases_active(self):
        store = _make_store()
        service = ReservationService(db=_make_mock_db(), store=store)
        service.repo.get_by_order = AsyncMock(return_value=[
            _make_reservation(store_id=store.id, status=ReservationStatus.ACTIVE),
            _make_reservation(store_id=store.id, status=ReservationStatus.COMMITTED),
        ])
        service.release_stock = AsyncMock(side_effect=lambda rid: _make_reservation(
            store_id=store.id, status=ReservationStatus.RELEASED,
        ))

        released = await service.cancel_order("ORDER-1")
        # Only the ACTIVE reservation is released
        assert len(released) == 1
        service.release_stock.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════
# ReservationService — queries & stats
# ═══════════════════════════════════════════════════════════════════

class TestQueries:
    @pytest.mark.asyncio
    async def test_validate_stock_sufficient(self):
        store = _make_store()
        variant = _make_variant(store_id=store.id, quantity=50)
        db = _make_mock_db(variant=variant)
        service = ReservationService(db=db, store=store)

        result = await service.validate_stock(variant.id, 10)
        assert result["sufficient"] is True
        assert result["available_quantity"] == 50

    @pytest.mark.asyncio
    async def test_validate_stock_insufficient(self):
        store = _make_store()
        variant = _make_variant(store_id=store.id, quantity=5)
        db = _make_mock_db(variant=variant)
        service = ReservationService(db=db, store=store)

        result = await service.validate_stock(variant.id, 10)
        assert result["sufficient"] is False

    @pytest.mark.asyncio
    async def test_dashboard_stats(self):
        store = _make_store()
        db = _make_mock_db()
        db.execute.return_value.scalar.return_value = 3
        db.execute.return_value.all.return_value = [
            (ReservationSource.WOOCOMMERCE, 2),
            (ReservationSource.MANUAL, 1),
        ]
        service = ReservationService(db=db, store=store)

        stats = await service.get_dashboard_stats()
        assert stats["active_reservations"] == 3
        assert stats["reserved_stock_units"] == 3
        assert stats["reservations_by_source"]["woocommerce"] == 2
        assert stats["reservation_success_rate"] == 100.0

    @pytest.mark.asyncio
    async def test_get_reservations(self):
        store = _make_store()
        db = _make_mock_db()
        db.execute.return_value.scalar.return_value = 4
        db.execute.return_value.scalars.return_value.all.return_value = [MagicMock()]
        service = ReservationService(db=db, store=store)

        items, total, active = await service.get_reservations(page=1, page_size=20)
        assert total == 4
        assert len(items) == 1
