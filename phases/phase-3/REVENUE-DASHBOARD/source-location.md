# Revenue Dashboard — Canonical Source Location

**Canonical implementation — edit only here:**

```
backend-fte/app/woocommerce/constants.py                (REVENUE_ORDER_STATUSES, line 76)
backend-fte/app/woocommerce/service.py                  (WooCommerceService.get_revenue_analytics, line 1456;
                                                           get_top_products, line 1541; ANALYTICS section starts line 1446)
backend-fte/app/woocommerce/schemas.py                  (RevenueAnalyticsOut, line 685; TopProductsOut, line 709;
                                                           ANALYTICS SCHEMAS section starts line 675)
backend-fte/app/woocommerce/router.py                   (GET /woocommerce/stores/{store_id}/analytics/revenue, line 632;
                                                           GET .../analytics/top-products, line 650;
                                                           ANALYTICS ENDPOINTS section starts line 628)
frontend-fte/app/components/RevenueAnalytics.tsx         (revenue trend chart, summary cards, top-products table)
frontend-fte/app/components/BusinessDashboard.tsx         (renders <RevenueAnalytics> inside the "Reports" tab, line 1544)
frontend-fte/lib/api.ts                                   (analyticsApi.getRevenue / getTopProducts, lines 465-471;
                                                           RevenueAnalytics/TopProduct types, lines 433-458)
```

`get_revenue_analytics` computes a daily revenue trend plus a period-over-
period comparison (current N days vs. the prior N days), scoped to
`REVENUE_ORDER_STATUSES` (processing/on-hold/completed — see
`constants.py`, deliberately excludes pending/cancelled/refunded/failed/
trash/draft). Figures are computed directly from `WooCommerceOrder` rows
already synced for the store; nothing is estimated or hard-coded.

**Do not duplicate.** The separate `sales_capabilities.py`
(`SalesRevenueSummaryCapability`) still exists as an **AI agent capability**
— a different surface, reached through the AI execution path
(`POST /ai/capabilities/{name}/execute`), not this dashboard endpoint. It
was not modified and was not merged into `service.py`; the two coexist
because they serve different callers (AI agent vs. human dashboard user)
with different authorization contexts (`user_id`-scoped vs.
`store_id`+ownership-scoped via `_get_store`). If you need to change revenue
logic, decide first which of the two surfaces you're changing — do not
copy one into the other. See `../../phase-4/CAPABILITIES/source-location.md`
for the AI-capability side.

No snapshot exists; this feature is small enough that the map above is
sufficient.

## Tests

`backend-fte/tests/test_analytics.py` — `TestRevenueAnalytics`,
`TestTopProducts`, `TestOrderStatusBreakdown` (mock-based, no live
PostgreSQL required; see `PAYMENT-INTEGRATION/source-location.md` for how
this project's tests are gated against a real database).
