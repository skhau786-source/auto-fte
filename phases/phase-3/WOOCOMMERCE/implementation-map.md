# WooCommerce Integration — Implementation Map

All paths relative to repo root. Nothing here was moved.

## Backend — `backend-fte/app/woocommerce/`

| File | Lines | Purpose |
|---|---|---|
| `client.py` | 1,097 | WooCommerce REST API client, incl. `register_required_webhooks` |
| `service.py` | 1,534 | Core service — stores, products, orders, customers, categories, coupons, alerts, dashboard (`get_dashboard` at ~line 1327, revenue sum at ~line 1360-1364) |
| `router.py` | 952 | Tenant API — store CRUD, product/order/customer/category/coupon CRUD, health, webhook registration, bulk import/update |
| `models.py` | 627 | `WooCommerceStore`, `WooCommerceProduct`, `WooCommerceOrder`, `WooCommerceOrderItem`, `WooCommerceCustomer`, `WooCommerceCategory`, `WooCommerceCoupon`, `WooCommerceAlert`, `WooCommerceSyncLog`. Tax fields: `models.py:216-218` (product `tax_status`/`tax_class`), `models.py:296-308` (order `discount_tax`/`shipping_tax`/`cart_tax`/`total_tax`/`tax_lines`), `models.py:355-357` (item-level tax) |
| `schemas.py` | 671 | Pydantic I/O schemas |
| `sync_engine.py` | 888 | Full/incremental sync orchestration |
| `sync_service.py` | 46 | Thin wrapper/entry point for sync |
| `bulk_operations.py` | 380 | Bulk product import/update, CSV/JSON parsing |
| `order_integration_service.py` | 397 | `allocate_order`, `handle_order_status_change`, `process_synced_order`, `get_fulfillment_summary`, `_commit_order_reservations`, `_release_order_reservations` — imports `ReservationService`/`AllocationService` from `../INVENTORY/` |
| `order_integration_router.py` | 277 | API surface for the above |
| `webhook.py` | 65 | Inbound webhook receiver |
| `webhook_manager.py` | 764 | Webhook lifecycle management |
| `webhook_queue.py` | 262 | Retry queue for failed webhook processing |
| `tasks.py` | 659 | Background task definitions |
| `health.py` | 230 | `get_store_health` — connectivity, sync freshness, webhook status |
| `notifications.py` | 229 | Alert notification dispatch |
| `encryption.py` | 147 | Encrypts `consumer_key`/`consumer_secret` at rest |
| `constants.py` | 138 | Enums (order/product status, etc.) |
| `exceptions.py` | 199 | Domain exceptions (`StoreNotFoundError`, `StoreConnectionError`, `StoreInactiveError`) |

## Frontend

| File | Lines | Purpose |
|---|---|---|
| `frontend-fte/components/woocommerce/WooCommerceDashboard.tsx` | 980 | WooCommerce management UI |
| `frontend-fte/lib/api.ts` | 949 | Includes `payment_method_title` field mapping (line 249) — a WooCommerce order display field, not a payment gateway integration; see `../PAYMENT-INTEGRATION/` |

## Migrations

| File | Lines | Adds |
|---|---|---|
| `backend-fte/alembic/versions/woocommerce_initial.py` | 380 | All WooCommerce tables |

## Tests — `backend-fte/tests/`

| File | Lines | Covers |
|---|---|---|
| `test_woocommerce_client.py` | 198 | `client.py` |
| `test_woocommerce_service.py` | 280 | `service.py` |
| `test_webhooks.py` | 332 | Webhook receive/manage/retry |
| `test_order_integration.py` | 859 | Order↔Inventory allocation |

**Test run (this audit):** `test_woocommerce_client.py test_woocommerce_service.py
test_webhooks.py` → **18 passed, 0 failed, 16 skipped**.
`test_order_integration.py` included in the Inventory suite run → passing
(see `../INVENTORY/implementation-map.md`).

## Endpoint inventory (`router.py`, selected)

| Endpoint area | Router lines |
|---|---|
| Store CRUD | 107-180 |
| Product CRUD | 182-280 |
| Order read + fulfillment | 302-405 |
| Customer CRUD | 431-495 |
| Category CRUD | 492-590 |
| Coupon CRUD | 588-660 |
| Store health | 792-822 |
| Webhook registration | 828-860 |
| Bulk import/update | 868-952 |

## Dependents (why this can't be freely moved)

- `../INVENTORY/`'s `ReservationService`/`AllocationService` are imported
  directly by `order_integration_service.py`.
- `app/dashboard/unified_service.py` imports `OrderIntegrationService` for
  the unified dashboard's order-integration widget.
- `app/ai/capabilities/sales_capabilities.py` (Phase 4) queries
  `WooCommerceOrder` directly for revenue/analytics capabilities.
