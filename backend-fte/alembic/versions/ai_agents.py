"""ai_agents — Phase 4 AI Agent Collaboration Foundation

Revision ID: ai_agents_001
Revises: None (adds new tables only)
Create Date: 2026-08-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = "ai_agents_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── AI Agents table ──
    op.create_table(
        "ai_agents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id", UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "agent_type",
            sa.Enum("inventory", "social", "sales", "analytics", "custom",
                     name="ai_agent_type_enum"),
            nullable=False, server_default="custom",
        ),
        sa.Column(
            "status",
            sa.Enum("active", "inactive", "error", name="ai_agent_status_enum"),
            nullable=False, server_default="inactive",
        ),
        sa.Column("config", JSONB, nullable=True),
        sa.Column("granted_permissions", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_by", UUID(as_uuid=True),
            sa.ForeignKey("registered_students.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── AI Agent Tasks table ──
    op.create_table(
        "ai_agent_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "agent_id", UUID(as_uuid=True),
            sa.ForeignKey("ai_agents.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column(
            "organization_id", UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column(
            "task_type",
            sa.Enum(
                "inventory_check", "inventory_adjust", "stock_recommendation",
                "content_generate", "post_schedule", "sales_analysis",
                "price_optimization", "custom",
                name="ai_task_type_enum",
            ),
            nullable=False, server_default="custom",
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "pending_approval", "running", "completed",
                "failed", "cancelled", "rejected",
                name="ai_task_status_enum",
            ),
            nullable=False, server_default="pending",
        ),
        sa.Column("input_data", JSONB, nullable=True),
        sa.Column("output_data", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("requires_human_approval", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "approved_by", UUID(as_uuid=True),
            sa.ForeignKey("registered_students.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column(
            "submitted_by", UUID(as_uuid=True),
            sa.ForeignKey("registered_students.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("execution_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_duration_ms", sa.Integer, nullable=True),
        sa.Column("llm_provider", sa.String(50), nullable=True),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("llm_tokens_used", sa.Integer, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── AI Agent Actions (audit trail) table ──
    op.create_table(
        "ai_agent_actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "agent_id", UUID(as_uuid=True),
            sa.ForeignKey("ai_agents.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column(
            "task_id", UUID(as_uuid=True),
            sa.ForeignKey("ai_agent_tasks.id", ondelete="SET NULL"),
            nullable=True, index=True,
        ),
        sa.Column(
            "organization_id", UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("action_type", sa.String(100), nullable=False, index=True),
        sa.Column("target_resource", sa.String(100), nullable=True),
        sa.Column("target_id", sa.String(255), nullable=True),
        sa.Column("result_status", sa.String(50), nullable=False, server_default="success"),
        sa.Column("details", JSONB, nullable=True),
        sa.Column(
            "performed_by", UUID(as_uuid=True),
            sa.ForeignKey("registered_students.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ai_agent_actions")
    op.drop_table("ai_agent_tasks")
    op.drop_table("ai_agents")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS ai_task_status_enum")
    op.execute("DROP TYPE IF EXISTS ai_task_type_enum")
    op.execute("DROP TYPE IF EXISTS ai_agent_status_enum")
    op.execute("DROP TYPE IF EXISTS ai_agent_type_enum")
