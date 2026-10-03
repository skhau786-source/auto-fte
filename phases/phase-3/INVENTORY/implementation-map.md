# Inventory — Implementation Map

All paths relative to repo root. Nothing here was moved; this is an index
into `backend-fte/` and `frontend-fte/`.

## Models — `backend-fte/app/models.py`

| Model | Line | Purpose |
|---|---|---|
| `Store` | 87 | Tenant's connected commerce store |
| `Category` | 121 | Product category |
| `Product` | 157 | Product catalog entry |
| `ProductVariant` | 201 | SKU-level variant with stock quantity |
| `InventoryTransaction` | 246 | Stock movement ledger entry |
| `InventoryLog` | 289 | Structured action log (sync, adjustment, etc.) |
| `StoreSettings` | 325 | Per-store config, incl. `allocation_priority` (added by migration `allocation_engine`) |
| `InventoryReservation` | 365 | Reservation record — reused by both the reservation engine and the allocation engine (allocation does not have its own table; it consumes/produces `InventoryReservation` rows via `ReservationService`) |

## Backend — `backend-fte/app/inventory/`

| File | Lines | Purpose |
|---|---|---|
| `repository.py` | 729 | `ProductRepository`, `VariantRepository` — data access |
| `service.py` | 961 | Core inventory service (CRUD, stock adjustment, sync) |
| `reservation_service.py` | 469 | Reserve → commit/release stock, expiry handling |
| `allocation_service.py` | 356 | Allocates stock to orders using pluggable strategies; imports `InventoryReservation` directly (`allocation_service.py:28`) |
| `allocation_strategies.py` | 96 | Strategy implementations (incl. `PriorityWarehouseStrategy`) |
| `aggregation_engine.py` | 401 | Cross-store/warehouse stock aggregation |
| `aggregation_cache.py` | 213 | Caching layer for aggregation queries |
| `audit_service.py` | 273 | Immutable inventory audit trail |
| `rate_limiter.py` | 154 | Rate limiting for mutating endpoints |
| `router.py` | 388 | Tenant-facing inventory API |
| `admin_router.py` | 345 | Admin-only inventory API |
| `reservation_router.py` | 371 | Reservation API |
| `allocation_router.py` | 321 | Allocation API |
| `aggregation_router.py` | 160 | Aggregation API |
| `schemas.py` | 314 | Pydantic request/response models |
| `constants.py` | 79 | Enums: `ReservationSource`, `ReservationStatus`, `TransactionType`, `InventoryAction` |
| `exceptions.py` | 216 | Domain exceptions |
| `dependencies.py` | 47 | `get_store_for_user` and friends |

## Dashboard — `backend-fte/app/dashboard/` (inventory-only monitoring, not revenue)

| File | Lines | Purpose |
|---|---|---|
| `dashboard.py` | 45 | `GET /dashboard` router |
| `dashboard_service.py` | 244 | Aggregates inventory health metrics (low/out-of-stock, sync health, webhook health, recent errors) |
| `dashboard_schema.py` | 71 | Response schema |
| `unified_router.py` / `unified_service.py` / `unified_schema.py` | 52 / 258 / 121 | `GET /dashboard/unified` — combines Inventory + Reservation + Allocation + Order Integration + Aggregation into one response. Docstring in `unified_service.py:1-16` labels these with the codebase's **internal** Phase 1/3/4/5/6 numbers — see `../../README.md` for why that's unrelated to this roadmap's Phase 3/4. |

## Export — `backend-fte/app/export/`

| File | Lines | Purpose |
|---|---|---|
| `export_service.py` | 285 | CSV/Excel/JSON export of products, variants, transactions, logs, dashboard reports |
| `export_router.py` | 147 | 3 endpoints (`GET` × 3) |

## Frontend — `frontend-fte/`

| File | Lines | Purpose |
|---|---|---|
| `app/components/InventoryHub.tsx` | 1,321 | Inventory UI — the dedicated hub. Currently shows as modified in `git status` (pre-existing working-tree change, not touched by this audit). |
| `lib/api.ts` | 949 | API client, includes inventory endpoint bindings |

## Tests — `backend-fte/tests/`

| File | Lines | Covers |
|---|---|---|
| `test_repository.py` | 705 | `ProductRepository`, `VariantRepository` |
| `test_service.py` | 765 | Core inventory service |
| `test_router.py` | 428 | Tenant inventory API |
| `test_reservation_engine.py` | 363 | Reservation service |
| `test_allocation.py` | 257 | Allocation service + strategies |
| `test_aggregation_engine.py` | 267 | Aggregation engine + cache |
| `test_order_integration.py` | 859 | Order ↔ Inventory integration (see `../WOOCOMMERCE/`) |
| `test_unified_dashboard.py` | 357 | `GET /dashboard/unified` |
| `test_end_to_end.py` | 527 | Full-stack flows (many cases skip without a live Postgres DB) |

**Test run (this audit, `backend-fte/venv/Scripts/python.exe -m pytest`):**
`test_reservation_engine.py test_allocation.py test_aggregation_engine.py
test_repository.py test_service.py test_router.py test_order_integration.py
test_unified_dashboard.py test_end_to_end.py` → **99 passed, 0 failed, 163
skipped** (skips are DB-integration tests gated behind a live Postgres
instance, not failures).

## Migrations — `backend-fte/alembic/versions/`

| File | Lines | Adds |
|---|---|---|
| `warehouse_initial.py` | 142 | Warehouse tables |
| `warehouse_settings.py` | 45 | `warehouse_settings` table |
| `warehouse_is_default.py` | 43 | `is_default` flag |
| `reservation_engine.py` | 197 | `InventoryReservation` table + reservation constants |
| `allocation_engine.py` | 41 | `allocation_priority` JSONB column on `warehouse_settings`, for `PriorityWarehouseStrategy` |
| `remove_warehouse.py` | 323 | Removes warehouse tables (SaaS pivot — store-centric model instead) |

Note: `remove_warehouse.py` runs after the warehouse-adding migrations
above — the warehouse concept was added then removed in the SaaS pivot.
Current runtime model is store-centric, not warehouse-centric, despite the
migration file names.

## Dependents (why you can't just move this folder)

- `backend-fte/app/woocommerce/order_integration_service.py` imports
  `ReservationService` and `AllocationService` directly to allocate/release
  stock for WooCommerce orders (see `../WOOCOMMERCE/implementation-map.md`).
- `backend-fte/app/ai/capabilities/inventory_capabilities.py` (Phase 4
  surface) calls into inventory repositories/services to expose
  inventory data to AI agents (see `../../phase-4/CAPABILITIES/`).
- `backend-fte/app/dashboard/unified_service.py` imports `ReservationService`,
  `AllocationService`, and `InventoryAggregationEngine` directly.

Moving any `app/inventory/*.py` file would break all three call sites above.
