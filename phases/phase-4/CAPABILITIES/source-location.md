# Capability System — Canonical Source Location

**Canonical implementation — edit only here:**

```
backend-fte/app/ai/capabilities/
backend-fte/app/ai/router.py        (lines 417-512)
backend-fte/alembic/versions/ai_agent_handoff.py
```

**Do not duplicate.** `sales_capabilities.py` is the single source for
revenue/analytics logic referenced from both `phases/phase-3/` (commerce
angle) and here (AI angle). `inventory_capabilities.py` calls directly into
`app/inventory/service.py` and friends — see
`../../phase-3/INVENTORY/source-location.md`. Any change to capability
behavior belongs in `app/ai/capabilities/`, never copied into a phase
folder.

No snapshot exists.
