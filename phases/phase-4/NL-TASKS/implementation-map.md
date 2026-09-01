# Natural Language Task Execution — Implementation Map

| File | Lines/Location | Purpose |
|---|---|---|
| `backend-fte/app/ai/router.py` | 643-819 | `POST /ai/tasks/nl` (`create_nl_task`) |
| `backend-fte/app/ai/service.py` | `submit_nl_task` method | Creates the task, invokes the planner, persists plan + results |
| `backend-fte/app/ai/schemas.py` | `NLTaskRequest`, `NLTaskResponse` | Request/response models |
| `backend-fte/app/ai/runtime/llm_planner.py` | see `../AGENT-RUNTIME/implementation-map.md` | Plan generation used by this endpoint |
| `backend-fte/tests/test_ai_nl_tasks.py` | 1,101 lines | Full test coverage |

## Dependents / dependencies

- Depends on `../AGENT-RUNTIME/` (`LLMPlanner`) for plan generation.
- Depends on `../AI-AGENTS/` for the `PENDING_APPROVAL` state machine.
- Depends on `../TEAM-AUTHORIZATION/` (`check_team_agent_access`) to gate
  which agents a user may submit NL tasks to.
