# 4.6D Team-Level Audit Trail — Implementation Map

Updated 2026-08-26 after the team-scoping fix (see `README.md` for the
before/after). Line numbers below reflect the current state of each file.

## Backend — `backend-fte/app/ai/models.py`

| Symbol | Line | Notes |
|---|---|---|
| `AIAgentAction` | 208 | class docstring explains the nullable `agent_id`/`team_id` design |
| `AIAgentAction.agent_id` | 229 | now nullable (was `NOT NULL`), FK → `ai_agents.id`, `ON DELETE CASCADE` (unchanged) |
| `AIAgentAction.team_id` | 236 | new column, nullable, FK → `teams.id`, `ON DELETE SET NULL`, indexed |
| `AIAgent.team_id` | 46 | the pre-existing sibling column this design mirrors |

## Backend — `backend-fte/app/ai/team_service.py`

| Symbol | Line | Notes |
|---|---|---|
| `_log_action` | 769 | now takes `team_id` as a required parameter; writes `agent_id=None` |
| `get_user_accessible_team_ids` | 617 | new — OWNER/ADMIN see all org teams, a member sees only their own team |
| 7 call sites | 91, 164, 205, 263, 305, 392, 435 | each now passes `team_id=team.id` |

## Backend — `backend-fte/app/ai/service.py`

| Symbol | Line | Notes |
|---|---|---|
| `get_visible_agent_ids` | 548 | pre-existing, unchanged |
| `get_visible_team_ids` | 573 | new — mirrors `get_visible_agent_ids`, delegates to `TeamService.get_user_accessible_team_ids` |
| `get_agent_actions` | 797 | now applies SQL-level team/agent visibility filtering when `user_id is not None` |
| `_log_action` | 1661 | gained an optional `team_id` parameter (never re-derived via a new query — always passed in from an already-loaded `AIAgent` by the caller) |
| 20 agent-scoped call sites | throughout | each passes `team_id=agent.team_id` from an already-loaded agent object |
| `handoff_task`'s `_log_action` call | — | the one exception: `team_id` intentionally omitted, with an explanatory comment in the source |

## Backend — `backend-fte/app/ai/router.py` / `schemas.py`

| Symbol | Notes |
|---|---|
| `GET /ai/actions` (`list_actions`, line 517) | response now includes `team_id`; no client-supplied team filter — scoping is always server-derived |
| `AgentActionOut` | `agent_id` now `Optional[str]`, `team_id: Optional[str]` added |

## Frontend — `frontend-fte/lib/api.ts`

| Symbol | Notes |
|---|---|
| `AIAgentAction` interface | `agent_id: string \| null`, `team_id: string \| null` — matches the API response |

## Migration

| File | Notes |
|---|---|
| `backend-fte/alembic/versions/ai_action_team_scope.py` | `down_revision = "ai_team_agents_001"`; relaxes `agent_id` nullable, adds `team_id` + index. Downgrade removes `team_id` but deliberately does not restore `agent_id`'s `NOT NULL` (would require deleting or fabricating audit rows — see the migration's own docstring). |

## Tests

| File | Notes |
|---|---|
| `backend-fte/tests/test_ai_action_team_scope.py` | 17 tests: action creation (3), get_agent_actions team scoping incl. cross-team isolation and empty-team (4), existing-behavior preservation (4), `get_user_accessible_team_ids` unit tests (4), real-Postgres-gated schema tests (2, skipped in this environment — see README.md "Verification") |
| `backend-fte/tests/test_ai_teams.py::TestTeamAuditLogging` | 2 of the 8 existing tests gained `team_id`/`agent_id` assertions |
