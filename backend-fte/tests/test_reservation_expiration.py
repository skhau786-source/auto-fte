"""
Tests for the automatic reservation-expiration sweep
(app.inventory.reservation_service.expire_stale_reservations).

Covers:
- a genuinely expired reservation is auto-expired and its stock released
- a reservation that is no longer eligible by the time it's re-checked
  (already committed/released/cancelled/expired, or not actually past
  expires_at) is left untouched — this is the idempotency/race-safety
  guarantee: the sweep always re-validates under lock immediately before
  acting, so a second/overlapping run of the sweep, or a user action that
  raced with it, never gets double-processed
- multiple expired reservations are each handled independently
- a failure processing one reservation does not block the others

All tests are mock-based (no PostgreSQL required), matching the rest of
this project's test suite. Because the database session is mocked, these
tests exercise expire_stale_reservations' own control flow (its
check-then-act-under-lock logic) rather than the real SQL WHERE clause in
ReservationRepository.get_expired_ids — that clause is exercised for real
whenever this runs against an actual PostgreSQL database.
"""

import uuid
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.inventory.reservation_service import expire_stale_reservations
from app.inventory.constants import ReservationStatus


_UNSET = object()


def _make_reservation(status=ReservationStatus.ACTIVE, quantity=5, variant_id=_UNSET):
    res = MagicMock()
    res.id = uuid.uuid4()
    res.store_id = uuid.uuid4()
    res.variant_id = uuid.uuid4() if variant_id is _UNSET else variant_id
    res.quantity = quantity
    res.status = status
    res.expires_at = None
    res.released_at = None
    return res


def _make_variant(quantity=100, variant_id=None):
    variant = MagicMock()
    variant.id = variant_id or uuid.uuid4()
    variant.inventory_quantity = quantity
    return variant


def _db_sequential_mixed(*configs):
    """
    db.execute() returns each configured MagicMock result in call order.

    Each config is ("scalars", [values]) for a `.scalars().all()` query
    (used by get_expired_ids), or ("scalar_one", value) for a
    `.scalar_one_or_none()` query (used by the per-row re-fetches).
    """
    db = AsyncMock()
    results = []
    for kind, value in configs:
        r = MagicMock()
        if kind == "scalars":
            r.scalars.return_value.all.return_value = value
        else:
            r.scalar_one_or_none.return_value = value
        results.append(r)
    db.execute.side_effect = results
    return db


class TestAutoExpireHappyPath:
    @pytest.mark.asyncio
    async def test_expires_stale_reservation_and_restores_stock(self):
        now = datetime.now(timezone.utc)
        res = _make_reservation(status=ReservationStatus.ACTIVE, quantity=5)
        res.expires_at = now - timedelta(minutes=1)
        variant = _make_variant(quantity=20, variant_id=res.variant_id)

        db = _db_sequential_mixed(
            ("scalars", [res.id]),
            ("scalar_one", res),
            ("scalar_one", variant),
        )

        expired = await expire_stale_reservations(db, now=now)

        assert expired == [res.id]
        assert res.status == ReservationStatus.EXPIRED
        assert res.released_at == now
        assert variant.inventory_quantity == 25
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_expires_multiple_reservations_independently(self):
        now = datetime.now(timezone.utc)
        res1 = _make_reservation(status=ReservationStatus.ACTIVE, quantity=3)
        res1.expires_at = now - timedelta(minutes=1)
        v1 = _make_variant(quantity=10, variant_id=res1.variant_id)

        res2 = _make_reservation(status=ReservationStatus.ACTIVE, quantity=7)
        res2.expires_at = now - timedelta(minutes=2)
        v2 = _make_variant(quantity=50, variant_id=res2.variant_id)

        db = _db_sequential_mixed(
            ("scalars", [res1.id, res2.id]),
            ("scalar_one", res1), ("scalar_one", v1),
            ("scalar_one", res2), ("scalar_one", v2),
        )

        expired = await expire_stale_reservations(db, now=now)

        assert set(expired) == {res1.id, res2.id}
        assert res1.status == ReservationStatus.EXPIRED
        assert res2.status == ReservationStatus.EXPIRED
        assert v1.inventory_quantity == 13
        assert v2.inventory_quantity == 57
        assert db.commit.await_count == 2

    @pytest.mark.asyncio
    async def test_expires_reservation_with_no_variant_without_crashing(self):
        """PENDING team-level-style reservation with no variant_id set."""
        now = datetime.now(timezone.utc)
        res = _make_reservation(status=ReservationStatus.PENDING, quantity=2, variant_id=None)
        res.expires_at = now - timedelta(minutes=1)

        db = _db_sequential_mixed(
            ("scalars", [res.id]),
            ("scalar_one", res),
        )

        expired = await expire_stale_reservations(db, now=now)

        assert expired == [res.id]
        assert res.status == ReservationStatus.EXPIRED


