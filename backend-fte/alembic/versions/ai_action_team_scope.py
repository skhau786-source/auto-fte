"""ai_action_team_scope — Add team_id to ai_agent_actions for team-scoped audit trail.

Fixes the Phase 4 audit-trail gap identified in the phase-3/4 audit
(phases/phase-4/TEAM-AUDIT/README.md): GET /ai/actions had no way to
filter by team, and TeamService._log_action was writing a fabricated
random UUID into the NOT NULL agent_id column for team-level actions
(actions with no associated AIAgent), which violates the ai_agents FK
against a real database.

This migration:
1. Makes ai_agent_actions.agent_id nullable, so team-level actions (team
   create/update/deactivate, membership, agent assignment) can leave it
   NULL instead of a fake agent reference. No existing row's agent_id
   value changes — this only relaxes the constraint.
2. Adds a nullable team_id column (FK -> teams.id, ON DELETE SET NULL,
   indexed) so audit records can be queried per team. Existing rows get
   NULL, which is safe: they were all agent-scoped actions written before
   this column existed, and the application backfills team_id for new
   agent-scoped actions from the agent's current team assignment going
   forward (see AIService._log_action). No backfill of historical rows
   is attempted here — that data (which team an agent belonged to at the
   time of a past action) is not reliably reconstructable from an
   agent's *current* team_id.

Revision ID: ai_action_team_scope
Revises: ai_team_agents_001
Create Date: 2026-08-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = "ai_action_team_scope"
down_revision = "ai_team_agents_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Relax agent_id to nullable — existing rows are untouched (all
    #    have a real, non-null agent_id already); this only allows future
    #    team-level actions to omit it instead of faking a value.
    op.alter_column(
        "ai_agent_actions",
        "agent_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
    )

    # 2. Add team_id for team-scoped audit querying.
    op.add_column(
        "ai_agent_actions",
        sa.Column(
            "team_id",
            UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_ai_agent_actions_team_id", table_name="ai_agent_actions")
    op.drop_column("ai_agent_actions", "team_id")

    # Intentionally NOT restoring agent_id's NOT NULL constraint here.
    # Team-level audit rows written while this migration was applied have
    # agent_id IS NULL (by design — see upgrade() docstring); restoring
    # NOT NULL would require either deleting those audit records or
    # fabricating a fake agent_id for them, and this project's audit
    # trail must never lose or falsify existing records. agent_id stays
    # nullable after downgrade; only the team_id column is removed.
