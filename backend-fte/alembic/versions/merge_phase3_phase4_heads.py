"""merge_phase3_phase4_heads — Merge point for all outstanding migration heads.

Pure merge migration — no schema changes. Collapses the three previously
divergent heads into one so `alembic upgrade head` (as every deployment
doc in this repo instructs) resolves unambiguously again:

- ai_handoff_001            (Phase 4: agent task handoff)
- ai_action_team_scope      (Phase 4.6D: team-scoped audit trail)
- subscriptions_initial     (Phase 3: Stripe payment integration)

Before this migration, running `alembic upgrade head` against a real
database would fail outright with "Multiple head revisions are present"
— this was true even before the Phase 3 work that added
`subscriptions_initial` (see organizations_teams_initial.py's docstring:
`ai_agents_001` was a second, disconnected root). This migration is the
final step that makes the whole chain deployable with the single command
every doc already tells operators to run.

Revision ID: merge_phase3_phase4_heads
Revises: ai_handoff_001, ai_action_team_scope, subscriptions_initial
Create Date: 2026-08-27
"""

# revision identifiers
revision = "merge_phase3_phase4_heads"
down_revision = ("ai_handoff_001", "ai_action_team_scope", "subscriptions_initial")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
