# ═══════════════════════════════════════════════════════════════
# domains / ecommerce / reservation_service.py
#
# PURPOSE: Stock reservations — order ke liye stock hold karo,
#          phir commit / release / expire / cancel.
#
#   reserve  → variant stock kam + ACTIVE reservation
#   commit   → COMMITTED (stock deducted hi rehta hai)
#   release  → RELEASED, stock wapas
#   expire   → EXPIRED, stock wapas
#   cancel_order → order ki saari ACTIVE reservations release
#
# USED BY: domains/ecommerce/reservation_routes.py, main.py
#
# NOTE:    Ported from kulsoom (backend-fte/app/inventory/
#          reservation_service.py). Stock changes InventoryService
#          ke through jaate hain (ledger + low-stock alerts free).
#          Changes vs kulsoom: reservation row lock (double
#          release se bachao), partial release hata diya (poori
#          reservation ek saath release hoti hai).
# ═══════════════════════════════════════════════════════════════

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.sdk.exceptions import AgentError
from src.sdk.models.base import Product, Variant
from src.sdk.models.inventory import (
    StockReservation, MOVEMENT_RESERVATION,
    RESERVATION_ACTIVE, RESERVATION_COMMITTED, RESERVATION_RELEASED,
    RESERVATION_EXPIRED, RESERVATION_CANCELLED, RESERVATION_STATUSES, RESERVATION_SOURCES,
)
from src.domains.ecommerce.inventory_service import InventoryService

logger = logging.getLogger(__name__)


class ReservationNotFoundError(AgentError):
    def __init__(self, reservation_id: int):
        super().__init__(f"Reservation {reservation_id} not found", code=404)


class InvalidReservationStateError(AgentError):
    def __init__(self, reservation_id: int, status: str, action: str):
        super().__init__(f"Cannot {action} reservation {reservation_id}: status is '{status}'", code=409)


class DuplicateReservationError(AgentError):
    def __init__(self, variant_id: int, order_id: str):
        super().__init__(
            f"Active reservation already exists for variant {variant_id} and order '{order_id}'", code=409
        )


