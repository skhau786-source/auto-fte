# WooCommerce Integration — 🟢 COMPLETE

The largest backend module in the repo (~9,580 lines across 19 files). This
is also where the roadmap's **Orders**, **Sales**, and **Taxes** items
actually live — they are not separate modules, they are sub-features of the
WooCommerce integration (order sync, order↔inventory allocation, and
tax-field pass-through), documented together here.

## What it does

- Store connection (consumer key/secret, encrypted at rest — `encryption.py`).
- Product, order, customer, category, coupon sync from a live WooCommerce
  store (`client.py`, `sync_engine.py`, `sync_service.py`).
- Bulk product import/update (CSV/JSON, up to 5,000 items/request —
  `bulk_operations.py`).
- Webhook ingestion + registration + retry queue
  (`webhook.py`, `webhook_manager.py`, `webhook_queue.py`, `tasks.py`).
- Store health checks (`health.py`).
- Order ↔ Inventory integration: allocates/releases stock reservations
  against WooCommerce orders (`order_integration_service.py`,
  `order_integration_router.py`) — built directly on top of
  `../INVENTORY/`'s `ReservationService`/`AllocationService`.
- Low-stock/out-of-stock/sync-failure alerts (`WooCommerceAlert` model +
  dashboard surfacing).
- A dashboard aggregation (`service.py:get_dashboard`, line ~1327) that
  includes **basic revenue** (`total_revenue` = `SUM(WooCommerceOrder.total)`)
  — this is the actual source of the "Revenue" number shown in the
  frontend; see `../REVENUE-DASHBOARD/` for why that alone doesn't make a
  full revenue dashboard.
- **Orders**: full order sync + line items + `get_dashboard`'s order counts.
- **Sales**: order/revenue totals inside the same dashboard aggregation; a
  richer sales analysis (top products, revenue trend) exists only as an
  AI-agent capability — see `../../phase-4/CAPABILITIES/`.
- **Taxes**: WooCommerce tax fields (`tax_status`, `tax_class`,
  `subtotal_tax`, `total_tax`, `cart_tax`, `shipping_tax`, `tax_lines`) are
  synced and stored verbatim from WooCommerce (`models.py:216-308`). There
  is **no independent tax calculation or rules engine** — this system is a
  passive mirror of whatever WooCommerce computed. 🟡 PARTIAL if "Taxes"
  was meant as a first-party feature; 🟢 if it was meant as "reflect
  WooCommerce's tax data," which it does correctly.
- Frontend: `components/woocommerce/WooCommerceDashboard.tsx` (980 lines).

## Status detail

| Sub-feature | Status | Evidence |
|---|---|---|
| Store connection & sync | 🟢 | `client.py` (1,097 lines), `sync_engine.py` (888 lines) |
| Bulk import/update | 🟢 | `bulk_operations.py`, `router.py:864-940` |
| Webhooks | 🟢 | `webhook_manager.py` (764 lines), `webhook_queue.py`, `tasks.py` |
| Order↔Inventory allocation | 🟢 | `order_integration_service.py` (397 lines) + `tests/test_order_integration.py` (859 lines) |
| Orders | 🟢 | `models.py` `WooCommerceOrder`/`WooCommerceOrderItem`, `service.py` |
| Sales (basic) | 🟢 | `service.py:1327-1440` dashboard totals |
| Sales (advanced/trend) | 🟡 | only via `../../phase-4/CAPABILITIES/` AI capability, not a human-facing report |
| Taxes | 🟡 | pass-through storage only, no calculation engine |
| Frontend | 🟢 | `WooCommerceDashboard.tsx` (980 lines) |
| Migrations | 🟢 | `alembic/versions/woocommerce_initial.py` (380 lines) |
| Tests | 🟢 | `test_woocommerce_client.py`, `test_woocommerce_service.py`, `test_webhooks.py`, `test_order_integration.py` — 18 passed / 0 failed / 16 skipped (skips need a live DB) |

## Full detail

- [`implementation-map.md`](./implementation-map.md)
- [`source-location.md`](./source-location.md)
