"use client";

/**
 * Revenue Dashboard / Advanced Analytics (Phase 3).
 *
 * Every number here comes from analyticsApi, which is computed backend-side
 * directly from synced WooCommerce orders/order-items — nothing is
 * estimated or hard-coded client-side.
 */

import React, { useCallback, useEffect, useState } from "react";
import { DollarSign, ShoppingBag, TrendingUp, TrendingDown, Loader2, AlertCircle, Package } from "lucide-react";
import {
  analyticsApi,
  type RevenueAnalytics,
  type TopProduct,
  type OrderStatusBreakdown,
} from "@/lib/api";
import { useTranslation } from "@/app/lib/i18n";

const ORDER_STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  processing: "Processing",
  completed: "Completed",
  cancelled: "Cancelled",
  refunded: "Refunded",
  "on-hold": "On Hold",
  failed: "Failed",
  trash: "Cancelled",
  draft: "Draft",
};

const ORDER_STATUS_COLORS: Record<string, string> = {
  pending: "bg-slate-400",
  processing: "bg-blue-500",
  completed: "bg-emerald-500",
  cancelled: "bg-rose-400",
  refunded: "bg-amber-500",
  "on-hold": "bg-violet-400",
  failed: "bg-rose-600",
  trash: "bg-slate-300",
  draft: "bg-slate-300",
};

