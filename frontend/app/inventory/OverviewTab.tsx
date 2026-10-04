"use client";

import { useEffect, useState } from "react";
import { PackageCheck } from "lucide-react";
import { Btn, Card, Empty, SectionTitle, Spinner, Stat, fmtMoney } from "../components/workspace/ui";
import { apiFetch, ApiError, InventoryReport, InventorySummary, LowStockAlert, MoverRow } from "../lib/api";

interface Props {
  storeId: number;
  version: number;
  toast: (kind: "ok" | "err", text: string) => void;
  onChange: () => void;
}

export function OverviewTab({ storeId, version, toast, onChange }: Props) {
  const [summary, setSummary] = useState<InventorySummary | null>(null);
  const [report, setReport] = useState<InventoryReport | null>(null);
  const [alerts, setAlerts] = useState<LowStockAlert[]>([]);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      apiFetch<InventorySummary>(`/api/v1/stores/${storeId}/inventory/summary`),
      apiFetch<InventoryReport>(`/api/v1/stores/${storeId}/inventory/report?days=${days}`),
      apiFetch<{ items: LowStockAlert[] }>(`/api/v1/stores/${storeId}/alerts/low-stock`),
    ])
      .then(([s, r, a]) => {
        if (cancelled) return;
        setSummary(s);
        setReport(r);
        setAlerts(a.items);
      })
      .catch((e: ApiError) => !cancelled && toast("err", e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [storeId, days, version, toast]);

  const resolve = async (id: number) => {
    try {
      await apiFetch(`/api/v1/stores/${storeId}/alerts/${id}/resolve`, { method: "POST" });
      setAlerts((cur) => cur.filter((a) => a.id !== id));
      toast("ok", "Alert marked as resolved");
      onChange();
    } catch (e) {
      toast("err", (e as ApiError).message);
    }
  };

  if (loading && !summary) return <Spinner />;
  if (!summary) return null;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Available units" value={summary.total_available_units.toLocaleString()} sub={`${summary.variant_count} variants · ${summary.product_count} products`} />
        <Stat label="Reserved units" value={summary.total_reserved_units.toLocaleString()} sub={`${summary.active_reservations} active reservations`} />
        <Stat label="Inventory value" value={fmtMoney(summary.inventory_value)} tone="good" />
        <Stat
          label="Needs attention"
          value={summary.low_stock_variants + summary.out_of_stock_variants}
          tone={summary.low_stock_variants + summary.out_of_stock_variants ? "warn" : "default"}
          sub={`${summary.low_stock_variants} low · ${summary.out_of_stock_variants} out of stock`}
        />
      </div>

      <Card className="p-4">
        <SectionTitle title="Low stock alerts" hint="Variants at or below their threshold." />
        {alerts.length === 0 ? (
          <Empty icon={<PackageCheck className="h-8 w-8" />} title="No open alerts" text="Everything is above its threshold." />
        ) : (
          <ul className="divide-y divide-white/5">
            {alerts.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {a.product_title} — {a.variant_title}
                  </p>
                  <p className="text-xs text-slate-400">
                    {a.sku && `${a.sku} · `}
                    <span className="text-amber-300">{a.current_stock} left</span> (threshold {a.threshold})
                  </p>
                </div>
                <Btn variant="ghost" onClick={() => resolve(a.id)}>
                  Resolve
                </Btn>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Sales movement</h2>
        <select
          aria-label="Window"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="rounded-lg border border-white/10 bg-black/30 px-2 py-1 text-sm"
        >
          {[7, 30, 90, 365].map((d) => (
            <option key={d} value={d}>
              Last {d} days
            </option>
          ))}
        </select>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <MoverList
          title="Fast movers"
          hint="Most units sold in the window."
          rows={report?.fast_movers ?? []}
          valueLabel={(r) => `${r.units_sold} sold`}
          empty="No sales in this window."
        />
        <MoverList
          title="Dead stock"
          hint={`In stock but nothing sold in ${days} days.${report && report.dead_stock_count > report.dead_stock.length ? ` Showing ${report.dead_stock.length} of ${report.dead_stock_count}.` : ""}`}
          rows={report?.dead_stock ?? []}
          valueLabel={(r) => `${r.available_quantity} in stock`}
          empty="No dead stock — everything is selling."
        />
      </div>
    </div>
  );
}

function MoverList({
  title,
  hint,
  rows,
  valueLabel,
  empty,
}: {
  title: string;
  hint: string;
  rows: MoverRow[];
  valueLabel: (r: MoverRow) => string;
  empty: string;
}) {
  return (
    <Card className="p-4">
      <SectionTitle title={title} hint={hint} />
      {rows.length === 0 ? (
        <Empty title={empty} />
      ) : (
        <ul className="divide-y divide-white/5">
          {rows.map((r) => (
            <li key={r.variant_id} className="flex items-center justify-between gap-3 py-2">
              <span className="min-w-0 truncate text-sm">
                {r.product_title} — {r.variant_title}
              </span>
              <span className="shrink-0 text-xs text-slate-400">{valueLabel(r)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
