"""
Comprehensive tests for the Reservation Engine (Phase 3).

Covers:
- ReservationRepository: create, get_by_id, get_by_order, list_active, update_status
- ReservationService: reserve_stock, commit_stock, release_stock, expire, cancel_order
- Business rules: no negative stock, no duplicate reservations, FOR UPDATE
- Ownership validation, warehouse validation, variant validation
- Expiration and background cleanup
- Dashboard statistics
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from app.inventory.constants import (
    ReservationStatus, ReservationSource,
)
from app.warehouse.reservation_service import (
    ReservationService, ReservationRepository,
)
from app.warehouse.exceptions import (
    ReservationNotFoundError, InsufficientStockForReservationError,
    InvalidReservationStateError, DuplicateReservationError,
    WarehouseNotFoundError, WarehouseInactiveError,
)

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


def _make_mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _make_mock_store(store_id=None):
    store = MagicMock()
    store.id = store_id or uuid.uuid4()
    store.owner_id = uuid.uuid4()
    store.is_active = True
    return store


def _make_mock_user(user_id=None):
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    return user


def _make_mock_warehouse(store_id=None, wh_id=None, is_active=True):
    wh = MagicMock()
    wh.id = wh_id or uuid.uuid4()
    wh.store_id = store_id or uuid.uuid4()
    wh.code = "WH-TEST"
    wh.name = "Test Warehouse"
    wh.is_active = is_active
    return wh


def _make_mock_variant(variant_id=None, product_id=None):
    v = MagicMock()
    v.id = variant_id or uuid.uuid4()
    v.product_id = product_id or uuid.uuid4()
    v.sku = "SKU-TEST"
    v.title = "Test Variant"
    return v


def _make_mock_wh_inv(wh_inv_id=None, available=100, reserved=0):
    inv = MagicMock()
    inv.id = wh_inv_id or uuid.uuid4()
    inv.available_stock = available
    inv.reserved_stock = reserved
    return inv


def _make_mock_reservation(
    res_id=None, store_id=None, warehouse_id=None,
    variant_id=None, quantity=5, status=ReservationStatus.ACTIVE,
    order_id=None,
):
    r = MagicMock()
    r.id = res_id or uuid.uuid4()
    r.store_id = store_id or uuid.uuid4()
    r.warehouse_id = warehouse_id or uuid.uuid4()
    r.variant_id = variant_id or uuid.uuid4()
    r.inventory_id = uuid.uuid4()
    r.product_id = uuid.uuid4()
    r.quantity = quantity
    r.status = status
    r.order_id = order_id
    r.order_source = ReservationSource.MANUAL
    r.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    r.created_at = datetime.now(timezone.utc)
    r.updated_at = datetime.now(timezone.utc)
    r.released_at = None
    r.committed_at = None
    r.metadata = {}
    return r


# ═══════════════════════════════════════════════════════════════════
# REPOSITORY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestReservationRepository:
    """Tests for the ReservationRepository."""

    async def test_create_reservation(self):
        """Repository: create_reservation creates a new record."""
        db = _make_mock_db()
        repo = ReservationRepository(db)
        store_id = uuid.uuid4()
        wh_id = uuid.uuid4()
        v_id = uuid.uuid4()

        result = await repo.create(
            store_id=store_id,
            warehouse_id=wh_id,
            variant_id=v_id,
            quantity=10,
        )
        assert result is not None
        assert db.add.called
        assert db.flush.called

    async def test_get_by_id_found(self):
        """Repository: get_by_id returns a reservation when found."""
        from app.warehouse.reservation_service import ReservationRepository
        db = _make_mock_db()
        repo = ReservationRepository(db)

        mock_res = _make_mock_reservation()
        scalar_result = MagicMock()
        scalar_result.unique.return_value.scalar_one_or_none.return_value = mock_res
        db.execute.return_value = scalar_result

        result = await repo.get_by_id(mock_res.id)
        assert result is not None
        assert result.id == mock_res.id

    async def test_get_by_id_not_found(self):
        """Repository: get_by_id returns None when not found."""
        from app.warehouse.reservation_service import ReservationRepository
        db = _make_mock_db()
        repo = ReservationRepository(db)

        scalar_result = MagicMock()
        scalar_result.unique.return_value.scalar_one_or_none.return_value = None
        db.execute.return_value = scalar_result

        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    async def test_get_by_order(self):
        """Repository: get_by_order returns reservations for an order."""
        from app.warehouse.reservation_service import ReservationRepository
        db = _make_mock_db()
        repo = ReservationRepository(db)

        mock_res = _make_mock_reservation(order_id="ORD-123")
        scalar_result = MagicMock()
        scalar_result.unique.return_value.scalars.return_value.all.return_value = [mock_res]
        db.execute.return_value = scalar_result

        result = await repo.get_by_order(uuid.uuid4(), "ORD-123")
        assert len(result) == 1

    async def test_find_active_by_variant_and_order(self):
        """Repository: find_active_by_variant_and_order finds matching reservation."""
        from app.warehouse.reservation_service import ReservationRepository
        db = _make_mock_db()
        repo = ReservationRepository(db)

        mock_res = _make_mock_reservation(order_id="ORD-123")
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = mock_res
        db.execute.return_value = scalar_result

        result = await repo.find_active_by_variant_and_order(
            store_id=uuid.uuid4(),
            variant_id=uuid.uuid4(),
            warehouse_id=uuid.uuid4(),
            order_id="ORD-123",
        )
        assert result is not None

    async def test_update_status(self):
        """Repository: update_status changes reservation status."""
        from app.warehouse.reservation_service import ReservationRepository
        db = _make_mock_db()
        repo = ReservationRepository(db)

        mock_res = _make_mock_reservation()
        scalar_result = MagicMock()
        scalar_result.unique.return_value.scalar_one_or_none.return_value = mock_res
        db.execute.return_value = scalar_result

        result = await repo.update_status(
            mock_res.id,
            ReservationStatus.COMMITTED,
            committed_at=datetime.now(timezone.utc),
        )
        assert result is not None
        assert result.status == ReservationStatus.COMMITTED


# ═══════════════════════════════════════════════════════════════════
# SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestReservationService:
    """Tests for the ReservationService business logic."""

    async def _make_service(self):
        db = _make_mock_db()
        store = _make_mock_store()
        user = _make_mock_user()
        service = ReservationService(db=db, store=store, user_id=user.id)
        return db, store, service

    async def test_reserve_stock_success(self):
        """Service: reserve_stock creates reservation and updates inventory."""
        db, store, service = await self._make_service()
        wh_id = uuid.uuid4()
        v_id = uuid.uuid4()

        mock_wh = _make_mock_warehouse(store_id=store.id, wh_id=wh_id)
        mock_variant = _make_mock_variant(variant_id=v_id)
        mock_inv = _make_mock_wh_inv(available=100)

        # Replace repo methods with AsyncMocks
        service.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)
        service.variant_repo.get_by_id = AsyncMock(return_value=mock_variant)
        service.inv_repo.get_or_create = AsyncMock(return_value=mock_inv)
        service.repo.find_active_by_variant_and_order = AsyncMock(return_value=None)
        mock_res = _make_mock_reservation(
            store_id=store.id, warehouse_id=wh_id, variant_id=v_id, quantity=10,
        )
        service.repo.create = AsyncMock(return_value=mock_res)
        service.txn_repo.create = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        service.log_repo.create = AsyncMock(return_value=MagicMock())

        result = await service.reserve_stock(
            warehouse_id=wh_id,
            variant_id=v_id,
            quantity=10,
            reason="Test reservation",
        )

        assert result is not None
        assert result.quantity == 10
        # Verify inventory was updated: 100 - 10 = 90 available, 10 reserved
        assert mock_inv.available_stock == 90
        assert mock_inv.reserved_stock == 10

    async def test_reserve_stock_insufficient(self):
        """Service: reserve_stock raises when not enough available stock."""
        db, store, service = await self._make_service()
        wh_id = uuid.uuid4()
        v_id = uuid.uuid4()

        mock_wh = _make_mock_warehouse(store_id=store.id, wh_id=wh_id)
        mock_variant = _make_mock_variant(variant_id=v_id)
        mock_inv = _make_mock_wh_inv(available=5)

        service.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)
        service.variant_repo.get_by_id = AsyncMock(return_value=mock_variant)
        service.inv_repo.get_or_create = AsyncMock(return_value=mock_inv)

        with pytest.raises(InsufficientStockForReservationError):
            await service.reserve_stock(
                warehouse_id=wh_id,
                variant_id=v_id,
                quantity=10,
            )

    async def test_reserve_stock_duplicate(self):
        """Service: reserve_stock raises on duplicate variant/order/warehouse."""
        db, store, service = await self._make_service()
        wh_id = uuid.uuid4()
        v_id = uuid.uuid4()

        mock_wh = _make_mock_warehouse(store_id=store.id, wh_id=wh_id)
        mock_variant = _make_mock_variant(variant_id=v_id)
        mock_inv = _make_mock_wh_inv(available=100)

        service.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)
        service.variant_repo.get_by_id = AsyncMock(return_value=mock_variant)
        service.inv_repo.get_or_create = AsyncMock(return_value=mock_inv)
        # Simulate existing reservation
        service.repo.find_active_by_variant_and_order = AsyncMock(
            return_value=_make_mock_reservation()
        )

        with pytest.raises(DuplicateReservationError):
            await service.reserve_stock(
                warehouse_id=wh_id,
                variant_id=v_id,
                quantity=10,
                order_id="ORD-123",
            )

    async def test_reserve_stock_wrong_store(self):
        """Service: reserve_stock raises when warehouse belongs to different store."""
        db, store, service = await self._make_service()
        wh_id = uuid.uuid4()
        mock_wh = _make_mock_warehouse(store_id=uuid.uuid4(), wh_id=wh_id)

        service.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)

        with pytest.raises(WarehouseNotFoundError):
            await service.reserve_stock(
                warehouse_id=wh_id,
                variant_id=uuid.uuid4(),
                quantity=10,
            )

    async def test_reserve_stock_inactive_warehouse(self):
        """Service: reserve_stock raises when warehouse is inactive."""
        db, store, service = await self._make_service()
        wh_id = uuid.uuid4()
        mock_wh = _make_mock_warehouse(store_id=store.id, wh_id=wh_id, is_active=False)

        service.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)

        with pytest.raises(WarehouseInactiveError):
            await service.reserve_stock(
                warehouse_id=wh_id,
                variant_id=uuid.uuid4(),
                quantity=10,
            )

    async def test_commit_stock(self):
        """Service: commit_stock finalizes a reservation."""
        db, store, service = await self._make_service()
        wh_id = uuid.uuid4()
        v_id = uuid.uuid4()

        mock_inv = _make_mock_wh_inv(available=90, reserved=10)
        mock_res = _make_mock_reservation(
            store_id=store.id, warehouse_id=wh_id, variant_id=v_id,
            quantity=10, status=ReservationStatus.ACTIVE,
        )

        service.repo.get_by_id = AsyncMock(return_value=mock_res)
        service.inv_repo.get_or_create = AsyncMock(return_value=mock_inv)
        service.txn_repo.create = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        service.log_repo.create = AsyncMock(return_value=MagicMock())

        result = await service.commit_stock(uuid.uuid4())

        assert result.status == ReservationStatus.COMMITTED
        assert result.committed_at is not None
        # Reserved should be deducted
        assert mock_inv.reserved_stock == 0
        # Available should stay the same (not returned)
        assert mock_inv.available_stock == 90

    async def test_commit_stock_wrong_status(self):
        """Service: commit_stock raises when reservation is not ACTIVE."""
        db, store, service = await self._make_service()
        mock_res = _make_mock_reservation(
            store_id=store.id, status=ReservationStatus.RELEASED,
        )

        service.repo.get_by_id = AsyncMock(return_value=mock_res)

        with pytest.raises(InvalidReservationStateError):
            await service.commit_stock(uuid.uuid4())

    async def test_release_stock(self):
        """Service: release_stock returns stock to available."""
        db, store, service = await self._make_service()
        wh_id = uuid.uuid4()
        v_id = uuid.uuid4()

        mock_inv = _make_mock_wh_inv(available=90, reserved=10)
        mock_res = _make_mock_reservation(
            store_id=store.id, warehouse_id=wh_id, variant_id=v_id,
            quantity=10, status=ReservationStatus.ACTIVE,
        )

        service.repo.get_by_id = AsyncMock(return_value=mock_res)
        service.inv_repo.get_or_create = AsyncMock(return_value=mock_inv)
        service.txn_repo.create = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        service.log_repo.create = AsyncMock(return_value=MagicMock())

        result = await service.release_stock(uuid.uuid4())

        assert result.status == ReservationStatus.RELEASED
        # Available should increase by 10, reserved decrease by 10
        assert mock_inv.available_stock == 100
        assert mock_inv.reserved_stock == 0

    async def test_expire_reservation(self):
        """Service: expire_reservation releases stock as expired."""
        db, store, service = await self._make_service()
        wh_id = uuid.uuid4()
        v_id = uuid.uuid4()

        mock_inv = _make_mock_wh_inv(available=90, reserved=10)
        mock_res = _make_mock_reservation(
            store_id=store.id, warehouse_id=wh_id, variant_id=v_id,
            quantity=10, status=ReservationStatus.ACTIVE,
        )

        service.repo.get_by_id = AsyncMock(return_value=mock_res)
        service.inv_repo.get_or_create = AsyncMock(return_value=mock_inv)
        service.txn_repo.create = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        service.log_repo.create = AsyncMock(return_value=MagicMock())

        result = await service.expire_reservation(uuid.uuid4())

        assert result.status == ReservationStatus.EXPIRED
        assert mock_inv.available_stock == 100
        assert mock_inv.reserved_stock == 0

    async def test_expire_old_reservations(self):
        """Service: expire_old_reservations processes all overdue reservations."""
        db, store, service = await self._make_service()
        wh_id = uuid.uuid4()
        v_id = uuid.uuid4()

        mock_res1 = _make_mock_reservation(
            store_id=store.id, warehouse_id=wh_id, variant_id=v_id,
            quantity=5, status=ReservationStatus.ACTIVE,
        )
        mock_res2 = _make_mock_reservation(
            store_id=store.id, warehouse_id=wh_id, variant_id=v_id,
            quantity=3, status=ReservationStatus.ACTIVE,
        )

        service.repo.find_expired = AsyncMock(return_value=[mock_res1, mock_res2])
        mock_inv = _make_mock_wh_inv(available=100, reserved=10)
        service.inv_repo.get_or_create = AsyncMock(return_value=mock_inv)
        service.txn_repo.create = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        service.log_repo.create = AsyncMock(return_value=MagicMock())

        # Mock expire_reservation to update status directly so we count properly
        async def _mock_expire(res_id):
            if res_id == mock_res1.id:
                mock_res1.status = ReservationStatus.EXPIRED
            elif res_id == mock_res2.id:
                mock_res2.status = ReservationStatus.EXPIRED
            return mock_res1 if res_id == mock_res1.id else mock_res2
        service.expire_reservation = _mock_expire

        count = await service.expire_old_reservations()
        assert count == 2

    async def test_cancel_order(self):
        """Service: cancel_order releases all reservations for an order."""
        db, store, service = await self._make_service()
        wh_id = uuid.uuid4()
        v_id = uuid.uuid4()

        mock_res1 = _make_mock_reservation(
            store_id=store.id, warehouse_id=wh_id, variant_id=v_id,
            quantity=5, status=ReservationStatus.ACTIVE, order_id="ORD-123",
        )
        mock_res2 = _make_mock_reservation(
            store_id=store.id, warehouse_id=wh_id, variant_id=v_id,
            quantity=3, status=ReservationStatus.ACTIVE, order_id="ORD-123",
        )

        service.repo.get_by_order = AsyncMock(return_value=[mock_res1, mock_res2])
        # Need get_by_id for the internal release_stock -> _get_active_reservation call
        service.repo.get_by_id = AsyncMock(
            side_effect=lambda rid: mock_res1 if rid == mock_res1.id else mock_res2
        )
        mock_inv = _make_mock_wh_inv(available=100, reserved=10)
        service.inv_repo.get_or_create = AsyncMock(return_value=mock_inv)
        service.txn_repo.create = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        service.log_repo.create = AsyncMock(return_value=MagicMock())

        result = await service.cancel_order("ORD-123")
        assert len(result) == 2

    async def test_validate_stock_sufficient(self):
        """Service: validate_stock returns can_fulfill=True when stock available."""
        db, store, service = await self._make_service()
        mock_inv = _make_mock_wh_inv(available=50, reserved=10)

        service.inv_repo.get_by_variant_and_warehouse = AsyncMock(return_value=mock_inv)

        result = await service.validate_stock(
            warehouse_id=uuid.uuid4(),
            variant_id=uuid.uuid4(),
            requested_quantity=30,
        )
        assert result["can_fulfill"] is True
        assert result["available_stock"] == 50
        assert result["requested"] == 30

    async def test_validate_stock_insufficient(self):
        """Service: validate_stock returns can_fulfill=False when insufficient."""
        db, store, service = await self._make_service()
        mock_inv = _make_mock_wh_inv(available=20, reserved=10)

        service.inv_repo.get_by_variant_and_warehouse = AsyncMock(return_value=mock_inv)

        result = await service.validate_stock(
            warehouse_id=uuid.uuid4(),
            variant_id=uuid.uuid4(),
            requested_quantity=30,
        )
        assert result["can_fulfill"] is False
        assert result["available_stock"] == 20
        assert result["requested"] == 30

    async def test_get_dashboard_stats(self):
        """Service: get_dashboard_stats returns aggregated stats."""
        db, store, service = await self._make_service()
        mock_stats = {
            "active_reservations": 15,
            "reserved_stock_units": 250,
            "expired_today": 3,
            "reservation_success_rate": 94.2,
            "reservations_by_source": {"woocommerce": 10, "manual": 5},
        }

        service.repo.get_dashboard_stats = AsyncMock(return_value=mock_stats)

        stats = await service.get_dashboard_stats()
        assert stats["active_reservations"] == 15
        assert stats["reserved_stock_units"] == 250
        assert stats["reservation_success_rate"] == 94.2
        assert stats["reservations_by_source"]["woocommerce"] == 10

    async def test_woocommerce_reservation(self):
        """Service: reserve_for_woocommerce_order creates reservation with WC source."""
        db, store, service = await self._make_service()
        wh_id = uuid.uuid4()
        v_id = uuid.uuid4()

        mock_wh = _make_mock_warehouse(store_id=store.id, wh_id=wh_id)
        mock_variant = _make_mock_variant(variant_id=v_id)
        mock_inv = _make_mock_wh_inv(available=100)

        service.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)
        service.variant_repo.get_by_id = AsyncMock(return_value=mock_variant)
        service.inv_repo.get_or_create = AsyncMock(return_value=mock_inv)
        service.repo.find_active_by_variant_and_order = AsyncMock(return_value=None)
        mock_res = _make_mock_reservation(
            store_id=store.id, warehouse_id=wh_id, variant_id=v_id,
            quantity=5, order_id="WC-123",
        )
        service.repo.create = AsyncMock(return_value=mock_res)
        service.txn_repo.create = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        service.log_repo.create = AsyncMock(return_value=MagicMock())

        result = await service.reserve_for_woocommerce_order(
            warehouse_id=wh_id,
            variant_id=v_id,
            quantity=5,
            order_id="WC-123",
        )
        assert result is not None
        assert result.quantity == 5

    async def test_get_available_for_transfer(self):
        """Service: get_available_for_transfer returns available stock."""
        db, store, service = await self._make_service()
        mock_inv = _make_mock_wh_inv(available=75, reserved=25)

        service.inv_repo.get_by_variant_and_warehouse = AsyncMock(return_value=mock_inv)

        result = await service.get_available_for_transfer(
            warehouse_id=uuid.uuid4(),
            variant_id=uuid.uuid4(),
        )
        assert result == 75

    async def test_get_available_for_transfer_no_inv(self):
        """Service: get_available_for_transfer returns 0 when no inventory record."""
        db, store, service = await self._make_service()

        service.inv_repo.get_by_variant_and_warehouse = AsyncMock(return_value=None)

        result = await service.get_available_for_transfer(
            warehouse_id=uuid.uuid4(),
            variant_id=uuid.uuid4(),
        )
        assert result == 0


# ═══════════════════════════════════════════════════════════════════
# OWNERSHIP VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOwnershipValidation:
    """Tests for ownership/cross-store validation."""

    async def test_get_reservation_wrong_store(self):
        """Ownership: get_reservation raises error for wrong store."""
        db, store, service = await TestReservationService()._make_service()
        mock_res = _make_mock_reservation(
            store_id=uuid.uuid4(),  # Different store
        )

        service.repo.get_by_id = AsyncMock(return_value=mock_res)

        from app.inventory.exceptions import InvalidStoreOwnershipError
        with pytest.raises(InvalidStoreOwnershipError):
            await service.get_reservation(uuid.uuid4())

    async def test_release_stock_wrong_store(self):
        """Ownership: release_stock raises error for wrong store."""
        db, store, service = await TestReservationService()._make_service()
        mock_res = _make_mock_reservation(
            store_id=uuid.uuid4(),  # Different store
        )

        service.repo.get_by_id = AsyncMock(return_value=mock_res)

        from app.inventory.exceptions import InvalidStoreOwnershipError
        with pytest.raises(InvalidStoreOwnershipError):
            await service.release_stock(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════════
# CONCURRENCY TESTS (FOR UPDATE Locking)
# ═══════════════════════════════════════════════════════════════════

class TestConcurrency:
    """Tests that FOR UPDATE is used for stock mutations."""

    async def test_reserve_uses_for_update(self):
        """Concurrency: reserve_stock uses get_or_create with with_lock=True."""
        db, store, service = await TestReservationService()._make_service()
        wh_id = uuid.uuid4()
        v_id = uuid.uuid4()

        mock_wh = _make_mock_warehouse(store_id=store.id, wh_id=wh_id)
        mock_variant = _make_mock_variant(variant_id=v_id)
        mock_inv = _make_mock_wh_inv(available=100)

        service.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)
        service.variant_repo.get_by_id = AsyncMock(return_value=mock_variant)
        service.inv_repo.get_or_create = AsyncMock(return_value=mock_inv)
        service.repo.find_active_by_variant_and_order = AsyncMock(return_value=None)
        mock_res = _make_mock_reservation(
            store_id=store.id, warehouse_id=wh_id, variant_id=v_id, quantity=5,
        )
        service.repo.create = AsyncMock(return_value=mock_res)
        service.txn_repo.create = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        service.log_repo.create = AsyncMock(return_value=MagicMock())

        await service.reserve_stock(
            warehouse_id=wh_id,
            variant_id=v_id,
            quantity=5,
            reason="Concurrency test",
        )

        # Verify get_or_create was called with with_lock=True
        service.inv_repo.get_or_create.assert_called_once()
        _, kwargs = service.inv_repo.get_or_create.call_args
        assert kwargs.get("with_lock") is True

    async def test_commit_uses_for_update(self):
        """Concurrency: commit_stock uses get_or_create with with_lock=True."""
        db, store, service = await TestReservationService()._make_service()
        wh_id = uuid.uuid4()
        v_id = uuid.uuid4()

        mock_inv = _make_mock_wh_inv(available=90, reserved=10)
        mock_res = _make_mock_reservation(
            store_id=store.id, warehouse_id=wh_id, variant_id=v_id,
            quantity=10, status=ReservationStatus.ACTIVE,
        )

        service.repo.get_by_id = AsyncMock(return_value=mock_res)
        service.inv_repo.get_or_create = AsyncMock(return_value=mock_inv)
        service.txn_repo.create = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        service.log_repo.create = AsyncMock(return_value=MagicMock())

        await service.commit_stock(uuid.uuid4())

        # Verify get_or_create was called with with_lock=True
        service.inv_repo.get_or_create.assert_called_once()
        _, kwargs = service.inv_repo.get_or_create.call_args
        assert kwargs.get("with_lock") is True
