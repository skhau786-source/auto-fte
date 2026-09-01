# Agent Runtime — 🟢 COMPLETE

The execution pipeline that turns a request into a validated plan and runs
it through capabilities, including two interchangeable planner
implementations.

## What it does

- `AgentRuntime` (`runtime/runtime.py`, 342 lines) — orchestrates:
  request → plan (via a `BasePlanner`) → validate actions → execute via
  `CapabilityExecutor` → record results, all with audit + event emission.
- `BasePlanner` / rule-based `Planner` (`runtime/planner.py`, 159 lines).
- `LLMPlanner` (`runtime/llm_planner.py`, 448 lines) — uses an LLM to
  generate a plan: discovers available capabilities (`_discover_capabilities`,
  line 207), builds a prompt (`_build_user_prompt`, 242), parses the LLM's
  response into structured actions (`_parse_llm_response`, 284), and
  validates them (`_validate_actions`, 361) before anything executes.
- `runtime/models.py` (205 lines) — `AgentRequest`, `PlanStatus`, and
  related runtime data structures.
- `llm_client.py` (361 lines) — `BaseLLMClient` abstraction so the planner
  isn't hard-wired to one LLM provider.
- `POST /ai/runtime/execute` — the single entry point that runs a request
  through the full pipeline (`app/ai/router.py:557-643`).

## Status detail

| Piece | Status | Evidence |
|---|---|---|
| Runtime orchestration | 🟢 | `runtime/runtime.py` (342 lines) |
| Rule-based planner | 🟢 | `runtime/planner.py` (159 lines) |
| LLM planner | 🟢 | `runtime/llm_planner.py` (448 lines) — plan generation, capability discovery, response parsing, action validation all present |
| LLM client abstraction | 🟢 | `llm_client.py` (361 lines) |
| Runtime models | 🟢 | `runtime/models.py` (205 lines) |
| Endpoint | 🟢 | `router.py:557-643` (`POST /ai/runtime/execute`) |
| Tests | 🟢 | `tests/test_ai_runtime.py` (1,031 lines), `tests/test_ai_llm_planner.py` (799 lines) |

## Full detail

- [`implementation-map.md`](./implementation-map.md)
- [`source-location.md`](./source-location.md)
