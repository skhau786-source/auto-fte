# Advanced Automation Workflows — Implementation Map

## Backend — `backend-fte/app/ai/workflow/`

| File | Lines | Key sections |
|---|---|---|
| `engine.py` | 399 | `WorkflowValidationError` (50), `WorkflowStepError` (59), `WorkflowEngine` (71) — `execute` (103), `validate_workflow` (212), `_validate_workflow` (261), `_execute_step` (277) |
| `models.py` | 395 | `WorkflowStatus` (26), `StepStatus` (37), `WorkflowCondition` (63), `WorkflowStep` (169), `WorkflowDefinition` (222), `WorkflowStepResult` (317), `WorkflowResult` (347) |
| `__init__.py` | 57 | Module summary |

## Router (`app/ai/router.py`)

| Endpoint | Lines |
|---|---|
| `POST /ai/workflows` | 819-950 |
| `POST /ai/workflows/validate` | 950-1016 |
| `GET /ai/workflows` | 1016-1063 |
| `GET /ai/workflows/{id}` | 1063-1149 |

## Tests

| File | Lines |
|---|---|
| `tests/test_ai_workflows.py` | 1,310 |

## Dependents

- Each workflow step ultimately executes via
  `../CAPABILITIES/`'s `CapabilityExecutor`.
- Workflow steps can invoke `../AGENT-RUNTIME/` for LLM-planned sub-steps.
