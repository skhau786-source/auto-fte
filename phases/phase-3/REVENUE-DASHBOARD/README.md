# Revenue Dashboard — 🟢 COMPLETE

**What exists:** a dedicated, human-facing revenue analytics endpoint and
UI — daily revenue trend, period-over-period comparison (current N days vs.
the prior N days), average order value, and a top-products-by-revenue
table — rendered as a chart-and-table section inside the "Reports" tab,
selectable over 7/30/90-day windows.

This supersedes the earlier state (a single stat card, no trend, no
comparison, no dedicated router) described in prior audit passes. The
richer revenue-trend logic that already existed as an **AI agent
capability** (`sales.revenue_summary`) was left in place, unmodified — it
remains a separate surface for AI agents, not a duplicate of this feature.

## Evidence

| Piece | Status | Location |
|---|---|---|
| Revenue-counted order statuses | 🟢 | `backend-fte/app/woocommerce/constants.py:76` (`REVENUE_ORDER_STATUSES`) |
| Revenue trend + period comparison | 🟢 | `backend-fte/app/woocommerce/service.py:1456` (`get_revenue_analytics`) |
| Top products by realized revenue | 🟢 | `backend-fte/app/woocommerce/service.py:1541` (`get_top_products`) |
| Response schemas | 🟢 | `backend-fte/app/woocommerce/schemas.py:685-717` |
| REST endpoints | 🟢 | `backend-fte/app/woocommerce/router.py:632-687` (`GET .../analytics/revenue`, `GET .../analytics/top-products`) |
| Frontend chart + summary cards + table | 🟢 | `frontend-fte/app/components/RevenueAnalytics.tsx` |
| Wired into the dashboard UI | 🟢 | `frontend-fte/app/components/BusinessDashboard.tsx:1544` (rendered inside the "Reports" tab) |
| Frontend API client | 🟢 | `frontend-fte/lib/api.ts:433-471` (`analyticsApi`) |
| Basic revenue total (unchanged, still present) | 🟢 | `backend-fte/app/woocommerce/service.py:get_dashboard` → `total_revenue` field |
| Tests | 🟢 | `backend-fte/tests/test_analytics.py::TestRevenueAnalytics`, `TestTopProducts` |

## Status

```text
Implementation: COMPLETE
Automated tests: PASS (mock-based; see source-location.md)
Real PostgreSQL verification: NOT VERIFIED — no live PostgreSQL instance
  was available in the environment this was built in. The daily-trend
  SQL (`func.date(...)`, `GROUP BY`) is written for PostgreSQL syntax and
  is exercised by the mock-based tests above (control-flow only), but has
  not been run against a real Postgres database.
```

## Full detail

See `source-location.md` for exact file/line references and the
authorization-model distinction between this REST surface and the
separate AI-capability revenue logic.
