/**
 * English (fallback) translation dictionary.
 *
 * Scope: language-switcher chrome + the Revenue Dashboard / Advanced
 * Analytics UI (the Phase 3 feature this i18n infrastructure was built
 * for) — not a translation of the entire application. See
 * app/lib/i18n/index.tsx for how missing keys fall back to this file.
 */
const en = {
  "common.language": "Language",
  "common.retry": "Try again",
  "common.loading": "Loading…",
  "common.days_7": "7 days",
  "common.days_30": "30 days",
  "common.days_90": "90 days",

  "analytics.title": "Revenue & Analytics",
  "analytics.subtitle": "Real numbers from {{storeName}}'s synced orders — nothing estimated.",
  "analytics.period_label": "Period",
  "analytics.revenue": "Revenue",
  "analytics.orders": "Orders",
  "analytics.average_order_value": "Average order value",
  "analytics.vs_previous_period": "vs. previous period",
  "analytics.no_previous_data": "No prior-period data yet",
  "analytics.trend_title": "Revenue trend",
  "analytics.trend_empty": "No revenue recorded in this period yet.",
  "analytics.top_products_title": "Top products by revenue",
  "analytics.top_products_empty": "No product sales in this period yet.",
  "analytics.table_product": "Product",
  "analytics.table_units_sold": "Units sold",
  "analytics.table_revenue": "Revenue",
  "analytics.order_status_title": "Orders by status",
  "analytics.order_status_empty": "No orders in this period yet.",
  "analytics.error_loading": "Couldn't load analytics data.",
  "analytics.no_store": "Connect a store to see revenue analytics.",
} as const;

export default en;
export type TranslationKey = keyof typeof en;
