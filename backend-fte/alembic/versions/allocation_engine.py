"""
Allocation Engine — Allocation Priority Support (Phase 4)

Adds allocation_priority column to warehouse_settings table.
Stores a JSON array of warehouse IDs in priority order for the
PriorityWarehouseStrategy.

Revision ID: allocation_engine
Revises: reservation_engine
Create Date: 2026-07-30
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "allocation_engine"
down_revision: Union[str, None] = "reservation_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add allocation_priority column to warehouse_settings."""
    op.add_column(
        "warehouse_settings",
        sa.Column(
            "allocation_priority",
            postgresql.JSONB(),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
            comment="Ordered list of warehouse IDs for PriorityWarehouseStrategy",
        ),
    )


def downgrade() -> None:
    """Remove allocation_priority column from warehouse_settings."""
    op.drop_column("warehouse_settings", "allocation_priority")
