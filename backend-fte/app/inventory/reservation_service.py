"""
Store-centric Reservation Engine.

Reservations lock inventory at the *store* level: each reservation
decrements the variant's available stock (`ProductVariant.inventory_quantity`)
under a `SELECT ... FOR UPDATE` lock and records the reservation in the
`inventory_reservations` table.

Lifecycle: PENDING -> ACTIVE -> COMMITTED / RELEASED / EXPIRED / CANCELLED

- reserve_stock:  decrement variant stock + create ACTIVE reservation
- commit_stock:   mark COMMITTED (fulfilled — stock stays deducted)
- release_stock:  mark RELEASED and restore variant stock
- expire:         mark EXPIRED and restore variant stock
- cancel_order:   release all ACTIVE reservations for an order

All failures raise domain exceptions from app.inventory.exceptions.
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Store, ProductVariant, InventoryReservation, InventoryLog
from app.inventory.constants import (
    ReservationStatus, ReservationSource, InventoryAction,
)
from app.inventory.aggregation_cache import aggregation_cache
from app.inventory.exceptions import (
    VariantNotFoundError,
    InvalidStoreOwnershipError,
    ReservationNotFoundError,
    InsufficientStockForReservationError,
    InvalidReservationStateError,
    DuplicateReservationError,
)

logger = logging.getLogger(__name__)


class ReservationRepository:
    """Data access for InventoryReservation records."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, reservation_id: uuid.UUID) -> Optional[InventoryReservation]:
        result = await self.db.execute(
            select(InventoryReservation).where(
                InventoryReservation.id == reservation_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_order(
        self, store_id: uuid.UUID, order_id: str,
    ) -> list[InventoryReservation]:
        result = await self.db.execute(
            select(InventoryReservation).where(
                InventoryReservation.store_id == store_id,
                InventoryReservation.order_id == order_id,
            ).order_by(InventoryReservation.created_at.asc())
        )
        return list(result.scalars().all())

    async def list(
        self,
        store_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        variant_id: Optional[uuid.UUID] = None,
    ) -> tuple[list[InventoryReservation], int, int]:
        """Paginated reservation list plus total and active counts."""
        conditions = [InventoryReservation.store_id == store_id]
        if variant_id is not None:
            conditions.append(InventoryReservation.variant_id == variant_id)

        total_result = await self.db.execute(
            select(func.count(InventoryReservation.id)).where(*conditions)
        )
        total = total_result.scalar() or 0

        active_result = await self.db.execute(
            select(func.count(InventoryReservation.id)).where(
                *conditions,
                InventoryReservation.status.in_(
                    [ReservationStatus.ACTIVE, ReservationStatus.PENDING]
                ),
            )
        )
        active_count = active_result.scalar() or 0

        result = await self.db.execute(
            select(InventoryReservation)
            .where(*conditions)
            .order_by(InventoryReservation.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total, active_count

    async def get_active_for_variant_order(
        self, store_id: uuid.UUID, variant_id: uuid.UUID, order_id: str,
    ) -> Optional[InventoryReservation]:
        """Find an existing ACTIVE reservation for the same variant/order."""
        result = await self.db.execute(
            select(InventoryReservation).where(
                InventoryReservation.store_id == store_id,
                InventoryReservation.variant_id == variant_id,
                InventoryReservation.order_id == order_id,
                InventoryReservation.status.in_(
                    [ReservationStatus.ACTIVE, ReservationStatus.PENDING]
                ),
            ).limit(1)
        )
        return result.scalar_one_or_none()


class ReservationService:
    """Store-level inventory reservation orchestration."""

    def __init__(
        self,
        db: AsyncSession,
        store: Store,
        user_id: Optional[uuid.UUID] = None,
    ):
        self.db = db
        self.store = store
        self.user_id = user_id
        self.repo = ReservationRepository(db)
        self.logger = logging.getLogger(f"{__name__}.ReservationService")

    # ═══════════════════════════════════════════════════════════════
    # CORE OPERATIONS
    # ═══════════════════════════════════════════════════════════════

    async def reserve_stock(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        order_id: Optional[str] = None,
        order_source: ReservationSource = ReservationSource.MANUAL,
        expires_in_minutes: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> InventoryReservation:
        """
        Reserve `quantity` units of a variant for the store.

        The variant row is locked with FOR UPDATE; available stock is
        decremented and an ACTIVE reservation is created atomically.
        """
        if quantity <= 0:
            raise ValueError("Reservation quantity must be positive")

        # Lock the variant row to prevent double reservations
        variant = await self._get_locked_variant(variant_id)
        if variant is None:
            raise VariantNotFoundError(str(variant_id))
        self._ensure_store_owns_variant(variant)

        available = variant.inventory_quantity
        if available < quantity:
            raise InsufficientStockForReservationError(
                variant_id=str(variant_id),
                requested=quantity,
                available=available,
            )

        # Duplicate active reservation guard (per variant + order)
        if order_id:
            existing = await self.repo.get_active_for_variant_order(
                self.store.id, variant_id, order_id,
            )
            if existing:
                raise DuplicateReservationError(str(variant_id), order_id)

        # Decrement available stock
        variant.inventory_quantity = available - quantity

        expires_at = None
        if expires_in_minutes:
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)

        reservation = InventoryReservation(
            store_id=self.store.id,
            product_id=variant.product_id,
            variant_id=variant_id,
            order_id=order_id,
            order_source=order_source,
            quantity=quantity,
            status=ReservationStatus.ACTIVE,
            expires_at=expires_at,
        )
        self.db.add(reservation)
        await self.db.flush()

        # Audit log
        if variant.product_id:
            await self._log(
                variant_id=variant_id,
                action=InventoryAction.STOCK_RESERVED.value,
                details={
                    "reservation_id": str(reservation.id),
                    "order_id": order_id,
                    "quantity": quantity,
                    "available_after": variant.inventory_quantity,
                    "reason": reason,
                },
            )

        await self.db.commit()
        await self.db.refresh(reservation)
        await self._invalidate_cache()

        self.logger.info(
            "Reserved %d units of variant %s (order=%s, reservation=%s)",
            quantity, variant_id, order_id, reservation.id,
        )
        return reservation

    async def commit_stock(self, reservation_id: uuid.UUID) -> InventoryReservation:
        """Commit an ACTIVE/PENDING reservation — mark fulfilled."""
        reservation = await self._get_owned_reservation(reservation_id)
        if reservation.status not in (
            ReservationStatus.ACTIVE, ReservationStatus.PENDING,
        ):
            raise InvalidReservationStateError(
                str(reservation.id), reservation.status.value, "commit",
            )

        reservation.status = ReservationStatus.COMMITTED
        reservation.committed_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(reservation)
        await self._invalidate_cache()

        self.logger.info("Reservation %s committed", reservation.id)
        return reservation

    async def release_stock(
        self,
        reservation_id: uuid.UUID,
        quantity: Optional[int] = None,
    ) -> InventoryReservation:
        """Release a reservation — restore stock to available."""
        reservation = await self._get_owned_reservation(reservation_id)
        if reservation.status not in (
            ReservationStatus.ACTIVE, ReservationStatus.PENDING,
        ):
            raise InvalidReservationStateError(
                str(reservation.id), reservation.status.value, "release",
            )

        quantity = quantity if quantity is not None else reservation.quantity

        # Restore available stock on the variant
        if reservation.variant_id:
            variant = await self._get_variant(reservation.variant_id)
            if variant:
                variant.inventory_quantity += quantity

        reservation.status = ReservationStatus.RELEASED
        reservation.released_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(reservation)
        await self._invalidate_cache()

        self.logger.info("Reservation %s released (%d units)", reservation.id, quantity)
        return reservation

    async def expire_reservation(self, reservation_id: uuid.UUID) -> InventoryReservation:
        """Expire a reservation — release stock with EXPIRED status."""
        reservation = await self._get_owned_reservation(reservation_id)
        if reservation.status not in (
            ReservationStatus.ACTIVE, ReservationStatus.PENDING,
        ):
            raise InvalidReservationStateError(
                str(reservation.id), reservation.status.value, "expire",
            )

        if reservation.variant_id:
            variant = await self._get_variant(reservation.variant_id)
            if variant:
                variant.inventory_quantity += reservation.quantity

        reservation.status = ReservationStatus.EXPIRED
        reservation.released_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(reservation)
        await self._invalidate_cache()
        return reservation

    async def cancel_order(self, order_id: str) -> list[InventoryReservation]:
        """Release all ACTIVE/PENDING reservations for an order."""
        reservations = await self.repo.get_by_order(self.store.id, order_id)
        released = []
        for reservation in reservations:
            if reservation.status in (
                ReservationStatus.ACTIVE, ReservationStatus.PENDING,
            ):
                released.append(await self.release_stock(reservation.id))
        return released

    # ═══════════════════════════════════════════════════════════════
    # QUERIES
    # ═══════════════════════════════════════════════════════════════

    async def get_reservation(self, reservation_id: uuid.UUID) -> InventoryReservation:
        reservation = await self.repo.get_by_id(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(str(reservation_id))
        self._ensure_store_owns_reservation(reservation)
        return reservation

    async def get_reservations(
        self,
        page: int = 1,
        page_size: int = 20,
        variant_id: Optional[uuid.UUID] = None,
    ) -> tuple[list[InventoryReservation], int, int]:
        return await self.repo.list(
            store_id=self.store.id,
            page=page,
            page_size=page_size,
            variant_id=variant_id,
        )

    async def get_order_reservations(self, order_id: str) -> list[InventoryReservation]:
        return await self.repo.get_by_order(self.store.id, order_id)

    async def validate_stock(
        self,
        variant_id: uuid.UUID,
        requested_quantity: int,
    ) -> dict:
        """Check whether the store has enough stock for a reservation."""
        variant = await self._get_variant(variant_id)
        if variant is None:
            raise VariantNotFoundError(str(variant_id))
        self._ensure_store_owns_variant(variant)

        available = variant.inventory_quantity
        return {
            "variant_id": str(variant_id),
            "available_quantity": available,
            "requested_quantity": requested_quantity,
            "sufficient": available >= requested_quantity,
        }

    async def get_dashboard_stats(self) -> dict:
        """Reservation statistics for dashboards."""
        conditions = [InventoryReservation.store_id == self.store.id]
        active_statuses = [ReservationStatus.ACTIVE, ReservationStatus.PENDING]

        active_count_result = await self.db.execute(
            select(func.count(InventoryReservation.id)).where(
                *conditions,
                InventoryReservation.status.in_(active_statuses),
            )
        )
        active_reservations = active_count_result.scalar() or 0

        reserved_units_result = await self.db.execute(
            select(func.coalesce(func.sum(InventoryReservation.quantity), 0)).where(
                *conditions,
                InventoryReservation.status.in_(active_statuses),
            )
        )
        reserved_stock_units = reserved_units_result.scalar() or 0

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        expired_today_result = await self.db.execute(
            select(func.count(InventoryReservation.id)).where(
                *conditions,
                InventoryReservation.status == ReservationStatus.EXPIRED,
                InventoryReservation.released_at >= today_start,
            )
        )
        expired_today = expired_today_result.scalar() or 0

        by_source: dict[str, int] = {}
        source_result = await self.db.execute(
            select(InventoryReservation.order_source, func.count(InventoryReservation.id))
            .where(*conditions)
            .group_by(InventoryReservation.order_source)
        )
        for source, count in source_result.all():
            by_source[source.value if hasattr(source, "value") else str(source)] = count

        return {
            "active_reservations": active_reservations,
            "reserved_stock_units": reserved_stock_units,
            "expired_today": expired_today,
            "reservation_success_rate": 100.0,
            "reservations_by_source": by_source,
        }

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ═══════════════════════════════════════════════════════════════

    async def _get_locked_variant(
        self, variant_id: uuid.UUID,
    ) -> Optional[ProductVariant]:
        """Fetch a variant with FOR UPDATE + eager product for ownership checks."""
        result = await self.db.execute(
            select(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .where(ProductVariant.id == variant_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def _get_variant(self, variant_id: uuid.UUID) -> Optional[ProductVariant]:
        result = await self.db.execute(
            select(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .where(ProductVariant.id == variant_id)
        )
        return result.scalar_one_or_none()

    async def _get_owned_reservation(
        self, reservation_id: uuid.UUID,
    ) -> InventoryReservation:
        reservation = await self.repo.get_by_id(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(str(reservation_id))
        self._ensure_store_owns_reservation(reservation)
        return reservation

    async def _log(
        self,
        variant_id: uuid.UUID,
        action: str,
        details: dict,
    ) -> None:
        entry = InventoryLog(
            variant_id=variant_id,
            action=action,
            details=details,
            performed_by=self.user_id,
        )
        self.db.add(entry)

    async def _invalidate_cache(self) -> None:
        try:
            await aggregation_cache.invalidate_store(self.store.id)
        except Exception as cache_exc:
            self.logger.warning(
                "Aggregation cache invalidation failed: %s", cache_exc,
            )

    def _ensure_store_owns_variant(self, variant: ProductVariant) -> None:
        if variant.product and str(variant.product.store_id) != str(self.store.id):
            raise InvalidStoreOwnershipError("Variant", str(variant.id))

    def _ensure_store_owns_reservation(
        self, reservation: InventoryReservation,
    ) -> None:
        if str(reservation.store_id) != str(self.store.id):
            raise InvalidStoreOwnershipError("Reservation", str(reservation.id))
