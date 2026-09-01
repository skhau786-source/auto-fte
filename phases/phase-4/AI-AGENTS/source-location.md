# AI Agent Foundation — Canonical Source Location

**Canonical implementation — edit only here:**

```
backend-fte/app/ai/models.py       (AIAgent, AIAgentTask, AIAgentAction)
backend-fte/app/ai/service.py      (AIService)
backend-fte/app/ai/router.py       (agent/task endpoints, lines 165-417)
backend-fte/app/ai/schemas.py
backend-fte/app/ai/dependencies.py (RBAC)
backend-fte/alembic/versions/ai_agents.py
```

**Do not duplicate.** `service.py` and `models.py` are the shared spine for
every other Phase 4 folder in this directory — Capabilities, Runtime,
NL Tasks, Workflows, and Teams all import from here. A copy under `phases/`
edited independently would immediately diverge from what `router.py`
actually calls. Every other Phase 4 `source-location.md` in this directory
repeats this same instruction rather than re-copying the file.

No snapshot exists.
