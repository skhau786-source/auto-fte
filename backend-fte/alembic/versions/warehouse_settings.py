"""Add warehouse_settings table for B.1 store configuration.

Revision ID: warehouse_settings_v2
Revises: warehouse_is_default
Create Date: 2026-07-30 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "warehouse_settings_v2"
down_revision: Union[str, None] = "warehouse_is_default"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["default_warehouse_id"], ["warehouses.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", name="uq_warehouse_settings_store"),
    )
    op.create_index(op.f("ix_warehouse_settings_store_id"), "warehouse_settings", ["store_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_warehouse_settings_store_id"), table_name="warehouse_settings")
    op.drop_table("warehouse_settings")
