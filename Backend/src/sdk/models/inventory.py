# ═══════════════════════════════════════════════════════════════
# fte_sdk / models / inventory.py
#
# PURPOSE: Inventory ledger models — har stock change ka immutable
#          record (StockMovement).
#
# USED BY: domains/ecommerce/inventory_service.py, inventory_routes.py
#
# NOTE:    Ported from kulsoom branch (InventoryTransaction in
#          backend-fte/app/models.py). UUID → int ids; Shopify-only
#          sync flags hata diye (main ke connectors read-only hain).
# ═══════════════════════════════════════════════════════════════

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Index, func,
)

from src.sdk.database import Base

# movement_type values
MOVEMENT_ADJUSTMENT = "adjustment"   # manual +/- by user
MOVEMENT_SALE = "sale"
MOVEMENT_PURCHASE = "purchase"       # restock
MOVEMENT_RETURN = "return"
MOVEMENT_RESERVATION = "reservation"
MOVEMENT_PLATFORM_SYNC = "platform_sync"
MOVEMENT_TYPES = (
    MOVEMENT_ADJUSTMENT, MOVEMENT_SALE, MOVEMENT_PURCHASE,
    MOVEMENT_RETURN, MOVEMENT_RESERVATION, MOVEMENT_PLATFORM_SYNC,
)


# ─── StockMovement ────────────────────────────────────────────
# Append-only: rows kabhi update nahi hoti.

class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("variants.id", ondelete="CASCADE"), nullable=False, index=True)

    movement_type = Column(String(30), nullable=False, default=MOVEMENT_ADJUSTMENT, index=True)
    quantity_change = Column(Integer, nullable=False)
    quantity_before = Column(Integer, nullable=False)
    quantity_after = Column(Integer, nullable=False)

    reason = Column(String(500), nullable=True)
    reference_id = Column(String(255), nullable=True)       # order id, PO number, etc.
    performed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_stock_movements_store_created", "store_id", "created_at"),
    )
