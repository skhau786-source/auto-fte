# AI Agent Foundation — 🟢 COMPLETE

Core agent + task CRUD, human approval workflow, and RBAC permission
enforcement.

## What it does

- Agent CRUD (create, list, get, update, deactivate) with per-agent
  `granted_permissions`.
- Task lifecycle: submit → (optional) `PENDING_APPROVAL` → approve/reject
  → execute → `COMPLETED`/`FAILED`.
- Human-in-the-loop approval: an agent/task can be flagged
  `requires_human_approval`; execution is blocked
  (`TaskRequiresApprovalError`) until a human calls the approve endpoint.
- RBAC via three permissions: `AGENT_MANAGE`, `AGENT_EXECUTE`,
  `AGENT_APPROVE`, enforced through FastAPI dependencies.
- Immutable audit trail of every agent action (`AIAgentAction`).

## Status detail

| Piece | Status | Evidence |
|---|---|---|
| Agent model | 🟢 | `app/ai/models.py:28-100` (`AIAgent`) |
| Task model + state machine | 🟢 | `app/ai/models.py:102-206` (`AIAgentTask`), docstring documents `PENDING → PENDING_APPROVAL → RUNNING → COMPLETED/FAILED` |
| Action audit model | 🟢 | `app/ai/models.py:208-260` (`AIAgentAction`) — see `../TEAM-AUDIT/` for a gap when this table is reused for team-level actions |
| Agent CRUD endpoints | 🟢 | `app/ai/router.py:165-286` (create/list/get/update/deactivate) |
| Task submit/list/get | 🟢 | `app/ai/router.py:286-373` |
| Approve/reject endpoints | 🟢 | `app/ai/router.py:373-417` |
| RBAC dependencies | 🟢 | `app/ai/dependencies.py:30-82` (`require_agent_manage`, `require_agent_execute`, `require_agent_approve`) |
| Service layer | 🟢 | `app/ai/service.py` (1,597 lines) |
| Exceptions | 🟢 | `app/ai/exceptions.py:56-75` (`TaskNotPendingApprovalError`, `TaskRequiresApprovalError`) |
| Metrics | 🟢 | `app/ai/metrics.py:70-72,129-130` (`ai_tasks_pending_approval` gauge) |
| Migrations | 🟢 | `alembic/versions/ai_agents.py` (156 lines) |
| Tests | 🟢 | `tests/test_ai_agents.py` (3,290 lines) |

## Test run (this audit)

`test_ai_agents.py` ran as part of the combined AI suite (see
`../MANIFEST.md`): **588 passed, 0 failed** across all 8 AI test files.

## Full detail

- [`implementation-map.md`](./implementation-map.md)
- [`source-location.md`](./source-location.md)
