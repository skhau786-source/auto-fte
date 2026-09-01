# Agent Runtime — Implementation Map

## Backend — `backend-fte/app/ai/runtime/` and related

| File | Lines | Key sections |
|---|---|---|
| `runtime/runtime.py` | 342 | `AgentRuntime`, `RuntimeValidationError` |
| `runtime/planner.py` | 159 | `BasePlanner`, rule-based `Planner` |
| `runtime/llm_planner.py` | 448 | `LLMPlanner` — `create_plan` (131), `_discover_capabilities` (207), `_build_user_prompt` (242), `_parse_llm_response` (284), `_validate_actions` (361), `get_capability_metadata_for_prompt` (440) |
| `runtime/models.py` | 205 | `AgentRequest`, `PlanStatus`, plan/action data structures |
| `runtime/__init__.py` | 62 | Module exports |
| `llm_client.py` | 361 | `BaseLLMClient` and concrete client(s) |

## Router (`app/ai/router.py`)

| Endpoint | Lines |
|---|---|
| `POST /ai/runtime/execute` | 557-643 |

## Tests

| File | Lines |
|---|---|
| `tests/test_ai_runtime.py` | 1,031 |
| `tests/test_ai_llm_planner.py` | 799 |

## Dependents

- `NL Tasks` (`../NL-TASKS/`) builds on top of `AgentRuntime`/`LLMPlanner`
  to turn free-text into an executed plan.
- `Automation Workflows` (`../AUTOMATION-WORKFLOWS/`) can invoke runtime
  execution as a workflow step.
