# Capability System — Implementation Map

## Backend — `backend-fte/app/ai/capabilities/`

| File | Lines | Purpose |
|---|---|---|
| `base.py` | 153 | `CapabilityType`, `CapabilityCategory`, `CapabilityDescriptor`, `BaseCapability`, `CapabilityRegistry`, singleton `capability_registry` (line 153) |
| `executor.py` | 203 | `CapabilityExecutor` — permission check + execution + audit logging |
| `inventory_capabilities.py` | 451 | Inventory-domain capabilities, incl. audit-trail capability (line 223) |
| `sales_capabilities.py` | 274 | `SalesAnalyzeOrdersCapability` (33-108), `SalesTopProductsCapability` (110-172), `SalesRevenueSummaryCapability` (174-257), `register_sales_capabilities()` (266) |
| `social_capabilities.py` | 201 | Social-domain capabilities |

## Router (`app/ai/router.py`)

| Endpoint | Lines |
|---|---|
| `GET /ai/capabilities` | 417-456 |
| `POST /ai/capabilities/{name}/execute` | 456-481 |
| `POST /ai/tasks/{id}/handoff` | 481-512 |

## Migrations

| File | Lines |
|---|---|
| `alembic/versions/ai_agent_handoff.py` | 60 |

## Cross-references (not duplicated elsewhere)

- `sales_capabilities.py` is also referenced from
  `../../phase-3/ADVANCED-ANALYTICS/` and `../../phase-3/REVENUE-DASHBOARD/`
  — same file, documented from the commerce-feature angle there.
- `inventory_capabilities.py` calls into `app/inventory/` services — see
  `../../phase-3/INVENTORY/implementation-map.md` → "Dependents".
