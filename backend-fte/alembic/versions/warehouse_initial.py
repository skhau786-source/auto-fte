"""
Warehouse & Multi-location Inventory — Initial Migration

Creates all warehouse management tables:
- warehouses: Physical/virtual storage locations
- warehouse_inventory: Per-variant stock tracking at each warehouse
- warehouse_transfers: Inter-warehouse transfer records
- warehouse_transfer_items: Individual line items within transfers

Revision ID: warehouse_initial
Revises: woocommerce_initial
Create Date: 2026-07-27
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "warehouse_initial"
down_revision: Union[str, None] = "woocommerce_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enums ──
    sa.Enum(
        "active", "inactive", "under_maintenance", "closed",
        name="warehouse_status_enum",
    ).create(op.get_bind(), checkfirst=True)

    sa.Enum(
        "draft", "pending", "approved", "in_transit",
        "completed", "cancelled", "partially_received",
        name="transfer_status_enum",
    ).create(op.get_bind(), checkfirst=True)

    # ══════════════════════════════════════════════════════════════
    # WAREHOUSE: warehouses
    # ══════════════════════════════════════════════════════════════
    op.create_table(
        "warehouses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
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
        sa.Column("capacity", sa.Integer(), nullable=True, comment="Maximum storage capacity in units"),
        sa.Column("capacity_unit", sa.String(20), nullable=False, server_default="units"),
        sa.Column("status", sa.Enum("active", "inactive", "under_maintenance", "closed", name="warehouse_status_enum"), nullable=False, server_default="active"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_warehouses_code"), "warehouses", ["code"], unique=False)

    # ══════════════════════════════════════════════════════════════
    # WAREHOUSE: warehouse_inventory
    # ══════════════════════════════════════════════════════════════
    op.create_table(
        "warehouse_inventory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
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

    # ══════════════════════════════════════════════════════════════
    # WAREHOUSE: warehouse_transfers
    # ══════════════════════════════════════════════════════════════
    op.create_table(
        "warehouse_transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
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

    # ══════════════════════════════════════════════════════════════
    # WAREHOUSE: warehouse_transfer_items
    # ══════════════════════════════════════════════════════════════
    op.create_table(
        "warehouse_transfer_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("transfer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("warehouse_transfers.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("received_quantity", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    """Drop all warehouse tables in reverse order."""
    op.drop_table("warehouse_transfer_items")
    op.drop_table("warehouse_transfers")
    op.drop_table("warehouse_inventory")
    op.drop_table("warehouses")

    # Drop enums
    sa.Enum(name="warehouse_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="transfer_status_enum").drop(op.get_bind(), checkfirst=True)
