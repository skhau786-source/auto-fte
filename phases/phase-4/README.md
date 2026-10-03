# Phase 4 — AI Agent Platform

Roadmap phase covering: AI Agents, Capabilities, Agent Runtime, NL Tasks,
Automation Workflows, Team Collaboration, Team Authorization, Team
Filtering, Team Audit Trail.

See `../README.md` for why this numbering is unrelated to the "Phase N"
comments found inside `backend-fte` source files (those refer to the
inventory subsystem's build order, not AI features).

This is a single, large module — `backend-fte/app/ai/` (~9,200 lines
across 22 files) — organized into 9 documentation folders below by
sub-feature. All 9 folders describe **the same codebase**, viewed from 9
angles; several source files (`service.py`, `router.py`, `models.py`) are
referenced from multiple folders because the code genuinely spans multiple
sub-features. None of it was duplicated to make that possible — every
folder's `source-location.md` points at the same canonical files.

## Status summary

| Feature | Status | Folder |
|---|---|---|
| AI Agent Foundation | 🟢 COMPLETE | [`AI-AGENTS/`](./AI-AGENTS/README.md) |
| Capability System | 🟢 COMPLETE | [`CAPABILITIES/`](./CAPABILITIES/README.md) |
| Agent Runtime | 🟢 COMPLETE | [`AGENT-RUNTIME/`](./AGENT-RUNTIME/README.md) |
| Natural Language Task Execution | 🟢 COMPLETE | [`NL-TASKS/`](./NL-TASKS/README.md) |
| Advanced Automation Workflows | 🟢 COMPLETE | [`AUTOMATION-WORKFLOWS/`](./AUTOMATION-WORKFLOWS/README.md) |
| 4.6A Team & Agent Collaboration | 🟢 COMPLETE | [`TEAM-COLLABORATION/`](./TEAM-COLLABORATION/README.md) |
| 4.6B Team-Level Authorization | 🟢 COMPLETE | [`TEAM-AUTHORIZATION/`](./TEAM-AUTHORIZATION/README.md) |
| 4.6C Team/Task/Workflow Visibility | 🟢 COMPLETE | [`TEAM-FILTERING/`](./TEAM-FILTERING/README.md) |
| 4.6D Team-Level Audit Trail | 🟢 FIXED (was 🟡 PARTIAL) | [`TEAM-AUDIT/`](./TEAM-AUDIT/README.md) |

Full detail: [`MANIFEST.md`](./MANIFEST.md).

## 4.6D Team-Level Audit Trail — fixed 2026-08-26

This was the one real gap in Phase 4: `AIAgentAction.agent_id` was
`NOT NULL` with a foreign key to `ai_agents.id`, but team-level actions
(team CRUD, membership, agent assignment) have no real agent, so
`TeamService._log_action` fabricated a random `agent_id=uuid.uuid4()` —
a value that doesn't exist in `ai_agents` and would violate the foreign
key against a real Postgres database (masked by the test suite's mocked
`AsyncSession`). There was also no `team_id` column and no way to filter
`GET /ai/actions` by team.

Both are fixed: `AIAgentAction` now has a nullable `team_id` (FK → teams,
`ON DELETE SET NULL`) and a nullable `agent_id`; team-level actions write
`agent_id=None`/`team_id=<the team>`, agent-level actions are stamped with
`team_id=agent.team_id`; and `get_agent_actions()`/`GET /ai/actions` filter
in SQL to the requesting user's own team scope (never a client-supplied
`team_id`). See `TEAM-AUDIT/README.md` for the full before/after, exact
file/line references, and — importantly — what was and wasn't verified
against a real database (a real-Postgres-gated test exists but did not run
in the environment this fix was written in; see that doc's "Verification"
section).
