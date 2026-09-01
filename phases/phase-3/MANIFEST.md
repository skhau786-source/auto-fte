# Phase 3 — Manifest

| Feature | Status | Backend | Frontend | Tests | Migrations | Notes |
|---|---|---|---|---|---|---|
| Inventory | 🟢 COMPLETE | `backend-fte/app/inventory/` (18 files, ~5.9k lines) | `frontend-fte/app/components/InventoryHub.tsx` | `test_repository.py`, `test_service.py`, `test_router.py`, `test_reservation_engine.py`, `test_allocation.py`, `test_aggregation_engine.py` — 99 passed / 0 failed / 163 skipped* | `reservation_engine.py`, `allocation_engine.py`, `warehouse_*`, `remove_warehouse.py` | Reused by WooCommerce order integration and AI capabilities — see dependents in `INVENTORY/implementation-map.md` |
| WooCommerce (incl. Orders, Sales, Taxes) | 🟢 COMPLETE | `backend-fte/app/woocommerce/` (19 files, ~9.6k lines) | `frontend-fte/components/woocommerce/WooCommerceDashboard.tsx` | `test_woocommerce_client.py`, `test_woocommerce_service.py`, `test_webhooks.py`, `test_order_integration.py` — 18 passed / 0 failed / 16 skipped* (+ order-integration tests passing under the Inventory run) | `woocommerce_initial.py` | Taxes = pass-through storage of WooCommerce's own tax fields, no independent calculation engine (see `WOOCOMMERCE/README.md`) |
| Revenue Dashboard | 🟢 COMPLETE | `app/woocommerce/service.py:1456` (`get_revenue_analytics`), `:1541` (`get_top_products`); `app/woocommerce/router.py:632-687`; `app/woocommerce/schemas.py:685-717` | `RevenueAnalytics.tsx`; rendered in `BusinessDashboard.tsx:1544` | `test_analytics.py::TestRevenueAnalytics`, `::TestTopProducts` — 191 passed / 0 failed across the Phase 3 suite (see final report) | — (no schema change; reuses existing `wc_orders`/`wc_order_items` tables) | Real Postgres NOT VERIFIED for the daily-trend SQL (`func.date`/`GROUP BY`); AI-agent revenue capability (`sales_capabilities.py`) left unmodified as a separate surface |
| Advanced Analytics | 🟢 COMPLETE | `app/woocommerce/service.py:1446-1607` (`get_revenue_analytics`, `get_top_products`, `get_order_status_breakdown`); `app/woocommerce/router.py:628-687`; `app/dashboard/dashboard_service.py` (inventory health, unchanged); `app/ai/capabilities/sales_capabilities.py` (3 AI-only capabilities, unchanged) | `RevenueAnalytics.tsx` — trend chart, top-products table, order-status bars | `test_analytics.py` (all 3 classes) | — | First-party human-facing analytics surface now exists; AI-only capabilities left in place, not merged in (different auth model) |
| Payment Integration | 🟢 COMPLETE (implementation) — Live Stripe NOT VERIFIED | `app/subscriptions/{models,service,router,schemas,stripe_client,exceptions}.py` — Stripe SDK isolated in `stripe_client.py`; checkout/portal/cancel + idempotent webhook processing in `service.py:67-283` | none (billing UI not in scope of this pass) | `test_subscriptions.py` — 17 tests, mock-based (StripeClient patched, no live Stripe call) | `subscriptions_initial.py`, `organizations_teams_initial.py`, `merge_phase3_phase4_heads.py` | Secrets via env only (`app/config.py`); live/Stripe-test-mode checkout and webhook delivery not exercised — see `PAYMENT-INTEGRATION/README.md` |
| Multi-language | 🔴 NOT IMPLEMENTED | none | none | none | none | Zero i18n infrastructure found anywhere |

\* Skipped tests require a live Postgres database not available in this
audit environment; they are not failures. Full command and output are
recorded in the final report.

## Dependency notes

- `Inventory` ← consumed by → `WooCommerce` (order allocation) and
  `Phase 4 / CAPABILITIES` (`inventory_capabilities.py`).
- `WooCommerce` ← consumed by → `Phase 4 / CAPABILITIES`
  (`sales_capabilities.py` queries `WooCommerceOrder` directly).
- `Revenue Dashboard` and `Advanced Analytics` both point at the *same*
  `app/woocommerce/service.py` analytics methods — one implementation,
  documented once from both angles (see `REVENUE-DASHBOARD/` and
  `ADVANCED-ANALYTICS/`), never duplicated.
- The pre-existing `sales_capabilities.py` (AI-agent revenue/analytics
  capabilities) was **not** modified or merged into the above — it remains
  a separate surface for the AI-agent execution path, still documented
  once from both `Advanced Analytics` and `Phase 4 / CAPABILITIES`.
