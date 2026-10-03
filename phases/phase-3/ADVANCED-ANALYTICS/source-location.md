# Advanced Analytics — Canonical Source Location

**Canonical implementation — edit only here:**

```
backend-fte/app/woocommerce/constants.py                (REVENUE_ORDER_STATUSES, line 76)
backend-fte/app/woocommerce/service.py                  (WooCommerceService.get_revenue_analytics, line 1456;
                                                           get_top_products, line 1541;
                                                           get_order_status_breakdown, line 1589)
backend-fte/app/woocommerce/schemas.py                  (RevenueAnalyticsOut, TopProductsOut,
                                                           OrderStatusBreakdownOut — lines 685/709/718)
backend-fte/app/woocommerce/router.py                   (GET .../analytics/revenue, .../analytics/top-products,
                                                           .../analytics/order-status — lines 632/650/669)
frontend-fte/app/components/RevenueAnalytics.tsx         (renders trend chart, top-products table, order-status
                                                           breakdown bars — the human-facing analytics surface)
frontend-fte/lib/api.ts                                   (analyticsApi — getRevenue/getTopProducts/getOrderStatusBreakdown)
```

Also still present, unchanged, and complementary (not duplicative — see
below):

```
backend-fte/app/dashboard/dashboard_service.py           (inventory health metrics — operational, not sales analytics)
backend-fte/app/ai/capabilities/sales_capabilities.py    (order/revenue/top-product analysis, AI-agent-only surface)
backend-fte/app/export/                                   (raw data export)
```

`get_order_status_breakdown` counts orders by status over a period
(deliberately unfiltered by `REVENUE_ORDER_STATUSES` — this is an
operational health view, so pending/cancelled orders are included on
purpose). `get_top_products` ranks products by realized order-item revenue
(`WooCommerceOrderItem.total`) within a period — not
`WooCommerceProduct.total_sales`, which is a lifetime WooCommerce counter
unrelated to any selected date range.

**Do not duplicate.** `sales_capabilities.py`'s three capabilities
(`SalesAnalyzeOrdersCapability`, `SalesTopProductsCapability`,
`SalesRevenueSummaryCapability`) were **not modified** and remain the
AI-agent-execution-path surface, documented from the Phase 4 side at
`../../phase-4/CAPABILITIES/source-location.md` (same file, same
registered capabilities, referenced from both angles rather than
duplicated — this cross-reference is still accurate). The new
`WooCommerceService` methods above are the separate, human-facing REST
surface — they compute similar figures independently rather than calling
into the AI capabilities, because the two paths have different
authorization models (`user_id`-scoped AI capability vs.
`store_id`+ownership-scoped REST endpoint via `_get_store`). If extending
either surface, keep that authorization difference in mind before merging
the two.

No snapshot exists.

## Tests

`backend-fte/tests/test_analytics.py` (mock-based; no live PostgreSQL in
this environment — see `PAYMENT-INTEGRATION/source-location.md`).