function money(value: number | null | undefined): string {
  const n = Number(value ?? 0);
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function ChangeBadge({ pct, noDataLabel }: { pct: number | null; noDataLabel: string }) {
  if (pct === null) {
    return <span className="text-[11px] font-semibold text-slate-400">{noDataLabel}</span>;
  }
  const positive = pct >= 0;
  return (
    <span
      className={`inline-flex items-center gap-1 text-[11px] font-bold ${
        positive ? "text-emerald-600" : "text-rose-600"
      }`}
    >
      {positive ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {positive ? "+" : ""}
      {pct}%
    </span>
  );
}

export function RevenueAnalytics({
  storeId,
  storeName,
  hasStores,
  storesLoading,
}: {
  storeId: string;
  storeName: string;
  hasStores: boolean;
  storesLoading: boolean;
}) {
  const { t } = useTranslation();
  const [days, setDays] = useState<7 | 30 | 90>(30);
  const [revenue, setRevenue] = useState<RevenueAnalytics | null>(null);
  const [topProducts, setTopProducts] = useState<TopProduct[]>([]);
  const [statusBreakdown, setStatusBreakdown] = useState<OrderStatusBreakdown | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!storeId) {
      setRevenue(null);
      setTopProducts([]);
      setStatusBreakdown(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [rev, top, status] = await Promise.all([
        analyticsApi.getRevenue(storeId, days),
        analyticsApi.getTopProducts(storeId, days, 8),
        analyticsApi.getOrderStatusBreakdown(storeId, days),
      ]);
      setRevenue(rev);
      setTopProducts(top.products);
      setStatusBreakdown(status);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("analytics.error_loading"));
    } finally {
      setLoading(false);
    }
  }, [storeId, days, t]);

  useEffect(() => {
    load();
  }, [load]);

  if (storesLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-violet-600" />
      </div>
    );
  }
  if (!hasStores) {
    return <p className="text-xs text-slate-400 py-6 text-center">{t("analytics.no_store")}</p>;
  }
  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 animate-spin text-violet-600" />
      </div>
    );
  }
  if (error || !revenue) {
    return (
      <div className="p-6 rounded-2xl bg-rose-50/70 border border-rose-100 text-center">
        <AlertCircle className="w-6 h-6 mx-auto text-rose-400 mb-2" />
        <p className="text-xs text-rose-600">{error ?? t("analytics.error_loading")}</p>
        <button
          onClick={load}
          className="mt-3 px-4 py-2 bg-white border border-rose-200 rounded-lg text-xs font-bold text-rose-600 hover:bg-rose-50 transition-colors"
        >
          {t("common.retry")}
        </button>
      </div>
    );
  }

  const maxTrendRevenue = Math.max(...revenue.trend.map((p) => p.revenue), 1);
  const maxStatusCount = Math.max(...(statusBreakdown?.breakdown.map((b) => b.count) ?? [1]), 1);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h3 className="text-lg font-bold text-slate-900">{t("analytics.title")}</h3>
          <p className="text-xs text-slate-500">{t("analytics.subtitle", { storeName })}</p>
        </div>
        <div className="flex items-center gap-1 p-1 bg-slate-100/80 rounded-xl border border-slate-200/50">
          {([7, 30, 90] as const).map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all ${
                days === d ? "bg-white text-violet-700 shadow-sm" : "text-slate-500 hover:text-slate-800"
              }`}
            >
              {t(`common.days_${d}` as "common.days_7" | "common.days_30" | "common.days_90")}
            </button>
          ))}
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <div className="p-5 rounded-2xl bg-white/80 border border-slate-200/60">
          <div className="flex items-center justify-between">
            <div className="p-2.5 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-500 text-white shadow-lg">
              <DollarSign className="w-5 h-5" />
            </div>
            <ChangeBadge pct={revenue.revenue_change_pct} noDataLabel={t("analytics.no_previous_data")} />
          </div>
          <p className="text-2xl font-black text-slate-900 mt-3">{money(revenue.revenue)}</p>
          <p className="text-xs font-medium text-slate-500 mt-0.5">{t("analytics.revenue")}</p>
        </div>

        <div className="p-5 rounded-2xl bg-white/80 border border-slate-200/60">
          <div className="flex items-center justify-between">
            <div className="p-2.5 rounded-xl bg-gradient-to-br from-violet-500 to-indigo-600 text-white shadow-lg">
              <ShoppingBag className="w-5 h-5" />
            </div>
            <ChangeBadge pct={revenue.order_change_pct} noDataLabel={t("analytics.no_previous_data")} />
          </div>
          <p className="text-2xl font-black text-slate-900 mt-3">{revenue.orders}</p>
          <p className="text-xs font-medium text-slate-500 mt-0.5">{t("analytics.orders")}</p>
        </div>

        <div className="p-5 rounded-2xl bg-white/80 border border-slate-200/60">
          <div className="p-2.5 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 text-white shadow-lg w-fit">
            <TrendingUp className="w-5 h-5" />
          </div>
          <p className="text-2xl font-black text-slate-900 mt-3">{money(revenue.average_order_value)}</p>
          <p className="text-xs font-medium text-slate-500 mt-0.5">{t("analytics.average_order_value")}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Revenue trend */}
        <div className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
          <h4 className="text-sm font-bold text-slate-900 mb-4">{t("analytics.trend_title")}</h4>
          {revenue.trend.length === 0 ? (
            <p className="text-xs text-slate-400 py-8 text-center">{t("analytics.trend_empty")}</p>
          ) : (
            <div className="flex items-end gap-1 h-36">
              {revenue.trend.map((point) => (
                <div key={point.date} className="flex-1 flex flex-col items-center justify-end h-full group relative">
                  <div
                    className="w-full rounded-t bg-gradient-to-t from-violet-500 to-indigo-400 hover:opacity-80 transition-opacity"
                    style={{ height: `${Math.max((point.revenue / maxTrendRevenue) * 100, 2)}%` }}
                    title={`${point.date}: ${money(point.revenue)} (${point.orders})`}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Order status breakdown */}
        <div className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
          <h4 className="text-sm font-bold text-slate-900 mb-4">{t("analytics.order_status_title")}</h4>
          {!statusBreakdown || statusBreakdown.breakdown.length === 0 ? (
            <p className="text-xs text-slate-400 py-8 text-center">{t("analytics.order_status_empty")}</p>
          ) : (
            <div className="space-y-3">
              {statusBreakdown.breakdown.map((s) => (
                <div key={s.status}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="font-semibold text-slate-600">
                      {ORDER_STATUS_LABELS[s.status] ?? s.status}
                    </span>
                    <span className="font-bold text-slate-800">{s.count}</span>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-2 rounded-full ${ORDER_STATUS_COLORS[s.status] ?? "bg-slate-400"}`}
                      style={{ width: `${(s.count / maxStatusCount) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Top products */}
      <div className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
        <h4 className="text-sm font-bold text-slate-900 mb-4">{t("analytics.top_products_title")}</h4>
        {topProducts.length === 0 ? (
          <p className="text-xs text-slate-400 py-8 text-center">{t("analytics.top_products_empty")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] font-bold text-slate-400 uppercase tracking-wide border-b border-slate-100">
                  <th className="py-2 pr-4">{t("analytics.table_product")}</th>
                  <th className="py-2 pr-4 text-right">{t("analytics.table_units_sold")}</th>
                  <th className="py-2 text-right">{t("analytics.table_revenue")}</th>
                </tr>
              </thead>
              <tbody>
                {topProducts.map((p) => (
                  <tr key={p.wc_product_id} className="border-b border-slate-50 last:border-0">
                    <td className="py-2.5 pr-4">
                      <div className="flex items-center gap-2 min-w-0">
                        <Package className="w-3.5 h-3.5 text-slate-300 shrink-0" />
                        <span className="font-medium text-slate-800 truncate">{p.name}</span>
                      </div>
                    </td>
                    <td className="py-2.5 pr-4 text-right text-slate-500">{p.units_sold}</td>
                    <td className="py-2.5 text-right font-bold text-slate-800">{money(p.revenue)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
