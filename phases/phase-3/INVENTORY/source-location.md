# Inventory — Canonical Source Location

**Canonical implementation — edit only here:**

```
backend-fte/app/inventory/            (service layer, routers, schemas)
backend-fte/app/models.py             (Product, ProductVariant, InventoryTransaction,
                                        InventoryLog, InventoryReservation, StoreSettings)
backend-fte/app/dashboard/            (inventory monitoring dashboard)
backend-fte/app/export/               (inventory data export)
backend-fte/alembic/versions/         (schema migrations, see implementation-map.md)
frontend-fte/app/components/InventoryHub.tsx
```

**Do not duplicate.** `backend-fte/app/inventory/service.py`,
`reservation_service.py`, and `allocation_service.py` are imported by both
`app/woocommerce/order_integration_service.py` and
`app/dashboard/unified_service.py`. A copy placed under `phases/` and
edited independently would silently diverge from what those two call sites
actually run in production — this has already happened once in this repo
(see `PAYMENT-INTEGRATION/README.md` for a real example: a docstring
claiming Stripe integration that the actual code never implements). Always
edit the file under `backend-fte/app/inventory/` directly.

No snapshot exists for this feature (see `../../README.md` → "Snapshots").
The implementation is stable and well-tested enough that a frozen copy adds
duplication risk without documentation value.
