"""organizations_teams_initial — Create the organizations/teams/organization_members tables.

Fixes a pre-existing migration-chain defect discovered while building the
Phase 3 Stripe payment integration: `organizations` (and `teams`,
`organization_members`) are core multi-tenant tables defined in
`app/organizations/models.py` and referenced by foreign key from several
already-existing migrations —
`alembic/versions/ai_agents.py` (`ai_agents.organization_id`,
`ai_agent_tasks.organization_id`, `ai_agent_actions.organization_id`) and
`alembic/versions/ai_team_agents.py` (`ai_agents.team_id` -> `teams.id`)
— but no migration has ever actually created these tables. Against a real
PostgreSQL database, `ai_agents_001` (the first migration to reference
`organizations.id`) would fail with "relation organizations does not
exist" before ever reaching the AI/Team/Payment features built on top of
it. This was masked because this project's entire test suite runs
against a mocked AsyncSession — no test in this repository has ever
created these tables against a real schema.

This migration creates exactly what `app/organizations/models.py`
declares today, nothing more. `ai_agents_001`'s `down_revision` is updated
(in the same change) from `None` to this revision, so the migration graph
becomes one connected tree instead of two disconnected roots — see
`merge_phase3_phase4_heads.py` for the final head-count cleanup.

Revision ID: organizations_teams_initial
Revises: remove_warehouse
Create Date: 2026-08-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = "organizations_teams_initial"
down_revision = "remove_warehouse"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("subscription_plan", sa.String(50), nullable=False, server_default="free"),
        sa.Column("subscription_status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
        sa.Column("features", JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "teams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id", UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "organization_members",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id", UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("registered_students.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column(
            "team_id", UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "role",
            sa.Enum("owner", "admin", "manager", "operator", "viewer",
                     name="membership_role_enum"),
            nullable=False, server_default="viewer",
        ),
        sa.Column("custom_permissions", JSONB, nullable=True),
        sa.Column("invited_by", UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_user"),
    )


def downgrade() -> None:
    op.drop_table("organization_members")
    op.drop_table("teams")
    op.drop_table("organizations")
    sa.Enum(name="membership_role_enum").drop(op.get_bind(), checkfirst=True)
