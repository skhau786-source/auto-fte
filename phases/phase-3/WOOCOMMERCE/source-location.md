# WooCommerce Integration — Canonical Source Location

**Canonical implementation — edit only here:**

```
backend-fte/app/woocommerce/
backend-fte/alembic/versions/woocommerce_initial.py
frontend-fte/components/woocommerce/WooCommerceDashboard.tsx
```

**Do not duplicate.** `app/woocommerce/order_integration_service.py` is a
direct consumer of `app/inventory/reservation_service.py` and
`allocation_service.py` (see `../INVENTORY/source-location.md`); a copy of
either side edited independently under `phases/` would desync from what
actually runs. `app/ai/capabilities/sales_capabilities.py` (Phase 4) queries
`WooCommerceOrder` directly for revenue capabilities — see
`../../phase-4/CAPABILITIES/source-location.md`.

No snapshot exists for this feature.