class TestAutoExpireSkipsIneligibleRows:
    """
    The sweep always re-fetches each candidate under FOR UPDATE and
    re-validates it immediately before acting — this is what makes it
    idempotent and race-safe. These tests drive that re-check path
    directly by making the re-fetch return a row that no longer
    qualifies, regardless of why it showed up as a candidate.
    """

    @pytest.mark.asyncio
    async def test_skips_reservation_not_actually_expired_yet(self):
        now = datetime.now(timezone.utc)
        res = _make_reservation(status=ReservationStatus.ACTIVE)
        res.expires_at = now + timedelta(minutes=10)  # future

        db = _db_sequential_mixed(
            ("scalars", [res.id]),
            ("scalar_one", res),
        )

        expired = await expire_stale_reservations(db, now=now)

        assert expired == []
        assert res.status == ReservationStatus.ACTIVE
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_already_committed_reservation(self):
        now = datetime.now(timezone.utc)
        res = _make_reservation(status=ReservationStatus.COMMITTED)
        res.expires_at = now - timedelta(minutes=5)

        db = _db_sequential_mixed(("scalars", [res.id]), ("scalar_one", res))

        expired = await expire_stale_reservations(db, now=now)

        assert expired == []
        assert res.status == ReservationStatus.COMMITTED
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_already_cancelled_reservation(self):
        now = datetime.now(timezone.utc)
        res = _make_reservation(status=ReservationStatus.CANCELLED)
        res.expires_at = now - timedelta(minutes=5)

        db = _db_sequential_mixed(("scalars", [res.id]), ("scalar_one", res))

        expired = await expire_stale_reservations(db, now=now)

        assert expired == []
        assert res.status == ReservationStatus.CANCELLED
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_already_released_reservation(self):
        now = datetime.now(timezone.utc)
        res = _make_reservation(status=ReservationStatus.RELEASED)
        res.expires_at = now - timedelta(minutes=5)

        db = _db_sequential_mixed(("scalars", [res.id]), ("scalar_one", res))

        expired = await expire_stale_reservations(db, now=now)

        assert expired == []
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_repeated_sweep_is_idempotent_for_already_expired_row(self):
        """
        Simulates a second sweep run seeing a reservation that a prior
        run (or a concurrent one) already expired — nothing should
        happen, and no stock should be double-credited.
        """
        now = datetime.now(timezone.utc)
        res = _make_reservation(status=ReservationStatus.EXPIRED)
        res.expires_at = now - timedelta(minutes=5)

        db = _db_sequential_mixed(("scalars", [res.id]), ("scalar_one", res))

        expired = await expire_stale_reservations(db, now=now)

        assert expired == []
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_row_deleted_before_recheck(self):
        now = datetime.now(timezone.utc)
        missing_id = uuid.uuid4()

        db = _db_sequential_mixed(("scalars", [missing_id]), ("scalar_one", None))

        expired = await expire_stale_reservations(db, now=now)

        assert expired == []
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_candidates_is_a_safe_no_op(self):
        now = datetime.now(timezone.utc)
        db = _db_sequential_mixed(("scalars", []))

        expired = await expire_stale_reservations(db, now=now)

        assert expired == []
        db.commit.assert_not_awaited()


