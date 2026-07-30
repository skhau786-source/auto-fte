"""
Reservation Engine Service — Phase 3.

Manages the full reservation lifecycle:
- reserve_stock: Lock inventory with SELECT FOR UPDATE, create reservation, update stock
- commit_stock: Finalize a reservation (deduct from reserved, no return to available)
- release_stock: Release reserved stock back to available
- expire_reservation: Auto-release expired reservations (with audit trail)
- cancel_order: Release all reservations for an order

Concurrency:
- Every inventory mutation uses SELECT FOR UPDATE
- All writes within a single atomic transaction
- No lost updates, no double reservations, no negative stock
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import (
    Store, Warehouse, WarehouseInventory, ProductVariant,
    InventoryReservation,
)
from app.inventory.constants import (
    ReservationStatus, ReservationSource, InventoryAction, TransactionType,
)
from app.inventory.repository import TransactionRepository, LogRepository, VariantRepository
from app.warehouse.repository import WarehouseRepository, WarehouseInventoryRepository
from app.warehouse.exceptions import (
    ReservationNotFoundError, InsufficientStockForReservationError,
    InvalidReservationStateError, DuplicateReservationError,
    WarehouseNotFoundError, WarehouseInactiveError,
)
from app.inventory.exceptions import VariantNotFoundError
from app.warehouse.aggregation_cache import aggregation_cache

# Reservations expire after this duration by default
DEFAULT_RESERVATION_TTL_MINUTES = 60
MAX_RESERVATION_TTL_MINUTES = 10080  # 7 days


class ReservationRepository:
    """Data access for InventoryReservation records."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        store_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        quantity: int,
        inventory_id: Optional[uuid.UUID] = None,
        product_id: Optional[uuid.UUID] = None,
        order_id: Optional[str] = None,
        order_source: ReservationSource = ReservationSource.MANUAL,
        status: ReservationStatus = ReservationStatus.ACTIVE,
        expires_at: Optional[datetime] = None,
        meta_data: Optional[dict] = None,
    ) -> InventoryReservation:
        """Create a new reservation record."""
        reservation = InventoryReservation(
            store_id=store_id,
            warehouse_id=warehouse_id,
            inventory_id=inventory_id,
            product_id=product_id,
            variant_id=variant_id,
            order_id=order_id,
            order_source=order_source,
            quantity=quantity,
            status=status,
            expires_at=expires_at,
            meta_data=meta_data or {},
        )
        self.db.add(reservation)
        await self.db.flush()
        return reservation

    async def get_by_id(self, reservation_id: uuid.UUID) -> Optional[InventoryReservation]:
        """Get a reservation by ID."""
        result = await self.db.execute(
            select(InventoryReservation)
            .options(
                joinedload(InventoryReservation.warehouse),
                joinedload(InventoryReservation.variant),
                joinedload(InventoryReservation.product),
            )
            .where(InventoryReservation.id == reservation_id)
        )
        return result.unique().scalar_one_or_none()

    async def get_by_order(
        self, store_id: uuid.UUID, order_id: str,
    ) -> list[InventoryReservation]:
        """Get all reservations for an order."""
        result = await self.db.execute(
            select(InventoryReservation)
            .options(
                joinedload(InventoryReservation.warehouse),
                joinedload(InventoryReservation.variant),
            )
            .where(
                InventoryReservation.store_id == store_id,
                InventoryReservation.order_id == order_id,
            )
            .order_by(InventoryReservation.created_at.desc())
        )
        return list(result.unique().scalars().all())

    async def list_active(
        self,
        store_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        warehouse_id: Optional[uuid.UUID] = None,
        variant_id: Optional[uuid.UUID] = None,
    ) -> tuple[list[InventoryReservation], int, int]:
        """
        List active (non-committed, non-released, non-expired) reservations.
        Returns (reservations, total, active_count).
        """
        query = select(InventoryReservation).options(
            joinedload(InventoryReservation.warehouse),
            joinedload(InventoryReservation.variant),
        )
        count_query = select(func.count(InventoryReservation.id))
        active_count_query = select(func.count(InventoryReservation.id))

        conditions = [InventoryReservation.store_id == store_id]

        if warehouse_id:
            conditions.append(InventoryReservation.warehouse_id == warehouse_id)
        if variant_id:
            conditions.append(InventoryReservation.variant_id == variant_id)

        where_clause = and_(*conditions)
        final_query = query.where(where_clause).order_by(
            InventoryReservation.created_at.desc()
        )
        count_query = count_query.where(where_clause)

        # Active count: status in (PENDING, ACTIVE)
        active_conditions = conditions + [
            InventoryReservation.status.in_([
                ReservationStatus.PENDING,
                ReservationStatus.ACTIVE,
            ])
        ]
        active_count_query = active_count_query.where(and_(*active_conditions))

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        active_result = await self.db.execute(active_count_query)
        active_count = active_result.scalar() or 0

        offset = (page - 1) * page_size
        final_query = final_query.offset(offset).limit(page_size)

        result = await self.db.execute(final_query)
        reservations = list(result.unique().scalars().all())

        return reservations, total, active_count

    async def update_status(
        self,
        reservation_id: uuid.UUID,
        status: ReservationStatus,
        **extra_fields,
    ) -> Optional[InventoryReservation]:
        """Update reservation status and optional lifecycle timestamps."""
        reservation = await self.get_by_id(reservation_id)
        if reservation is None:
            return None

        reservation.status = status
        for field, value in extra_fields.items():
            if hasattr(reservation, field) and value is not None:
                setattr(reservation, field, value)
        await self.db.flush()
        return reservation

    async def find_active_by_variant_and_order(
        self,
        store_id: uuid.UUID,
        variant_id: uuid.UUID,
        warehouse_id: uuid.UUID,
        order_id: str,
    ) -> Optional[InventoryReservation]:
        """Find an active reservation for a specific variant/order/warehouse combo."""
        result = await self.db.execute(
            select(InventoryReservation).where(
                InventoryReservation.store_id == store_id,
                InventoryReservation.variant_id == variant_id,
                InventoryReservation.warehouse_id == warehouse_id,
                InventoryReservation.order_id == order_id,
                InventoryReservation.status.in_([
                    ReservationStatus.PENDING,
                    ReservationStatus.ACTIVE,
                ]),
            ).limit(1)
        )
        return result.scalar_one_or_none()

    async def find_expired(self, store_id: uuid.UUID) -> list[InventoryReservation]:
        """Find all expired reservations for a store."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(InventoryReservation).where(
                InventoryReservation.store_id == store_id,
                InventoryReservation.status.in_([
                    ReservationStatus.PENDING,
                    ReservationStatus.ACTIVE,
                ]),
                InventoryReservation.expires_at.isnot(None),
                InventoryReservation.expires_at <= now,
            )
        )
        return list(result.scalars().all())

    async def get_dashboard_stats(self, store_id: uuid.UUID) -> dict:
        """Get reservation dashboard statistics."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Active reservations count
        active_result = await self.db.execute(
            select(func.count(InventoryReservation.id)).where(
                InventoryReservation.store_id == store_id,
                InventoryReservation.status.in_([
                    ReservationStatus.PENDING,
                    ReservationStatus.ACTIVE,
                ]),
            )
        )
        active_count = active_result.scalar() or 0

        # Total reserved stock units
        reserved_result = await self.db.execute(
            select(func.coalesce(func.sum(InventoryReservation.quantity), 0)).where(
                InventoryReservation.store_id == store_id,
                InventoryReservation.status.in_([
                    ReservationStatus.PENDING,
                    ReservationStatus.ACTIVE,
                ]),
            )
        )
        reserved_units = reserved_result.scalar() or 0

        # Expired today
        expired_result = await self.db.execute(
            select(func.count(InventoryReservation.id)).where(
                InventoryReservation.store_id == store_id,
                InventoryReservation.status == ReservationStatus.EXPIRED,
                InventoryReservation.updated_at >= today_start,
            )
        )
        expired_today = expired_result.scalar() or 0

        # Total reservations ever
        total_all_result = await self.db.execute(
            select(func.count(InventoryReservation.id)).where(
                InventoryReservation.store_id == store_id,
            )
        )
        total_all = total_all_result.scalar() or 0

        # Successful (committed) reservations
        committed_result = await self.db.execute(
            select(func.count(InventoryReservation.id)).where(
                InventoryReservation.store_id == store_id,
                InventoryReservation.status == ReservationStatus.COMMITTED,
            )
        )
        committed_count = committed_result.scalar() or 0

        success_rate = round(
            (committed_count / total_all * 100), 1
        ) if total_all > 0 else 100.0

        # Reservations by source
        source_result = await self.db.execute(
            select(
                InventoryReservation.order_source,
                func.count(InventoryReservation.id),
            )
            .where(InventoryReservation.store_id == store_id)
            .group_by(InventoryReservation.order_source)
        )
        by_source = {row[0]: row[1] for row in source_result.all()}

        return {
            "active_reservations": active_count,
            "reserved_stock_units": reserved_units,
            "expired_today": expired_today,
            "reservation_success_rate": success_rate,
            "reservations_by_source": by_source,
        }


