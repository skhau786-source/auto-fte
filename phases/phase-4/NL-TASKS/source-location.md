# Natural Language Task Execution — Canonical Source Location

**Canonical implementation — edit only here:**

```
backend-fte/app/ai/router.py     (lines 643-819)
backend-fte/app/ai/service.py    (submit_nl_task)
backend-fte/app/ai/schemas.py    (NLTaskRequest, NLTaskResponse)
```

**Do not duplicate.** This endpoint is a thin orchestration layer over
`../AGENT-RUNTIME/`'s `LLMPlanner` and `../AI-AGENTS/`'s task state machine
— both canonical elsewhere. Nothing NL-task-specific needs a copy.

No snapshot exists.
