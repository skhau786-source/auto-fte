"""
Add is_default column to warehouses table.

Revision ID: warehouse_is_default
Revises: warehouse_initial
Create Date: 2026-07-30
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "warehouse_is_default"
down_revision: Union[str, None] = "warehouse_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_default column to warehouses table."""
    op.add_column(
        "warehouses",
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Only one warehouse per store can be default",
        ),
    )
    op.create_index(
        op.f("ix_warehouses_is_default"),
        "warehouses",
        ["is_default"],
        unique=False,
    )


def downgrade() -> None:
    """Remove is_default column from warehouses table."""
    op.drop_index(op.f("ix_warehouses_is_default"), table_name="warehouses")
    op.drop_column("warehouses", "is_default")