class ReservationService:
    """
    Business logic for inventory reservations.

    All stock mutations use SELECT FOR UPDATE to prevent race conditions.
    All writes are within a single atomic transaction.
    """

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
        self.wh_repo = WarehouseRepository(db)
        self.inv_repo = WarehouseInventoryRepository(db)
        self.variant_repo = VariantRepository(db)
        self.txn_repo = TransactionRepository(db)
        self.log_repo = LogRepository(db)
        self.logger = logging.getLogger(f"{__name__}.ReservationService")

    # ═══════════════════════════════════════════════════════════════
    # RESERVE STOCK
    # ═══════════════════════════════════════════════════════════════

    async def reserve_stock(
        self,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        quantity: int,
        order_id: Optional[str] = None,
        order_source: ReservationSource = ReservationSource.MANUAL,
        expires_in_minutes: Optional[int] = None,
        reason: Optional[str] = None,
        meta_data: Optional[dict] = None,
    ) -> InventoryReservation:
        """
        Reserve stock at a specific warehouse.

        Flow (all within one committed transaction):
        1. Validate warehouse and variant (ownership + active)
        2. Lock the inventory row with SELECT FOR UPDATE
        3. Check available_stock >= quantity
        4. Deduct available_stock, increase reserved_stock
        5. Create reservation record
        6. Create audit trail transaction (type=ADJUSTMENT)
        7. Log the event

        Raises:
            InsufficientStockForReservationError: Not enough available stock
            DuplicateReservationError: Active reservation exists
            WarehouseNotFoundError / WarehouseInactiveError / VariantNotFoundError
        """
        # Step 1: Validate warehouse
        warehouse = await self.wh_repo.get_by_id(warehouse_id)
        if warehouse is None or str(warehouse.store_id) != str(self.store.id):
            raise WarehouseNotFoundError(str(warehouse_id))
        if not warehouse.is_active:
            raise WarehouseInactiveError(str(warehouse_id))

        # Step 2: Validate variant
        variant = await self.variant_repo.get_by_id(variant_id)
        if variant is None:
            raise VariantNotFoundError(str(variant_id))

        # Step 3: Lock inventory with SELECT FOR UPDATE
        wh_inv = await self.inv_repo.get_or_create(
            warehouse_id, variant_id, with_lock=True,
        )

        # Step 4: Check for duplicate reservation
        if order_id:
            existing = await self.repo.find_active_by_variant_and_order(
                store_id=self.store.id,
                variant_id=variant_id,
                warehouse_id=warehouse_id,
                order_id=order_id,
            )
            if existing:
                raise DuplicateReservationError(
                    str(variant_id), order_id, str(warehouse_id),
                )

        # Step 5: Check available stock (accounting for existing reservations)
        if wh_inv.available_stock < quantity:
            raise InsufficientStockForReservationError(
                variant_id=str(variant_id),
                warehouse_id=str(warehouse_id),
                available=wh_inv.available_stock,
                requested=quantity,
            )

        # Step 6: Update inventory levels (under lock)
        wh_inv.available_stock -= quantity
        wh_inv.reserved_stock += quantity
        wh_inv.updated_at = datetime.now(timezone.utc)

        # Step 7: Calculate expiration
        ttl = expires_in_minutes or DEFAULT_RESERVATION_TTL_MINUTES
        if ttl > MAX_RESERVATION_TTL_MINUTES:
            ttl = MAX_RESERVATION_TTL_MINUTES
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl)

        # Step 8: Create reservation record
        reservation = await self.repo.create(
            store_id=self.store.id,
            warehouse_id=warehouse_id,
            variant_id=variant_id,
            quantity=quantity,
            inventory_id=wh_inv.id,
            product_id=variant.product_id,
            order_id=order_id,
            order_source=order_source,
            status=ReservationStatus.ACTIVE,
            expires_at=expires_at,
            meta_data=meta_data,
        )

        # Step 9: Create inventory transaction audit trail (use ADJUSTMENT for all reservations)
        await self.txn_repo.create(
            variant_id=variant_id,
            transaction_type=TransactionType.ADJUSTMENT,
            quantity_change=-quantity,
            quantity_before=wh_inv.available_stock + quantity,
            quantity_after=wh_inv.available_stock,
            reason=reason or f"Reservation: {reservation.id}",
            reference_id=str(reservation.id),
            performed_by=self.user_id,
        )

        # Step 10: Log
        await self.log_repo.create(
            variant_id=variant_id,
            action=InventoryAction.STOCK_RESERVED.value,
            details={
                "reservation_id": str(reservation.id),
                "warehouse_id": str(warehouse_id),
                "quantity": quantity,
                "order_id": order_id,
                "order_source": order_source.value,
                "reason": reason,
            },
            performed_by=self.user_id,
        )

        await self.db.commit()

        # Invalidate aggregation cache
        try:
            await aggregation_cache.invalidate_store(self.store.id)
        except Exception as cache_exc:
            self.logger.warning(
                "Cache invalidation failed after reserve: %s", cache_exc,
            )

        self.logger.info(
            "Stock reserved: reservation=%s, variant=%s, warehouse=%s, qty=%d, order=%s",
            reservation.id, variant_id, warehouse_id, quantity, order_id,
        )

        return reservation

    # ═══════════════════════════════════════════════════════════════
    # COMMIT STOCK
    # ═══════════════════════════════════════════════════════════════

    async def commit_stock(
        self, reservation_id: uuid.UUID,
    ) -> InventoryReservation:
        """
        Commit a reservation — finalize the stock movement.

        reserved_stock -= quantity
        (No return to available — the stock is consumed)
        """
        reservation = await self._get_active_reservation(reservation_id)
        self._ensure_store_owns_reservation(reservation)

        if reservation.status != ReservationStatus.ACTIVE:
            raise InvalidReservationStateError(
                str(reservation_id), reservation.status.value,
                [ReservationStatus.ACTIVE.value],
            )

        # Lock the inventory row
        wh_inv = await self.inv_repo.get_or_create(
            reservation.warehouse_id, reservation.variant_id,
            with_lock=True,
        )

        # Deduct from reserved only (available was already deducted at reserve time)
        deduction = min(reservation.quantity, wh_inv.reserved_stock)
        wh_inv.reserved_stock -= deduction
        wh_inv.updated_at = datetime.now(timezone.utc)

        # Update reservation status
        reservation.status = ReservationStatus.COMMITTED
        reservation.committed_at = datetime.now(timezone.utc)

        # Create audit trail transaction
        await self.txn_repo.create(
            variant_id=reservation.variant_id,
            transaction_type=TransactionType.ADJUSTMENT,
            quantity_change=-deduction,
            quantity_before=wh_inv.reserved_stock + deduction,
            quantity_after=wh_inv.reserved_stock,
            reason=f"Reservation committed: {reservation_id}",
            reference_id=str(reservation_id),
            performed_by=self.user_id,
        )

        await self.log_repo.create(
            variant_id=reservation.variant_id,
            action=InventoryAction.TRANSFER_COMPLETED.value,
            details={
                "reservation_id": str(reservation_id),
                "quantity": deduction,
            },
            performed_by=self.user_id,
        )

        await self.db.commit()

        # Invalidate aggregation cache
        try:
            await aggregation_cache.invalidate_store(self.store.id)
        except Exception as cache_exc:
            self.logger.warning(
                "Cache invalidation failed after commit: %s", cache_exc,
            )

        self.logger.info(
            "Reservation committed: reservation=%s, qty=%d",
            reservation_id, deduction,
        )

        return reservation

    # ═══════════════════════════════════════════════════════════════
    # RELEASE STOCK
    # ═══════════════════════════════════════════════════════════════

    async def release_stock(
        self,
        reservation_id: uuid.UUID,
        quantity: Optional[int] = None,
    ) -> InventoryReservation:
        """
        Release a reservation — return reserved stock to available.

        reserved_stock -= quantity
        available_stock += quantity
        """
        reservation = await self._get_active_reservation(reservation_id)
        self._ensure_store_owns_reservation(reservation)

        if reservation.status not in (
            ReservationStatus.ACTIVE, ReservationStatus.PENDING,
        ):
            raise InvalidReservationStateError(
                str(reservation_id), reservation.status.value,
                [ReservationStatus.ACTIVE.value, ReservationStatus.PENDING.value],
            )

        # Lock the inventory row
        wh_inv = await self.inv_repo.get_or_create(
            reservation.warehouse_id, reservation.variant_id,
            with_lock=True,
        )

        release_qty = min(
            quantity if quantity is not None else reservation.quantity,
            wh_inv.reserved_stock,
            reservation.quantity,
        )

        # Return stock to available
        wh_inv.available_stock += release_qty
        wh_inv.reserved_stock -= release_qty
        wh_inv.updated_at = datetime.now(timezone.utc)

        # Update reservation
        reservation.status = ReservationStatus.RELEASED
        reservation.released_at = datetime.now(timezone.utc)

        # Create audit trail transaction
        await self.txn_repo.create(
            variant_id=reservation.variant_id,
            transaction_type=TransactionType.ADJUSTMENT,
            quantity_change=release_qty,
            quantity_before=wh_inv.available_stock - release_qty,
            quantity_after=wh_inv.available_stock,
            reason=f"Reservation released: {reservation_id}",
            reference_id=str(reservation_id),
            performed_by=self.user_id,
        )

        await self.log_repo.create(
            variant_id=reservation.variant_id,
            action=InventoryAction.RESERVATION_RELEASED.value,
            details={
                "reservation_id": str(reservation_id),
                "quantity": release_qty,
            },
            performed_by=self.user_id,
        )

        await self.db.commit()

        # Invalidate aggregation cache
        try:
            await aggregation_cache.invalidate_store(self.store.id)
        except Exception as cache_exc:
            self.logger.warning(
                "Cache invalidation failed after release: %s", cache_exc,
            )

        self.logger.info(
            "Reservation released: reservation=%s, qty=%d",
            reservation_id, release_qty,
        )

        return reservation

    # ═══════════════════════════════════════════════════════════════
    # EXPIRE RESERVATIONS
    # ═══════════════════════════════════════════════════════════════

    async def expire_reservation(
        self, reservation_id: uuid.UUID,
    ) -> InventoryReservation:
        """Expire a reservation — release stock with EXPIRED status and audit trail."""
        reservation = await self._get_active_reservation(reservation_id)
        self._ensure_store_owns_reservation(reservation)

        if reservation.status not in (
            ReservationStatus.ACTIVE, ReservationStatus.PENDING,
        ):
            raise InvalidReservationStateError(
                str(reservation_id), reservation.status.value,
                [ReservationStatus.ACTIVE.value, ReservationStatus.PENDING.value],
            )

        # Lock and release
        wh_inv = await self.inv_repo.get_or_create(
            reservation.warehouse_id, reservation.variant_id,
            with_lock=True,
        )

        release_qty = min(reservation.quantity, wh_inv.reserved_stock)
        wh_inv.available_stock += release_qty
        wh_inv.reserved_stock -= release_qty
        wh_inv.updated_at = datetime.now(timezone.utc)

        reservation.status = ReservationStatus.EXPIRED
        reservation.released_at = datetime.now(timezone.utc)

        # Create audit trail transaction (same as release)
        await self.txn_repo.create(
            variant_id=reservation.variant_id,
            transaction_type=TransactionType.ADJUSTMENT,
            quantity_change=release_qty,
            quantity_before=wh_inv.available_stock - release_qty,
            quantity_after=wh_inv.available_stock,
            reason=f"Reservation expired: {reservation_id}",
            reference_id=str(reservation_id),
            performed_by=self.user_id,
        )

        await self.log_repo.create(
            variant_id=reservation.variant_id,
            action=InventoryAction.RESERVATION_RELEASED.value,
            details={
                "reservation_id": str(reservation_id),
                "quantity": release_qty,
                "reason": "expired",
            },
            performed_by=self.user_id,
        )

        await self.db.commit()

        # Invalidate aggregation cache
        try:
            await aggregation_cache.invalidate_store(self.store.id)
        except Exception as cache_exc:
            self.logger.warning(
                "Cache invalidation failed after expire: %s", cache_exc,
            )

        self.logger.info(
            "Reservation expired: reservation=%s, qty=%d",
            reservation_id, release_qty,
        )

        return reservation

    async def expire_old_reservations(self) -> int:
        """
        Background cleanup task — expire all overdue reservations.
        Returns the number of reservations expired.

        Celery scheduled usage:
            from app.warehouse.reservation_service import ReservationService
            celery_app.task(name="expire_old_reservations")
            async def task():
                async with AsyncSessionLocal() as db:
                    for store_id in active_stores:
                        service = ReservationService(db, store)
                        await service.expire_old_reservations()
        """
        expired_list = await self.repo.find_expired(self.store.id)
        expired_count = 0

        for reservation in expired_list:
            try:
                await self.expire_reservation(reservation.id)
                expired_count += 1
            except Exception as exc:
                self.logger.error(
                    "Failed to expire reservation %s: %s",
                    reservation.id, exc,
                )

        if expired_count > 0:
            self.logger.info(
                "Expired %d old reservations for store %s",
                expired_count, self.store.id,
            )

        return expired_count

    # ═══════════════════════════════════════════════════════════════
    # CANCEL ORDER — Release All
    # ═══════════════════════════════════════════════════════════════

    async def cancel_order(self, order_id: str) -> list[InventoryReservation]:
        """Cancel all active reservations for an order."""
        reservations = await self.repo.get_by_order(self.store.id, order_id)

        released = []
        for res in reservations:
            if res.status in (
                ReservationStatus.ACTIVE, ReservationStatus.PENDING,
            ):
                released.append(await self.release_stock(res.id))

        self.logger.info(
            "Order %s cancelled: %d reservations released",
            order_id, len(released),
        )

        return released

    # ═══════════════════════════════════════════════════════════════
    # WOOCOMMERCE INTEGRATION (C.6)
    # ═══════════════════════════════════════════════════════════════

    async def reserve_for_woocommerce_order(
        self,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        quantity: int,
        order_id: str,
        meta_data: Optional[dict] = None,
    ) -> InventoryReservation:
        """
        Auto-reserve inventory when a WooCommerce order arrives.

        Uses the same reservation logic with WOOCOMMERCE source and a shorter
        default TTL (30 minutes) to prevent indefinite holds if the order
        processing pipeline stalls.

        If insufficient stock, raises InsufficientStockForReservationError
        (structured failure — no overselling).
        """
        return await self.reserve_stock(
            warehouse_id=warehouse_id,
            variant_id=variant_id,
            quantity=quantity,
            order_id=order_id,
            order_source=ReservationSource.WOOCOMMERCE,
            expires_in_minutes=30,  # Shorter TTL for WooCommerce orders
            reason=f"WooCommerce order {order_id}",
            meta_data=meta_data,
        )

    # ═══════════════════════════════════════════════════════════════
    # TRANSFER INTEGRATION (C.7)
    # ═══════════════════════════════════════════════════════════════

    async def get_available_for_transfer(
        self,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
    ) -> int:
        """
        Get the true available stock for a transfer, accounting for
        existing reservations.

        Returns the quantity that can be transferred (available_stock
        is already reduced by existing reservations).

        This is called by WarehouseTransferService.create_transfer
        to ensure transfers don't reserve stock that's already reserved.
        """
        wh_inv = await self.inv_repo.get_by_variant_and_warehouse(
            warehouse_id, variant_id,
        )
        return wh_inv.available_stock if wh_inv else 0

    # ═══════════════════════════════════════════════════════════════
    # QUERIES
    # ═══════════════════════════════════════════════════════════════

    async def get_reservation(
        self, reservation_id: uuid.UUID,
    ) -> InventoryReservation:
        """Get a reservation by ID with ownership validation."""
        reservation = await self.repo.get_by_id(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(str(reservation_id))
        self._ensure_store_owns_reservation(reservation)
        return reservation

    async def get_reservations(
        self,
        page: int = 1,
        page_size: int = 20,
        warehouse_id: Optional[uuid.UUID] = None,
        variant_id: Optional[uuid.UUID] = None,
    ) -> tuple[list[InventoryReservation], int, int]:
        """List reservations with pagination."""
        return await self.repo.list_active(
            store_id=self.store.id,
            page=page,
            page_size=page_size,
            warehouse_id=warehouse_id,
            variant_id=variant_id,
        )

    async def get_order_reservations(
        self, order_id: str,
    ) -> list[InventoryReservation]:
        """Get all reservations for a specific order."""
        return await self.repo.get_by_order(self.store.id, order_id)

    async def get_dashboard_stats(self) -> dict:
        """Get reservation dashboard statistics."""
        return await self.repo.get_dashboard_stats(self.store.id)

    async def validate_stock(
        self,
        warehouse_id: uuid.UUID,
        variant_id: uuid.UUID,
        requested_quantity: int,
    ) -> dict:
        """
        Validate that sufficient stock is available for a reservation.

        Returns available, reserved, and whether the request can be fulfilled.
        Does NOT create a reservation.
        """
        wh_inv = await self.inv_repo.get_by_variant_and_warehouse(
            warehouse_id, variant_id,
        )
        available = wh_inv.available_stock if wh_inv else 0
        reserved = wh_inv.reserved_stock if wh_inv else 0

        return {
            "variant_id": str(variant_id),
            "warehouse_id": str(warehouse_id),
            "available_stock": available,
            "reserved_stock": reserved,
            "total_stock": available + reserved,
            "requested": requested_quantity,
            "can_fulfill": available >= requested_quantity,
        }

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ═══════════════════════════════════════════════════════════════

    async def _get_active_reservation(
        self, reservation_id: uuid.UUID,
    ) -> InventoryReservation:
        """Get a reservation, raising if not found."""
        reservation = await self.repo.get_by_id(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(str(reservation_id))
        return reservation

    def _ensure_store_owns_reservation(
        self, reservation: InventoryReservation,
    ) -> None:
        """Raise if the reservation doesn't belong to the current store."""
        from app.inventory.exceptions import InvalidStoreOwnershipError
        if str(reservation.store_id) != str(self.store.id):
            raise InvalidStoreOwnershipError(
                "Reservation", str(reservation.id),
            )
