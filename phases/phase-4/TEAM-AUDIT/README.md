# 4.6D Team-Level Audit Trail — 🟢 FIXED (was 🟡 PARTIAL)

**Update (2026-08-26):** the two gaps described below have been fixed.
`AIAgentAction` now has a `team_id` column, `TeamService._log_action` no
longer fabricates a fake `agent_id`, agent-scoped actions are stamped with
their agent's `team_id`, and `GET /ai/actions` filters results to the
requesting user's own team scope. See "What changed" below for exact
file/line references and "Verification" for what was and wasn't run.

## What existed before (the original finding)

Write-side logging existed and was unit-tested for every team mutation,
but the storage model wasn't team-shaped and there was no way to query it
by team through the API:

1. **Foreign-key violation risk against a real database.**
   `AIAgentAction.agent_id` was `NOT NULL` with a foreign key to
   `ai_agents.id`, but `TeamService._log_action` wrote
   `agent_id=uuid.uuid4()` — a random UUID that doesn't exist in
   `ai_agents` — for team-level actions (team CRUD, membership,
   agent assignment). Against a real PostgreSQL database this insert
   would fail with a foreign-key constraint violation; it was masked by
   the test suite's mocked `AsyncSession`.
2. **No way to query the audit trail by team.** `GET /ai/actions`
   accepted `agent_id`/`task_id` filters only — no `team_id` column
   existed to filter on.

## What changed

| Area | File | Change |
|---|---|---|
| Model | `app/ai/models.py` | `AIAgentAction.agent_id` is now nullable (was `NOT NULL`); added `team_id` (nullable, FK → `teams.id`, `ON DELETE SET NULL`, indexed) |
| Migration | `alembic/versions/ai_action_team_scope.py` | Relaxes `agent_id` to nullable, adds `team_id` column + index. Does not touch or delete any existing row. |
| Team-level audit writes | `app/ai/team_service.py::_log_action` | Now requires an explicit `team_id` (the team being operated on) and writes `agent_id=None` instead of a fabricated UUID — all 7 call sites (`create_team`, `update_team`, `deactivate_team`, `add_member`, `remove_member`, `assign_agent`, `unassign_agent`) updated |
| Agent-level audit writes | `app/ai/service.py::_log_action` | Gained an optional `team_id` parameter; all 20 agent-scoped call sites pass `team_id=agent.team_id` (from the already-loaded agent object — never a new query, never client-supplied) |
| Read/query path | `app/ai/service.py::get_agent_actions` | Now filters in SQL using the indexed `team_id` column: a row is visible if its `agent_id` is one the user can access, or its `team_id` is one the user can access, or it has neither (org-level action, visible to all org members) |
| New helper | `app/ai/service.py::get_visible_team_ids`, `app/ai/team_service.py::get_user_accessible_team_ids` | Mirrors the existing `get_visible_agent_ids`/`get_user_accessible_agent_ids` pattern (OWNER/ADMIN see all teams; a member sees only their own team) |
| API | `app/ai/router.py` (`GET /ai/actions`), `app/ai/schemas.py` (`AgentActionOut`) | Response now includes `team_id`; `agent_id` is nullable in the response too. No client-supplied `team_id` filter was added — scoping is always derived server-side from the authenticated user, never trusted from request input |
| Frontend contract | `frontend-fte/lib/api.ts` (`AIAgentAction` interface) | `agent_id` marked nullable, `team_id` added, matching the API response shape |

One deliberate exception: the `task_handoff` audit action (source agent
hands off to a target agent) leaves `team_id` unset, since source and
target may belong to different teams and neither loaded object at that
call site is guaranteed to match the logged `agent_id`'s team. This row
stays correctly scoped via its (unchanged) `agent_id` field — see the
comment at `app/ai/service.py::handoff_task`'s `_log_action` call for the
full reasoning.

## Verification

- **Unit tests (mocked `AsyncSession`, this project's standard for
  Phase 4):** `tests/test_ai_action_team_scope.py` (15 tests) plus 2
  updated assertions in `tests/test_ai_teams.py::TestTeamAuditLogging`.
  Cover: action creation carries the correct `team_id` (team-level and
  agent-level, including teamless agents); a team member retrieves only
  their team's actions; cross-team actions are excluded (and the SQL
  `WHERE` clause itself is asserted to reference `team_id`, not just a
  Python post-filter); an empty team gets an empty result; OWNER/ADMIN,
  teamless/org-level actions, internal execution, and explicit
  `agent_id`/`task_id` filters all continue working. **All passing.**
- **Full Phase 4 regression:** all 8 pre-existing AI test files
  (588 tests) still pass unchanged, plus the new file — 603 passed, 0
  failed.
- **Real PostgreSQL integration test:** `tests/test_ai_action_team_scope.py::TestRealDatabaseSchema`
  contains two tests — one that inserts a team-only action
  (`agent_id=NULL`) against a real schema (the exact scenario that used to
  violate the FK), and one confirming agent-scoped inserts are unaffected.
  These are gated by the project's existing `_postgres_available()` check
  (same mechanism every DB-integration test in this repo already uses) and
  **were not executed in the environment this fix was written in** — no
  PostgreSQL instance was reachable there. They will run automatically
  wherever this project's test database is configured (CI, or a developer
  machine with `TEST_DATABASE_URL` pointed at a real Postgres). This is
  the one honest limitation of this fix's verification — see the parent
  session's final report for the same caveat stated plainly.

## Full detail

- [`implementation-map.md`](./implementation-map.md)
- [`source-location.md`](./source-location.md)
