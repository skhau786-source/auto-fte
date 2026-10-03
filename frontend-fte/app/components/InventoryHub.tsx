"use client";

/**
 * InventoryHub — the real Inventory Management experience for business users.
 *
 * Every number comes from the backend inventory APIs:
 *   /inventory/*            products, stock adjustment, history, low stock
 *   /inventory/aggregate/*  available/reserved stock, value, reports
 *   /reservations/*         reservations engine
 *   /allocation/*           allocation engine
 *   /dashboard/unified      combined dashboard metrics
 *
 * No mock data. If no store is connected the backend returns STORE_NOT_FOUND
 * and we show a friendly "connect your store" state. All errors are shown in
 * plain business language — never raw errors, IDs, URLs or JSON.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Package,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Plus,
  Search,
  TrendingUp,
  DollarSign,
  Boxes,
  CalendarClock,
  Layers,
  ShoppingCart,
  Store,
  X,
} from "lucide-react";
import {
  coreInventoryApi,
  reservationApi,
  allocationApi,
  unifiedApi,
  type InventoryProduct,
  type InventoryVariant,
  type InventoryTransaction,
  type Reservation,
  type UnifiedDashboard,
  type StoreAggregation,
  type LowStockItem,
  type AllocationSettings,
} from "@/lib/api";

// ───────────────────────────────────────────────────────────────────
// Types & helpers
// ───────────────────────────────────────────────────────────────────

type InvTab = "overview" | "products" | "reservations" | "allocations";

function money(value: number | string | null | undefined): string {
  const n = Number(value ?? 0);
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "Never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "Never";
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins} minute${mins === 1 ? "" : "s"} ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} day${days === 1 ? "" : "s"} ago`;
  return new Date(iso).toLocaleDateString();
}

function variantStatus(v: { inventory_quantity: number; low_stock_threshold?: number | null }): {
  icon: React.ReactNode;
  text: string;
  cls: string;
} {
  const qty = v.inventory_quantity;
  const threshold = v.low_stock_threshold ?? 10;
  if (qty <= 0) return { icon: <AlertCircle className="w-3.5 h-3.5 text-rose-500" />, text: "Out of Stock", cls: "bg-rose-50 text-rose-700 border-rose-100" };
  if (qty <= threshold) return { icon: <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />, text: "Low Stock", cls: "bg-amber-50 text-amber-700 border-amber-100" };
  return { icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />, text: "In Stock", cls: "bg-emerald-50 text-emerald-700 border-emerald-100" };
}

function isNoStore(err: unknown): boolean {
  return (err as { errorCode?: string })?.errorCode === "STORE_NOT_FOUND";
}

const friendly = (err: unknown, fallback: string): string => {
  if (err instanceof Error && err.message && err.message !== "An unexpected error occurred") {
    return err.message;
  }
  return fallback;
};

// ───────────────────────────────────────────────────────────────────
// Shared UI bits
// ───────────────────────────────────────────────────────────────────

function LoadingBlock() {
  return (
    <div className="flex items-center justify-center py-20">
      <Loader2 className="w-8 h-8 animate-spin text-violet-600" />
    </div>
  );
}

function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="p-8 rounded-2xl bg-rose-50/70 border border-rose-100 text-center">
      <AlertCircle className="w-8 h-8 mx-auto text-rose-400 mb-2" />
      <p className="text-sm font-semibold text-rose-700">Something went wrong</p>
      <p className="text-xs text-rose-500 mt-1">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 px-4 py-2 bg-white border border-rose-200 rounded-lg text-xs font-bold text-rose-600 hover:bg-rose-50 transition-colors"
        >
          Try again
        </button>
      )}
    </div>
  );
}

function EmptyBlock({ icon, title, subtitle, action }: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="p-10 rounded-2xl bg-white/70 border border-slate-200/70 text-center">
      <div className="w-14 h-14 mx-auto rounded-2xl bg-violet-50 border border-violet-100 flex items-center justify-center text-violet-500 mb-3">
        {icon}
      </div>
      <p className="text-sm font-bold text-slate-800">{title}</p>
      {subtitle && <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">{subtitle}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

function StatCard({ label, value, icon, tone, sub }: {
  label: string;
  value: React.ReactNode;
  icon: React.ReactNode;
  tone: string;
  sub?: string;
}) {
  return (
    <div className="p-5 rounded-2xl bg-white/80 border border-slate-200/60 hover:shadow-xl hover:-translate-y-0.5 transition-all duration-300">
      <div className="flex items-center justify-between">
        <div className={`p-2.5 rounded-xl bg-gradient-to-br ${tone} text-white shadow-lg`}>{icon}</div>
        {sub && <span className="text-[10px] font-semibold text-slate-400">{sub}</span>}
      </div>
      <p className="text-2xl font-black text-slate-900 mt-3">{value}</p>
      <p className="text-xs font-medium text-slate-500 mt-0.5">{label}</p>
    </div>
  );
}

function Modal({ title, subtitle, onClose, children }: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-md bg-white rounded-3xl shadow-2xl p-6 animate-fade-in max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-4">
          <div>
            <h4 className="text-lg font-bold text-slate-900">{title}</h4>
            {subtitle && <p className="text-xs text-slate-500 mt-1">{subtitle}</p>}
          </div>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-slate-600">
            <X className="w-4 h-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// Main hub
// ───────────────────────────────────────────────────────────────────

export default function InventoryHub({ onNavigateToStores }: {
  onNavigateToStores: () => void;
}) {
  const [tab, setTab] = useState<InvTab>("overview");
  const [hasStore, setHasStore] = useState<boolean | null>(null);
  // Product list used to translate variant IDs into readable names.
  const [nameLookup, setNameLookup] = useState<InventoryProduct[]>([]);

  const loadLookup = useCallback(async () => {
    try {
      // Load the full product list (paginated) so reservations and history
      // always show real product/variant names instead of placeholders.
      const all: InventoryProduct[] = [];
      let page = 1;
      let total = Infinity;
      while (all.length < total && page <= 6) {
        const data = await coreInventoryApi.list({ page_size: 100, page });
        all.push(...data.items);
        total = data.total;
        page += 1;
      }
      setNameLookup(all);
    } catch {
      setNameLookup([]);
    }
  }, []);

  const checkStore = useCallback(async () => {
    try {
      await unifiedApi.get();
      setHasStore(true);
      await loadLookup();
    } catch (err) {
      if (isNoStore(err)) {
        setHasStore(false);
      } else {
        // Transient/other errors: show the real UI with per-section error states.
        setHasStore(true);
        await loadLookup();
      }
    }
  }, [loadLookup]);

  useEffect(() => {
    checkStore();
  }, [checkStore]);

  const variantName = useMemo(() => {
    const map = new Map<string, { productTitle: string; variantTitle: string; sku: string | null }>();
    for (const p of nameLookup) {
      for (const v of p.variants) {
        map.set(v.id, { productTitle: p.title, variantTitle: v.title, sku: v.sku });
      }
    }
    return map;
  }, [nameLookup]);

  if (hasStore === null) return <LoadingBlock />;

  if (!hasStore) {
    return (
      <EmptyBlock
        icon={<Store className="w-7 h-7" />}
        title="Connect your store to manage inventory"
        subtitle="Once your store is connected, your products, stock levels, reservations and reports will appear here automatically."
        action={
          <button
            onClick={onNavigateToStores}
            className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg hover:shadow-violet-500/25 hover:scale-[1.02] transition-all"
          >
            Connect Store
          </button>
        }
      />
    );
  }

  const tabs: { id: InvTab; label: string; icon: React.ReactNode }[] = [
    { id: "overview", label: "Overview", icon: <TrendingUp className="w-4 h-4" /> },
    { id: "products", label: "Products", icon: <Package className="w-4 h-4" /> },
    { id: "reservations", label: "Reservations", icon: <CalendarClock className="w-4 h-4" /> },
    { id: "allocations", label: "Allocations", icon: <Layers className="w-4 h-4" /> },
  ];

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-slate-900">Inventory</h3>
        <p className="text-xs text-slate-500">
          Your real-time stock, reservations and allocation activity.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all flex items-center gap-2 ${
              tab === t.id
                ? "bg-violet-600 text-white shadow-md shadow-violet-500/20"
                : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewPage />}
      {tab === "products" && <ProductsPage variantName={variantName} />}
      {tab === "reservations" && <ReservationsPage variantName={variantName} />}
      {tab === "allocations" && <AllocationsPage />}
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// OVERVIEW
// ───────────────────────────────────────────────────────────────────

function OverviewPage() {
  const [unified, setUnified] = useState<UnifiedDashboard | null>(null);
  const [agg, setAgg] = useState<StoreAggregation | null>(null);
  const [lowStock, setLowStock] = useState<LowStockItem[]>([]);
  const [activity, setActivity] = useState<InventoryTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [u, a, low, hist] = await Promise.all([
        unifiedApi.get(),
        coreInventoryApi.aggregate.store(),
        coreInventoryApi.lowStock({ page_size: 10 }),
        coreInventoryApi.history({ page_size: 8 }),
      ]);
      setUnified(u);
      setAgg(a);
      setLowStock(low.items);
      setActivity(hist.items);
    } catch (err) {
      setError(friendly(err, "We couldn't load your inventory overview."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingBlock />;
  if (error) return <ErrorBlock message={error} onRetry={load} />;
  if (!unified || !agg) return <ErrorBlock message="No inventory data available yet." onRetry={load} />;

  const attention: { icon: React.ReactNode; tone: string; text: string }[] = [];
  if (unified.inventory.low_stock_count > 0)
    attention.push({ icon: <AlertTriangle className="w-5 h-5 text-amber-500" />, tone: "bg-amber-50 border-amber-100", text: `${unified.inventory.low_stock_count} product${unified.inventory.low_stock_count === 1 ? "" : "s"} need restocking` });
  if (unified.inventory.out_of_stock_count > 0)
    attention.push({ icon: <AlertCircle className="w-5 h-5 text-rose-500" />, tone: "bg-rose-50 border-rose-100", text: `${unified.inventory.out_of_stock_count} product${unified.inventory.out_of_stock_count === 1 ? "" : "s"} are out of stock` });
  if (unified.reservation.active_reservations > 0)
    attention.push({ icon: <CalendarClock className="w-5 h-5 text-blue-500" />, tone: "bg-blue-50 border-blue-100", text: `${unified.reservation.active_reservations} active reservation${unified.reservation.active_reservations === 1 ? "" : "s"} on your stock` });
  if (attention.length === 0)
    attention.push({ icon: <CheckCircle2 className="w-5 h-5 text-emerald-500" />, tone: "bg-emerald-50 border-emerald-100", text: "Everything looks healthy — no stock alerts right now" });

  return (
    <div className="space-y-6">
      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        <StatCard label="Total Products" value={unified.inventory.total_products} icon={<Package className="w-5 h-5" />} tone="from-violet-500 to-indigo-600" />
        <StatCard label="Stock on Hand" value={unified.aggregation.total_available_inventory.toLocaleString()} icon={<Boxes className="w-5 h-5" />} tone="from-emerald-400 to-green-500" />
        <StatCard label="Reserved Stock" value={unified.aggregation.total_reserved_inventory.toLocaleString()} icon={<CalendarClock className="w-5 h-5" />} tone="from-blue-400 to-cyan-500" />
        <StatCard label="Low Stock" value={unified.inventory.low_stock_count} icon={<AlertTriangle className="w-5 h-5" />} tone="from-amber-400 to-orange-500" />
        <StatCard label="Out of Stock" value={unified.inventory.out_of_stock_count} icon={<AlertCircle className="w-5 h-5" />} tone="from-rose-400 to-red-500" />
        <StatCard label="Inventory Value" value={money(unified.aggregation.inventory_value)} icon={<DollarSign className="w-5 h-5" />} tone="from-emerald-400 to-teal-500" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Needs attention */}
        <div className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
          <h4 className="text-sm font-bold text-slate-900 mb-4">Needs Your Attention</h4>
          <div className="space-y-2.5">
            {attention.map((a, i) => (
              <div key={i} className={`flex items-center gap-2.5 p-3 rounded-xl border ${a.tone}`}>
                <span className="flex shrink-0 items-center justify-center">{a.icon}</span>
                <p className="text-xs font-medium text-slate-700">{a.text}</p>
              </div>
            ))}
          </div>
          {lowStock.length > 0 && (
            <div className="mt-4 pt-4 border-t border-slate-100">
              <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wide mb-2">Low stock items</p>
              <div className="space-y-1.5">
                {lowStock.slice(0, 4).map((item) => (
                  <div key={item.variant_id} className="flex items-center justify-between text-xs">
                    <span className="text-slate-600 truncate">{item.product_title} · {item.variant_title}</span>
                    <span className="font-bold text-amber-700">{item.inventory_quantity} left</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Recent activity */}
        <div className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
          <h4 className="text-sm font-bold text-slate-900 mb-4">Recent Inventory Activity</h4>
          {activity.length === 0 ? (
            <p className="text-xs text-slate-400 py-6 text-center">
              No stock movements yet — adjustments will show up here.
            </p>
          ) : (
            <div className="space-y-2">
              {activity.map((t) => (
                <div key={t.id} className="flex items-center justify-between p-2.5 bg-slate-50/70 rounded-xl border border-slate-100/60">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-800">
                      {t.quantity_change > 0 ? "📦 Stock added" : "📉 Stock removed"}
                    </p>
                    <p className="text-[10px] text-slate-400 truncate">{t.reason || "Manual adjustment"} · {timeAgo(t.created_at)}</p>
                  </div>
                  <span className={`text-sm font-bold shrink-0 ${t.quantity_change > 0 ? "text-emerald-600" : "text-rose-600"}`}>
                    {t.quantity_change > 0 ? "+" : ""}{t.quantity_change} → {t.quantity_after}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// PRODUCTS
// ───────────────────────────────────────────────────────────────────

function ProductsPage({ variantName }: {
  variantName: Map<string, { productTitle: string; variantTitle: string; sku: string | null }>;
}) {
  const [products, setProducts] = useState<InventoryProduct[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string | number | boolean | undefined> = {
        page_size: 100,
        search: search || undefined,
      };
      if (lowOnly) params.low_stock_only = true;
      const data = await coreInventoryApi.list(params);
      setProducts(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(friendly(err, "We couldn't load your products."));
    } finally {
      setLoading(false);
    }
  }, [search, lowOnly]);

  useEffect(() => {
    load();
  }, [load]);

  if (selectedId) {
    return (
      <ProductDetailPage
        productId={selectedId}
        variantName={variantName}
        onBack={() => setSelectedId(null)}
        onChanged={() => {
          load();
        }}
      />
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <p className="text-xs text-slate-500">
            {total} product{total === 1 ? "" : "s"} · showing real-time stock from your store
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search products…"
              className="pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg bg-slate-50 focus:outline-none focus:ring-2 focus:ring-violet-500/30 w-full sm:w-56"
            />
          </div>
          <button
            onClick={() => setLowOnly((v) => !v)}
            className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all ${
              lowOnly
                ? "bg-amber-500 text-white shadow-md shadow-amber-500/20"
                : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}
          >
            Low stock only
          </button>
          <button
            onClick={() => setShowAdd(true)}
            className="px-4 py-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg hover:shadow-violet-500/25 transition-all flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" /> Add Product
          </button>
        </div>
      </div>

      {loading ? (
        <LoadingBlock />
      ) : error ? (
        <ErrorBlock message={error} onRetry={load} />
      ) : products.length === 0 ? (
        <EmptyBlock
          icon={<Package className="w-7 h-7" />}
          title={lowOnly ? "No low-stock products right now" : "No products yet"}
          subtitle={
            lowOnly
              ? "Good news — nothing needs restocking right now."
              : "Add your first product below, or sync your store to pull products in."
          }
          action={!lowOnly ? (
            <button
              onClick={() => setShowAdd(true)}
              className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg transition-all"
            >
              Add Product
            </button>
          ) : undefined}
        />
      ) : (
        <div className="bg-white/80 border border-slate-200/60 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-3 text-left font-bold">Product</th>
                  <th className="px-4 py-3 text-left font-bold">SKU</th>
                  <th className="px-4 py-3 text-left font-bold">Variants</th>
                  <th className="px-4 py-3 text-left font-bold">On Hand</th>
                  <th className="px-4 py-3 text-left font-bold">Status</th>
                  <th className="px-4 py-3 text-left font-bold hidden md:table-cell">Updated</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {products.map((p) => {
                  const totalQty = p.variants.reduce((s, v) => s + v.inventory_quantity, 0);
                  const worst = p.variants.some((v) => v.inventory_quantity <= 0)
                    ? { icon: <AlertCircle className="w-3.5 h-3.5 text-rose-500" />, text: "Out of Stock", cls: "bg-rose-50 text-rose-700 border-rose-100" }
                    : p.variants.some((v) => v.inventory_quantity <= (v.low_stock_threshold ?? 10))
                    ? { icon: <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />, text: "Low Stock", cls: "bg-amber-50 text-amber-700 border-amber-100" }
                    : { icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />, text: "In Stock", cls: "bg-emerald-50 text-emerald-700 border-emerald-100" };
                  return (
                    <tr key={p.id} className="hover:bg-violet-50/30 transition-colors cursor-pointer" onClick={() => setSelectedId(p.id)}>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3 min-w-0">
                          {p.featured_image_url ? (
                            <img src={p.featured_image_url} alt="" className="w-10 h-10 rounded-lg object-cover bg-slate-100 shrink-0" />
                          ) : (
                            <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
                              <Package className="w-4 h-4 text-slate-400" />
                            </div>
                          )}
                          <span className="font-medium text-slate-900 truncate max-w-[200px]">{p.title}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-slate-500">{p.variants[0]?.sku || "—"}</td>
                      <td className="px-4 py-3 text-slate-500">{p.variants.length}</td>
                      <td className="px-4 py-3 font-semibold text-slate-800">{totalQty}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-bold rounded-full border ${worst.cls}`}>{worst.icon} {worst.text}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-400 hidden md:table-cell">{timeAgo(p.updated_at)}</td>
                      <td className="px-4 py-3 text-right">
                        <span className="text-violet-600 text-xs font-bold inline-flex items-center gap-1">
                          Manage <ArrowRight className="w-3 h-3" />
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showAdd && <AddProductModal onClose={() => setShowAdd(false)} onDone={() => { setShowAdd(false); load(); }} />}
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// PRODUCT DETAIL (variants + stock history + adjust stock)
// ───────────────────────────────────────────────────────────────────

function ProductDetailPage({ productId, variantName, onBack, onChanged }: {
  productId: string;
  variantName: Map<string, { productTitle: string; variantTitle: string; sku: string | null }>;
  onBack: () => void;
  onChanged: () => void;
}) {
  const [product, setProduct] = useState<InventoryProduct | null>(null);
  const [history, setHistory] = useState<InventoryTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adjustVariant, setAdjustVariant] = useState<InventoryVariant | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, h] = await Promise.all([
        coreInventoryApi.get(productId),
        coreInventoryApi.history({ page_size: 50 }),
      ]);
      setProduct(p);
      setHistory(h.items.filter((t) => p.variants.some((v) => v.id === t.variant_id)));
    } catch (err) {
      setError(friendly(err, "We couldn't load this product."));
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingBlock />;
  if (error || !product) return <ErrorBlock message={error ?? "Product not found."} onRetry={load} />;

  const totalOnHand = product.variants.reduce((s, v) => s + v.inventory_quantity, 0);

  return (
    <div className="space-y-5">
      <button onClick={onBack} className="inline-flex items-center gap-1.5 text-sm font-bold text-violet-600 hover:underline">
        <ArrowLeft className="w-4 h-4" /> Back to Products
      </button>

      <div className="p-5 rounded-2xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white shadow-lg shadow-violet-500/20">
        <h4 className="text-lg font-extrabold">{product.title}</h4>
        <p className="text-xs text-violet-200 mt-1">
          {product.vendor || "No vendor"} · {product.product_type || "General"} ·{" "}
          {product.variants.length} variant{product.variants.length === 1 ? "" : "s"}
        </p>
        <div className="flex flex-wrap gap-6 mt-4 text-sm">
          <div><span className="text-violet-200 text-xs">On hand</span><p className="font-black text-xl">{totalOnHand}</p></div>
          <div><span className="text-violet-200 text-xs">Price from</span><p className="font-black text-xl">{money(product.variants[0]?.price)}</p></div>
          <div><span className="text-violet-200 text-xs">Last updated</span><p className="font-black text-xl">{timeAgo(product.updated_at)}</p></div>
        </div>
      </div>

      {/* Variants */}
      <div className="bg-white/80 border border-slate-200/60 rounded-2xl overflow-hidden">
        <div className="px-4 py-3 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
          <h4 className="text-sm font-bold text-slate-900">Variants</h4>
          <span className="text-[11px] text-slate-400">Adjust stock to increase or decrease quantity</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-slate-500 text-xs uppercase tracking-wide">
              <tr>
                <th className="px-4 py-3 text-left font-bold">Variant</th>
                <th className="px-4 py-3 text-left font-bold">SKU</th>
                <th className="px-4 py-3 text-left font-bold">On Hand</th>
                <th className="px-4 py-3 text-left font-bold">Status</th>
                <th className="px-4 py-3 text-left font-bold">Price</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {product.variants.map((v) => {
                const st = variantStatus(v);
                return (
                  <tr key={v.id} className="hover:bg-violet-50/30 transition-colors">
                    <td className="px-4 py-3 font-medium text-slate-900">{v.title}</td>
                    <td className="px-4 py-3 text-slate-500">{v.sku || "—"}</td>
                    <td className="px-4 py-3 font-bold text-slate-800">{v.inventory_quantity}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-bold rounded-full border ${st.cls}`}>{st.icon} {st.text}</span>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{money(v.price)}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => setAdjustVariant(v)}
                        className="px-3 py-1.5 rounded-lg bg-violet-50 text-violet-700 border border-violet-200 text-xs font-bold hover:bg-violet-100 transition-colors"
                      >
                        Adjust Stock
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Stock history */}
      <div className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
        <h4 className="text-sm font-bold text-slate-900 mb-4">Stock History</h4>
        {history.length === 0 ? (
          <p className="text-xs text-slate-400 py-4 text-center">No stock movements recorded for this product yet.</p>
        ) : (
          <div className="space-y-2">
            {history.map((t) => {
              const vn = variantName.get(t.variant_id);
              return (
                <div key={t.id} className="flex items-center justify-between p-2.5 bg-slate-50/70 rounded-xl border border-slate-100/60">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-800">
                      {vn ? `${vn.variantTitle}` : "Variant"} ·{" "}
                      {t.quantity_change > 0 ? "Stock added" : "Stock removed"}
                    </p>
                    <p className="text-[10px] text-slate-400 truncate">{t.reason || "Manual adjustment"} · {timeAgo(t.created_at)}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className={`text-sm font-bold ${t.quantity_change > 0 ? "text-emerald-600" : "text-rose-600"}`}>
                      {t.quantity_change > 0 ? "+" : ""}{t.quantity_change}
                    </p>
                    <p className="text-[10px] text-slate-400">now {t.quantity_after}</p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {adjustVariant && (
        <AdjustStockModal
          variant={adjustVariant}
          productTitle={product.title}
          onClose={() => setAdjustVariant(null)}
          onDone={() => {
            setAdjustVariant(null);
            load();
            onChanged();
          }}
        />
      )}
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────
// ADJUST STOCK MODAL
// ───────────────────────────────────────────────────────────────────

function AdjustStockModal({ variant, productTitle, onClose, onDone }: {
  variant: InventoryVariant;
  productTitle: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [direction, setDirection] = useState<"add" | "remove">("add");
  const [quantity, setQuantity] = useState("1");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const qty = Number(quantity);
    if (!Number.isInteger(qty) || qty <= 0) {
      setError("Please enter a whole number greater than zero.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await coreInventoryApi.adjust({
        variant_id: variant.id,
        quantity_change: direction === "add" ? qty : -qty,
        reason: reason.trim() || undefined,
      });
      onDone();
    } catch (err) {
      setError(friendly(err, "We couldn't update the stock. Please try again."));
    } finally {
      setBusy(false);
    }
  };

  const inputCls = "w-full p-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/30";

  return (
    <Modal
      title="Adjust Stock"
      subtitle={`${productTitle} — ${variant.title} · currently ${variant.inventory_quantity} on hand`}
      onClose={onClose}
    >
      <form onSubmit={submit} className="space-y-3">
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setDirection("add")}
            className={`flex-1 py-2.5 rounded-xl text-sm font-bold border transition-all ${
              direction === "add"
                ? "bg-emerald-500 text-white border-emerald-500 shadow-md shadow-emerald-500/20"
                : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}
          >
            + Add Stock
          </button>
          <button
            type="button"
            onClick={() => setDirection("remove")}
            className={`flex-1 py-2.5 rounded-xl text-sm font-bold border transition-all ${
              direction === "remove"
                ? "bg-rose-500 text-white border-rose-500 shadow-md shadow-rose-500/20"
                : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}
          >
            − Remove Stock
          </button>
        </div>
        <div>
          <label className="block text-xs font-bold text-slate-600 mb-1">Quantity</label>
          <input
            type="number"
            min={1}
            step={1}
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            className={inputCls}
            placeholder="e.g. 10"
          />
        </div>
        <div>
          <label className="block text-xs font-bold text-slate-600 mb-1">Reason <span className="text-slate-400 font-medium">(optional)</span></label>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className={inputCls}
            placeholder="e.g. New shipment received"
          />
        </div>
        {error && <p className="text-xs text-rose-600 bg-rose-50 border border-rose-100 rounded-lg p-2">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {busy && <Loader2 className="w-4 h-4 animate-spin" />} Update Stock
        </button>
      </form>
    </Modal>
  );
}

// ───────────────────────────────────────────────────────────────────
// ADD PRODUCT MODAL
// ───────────────────────────────────────────────────────────────────

function AddProductModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [form, setForm] = useState({
    title: "",
    vendor: "",
    product_type: "",
    variant_title: "Default",
    sku: "",
    price: "",
    inventory_quantity: "0",
    low_stock_threshold: "10",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) {
      setError("Please enter a product name.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await coreInventoryApi.create({
        title: form.title.trim(),
        vendor: form.vendor.trim() || undefined,
        product_type: form.product_type.trim() || undefined,
        variants: [
          {
            title: form.variant_title.trim() || "Default",
            sku: form.sku.trim() || undefined,
            price: form.price ? Number(form.price) : 0,
            inventory_quantity: Number(form.inventory_quantity) || 0,
            low_stock_threshold: Number(form.low_stock_threshold) || 0,
          },
        ],
      });
      onDone();
    } catch (err) {
      setError(friendly(err, "We couldn't add the product. Please try again."));
    } finally {
      setBusy(false);
    }
  };

  const inputCls = "w-full p-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/30";
  const labelCls = "block text-xs font-bold text-slate-600 mb-1";

  return (
    <Modal title="Add Product" subtitle="Add a product to your store inventory" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label className={labelCls}>Product name</label>
          <input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Classic Cotton Tee" className={inputCls} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={labelCls}>Vendor (optional)</label>
            <input value={form.vendor} onChange={(e) => setForm({ ...form, vendor: e.target.value })} placeholder="e.g. My Brand" className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>Category (optional)</label>
            <input value={form.product_type} onChange={(e) => setForm({ ...form, product_type: e.target.value })} placeholder="e.g. Apparel" className={inputCls} />
          </div>
        </div>
        <div className="border-t border-slate-100 pt-3">
          <p className="text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">First variant</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Variant name</label>
              <input value={form.variant_title} onChange={(e) => setForm({ ...form, variant_title: e.target.value })} className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>SKU</label>
              <input value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} placeholder="e.g. TEE-BLK-S" className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>Price</label>
              <input type="number" min={0} step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="24.99" className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>Initial quantity</label>
              <input type="number" min={0} step={1} value={form.inventory_quantity} onChange={(e) => setForm({ ...form, inventory_quantity: e.target.value })} className={inputCls} />
            </div>
          </div>
        </div>
        {error && <p className="text-xs text-rose-600 bg-rose-50 border border-rose-100 rounded-lg p-2">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {busy && <Loader2 className="w-4 h-4 animate-spin" />} Add Product
        </button>
      </form>
    </Modal>
  );
}

// ───────────────────────────────────────────────────────────────────
// RESERVATIONS
// ───────────────────────────────────────────────────────────────────

function ReservationsPage({ variantName }: {
  variantName: Map<string, { productTitle: string; variantTitle: string; sku: string | null }>;
}) {
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [activeCount, setActiveCount] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await reservationApi.list({ page_size: 100 });
      setReservations(data.items);
      setTotal(data.total);
      setActiveCount(data.active_count);
    } catch (err) {
      setError(friendly(err, "We couldn't load your reservations."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const action = async (r: Reservation, kind: "commit" | "release" | "cancel") => {
    setBusyId(r.id);
    setError(null);
    try {
      if (kind === "commit") await reservationApi.commit(r.id);
      else if (kind === "release") await reservationApi.release(r.id);
      else await reservationApi.cancel(r.id);
      await load();
    } catch (err) {
      setError(friendly(err, "We couldn't update the reservation. Please try again."));
    } finally {
      setBusyId(null);
    }
  };

  const statusLabel = (s: string) =>
    ({ active: "Active", pending: "Pending", committed: "Committed", released: "Released", expired: "Expired", cancelled: "Cancelled" } as Record<string, string>)[s] ?? s;

  const statusCls = (s: string) =>
    s === "committed"
      ? "bg-emerald-100 text-emerald-800"
      : s === "released" || s === "expired" || s === "cancelled"
      ? "bg-slate-100 text-slate-600"
      : "bg-blue-100 text-blue-800";

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-slate-500">
            {activeCount} active · {total} total reservation{total === 1 ? "" : "s"}
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="px-4 py-2 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg transition-all flex items-center gap-1.5"
        >
          <Plus className="w-4 h-4" /> Reserve Stock
        </button>
      </div>

      {error && <ErrorBlock message={error} onRetry={load} />}

      {loading ? (
        <LoadingBlock />
      ) : reservations.length === 0 ? (
        <EmptyBlock
          icon={<CalendarClock className="w-7 h-7" />}
          title="No reservations yet"
          subtitle="Reserve stock for pending orders or planned shipments — reserved stock is set aside so it can't be sold or allocated elsewhere."
          action={
            <button
              onClick={() => setShowCreate(true)}
              className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg transition-all"
            >
              Reserve Stock
            </button>
          }
        />
      ) : (
        <div className="bg-white/80 border border-slate-200/60 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-3 text-left font-bold">Product</th>
                  <th className="px-4 py-3 text-left font-bold">Variant</th>
                  <th className="px-4 py-3 text-left font-bold">Qty</th>
                  <th className="px-4 py-3 text-left font-bold">Status</th>
                  <th className="px-4 py-3 text-left font-bold">Reserved</th>
                  <th className="px-4 py-3 text-left font-bold">Expires</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {reservations.map((r) => {
                  const vn = variantName.get(r.variant_id);
                  const isOpen = r.status === "active" || r.status === "pending";
                  return (
                    <tr key={r.id} className="hover:bg-violet-50/30 transition-colors">
                      <td className="px-4 py-3 font-medium text-slate-900">{vn?.productTitle || "Product"}</td>
                      <td className="px-4 py-3 text-slate-500">{vn ? `${vn.variantTitle}${vn.sku ? ` · ${vn.sku}` : ""}` : "—"}</td>
                      <td className="px-4 py-3 font-bold text-slate-800">{r.quantity}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2.5 py-1 text-[11px] font-bold rounded-full ${statusCls(r.status)}`}>{statusLabel(r.status)}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-500">{timeAgo(r.created_at)}</td>
                      <td className="px-4 py-3 text-slate-500">{r.expires_at ? timeAgo(r.expires_at) : "Never"}</td>
                      <td className="px-4 py-3">
                        {isOpen && (
                          <div className="flex items-center gap-1.5 justify-end">
                            <button
                              onClick={() => action(r, "commit")}
                              disabled={busyId === r.id}
                              className="px-2.5 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200 text-[11px] font-bold hover:bg-emerald-100 transition-colors disabled:opacity-50"
                            >
                              Commit
                            </button>
                            <button
                              onClick={() => action(r, "release")}
                              disabled={busyId === r.id}
                              className="px-2.5 py-1.5 rounded-lg bg-slate-50 text-slate-600 border border-slate-200 text-[11px] font-bold hover:bg-slate-100 transition-colors disabled:opacity-50"
                            >
                              Release
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showCreate && (
        <CreateReservationModal
          variantName={variantName}
          onClose={() => setShowCreate(false)}
          onDone={() => {
            setShowCreate(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function CreateReservationModal({ variantName, onClose, onDone }: {
  variantName: Map<string, { productTitle: string; variantTitle: string; sku: string | null }>;
  onClose: () => void;
  onDone: () => void;
}) {
  // Build a selectable list from the name lookup (products already loaded).
  const options = useMemo(() => {
    return Array.from(variantName.entries()).map(([variantId, info]) => ({
      variantId,
      label: `${info.productTitle} — ${info.variantTitle}${info.sku ? ` (${info.sku})` : ""}`,
    }));
  }, [variantName]);

  const [variantId, setVariantId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!variantId) {
      setError("Please choose a product variant.");
      return;
    }
    const qty = Number(quantity);
    if (!Number.isInteger(qty) || qty <= 0) {
      setError("Please enter a whole number greater than zero.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await reservationApi.create({ variant_id: variantId, quantity: qty, reason: reason.trim() || undefined });
      onDone();
    } catch (err) {
      setError(friendly(err, "We couldn't reserve that stock. Please try again."));
    } finally {
      setBusy(false);
    }
  };

  const inputCls = "w-full p-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/30";

  return (
    <Modal title="Reserve Stock" subtitle="Set stock aside for an order or planned shipment" onClose={onClose}>
      {options.length === 0 ? (
        <p className="text-sm text-slate-500 py-4 text-center">Add products to your inventory before reserving stock.</p>
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="block text-xs font-bold text-slate-600 mb-1">Product variant</label>
            <select value={variantId} onChange={(e) => setVariantId(e.target.value)} className={inputCls}>
              <option value="">Choose a product…</option>
              {options.map((o) => (
                <option key={o.variantId} value={o.variantId}>{o.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-600 mb-1">Quantity</label>
            <input type="number" min={1} step={1} value={quantity} onChange={(e) => setQuantity(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-600 mb-1">Reason <span className="text-slate-400 font-medium">(optional)</span></label>
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Customer order #1234" className={inputCls} />
          </div>
          {error && <p className="text-xs text-rose-600 bg-rose-50 border border-rose-100 rounded-lg p-2">{error}</p>}
          <button
            type="submit"
            disabled={busy}
            className="w-full py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {busy && <Loader2 className="w-4 h-4 animate-spin" />} Reserve Stock
          </button>
        </form>
      )}
    </Modal>
  );
}

// ───────────────────────────────────────────────────────────────────
// ALLOCATIONS
// ───────────────────────────────────────────────────────────────────

function AllocationsPage() {
  const [settings, setSettings] = useState<AllocationSettings | null>(null);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingStrategy, setSavingStrategy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, d] = await Promise.all([allocationApi.settings(), allocationApi.dashboard()]);
      setSettings(s);
      setStats(d);
    } catch (err) {
      setError(friendly(err, "We couldn't load your allocation settings."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const changeStrategy = async (strategy: string) => {
    setSavingStrategy(true);
    setError(null);
    try {
      const updated = await allocationApi.updateSettings({ allocation_strategy: strategy });
      setSettings(updated);
    } catch (err) {
      setError(friendly(err, "We couldn't change the allocation strategy."));
    } finally {
      setSavingStrategy(false);
    }
  };

  if (loading) return <LoadingBlock />;
  if (error || !settings) return <ErrorBlock message={error ?? "No allocation data available."} onRetry={load} />;

  const num = (key: string): number => {
    const v = stats?.[key];
    return typeof v === "number" ? v : 0;
  };

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs text-slate-500">
          How your stock is handed out when orders come in.
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Allocated Units" value={num("total_allocated_units").toLocaleString()} icon={<Boxes className="w-5 h-5" />} tone="from-violet-500 to-indigo-600" />
        <StatCard label="Orders Allocated" value={num("orders_allocated").toLocaleString()} icon={<ShoppingCart className="w-5 h-5" />} tone="from-blue-400 to-cyan-500" />
        <StatCard label="Active Reservations" value={num("active_reservations").toLocaleString()} icon={<CalendarClock className="w-5 h-5" />} tone="from-amber-400 to-orange-500" />
        <StatCard label="Success Rate" value={`${num("allocation_success_rate").toFixed(1)}%`} icon={<CheckCircle2 className="w-5 h-5" />} tone="from-emerald-400 to-green-500" />
      </div>

      <div className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h4 className="text-sm font-bold text-slate-900">Allocation Strategy</h4>
            <p className="text-xs text-slate-500 mt-1">
              Currently: <span className="font-bold text-slate-700">{settings.active_strategy}</span>
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={settings.allocation_strategy}
              onChange={(e) => changeStrategy(e.target.value)}
              disabled={savingStrategy}
              className="text-sm border border-slate-200 rounded-lg px-3 py-2 bg-slate-50 focus:outline-none focus:ring-2 focus:ring-violet-500/30 disabled:opacity-50"
            >
              {settings.available_strategies.map((s) => (
                <option key={s.name} value={s.name}>{s.name}</option>
              ))}
            </select>
            {savingStrategy && <Loader2 className="w-4 h-4 animate-spin text-violet-600" />}
          </div>
        </div>
        <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
          <div className="flex items-center gap-2 text-slate-600">
            <span className={`w-2 h-2 rounded-full ${settings.auto_allocate_inventory ? "bg-emerald-400" : "bg-slate-300"}`} />
            Auto-allocate stock on new orders
          </div>
          <div className="flex items-center gap-2 text-slate-600">
            <span className={`w-2 h-2 rounded-full ${settings.reserve_stock_on_order ? "bg-emerald-400" : "bg-slate-300"}`} />
            Reserve stock when orders arrive
          </div>
          <div className="flex items-center gap-2 text-slate-600">
            <span className={`w-2 h-2 rounded-full ${settings.auto_release_cancelled_orders ? "bg-emerald-400" : "bg-slate-300"}`} />
            Auto-release cancelled orders
          </div>
        </div>
      </div>
    </div>
  );
}
