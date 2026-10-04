"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Store as StoreIcon } from "lucide-react";
import { WorkspaceShell } from "../components/workspace/WorkspaceShell";
import { Card, Empty, Spinner, inputCls, useToasts } from "../components/workspace/ui";
import { apiFetch, ApiError, ProductList, ProductRow, Store, VariantLabelMap } from "../lib/api";
import { OverviewTab } from "./OverviewTab";
import { StockTab } from "./StockTab";
import { ReservationsTab } from "./ReservationsTab";
import { HistoryTab } from "./HistoryTab";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "stock", label: "Stock" },
  { id: "reservations", label: "Reservations" },
  { id: "history", label: "History" },
] as const;
type TabId = (typeof TABS)[number]["id"];

export default function InventoryPage() {
  return (
    <WorkspaceShell
      title="Inventory"
      subtitle="Stock levels, reservations and every stock movement for your connected stores."
    >
      <InventoryWorkspace />
    </WorkspaceShell>
  );
}

function InventoryWorkspace() {
  const { toast, toastNode } = useToasts();
  const [stores, setStores] = useState<Store[] | null>(null);
  const [storeId, setStoreId] = useState<number | null>(null);
  const [tab, setTab] = useState<TabId>("overview");
  const [products, setProducts] = useState<ProductRow[]>([]);
  const [version, setVersion] = useState(0); // bump → child tabs refetch
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    apiFetch<Store[]>("/api/v1/stores")
      .then((list) => {
        setStores(list);
        if (list.length) setStoreId(list[0].id);
      })
      .catch((e: ApiError) =>
        setError(e.status === 401 ? "Your session expired. Please log in again." : e.message)
      );
  }, []);

  useEffect(() => {
    if (storeId === null) return;
    apiFetch<ProductList>(`/api/v1/stores/${storeId}/inventory/items?limit=250`)
      .then((d) => setProducts(d.items))
      .catch((e: ApiError) => toast("err", e.message));
  }, [storeId, version, toast]);

  const variantLabels = useMemo<VariantLabelMap>(() => {
    const map: VariantLabelMap = {};
    for (const p of products) {
      for (const v of p.variants) {
        map[v.id] = `${p.title} — ${v.title}${v.sku ? ` (${v.sku})` : ""}`;
      }
    }
    return map;
  }, [products]);

  if (error) {
    return (
      <Card className="p-6">
        <Empty title="Could not load inventory" text={error} />
      </Card>
    );
  }
  if (stores === null) return <Spinner label="Loading your stores…" />;
  if (stores.length === 0) {
    return (
      <Card className="p-6">
        <Empty
          icon={<StoreIcon className="h-8 w-8" />}
          title="No store connected yet"
          text="Connect a Shopify or WooCommerce store from the dashboard setup, then come back to manage its inventory."
        />
      </Card>
    );
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 rounded-xl border border-white/10 bg-white/[0.03] p-1" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                tab === t.id ? "bg-amber-400 text-slate-900" : "text-slate-300 hover:bg-white/5"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        {stores.length > 1 && (
          <select
            aria-label="Store"
            value={storeId ?? ""}
            onChange={(e) => setStoreId(Number(e.target.value))}
            className={`${inputCls} !w-auto`}
          >
            {stores.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name || `Store ${s.id}`} ({s.platform})
              </option>
            ))}
          </select>
        )}
        {stores.length === 1 && (
          <span className="text-sm text-slate-400">
            {stores[0].name || `Store ${stores[0].id}`} · {stores[0].platform}
          </span>
        )}
      </div>

      {storeId !== null && (
        <>
          {tab === "overview" && <OverviewTab storeId={storeId} version={version} toast={toast} onChange={refresh} />}
          {tab === "stock" && (
            <StockTab storeId={storeId} products={products} toast={toast} onChange={refresh} />
          )}
          {tab === "reservations" && (
            <ReservationsTab
              storeId={storeId}
              version={version}
              products={products}
              variantLabels={variantLabels}
              toast={toast}
              onChange={refresh}
            />
          )}
          {tab === "history" && (
            <HistoryTab storeId={storeId} version={version} variantLabels={variantLabels} toast={toast} />
          )}
        </>
      )}
      {toastNode}
    </>
  );
}
