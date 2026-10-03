# Phase 4 — Manifest

| Feature | Status | Canonical source | Frontend | Tests | Migrations | Notes |
|---|---|---|---|---|---|---|
| AI Agent Foundation | 🟢 COMPLETE | `app/ai/models.py`, `service.py`, `router.py:165-417`, `dependencies.py` | `app/components/AIAgentsHub.tsx` (852 lines) | `test_ai_agents.py` (3,290 lines) | `ai_agents.py` | RBAC via `AGENT_MANAGE`/`AGENT_EXECUTE`/`AGENT_APPROVE`; human approval state machine |
| Capability System | 🟢 COMPLETE | `app/ai/capabilities/` | — | covered in `test_ai_agents.py`, `test_ai_runtime.py` | `ai_agent_handoff.py` | Registry + executor + 3 domain capability packs (inventory/sales/social) |
| Agent Runtime | 🟢 COMPLETE | `app/ai/runtime/`, `app/ai/llm_client.py` | — | `test_ai_runtime.py` (1,031), `test_ai_llm_planner.py` (799) | — | Rule-based + LLM planners, both wired into `AgentRuntime` |
| Natural Language Task Execution | 🟢 COMPLETE | `app/ai/router.py:643-819`, `service.py:submit_nl_task` | — | `test_ai_nl_tasks.py` (1,101) | — | Built on Agent Runtime; team-authorized |
| Advanced Automation Workflows | 🟢 COMPLETE | `app/ai/workflow/` | — | `test_ai_workflows.py` (1,310) | — | Conditional multi-step execution, validate-only endpoint |
| 4.6A Team & Agent Collaboration | 🟢 COMPLETE | `app/ai/team_service.py` (lines 73-470), `router.py:1160-1442` | — | `test_ai_teams.py` (1,220) | `ai_team_agents.py` | Team CRUD, member mgmt, agent assignment |
| 4.6B Team-Level Authorization | 🟢 COMPLETE | `team_service.py:479-620`, `service.py:1627` | — | `test_ai_team_auth.py` (684) | — | `check_team_agent_access` called from 9 endpoints |
| 4.6C Team/Task/Workflow Visibility | 🟢 COMPLETE | `service.py:599-696` | — | `test_ai_team_filtering.py` (967) | — | Includes deliberate 404-not-403 anti-leakage design |
| 4.6D Team-Level Audit Trail | 🟢 FIXED (was 🟡 PARTIAL) | `team_service.py:_log_action` (line 769), `service.py:_log_action`/`get_agent_actions`/`get_visible_team_ids` (lines 1661/797/573), `models.py:208-260`, `router.py:512-546` | `lib/api.ts` (`AIAgentAction` interface) | `test_ai_action_team_scope.py` (17 tests, mocked + 2 real-Postgres-gated), `test_ai_teams.py::TestTeamAuditLogging` (updated) | `ai_action_team_scope.py` | `agent_id` now nullable, `team_id` added (FK → teams, `ON DELETE SET NULL`, indexed); no more fabricated `agent_id`; `GET /ai/actions` filters in SQL to the user's own team scope, never a client-supplied `team_id` |

**Test run (2026-08-26, after the 4.6D fix):**

```
cd backend-fte
./venv/Scripts/python.exe -m pytest tests/test_ai_agents.py tests/test_ai_runtime.py \
  tests/test_ai_llm_planner.py tests/test_ai_nl_tasks.py tests/test_ai_workflows.py \
  tests/test_ai_teams.py tests/test_ai_team_auth.py tests/test_ai_team_filtering.py \
  tests/test_ai_action_team_scope.py -q --tb=short
```
→ **603 passed, 0 failed, 2 skipped** (the 2 skips are the real-Postgres
integration tests for the 4.6D fix — no PostgreSQL was reachable in this
environment; see `TEAM-AUDIT/README.md` → "Verification").

Full backend suite (`pytest tests/`): **755 passed, 0 failed, 181 skipped**
(all skips are pre-existing DB-gated integration tests, same mechanism).

## Dependency graph (informal)

```
AI-AGENTS  ← everything else depends on Agent/Task/Action models + RBAC
   ├─ CAPABILITIES        (executes via granted_permissions + registry)
   ├─ AGENT-RUNTIME        (plans + executes tasks)
   │    └─ NL-TASKS         (free-text → runtime execution)
   ├─ AUTOMATION-WORKFLOWS (multi-step, uses CAPABILITIES per step)
   └─ TEAM-COLLABORATION   (team_service.py)
        ├─ TEAM-AUTHORIZATION (auth-check methods on team_service.py)
        │    └─ TEAM-FILTERING (list/get filtering built on the auth checks)
        └─ TEAM-AUDIT          (reuses AI-AGENTS' AIAgentAction table, now team_id-aware)
```
