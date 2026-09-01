# Advanced Automation Workflows — 🟢 COMPLETE

Multi-step, conditional workflow execution built on top of the capability
system and runtime.

## What it does

- `WorkflowEngine` (`workflow/engine.py`, 399 lines) — `execute` (103),
  `validate_workflow` (212, public) / `_validate_workflow` (261, internal),
  `_execute_step` (277). Raises `WorkflowValidationError` /
  `WorkflowStepError` (50-70) for bad definitions or failed steps.
- `workflow/models.py` (395 lines) — `WorkflowStatus`, `StepStatus`,
  `WorkflowCondition` (conditional branching), `WorkflowStep`,
  `WorkflowDefinition`, `WorkflowStepResult`, `WorkflowResult` — the module
  docstring calls these "persistent, auditable" (`workflow/__init__.py`).
- Endpoints:
  - `POST /ai/workflows` — create + execute (`router.py:819-950`).
  - `POST /ai/workflows/validate` — dry-run validation without executing
    (`router.py:950-1016`).
  - `GET /ai/workflows` — list (`router.py:1016-1063`).
  - `GET /ai/workflows/{id}` — get one (`router.py:1063-1149`).

## Status detail

| Piece | Status | Evidence |
|---|---|---|
| Engine | 🟢 | `workflow/engine.py` (399 lines) |
| Models | 🟢 | `workflow/models.py` (395 lines) |
| Create+execute endpoint | 🟢 | `router.py:819-950` |
| Validate-only endpoint | 🟢 | `router.py:950-1016` |
| List/get endpoints | 🟢 | `router.py:1016-1149` |
| Conditional steps | 🟢 | `WorkflowCondition` class (`workflow/models.py:63`) |
| Persistence/audit | 🟢 | `WorkflowResult` persisted; task_id linkage documented in `engine.py:117` |
| Tests | 🟢 | `tests/test_ai_workflows.py` (1,310 lines) |

## Full detail

- [`implementation-map.md`](./implementation-map.md)
- [`source-location.md`](./source-location.md)
