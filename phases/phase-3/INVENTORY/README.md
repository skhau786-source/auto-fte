# Inventory — 🟢 COMPLETE

The most mature subsystem in the codebase. It is a full stack: models →
repository → services (core, reservation, allocation, aggregation, audit) →
routers → schemas → migrations → ~5,300 lines of backend tests → a
dedicated frontend hub (`InventoryHub.tsx`, 1,321 lines).

This folder exists so the Inventory implementation is **visible in one
place**, since it was previously scattered across `backend-fte/app/`
sub-packages with no single index. Nothing below was moved — every path is
a pointer into `backend-fte/` or `frontend-fte/`.

## What it does

- Product & variant catalog with per-store inventory tracking.
- Stock **reservation** engine (reserve → commit / release, with expiry).
- Stock **allocation** engine (multiple allocation strategies for fulfilling
  orders against available stock).
- Cross-store/cross-warehouse **aggregation** (with caching).
- Immutable inventory **audit trail** (adjustments, syncs, returns).
- Rate limiting on inventory-mutating endpoints.
- Admin-only inventory endpoints (separate from the tenant-facing router).
- CSV/Excel/JSON **export** of products, transactions, and logs.
- Order ↔ Inventory integration (allocate stock for WooCommerce orders,
  release on cancellation) — see `WOOCOMMERCE/` for the order-side half.

## Status detail

| Layer | Status | Evidence |
|---|---|---|
| Models | 🟢 | `Product`, `ProductVariant`, `InventoryTransaction`, `InventoryLog`, `InventoryReservation` in `backend-fte/app/models.py` |
| Repository | 🟢 | `backend-fte/app/inventory/repository.py` (`ProductRepository`, `VariantRepository`) |
| Core service | 🟢 | `backend-fte/app/inventory/service.py` |
| Reservation service | 🟢 | `backend-fte/app/inventory/reservation_service.py` + `tests/test_reservation_engine.py` (363 lines) |
| Allocation service | 🟢 | `backend-fte/app/inventory/allocation_service.py` + `allocation_strategies.py` + `tests/test_allocation.py` (257 lines) |
| Aggregation engine | 🟢 | `backend-fte/app/inventory/aggregation_engine.py` + `aggregation_cache.py` + `tests/test_aggregation_engine.py` (267 lines) |
| Audit service | 🟢 | `backend-fte/app/inventory/audit_service.py` |
| Routers | 🟢 | `router.py`, `admin_router.py`, `reservation_router.py`, `allocation_router.py`, `aggregation_router.py` |
| Rate limiting | 🟢 | `backend-fte/app/inventory/rate_limiter.py` |
| Frontend | 🟢 | `frontend-fte/app/components/InventoryHub.tsx` (1,321 lines) |
| Export | 🟢 | `backend-fte/app/export/` (products, transactions, logs, dashboard reports; CSV/Excel/JSON) |
| Dashboard | 🟢 | `backend-fte/app/dashboard/dashboard.py` + `dashboard_service.py` — **inventory-only** monitoring dashboard, not revenue (see `../REVENUE-DASHBOARD/`) |
| Migrations | 🟢 | `reservation_engine.py`, `allocation_engine.py`, `warehouse_initial.py`, `warehouse_is_default.py`, `warehouse_settings.py`, `remove_warehouse.py` |
| Tests | 🟢 | 99 passed / 0 failed / 163 skipped (skips are Postgres-integration tests requiring a live DB — see `../../MANIFEST.md` test run log) |

## Full detail

- [`implementation-map.md`](./implementation-map.md) — every file, function, and test involved.
- [`source-location.md`](./source-location.md) — canonical paths, explicitly what NOT to duplicate.

## Note on naming confusion

`backend-fte/README.md` labels the reservation engine "✅ Phase 3" and the
allocation engine "✅ Phase 4" — using the codebase's **internal** build-order
numbering, unrelated to this directory's roadmap Phase 3/4. Both reservation
and allocation are part of *this* roadmap Phase 3 → Inventory feature. See
`../../README.md` for the full disambiguation.