class ReservationService:
    """Reservation operations scoped to one store."""

    def __init__(self, db: AsyncSession, store_id: int, user_id: Optional[int] = None):
        self.db = db
        self.store_id = store_id
        self.user_id = user_id
        self.inventory = InventoryService(db, store_id, user_id)

    # ─── Create ─────────────────────────────────────────────────

    async def reserve_stock(
        self,
        variant_id: int,
        quantity: int,
        order_id: Optional[str] = None,
        order_source: str = "manual",
        expires_in_minutes: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> StockReservation:
        if quantity <= 0:
            raise AgentError("Reservation quantity must be positive", code=400)
        if order_source not in RESERVATION_SOURCES:
            raise AgentError(f"Invalid order_source '{order_source}'", code=400)
        if expires_in_minutes is not None and expires_in_minutes <= 0:
            raise AgentError("expires_in_minutes must be positive", code=400)

        # Variant lock pehle — duplicate check aur stock check dono safe
        await self.inventory._get_variant_locked(variant_id)

        if order_id:
            existing = await self.db.execute(
                select(StockReservation.id).where(
                    StockReservation.store_id == self.store_id,
                    StockReservation.variant_id == variant_id,
                    StockReservation.order_id == order_id,
                    StockReservation.status == RESERVATION_ACTIVE,
                )
            )
            if existing.first():
                raise DuplicateReservationError(variant_id, order_id)

        reservation = StockReservation(
            store_id=self.store_id,
            variant_id=variant_id,
            order_id=order_id,
            order_source=order_source,
            quantity=quantity,
            status=RESERVATION_ACTIVE,
            reason=reason,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes))
            if expires_in_minutes else None,
            created_by=self.user_id,
        )
        self.db.add(reservation)
        await self.db.flush()

        await self.inventory.adjust_stock(
            variant_id=variant_id,
            quantity_change=-quantity,
            reason=reason or "stock reserved",
            movement_type=MOVEMENT_RESERVATION,
            reference_id=f"reservation:{reservation.id}",
            commit=False,
        )
        await self.db.commit()
        await self.db.refresh(reservation)
        logger.info(f"Reserved {quantity} of variant {variant_id} (reservation={reservation.id}, order={order_id})")
        return reservation

    # ─── State transitions ──────────────────────────────────────

    async def _get_locked_active(self, reservation_id: int, action: str) -> StockReservation:
        """Reservation row lock ke saath fetch; sirf ACTIVE par transition allowed."""
        result = await self.db.execute(
            select(StockReservation)
            .where(StockReservation.id == reservation_id, StockReservation.store_id == self.store_id)
            .with_for_update()
        )
        reservation = result.scalar_one_or_none()
        if reservation is None:
            raise ReservationNotFoundError(reservation_id)
        if reservation.status != RESERVATION_ACTIVE:
            raise InvalidReservationStateError(reservation_id, reservation.status, action)
        return reservation

    async def commit_stock(self, reservation_id: int) -> StockReservation:
        reservation = await self._get_locked_active(reservation_id, "commit")
        reservation.status = RESERVATION_COMMITTED
        reservation.committed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(reservation)
        return reservation

    async def _restore(self, reservation: StockReservation, new_status: str, reason: str, commit: bool) -> None:
        await self.inventory.adjust_stock(
            variant_id=reservation.variant_id,
            quantity_change=reservation.quantity,
            reason=reason,
            movement_type=MOVEMENT_RESERVATION,
            reference_id=f"reservation:{reservation.id}",
            commit=False,
        )
        reservation.status = new_status
        reservation.released_at = datetime.now(timezone.utc)
        if commit:
            await self.db.commit()
            await self.db.refresh(reservation)

    async def release_stock(self, reservation_id: int) -> StockReservation:
        reservation = await self._get_locked_active(reservation_id, "release")
        await self._restore(reservation, RESERVATION_RELEASED, "reservation released", commit=True)
        return reservation

    async def expire_reservation(self, reservation_id: int) -> StockReservation:
        reservation = await self._get_locked_active(reservation_id, "expire")
        await self._restore(reservation, RESERVATION_EXPIRED, "reservation expired", commit=True)
        return reservation

    async def cancel_order(self, order_id: str) -> list[StockReservation]:
        """Order ki saari ACTIVE reservations ek transaction mein cancel."""
        result = await self.db.execute(
            select(StockReservation)
            .where(
                StockReservation.store_id == self.store_id,
                StockReservation.order_id == order_id,
                StockReservation.status == RESERVATION_ACTIVE,
            )
            .order_by(StockReservation.id)
            .with_for_update()
        )
        reservations = list(result.scalars().all())
        for r in reservations:
            await self._restore(r, RESERVATION_CANCELLED, "order cancelled", commit=False)
        await self.db.commit()
        for r in reservations:
            await self.db.refresh(r)
        return reservations

    # ─── Queries ────────────────────────────────────────────────

    async def get_reservation(self, reservation_id: int) -> StockReservation:
        result = await self.db.execute(
            select(StockReservation).where(
                StockReservation.id == reservation_id, StockReservation.store_id == self.store_id
            )
        )
        reservation = result.scalar_one_or_none()
        if reservation is None:
            raise ReservationNotFoundError(reservation_id)
        return reservation

    async def list_reservations(
        self,
        status: Optional[str] = None,
        variant_id: Optional[int] = None,
        order_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[StockReservation], int]:
        if status and status not in RESERVATION_STATUSES:
            raise AgentError(f"Invalid status '{status}'", code=400)
        conditions = [StockReservation.store_id == self.store_id]
        if status:
            conditions.append(StockReservation.status == status)
        if variant_id is not None:
            conditions.append(StockReservation.variant_id == variant_id)
        if order_id:
            conditions.append(StockReservation.order_id == order_id)

        total = (await self.db.execute(
            select(func.count(StockReservation.id)).where(*conditions)
        )).scalar() or 0
        rows = (await self.db.execute(
            select(StockReservation).where(*conditions)
            .order_by(StockReservation.created_at.desc(), StockReservation.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        return list(rows), total

    async def validate_stock(self, variant_id: int, quantity: int) -> dict:
        """Kya itna stock abhi available hai? (read-only, lock nahi)"""
        result = await self.db.execute(select(Variant).where(Variant.id == variant_id))
        variant = result.scalar_one_or_none()
        # Ownership: variant isi store ka hona chahiye
        if variant is None or not await self._variant_in_store(variant):
            raise AgentError(f"Variant {variant_id} not found in this store", code=404)
        available = variant.inventory_quantity or 0
        return {
            "variant_id": variant_id,
            "requested": quantity,
            "available": available,
            "sufficient": available >= quantity,
        }

    async def _variant_in_store(self, variant: Variant) -> bool:
        r = await self.db.execute(
            select(Product.id).where(Product.id == variant.product_id, Product.store_id == self.store_id)
        )
        return r.first() is not None

    async def get_stats(self) -> dict:
        rows = (await self.db.execute(
            select(StockReservation.status, func.count(StockReservation.id), func.coalesce(func.sum(StockReservation.quantity), 0))
            .where(StockReservation.store_id == self.store_id)
            .group_by(StockReservation.status)
        )).all()
        by_status = {s: {"count": c, "units": int(u)} for s, c, u in rows}
        for s in RESERVATION_STATUSES:
            by_status.setdefault(s, {"count": 0, "units": 0})
        return {
            "active_reserved_units": by_status[RESERVATION_ACTIVE]["units"],
            "by_status": by_status,
        }


# ─── Expiry sweep (sab stores) ────────────────────────────────

async def expire_stale_reservations(db: AsyncSession) -> int:
    """ACTIVE reservations jinki expires_at guzar chuki hai, expire karo. Count return."""
    result = await db.execute(
        select(StockReservation.id, StockReservation.store_id).where(
            StockReservation.status == RESERVATION_ACTIVE,
            StockReservation.expires_at.is_not(None),
            StockReservation.expires_at <= datetime.now(timezone.utc),
        )
    )
    expired = 0
    for rid, store_id in result.all():
        try:
            await ReservationService(db, store_id).expire_reservation(rid)
            expired += 1
        except AgentError as exc:   # kisi aur ne pehle hi transition kar di
            await db.rollback()
            logger.debug(f"Skip expiring reservation {rid}: {exc.message}")
    if expired:
        logger.info(f"Expired {expired} stale reservation(s)")
    return expired
