# Advanced Automation Workflows — Canonical Source Location

**Canonical implementation — edit only here:**

```
backend-fte/app/ai/workflow/
backend-fte/app/ai/router.py    (lines 819-1149)
```

**Do not duplicate.** Workflow steps execute through the shared
`CapabilityExecutor` (`../CAPABILITIES/`) — do not fork capability-execution
logic into the workflow engine.

No snapshot exists.
