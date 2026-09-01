# Capability System — 🟢 COMPLETE

The plugin system that gives agents concrete abilities (query inventory,
analyze sales, post to social, etc.), plus the registry and secure executor
that runs them.

## What it does

- `BaseCapability` abstract class + `CapabilityDescriptor` metadata
  (name, category, supported agent types, required permissions).
- `CapabilityRegistry` — a singleton (`capability_registry`,
  `app/ai/capabilities/base.py:153`) that every capability registers into.
- `CapabilityExecutor` — runs a capability with permission checks and audit
  logging (`app/ai/capabilities/executor.py`).
- Three domain capability packs, each with multiple capabilities:
  - **Inventory** (`inventory_capabilities.py`, 451 lines) — e.g. the
    inventory audit-trail capability (line 223).
  - **Sales** (`sales_capabilities.py`, 274 lines) — order analysis, top
    products, revenue summary (also documented from the commerce side in
    `../../phase-3/ADVANCED-ANALYTICS/` and `../../phase-3/REVENUE-DASHBOARD/`
    — same file, not duplicated).
  - **Social** (`social_capabilities.py`, 201 lines).
- `POST /ai/capabilities/{name}/execute` — direct capability execution
  endpoint (`app/ai/router.py:456-481`).
- `GET /ai/capabilities` — list registered capabilities
  (`app/ai/router.py:417-456`).
- Agent handoff — `POST /ai/tasks/{id}/handoff` hands a task to another
  agent for a specific capability (`app/ai/router.py:481-512`).

## Status detail

| Piece | Status | Evidence |
|---|---|---|
| Base classes + registry | 🟢 | `app/ai/capabilities/base.py` (153 lines) |
| Executor | 🟢 | `app/ai/capabilities/executor.py` (203 lines) |
| Inventory capabilities | 🟢 | `inventory_capabilities.py` (451 lines) |
| Sales capabilities | 🟢 | `sales_capabilities.py` (274 lines) |
| Social capabilities | 🟢 | `social_capabilities.py` (201 lines) |
| List/execute endpoints | 🟢 | `router.py:417-481` |
| Agent handoff | 🟢 | `router.py:481-512`, uses `AIService.handoff_task` |
| Migration for handoff | 🟢 | `alembic/versions/ai_agent_handoff.py` (60 lines) |
| Tests | 🟢 | covered within `tests/test_ai_agents.py` and `tests/test_ai_runtime.py` (capability execution + handoff paths) |

## Full detail

- [`implementation-map.md`](./implementation-map.md)
- [`source-location.md`](./source-location.md)
