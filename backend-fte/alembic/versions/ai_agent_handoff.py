"""ai_agent_handoff — Add task handoff fields for agent collaboration

Revision ID: ai_handoff_001
Revises: ai_agents_001
Create Date: 2026-08-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = "ai_handoff_001"
down_revision = "ai_agents_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add handoff/collaboration fields to ai_agent_tasks
    op.add_column(
        "ai_agent_tasks",
        sa.Column(
            "parent_task_id", UUID(as_uuid=True),
            sa.ForeignKey("ai_agent_tasks.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
    )
    op.add_column(
        "ai_agent_tasks",
        sa.Column(
            "source_agent_id", UUID(as_uuid=True),
            sa.ForeignKey("ai_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "ai_agent_tasks",
        sa.Column(
            "target_agent_id", UUID(as_uuid=True),
            sa.ForeignKey("ai_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "ai_agent_tasks",
        sa.Column("capability_name", sa.String(200), nullable=True),
    )
    op.add_column(
        "ai_agent_tasks",
        sa.Column("handoff_depth", sa.Integer, nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("ai_agent_tasks", "handoff_depth")
    op.drop_column("ai_agent_tasks", "capability_name")
    op.drop_column("ai_agent_tasks", "target_agent_id")
    op.drop_column("ai_agent_tasks", "source_agent_id")
    op.drop_column("ai_agent_tasks", "parent_task_id")
