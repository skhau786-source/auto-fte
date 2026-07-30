"""
Reservation Engine — Inventory Reservations Table (Phase 3)

Creates the inventory_reservations table with:
- Full FK constraints to stores, warehouses, warehouse_inventory, products, variants
- Unique constraint preventing duplicate reservations for same variant/order/warehouse
- Reservation status enum
- Reservation source enum
- Expiration support
- Lifecycle timestamps

Revision ID: reservation_engine
Revises: warehouse_settings_v2
Create Date: 2026-07-30
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "reservation_engine"
down_revision: Union[str, None] = "warehouse_settings_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enums ──
    sa.Enum(
        "pending", "active", "committed", "released", "expired", "cancelled",
        name="reservation_status_enum",
    ).create(op.get_bind(), checkfirst=True)

    sa.Enum(
        "woocommerce", "shopify", "manual", "transfer", "ai_agent", "api",
        name="reservation_source_enum",
    ).create(op.get_bind(), checkfirst=True)

    # ══════════════════════════════════════════════════════════════
    # inventory_reservations
    # ══════════════════════════════════════════════════════════════
    op.create_table(
        "inventory_reservations",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "store_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stores.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "warehouse_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "inventory_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warehouse_inventory.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "product_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "variant_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("product_variants.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("order_id", sa.String(255), nullable=True, index=True),
        sa.Column(
            "order_source",
            sa.Enum(
                "woocommerce", "shopify", "manual", "transfer",
                "ai_agent", "api",
                name="reservation_source_enum",
            ),
            nullable=False,
            server_default="manual",
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "active", "committed", "released",
                "expired", "cancelled",
                name="reservation_status_enum",
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
    )

    # ── Additional indexes ──
    op.create_index(
        op.f("ix_inventory_reservations_store_id"),
        "inventory_reservations",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inventory_reservations_warehouse_id"),
        "inventory_reservations",
        ["warehouse_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inventory_reservations_variant_id"),
        "inventory_reservations",
        ["variant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inventory_reservations_order_id"),
        "inventory_reservations",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inventory_reservations_inventory_id"),
        "inventory_reservations",
        ["inventory_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inventory_reservations_product_id"),
        "inventory_reservations",
        ["product_id"],
        unique=False,
    )

    # ── Unique constraint: one active reservation per variant/order/warehouse ──
    op.create_unique_constraint(
        "uq_reservation_variant_order_warehouse",
        "inventory_reservations",
        ["variant_id", "order_id", "warehouse_id"],
    )


def downgrade() -> None:
    """Drop the inventory_reservations table and enums."""
    op.drop_constraint(
        "uq_reservation_variant_order_warehouse",
        "inventory_reservations",
    )
    op.drop_index(
        op.f("ix_inventory_reservations_product_id"),
        table_name="inventory_reservations",
    )
    op.drop_index(
        op.f("ix_inventory_reservations_inventory_id"),
        table_name="inventory_reservations",
    )
    op.drop_index(
        op.f("ix_inventory_reservations_order_id"),
        table_name="inventory_reservations",
    )
    op.drop_index(
        op.f("ix_inventory_reservations_variant_id"),
        table_name="inventory_reservations",
    )
    op.drop_index(
        op.f("ix_inventory_reservations_warehouse_id"),
        table_name="inventory_reservations",
    )
    op.drop_index(
        op.f("ix_inventory_reservations_store_id"),
        table_name="inventory_reservations",
    )
    op.drop_table("inventory_reservations")

    # Drop enums
    sa.Enum(name="reservation_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="reservation_source_enum").drop(op.get_bind(), checkfirst=True)
