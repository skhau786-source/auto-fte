"""
SaaS Pivot — Remove Physical Warehouse Management

Drops all warehouse-management tables and rewires reservations/settings
to the store-centric model:

- inventory_reservations: drop warehouse_id / inventory_id columns + FKs + indexes;
  replace the (variant, order, warehouse) unique constraint with (variant, order).
- warehouse_settings → store_settings (data copied, warehouse-only fields dropped).
- Drop warehouse_transfer_items, warehouse_transfers, warehouse_inventory, warehouses.
- Drop warehouse_status_enum and transfer_status_enum.

Revision ID: remove_warehouse
Revises: allocation_engine
Create Date: 2026-08-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "remove_warehouse"
down_revision: Union[str, None] = "allocation_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ══════════════════════════════════════════════════════════════
    # 1. inventory_reservations — strip warehouse references
    # ══════════════════════════════════════════════════════════════
    op.drop_constraint(
        "uq_reservation_variant_order_warehouse",
        "inventory_reservations",
        type_="unique",
    )
    op.drop_constraint(
        "inventory_reservations_warehouse_id_fkey",
        "inventory_reservations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "inventory_reservations_inventory_id_fkey",
        "inventory_reservations",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_inventory_reservations_warehouse_id"),
        table_name="inventory_reservations",
    )
    op.drop_index(
        op.f("ix_inventory_reservations_inventory_id"),
        table_name="inventory_reservations",
    )
    op.drop_column("inventory_reservations", "warehouse_id")
    op.drop_column("inventory_reservations", "inventory_id")
    op.create_unique_constraint(
        "uq_reservation_variant_order",
        "inventory_reservations",
        ["variant_id", "order_id"],
    )

    # ══════════════════════════════════════════════════════════════
    # 2. warehouse_settings → store_settings
    # ══════════════════════════════════════════════════════════════
    op.create_table(
        "store_settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.UUID(), nullable=False),
        sa.Column(
            "auto_allocate_inventory", sa.Boolean(),
            nullable=False, server_default=sa.text("true"),
        ),
        sa.Column(
            "allocation_strategy", sa.String(50),
            nullable=False, server_default=sa.text("'default'"),
        ),
        sa.Column(
            "allow_negative_stock", sa.Boolean(),
            nullable=False, server_default=sa.text("false"),
        ),
        sa.Column(
            "reserve_stock_on_order", sa.Boolean(),
            nullable=False, server_default=sa.text("true"),
        ),
        sa.Column(
            "auto_release_cancelled_orders", sa.Boolean(),
            nullable=False, server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", name="uq_store_settings_store"),
    )
    op.create_index(
        op.f("ix_store_settings_store_id"),
        "store_settings",
        ["store_id"],
        unique=True,
    )

    # Copy rows from warehouse_settings (normalizing the legacy strategy name)
    op.execute(
        """
        INSERT INTO store_settings (
            id, store_id, auto_allocate_inventory, allocation_strategy,
            allow_negative_stock, reserve_stock_on_order,
            auto_release_cancelled_orders, created_at, updated_at
        )
        SELECT
            id, store_id, auto_allocate_inventory,
            CASE WHEN allocation_strategy = 'default_warehouse'
                 THEN 'default' ELSE allocation_strategy END,
            allow_negative_stock, reserve_stock_on_order,
            auto_release_cancelled_orders, created_at, updated_at
        FROM warehouse_settings
        """
    )

    op.drop_index(op.f("ix_warehouse_settings_store_id"), table_name="warehouse_settings")
    op.drop_table("warehouse_settings")

    # ══════════════════════════════════════════════════════════════
    # 3. Drop warehouse tables (children first)
    # ══════════════════════════════════════════════════════════════
    op.drop_table("warehouse_transfer_items")
    op.drop_table("warehouse_transfers")
    op.drop_table("warehouse_inventory")
    op.drop_table("warehouses")

    # 4. Drop warehouse enums
    sa.Enum(name="warehouse_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="transfer_status_enum").drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    """Restore the warehouse schema (best-effort reverse of upgrade)."""
    # Recreate enums
    sa.Enum(
        "active", "inactive", "under_maintenance", "closed",
        name="warehouse_status_enum",
    ).create(op.get_bind(), checkfirst=True)
    sa.Enum(
        "draft", "pending", "approved", "in_transit",
        "completed", "cancelled", "partially_received",
        name="transfer_status_enum",
    ).create(op.get_bind(), checkfirst=True)

    # warehouses
    op.create_table(
        "warehouses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(50), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("manager_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("registered_students.id", ondelete="SET NULL"), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("capacity_unit", sa.String(20), nullable=False, server_default="units"),
        sa.Column("status", sa.Enum("active", "inactive", "under_maintenance", "closed", name="warehouse_status_enum"), nullable=False, server_default="active"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_warehouses_code"), "warehouses", ["code"], unique=False)
    op.create_index(op.f("ix_warehouses_is_default"), "warehouses", ["is_default"], unique=False)

    # warehouse_inventory
    op.create_table(
        "warehouse_inventory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("available_stock", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("reserved_stock", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("incoming_stock", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("damaged_stock", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("minimum_stock", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("maximum_stock", sa.Integer(), nullable=True),
        sa.Column("reorder_point", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("bin_location", sa.String(100), nullable=True),
        sa.Column("shelf", sa.String(100), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("warehouse_id", "variant_id", name="uq_warehouse_variant"),
    )
    op.create_index(op.f("ix_warehouse_inventory_warehouse_id"), "warehouse_inventory", ["warehouse_id"], unique=False)
    op.create_index(op.f("ix_warehouse_inventory_product_id"), "warehouse_inventory", ["product_id"], unique=False)
    op.create_index(op.f("ix_warehouse_inventory_variant_id"), "warehouse_inventory", ["variant_id"], unique=False)

    # warehouse_transfers
    op.create_table(
        "warehouse_transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("transfer_number", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("source_warehouse_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("destination_warehouse_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.Enum("draft", "pending", "approved", "in_transit", "completed", "cancelled", "partially_received", name="transfer_status_enum"), nullable=False, server_default="draft"),
        sa.Column("requested_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("registered_students.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("registered_students.id", ondelete="SET NULL"), nullable=True),
        sa.Column("transfer_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_warehouse_transfers_store_id"), "warehouse_transfers", ["store_id"], unique=False)
    op.create_index(op.f("ix_warehouse_transfers_transfer_number"), "warehouse_transfers", ["transfer_number"], unique=True)

    # warehouse_transfer_items
    op.create_table(
        "warehouse_transfer_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transfer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("warehouse_transfers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("received_quantity", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # warehouse_settings (recreate with warehouse columns)
    op.create_table(
        "warehouse_settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.UUID(), nullable=False),
        sa.Column("default_warehouse_id", sa.UUID(), nullable=True),
        sa.Column("auto_allocate_inventory", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("multi_warehouse_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("allocation_strategy", sa.String(50), nullable=False, server_default=sa.text("'default_warehouse'")),
        sa.Column("allow_negative_stock", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reserve_stock_on_order", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("auto_release_cancelled_orders", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("allocation_priority", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["default_warehouse_id"], ["warehouses.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", name="uq_warehouse_settings_store"),
    )
    op.create_index(op.f("ix_warehouse_settings_store_id"), "warehouse_settings", ["store_id"], unique=True)

    # Copy rows back from store_settings
    op.execute(
        """
        INSERT INTO warehouse_settings (
            id, store_id, auto_allocate_inventory, allocation_strategy,
            allow_negative_stock, reserve_stock_on_order,
            auto_release_cancelled_orders, created_at, updated_at
        )
        SELECT
            id, store_id, auto_allocate_inventory, allocation_strategy,
            allow_negative_stock, reserve_stock_on_order,
            auto_release_cancelled_orders, created_at, updated_at
        FROM store_settings
        """
    )

    # inventory_reservations — restore warehouse columns
    op.drop_constraint(
        "uq_reservation_variant_order",
        "inventory_reservations",
        type_="unique",
    )
    op.add_column(
        "inventory_reservations",
        sa.Column("warehouse_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.add_column(
        "inventory_reservations",
        sa.Column("inventory_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "inventory_reservations_warehouse_id_fkey",
        "inventory_reservations", "warehouses",
        ["warehouse_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "inventory_reservations_inventory_id_fkey",
        "inventory_reservations", "warehouse_inventory",
        ["inventory_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_inventory_reservations_warehouse_id"),
        "inventory_reservations", ["warehouse_id"], unique=False,
    )
    op.create_index(
        op.f("ix_inventory_reservations_inventory_id"),
        "inventory_reservations", ["inventory_id"], unique=False,
    )
    op.create_unique_constraint(
        "uq_reservation_variant_order_warehouse",
        "inventory_reservations",
        ["variant_id", "order_id", "warehouse_id"],
    )

    # Drop store_settings last (after data has been copied back)
    op.drop_index(op.f("ix_store_settings_store_id"), table_name="store_settings")
    op.drop_table("store_settings")
