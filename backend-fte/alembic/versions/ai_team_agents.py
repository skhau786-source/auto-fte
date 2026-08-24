"""ai_team_agents — Add team_id to ai_agents for team/agent association.

Revision ID: ai_team_agents_001
Revises: ai_agents_001
Create Date: 2026-08-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = "ai_team_agents_001"
down_revision = "ai_agents_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_agents",
        sa.Column(
            "team_id",
            UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_ai_agents_team_id", table_name="ai_agents")
    op.drop_column("ai_agents", "team_id")
