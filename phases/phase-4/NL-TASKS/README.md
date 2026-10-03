# Natural Language Task Execution — 🟢 COMPLETE

Turns a free-text instruction into a persistent, auditable task that plans
and (optionally) auto-executes itself.

## What it does

`POST /ai/tasks/nl` (`app/ai/router.py:643-819`) — flow documented in the
endpoint's own docstring (lines 655-664):

1. Validate agent exists and is active.
2. Create a persistent `AIAgentTask`.
3. `LLMPlanner` (see `../AGENT-RUNTIME/`) produces a validated execution
   plan from the instruction.
4. Plan is persisted in `task.output_data`.
5. Non-approval tasks auto-execute through the runtime.
6. Approval-required tasks stay in `PENDING_APPROVAL` (see
   `../AI-AGENTS/` for the approval mechanism).

Also performs a **team-level authorization check**
(`service.check_team_agent_access(agent_obj)`, `router.py:680`) before
planning — one of 9 call sites for this shared check; see
`../TEAM-AUTHORIZATION/` for the full list.

Explicitly documented as additive/backward-compatible in its own docstring:
`POST /ai/agents/{id}/tasks` and `POST /ai/runtime/execute` are unaffected.

## Status detail

| Piece | Status | Evidence |
|---|---|---|
| Endpoint | 🟢 | `router.py:643-819` (`POST /ai/tasks/nl`) |
| Service method | 🟢 | `AIService.submit_nl_task` (`app/ai/service.py`) |
| Team authorization check | 🟢 | `router.py:678` calls `service.check_team_agent_access` |
| Plan generation | 🟢 | delegates to `LLMPlanner` — see `../AGENT-RUNTIME/` |
| Tests | 🟢 | `tests/test_ai_nl_tasks.py` (1,101 lines) |

## Full detail

- [`implementation-map.md`](./implementation-map.md)
- [`source-location.md`](./source-location.md)
