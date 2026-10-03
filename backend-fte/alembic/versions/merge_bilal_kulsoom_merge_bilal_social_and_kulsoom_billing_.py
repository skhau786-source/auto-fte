"""merge bilal social and kulsoom billing/rag heads

Revision ID: merge_bilal_kulsoom
Revises: 0ee6c6850b53, merge_phase3_phase4_heads
Create Date: 2026-10-03 14:10:30.010269

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'merge_bilal_kulsoom'
down_revision = ('0ee6c6850b53', 'merge_phase3_phase4_heads')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