class TestAutoExpireErrorHandling:
    @pytest.mark.asyncio
    async def test_failure_on_one_reservation_does_not_block_the_rest(self):
        now = datetime.now(timezone.utc)
        res1 = _make_reservation(status=ReservationStatus.ACTIVE, quantity=3)
        res1.expires_at = now - timedelta(minutes=1)
        v1 = _make_variant(quantity=10, variant_id=res1.variant_id)

        res2 = _make_reservation(status=ReservationStatus.ACTIVE, quantity=7)
        res2.expires_at = now - timedelta(minutes=2)
        v2 = _make_variant(quantity=50, variant_id=res2.variant_id)

        db = _db_sequential_mixed(
            ("scalars", [res1.id, res2.id]),
            ("scalar_one", res1), ("scalar_one", v1),
            ("scalar_one", res2), ("scalar_one", v2),
        )
        # First commit (for res1) blows up; second (for res2) succeeds.
        db.commit = AsyncMock(side_effect=[Exception("db exploded"), None])

        expired = await expire_stale_reservations(db, now=now)

        assert expired == [res2.id]
        db.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_exception_fetching_candidates_propagates(self):
        """
        A failure before any row is touched (e.g. the initial listing
        query itself fails) should propagate rather than being silently
        swallowed — there's nothing safe to partially process yet.
        """
        db = AsyncMock()
        db.execute.side_effect = RuntimeError("connection lost")

        with pytest.raises(RuntimeError):
            await expire_stale_reservations(db, now=datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════════════════════
# Real-database regression test (gated, see tests/conftest.py::_postgres_available)
# ═══════════════════════════════════════════════════════════════════
#
# Everything above is mock-based and only exercises expire_stale_reservations'
# Python control flow — it cannot verify that ReservationRepository.get_expired_ids'
# actual SQL WHERE clause (status IN (...), expires_at <= now) correctly
# selects/excludes rows in a real database. This test does, and it is
# skipped automatically (not silently assumed to pass) when no PostgreSQL
# is reachable — it did NOT run in the environment this was written in;
# see the final report for that caveat stated plainly.

from app.models import InventoryReservation, Store, ProductVariant  # noqa: E402


class TestAutoExpireRealDatabaseSchema:
    @pytest.mark.asyncio
    async def test_sweep_expires_only_the_actually_expired_row(
        self, db_session, test_store: Store, test_variant: ProductVariant,
    ):
        """
        Creates three real reservations against the real variant row —
        one expired, one still in the future, one already committed —
        and asserts the sweep's real SQL query picks out exactly the
        expired one, restores its stock, and leaves the other two alone.
        """
        now = datetime.now(timezone.utc)
        starting_quantity = test_variant.inventory_quantity

        expired_res = InventoryReservation(
            store_id=test_store.id,
            variant_id=test_variant.id,
            product_id=test_variant.product_id,
            quantity=5,
            status=ReservationStatus.ACTIVE,
            expires_at=now - timedelta(minutes=1),
        )
        future_res = InventoryReservation(
            store_id=test_store.id,
            variant_id=test_variant.id,
            product_id=test_variant.product_id,
            quantity=3,
            status=ReservationStatus.ACTIVE,
            expires_at=now + timedelta(hours=1),
        )
        committed_res = InventoryReservation(
            store_id=test_store.id,
            variant_id=test_variant.id,
            product_id=test_variant.product_id,
            quantity=2,
            status=ReservationStatus.COMMITTED,
            expires_at=now - timedelta(minutes=1),  # past expiry, but not ACTIVE/PENDING
        )
        db_session.add_all([expired_res, future_res, committed_res])
        # Simulate that reserving this stock already decremented the variant,
        # the way ReservationService.reserve_stock does.
        test_variant.inventory_quantity = starting_quantity - 5 - 3 - 2
        await db_session.commit()

        expired_ids = await expire_stale_reservations(db_session, now=now)

        assert expired_ids == [expired_res.id]

        await db_session.refresh(expired_res)
        await db_session.refresh(future_res)
        await db_session.refresh(committed_res)
        await db_session.refresh(test_variant)

        assert expired_res.status == ReservationStatus.EXPIRED
        assert future_res.status == ReservationStatus.ACTIVE  # untouched — not yet expired
        assert committed_res.status == ReservationStatus.COMMITTED  # untouched — not ACTIVE/PENDING
        # Only the expired reservation's 5 units come back.
        assert test_variant.inventory_quantity == starting_quantity - 3 - 2 + 5

        # Running the sweep again must be a no-op: the row is no longer
        # ACTIVE/PENDING, so it can never be double-credited.
        again = await expire_stale_reservations(db_session, now=now)
        assert again == []
        await db_session.refresh(test_variant)
        assert test_variant.inventory_quantity == starting_quantity - 3 - 2 + 5
