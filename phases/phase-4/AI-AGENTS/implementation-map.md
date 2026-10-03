# AI Agent Foundation — Implementation Map

## Backend — `backend-fte/app/ai/`

| File | Lines | Relevant sections |
|---|---|---|
| `models.py` | 260 | `AIAgent` (28-100), `AIAgentTask` (102-206), `AIAgentAction` (208-260) |
| `service.py` | 1,597 | `AIService` — agent/task CRUD, approval, action logging (`_create_audit_log` ~line 1583) |
| `router.py` | 1,442 | Endpoints listed below |
| `schemas.py` | 506 | `AgentOut`, `TaskOut`, `TaskSubmitRequest`, `TaskApprovalRequest`, `AgentActionOut`, etc. |
| `dependencies.py` | 82 | `require_agent_manage` (30), `require_agent_execute` (50), `require_agent_approve` (70) |
| `constants.py` | 59 | `TaskStatus` incl. `PENDING_APPROVAL` (line 25) |
| `exceptions.py` | 250 | `TaskNotPendingApprovalError`, `TaskRequiresApprovalError` (56-75) |
| `events.py` | 363 | Domain events, incl. `requires_approval` flag (line 74) |
| `metrics.py` | 133 | Prometheus metrics incl. pending-approval gauge |

## Router endpoints (`app/ai/router.py`)

| Endpoint | Lines |
|---|---|
| `POST /ai/agents` (create) | 165-193 |
| `GET /ai/agents` (list) | 193-212 |
| `GET /ai/agents/{id}` (get) | 212-232 |
| `PATCH /ai/agents/{id}` (update) | 232-261 |
| `DELETE /ai/agents/{id}` (deactivate) | 261-286 |
| `POST /ai/tasks` (submit) | 286-315 |
| `GET /ai/tasks` (list) | 315-354 |
| `GET /ai/tasks/{id}` (get) | 354-373 |
| `POST /ai/tasks/{id}/approve` | 373-393 |
| `POST /ai/tasks/{id}/reject` | 393-417 |

## Migrations

| File | Lines |
|---|---|
| `alembic/versions/ai_agents.py` | 156 |

## Tests

| File | Lines |
|---|---|
| `tests/test_ai_agents.py` | 3,290 |

## Dependents

- `app/ai/team_service.py` writes into the same `AIAgentAction` table (see
  `../TEAM-AUDIT/`).
- `app/ai/runtime/runtime.py` and `app/ai/workflow/engine.py` both create
  `AIAgentTask`/`AIAgentAction` rows through `AIService`.
- `app/ai/capabilities/executor.py` checks `granted_permissions` on
  `AIAgent` before executing a capability.
