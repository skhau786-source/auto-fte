# Agent Runtime — Canonical Source Location

**Canonical implementation — edit only here:**

```
backend-fte/app/ai/runtime/
backend-fte/app/ai/llm_client.py
backend-fte/app/ai/router.py    (lines 557-643)
```

**Do not duplicate.** `runtime/runtime.py` and `runtime/llm_planner.py` are
the shared execution core for NL Tasks (`../NL-TASKS/`) and, indirectly,
Automation Workflows (`../AUTOMATION-WORKFLOWS/`). Change behavior here
once; do not fork a copy per consuming feature.

No snapshot exists.
