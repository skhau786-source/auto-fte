"use client";

/**
 * BusinessDashboard — a simple, non-technical dashboard for store owners.
 *
 * Replaces the developer/admin style dashboard with plain-language business
 * views. Reuses the existing backend APIs in lib/api.ts. No new backend
 * endpoints are invented: when data isn't available (no store connected,
 * backend unreachable), friendly empty states are shown instead.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  LayoutDashboard,
  Package,
  ShoppingCart,
  Store,
  BarChart3,
  AlertTriangle,
  Settings,
  LogOut,
  RefreshCw,
  Loader2,
  CheckCircle2,
  AlertCircle,
  TrendingUp,
  DollarSign,
  Bell,
  Menu,
  X,
  Search,
  ShoppingBag,
  Globe,
  User,
  Mail,
  ExternalLink,
  Sparkles,
  Boxes,
} from "lucide-react";
import {
  storeApi,
  productApi,
  orderApi,
  dashboardApi,
  settingsApi,
  alertApi,
  shopifyApi,
  type WooCommerceStore,
  type WooCommerceProduct,
  type WooCommerceOrder,
  type DashboardData,
  type StoreSettings,
  type ShopifyStatus,
  type ShopifyInventorySnapshot,
} from "@/lib/api";
import InventoryHub from "./InventoryHub";
import AIAgentsHub from "./AIAgentsHub";
import { RevenueAnalytics } from "./RevenueAnalytics";
import { LanguageSwitcher } from "./LanguageSwitcher";

// ═══════════════════════════════════════════════════════════════════
// Helpers (plain language)
// ═══════════════════════════════════════════════════════════════════

type TabId =
  | "dashboard"
  | "inventory"
  | "ai-agents"
  | "products"
  | "orders"
  | "stores"
  | "reports"
  | "alerts"
  | "settings";

type ProductFilter = "all" | "in" | "low" | "out";

const ORDER_STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  processing: "Processing",
  completed: "Completed",
  cancelled: "Cancelled",
  refunded: "Refunded",
  "on-hold": "On Hold",
  failed: "Failed",
  trash: "Cancelled",
  "checkout-draft": "Draft",
};

function humanOrderStatus(status: string): string {
  return ORDER_STATUS_LABELS[status?.toLowerCase()] ?? (status || "Unknown");
}

function money(value: number | string | null | undefined): string {
  const n = Number(value ?? 0);
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "Never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "Never";
  const diffMs = Date.now() - then;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins} minute${mins === 1 ? "" : "s"} ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} day${days === 1 ? "" : "s"} ago`;
  return new Date(iso).toLocaleDateString();
}

function customerName(order: WooCommerceOrder): string {
  const b = order.billing as Record<string, unknown> | null | undefined;
  const first = typeof b?.first_name === "string" ? b.first_name : "";
  const last = typeof b?.last_name === "string" ? b.last_name : "";
  return `${first} ${last}`.trim() || "Guest";
}

type StockTone = "in" | "low" | "out";

function stockTone(p: WooCommerceProduct): StockTone {
  const qty = p.stock_quantity ?? 0;
  if (p.stock_status === "outofstock" || qty <= 0) return "out";
  if (p.stock_status === "onbackorder" || qty <= 10) return "low";
  return "in";
}

function stockLabel(p: WooCommerceProduct): { icon: React.ReactNode; text: string; cls: string } {
  const tone = stockTone(p);
  if (tone === "out")
    return { icon: <AlertCircle className="w-3.5 h-3.5 text-rose-500" />, text: "Out of Stock", cls: "bg-rose-50 text-rose-700 border-rose-100" };
  if (tone === "low")
    return { icon: <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />, text: "Low Stock", cls: "bg-amber-50 text-amber-700 border-amber-100" };
  return { icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />, text: "In Stock", cls: "bg-emerald-50 text-emerald-700 border-emerald-100" };
}

function storeName(stores: WooCommerceStore[], storeId: string): string {
  return stores.find((s) => s.id === storeId)?.store_name ?? "My Store";
}

// ═══════════════════════════════════════════════════════════════════
// Main shell
// ═══════════════════════════════════════════════════════════════════

interface BusinessDashboardProps {
  userEmail?: string | null;
  onLogout?: () => void;
}

export default function BusinessDashboard({ userEmail, onLogout }: BusinessDashboardProps) {
  const [activeTab, setActiveTab] = useState<TabId>("dashboard");
  const [productFilter, setProductFilter] = useState<ProductFilter>("all");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const [stores, setStores] = useState<WooCommerceStore[]>([]);
  const [storesLoading, setStoresLoading] = useState(true);
  const [storesError, setStoresError] = useState<string | null>(null);
  const [selectedStoreId, setSelectedStoreId] = useState<string>("");

  const [shopify, setShopify] = useState<ShopifyStatus & { inventory?: ShopifyInventorySnapshot } | null>(null);
  const [shopifyLoading, setShopifyLoading] = useState(true);

  const loadStores = useCallback(async () => {
    setStoresLoading(true);
    setStoresError(null);
    try {
      const data = await storeApi.list();
      setStores(data.items);
      if (data.items.length > 0) {
        setSelectedStoreId((prev) => (data.items.some((s) => s.id === prev) ? prev : data.items[0].id));
      } else {
        setSelectedStoreId("");
      }
    } catch (err) {
      setStoresError(err instanceof Error ? err.message : "Couldn't load your stores.");
    } finally {
      setStoresLoading(false);
    }
  }, []);

  const loadShopify = useCallback(async () => {
    setShopifyLoading(true);
    try {
      const status = await shopifyApi.status();
      let inventory: ShopifyInventorySnapshot | undefined;
      if (status.connected) {
        try {
          inventory = await shopifyApi.inventory();
        } catch {
          inventory = undefined;
        }
      }
      setShopify({ ...status, inventory });
    } catch {
      // Not connected / backend unreachable — show "Not connected" state.
      setShopify({ connected: false, shopify_domain: null, shopify_store_id: null, shopify_location_id: null, created_at: null, updated_at: null });
    } finally {
      setShopifyLoading(false);
    }
  }, []);

  // If the session expires (401 anywhere), send the user back to login.
  useEffect(() => {
    const onUnauthorized = () => onLogout?.();
    window.addEventListener("auth:unauthorized", onUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", onUnauthorized);
  }, [onLogout]);

  useEffect(() => {
    loadStores();
    loadShopify();
  }, [loadStores, loadShopify]);

  const refreshAll = useCallback(() => {
    loadStores();
    loadShopify();
  }, [loadStores, loadShopify]);

  const navItems: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: "dashboard", label: "Dashboard", icon: <LayoutDashboard className="w-5 h-5" /> },
    { id: "inventory", label: "Inventory", icon: <Boxes className="w-5 h-5" /> },
    { id: "ai-agents", label: "AI Agents", icon: <Sparkles className="w-5 h-5" /> },
    { id: "products", label: "Products & Inventory", icon: <Package className="w-5 h-5" /> },
    { id: "orders", label: "Orders", icon: <ShoppingCart className="w-5 h-5" /> },
    { id: "stores", label: "Store Connections", icon: <Store className="w-5 h-5" /> },
    { id: "reports", label: "Reports", icon: <BarChart3 className="w-5 h-5" /> },
    { id: "alerts", label: "Alerts", icon: <AlertTriangle className="w-5 h-5" /> },
    { id: "settings", label: "Settings", icon: <Settings className="w-5 h-5" /> },
  ];

  const goTo = useCallback((tab: TabId, filter?: ProductFilter) => {
    setActiveTab(tab);
    if (filter) setProductFilter(filter);
  }, []);

  const hasStores = stores.length > 0;
  const displayName = useMemo(() => {
    if (!userEmail) return "";
    const part = userEmail.split("@")[0];
    return part.charAt(0).toUpperCase() + part.slice(1);
  }, [userEmail]);

  return (
    <div className="flex h-[calc(100vh-80px)] w-full max-w-7xl mx-auto gap-4">
      {/* ─── Mobile overlay ─── */}
      {sidebarOpen && (
        <button
          aria-label="Close menu"
          className="fixed inset-0 z-30 bg-slate-900/40 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ─── Sidebar ─── */}
      <aside
        className={`${
          sidebarOpen ? "flex" : "hidden"
        } lg:flex fixed lg:static inset-y-0 left-0 z-40 w-72 lg:w-64 bg-white/95 lg:bg-white/80 backdrop-blur-xl border border-white/20 rounded-3xl shadow-2xl p-4 flex-col shrink-0 overflow-y-auto`}
      >
        <div className="flex items-center gap-3 px-3 py-4 border-b border-slate-100/50">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center text-white font-bold shadow-lg shadow-violet-500/30">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div className="flex-1">
            <h1 className="text-lg font-extrabold text-slate-900">Digital FTE</h1>
            <p className="text-[8px] font-bold text-slate-400 tracking-widest uppercase">My Business</p>
          </div>
          <button className="lg:hidden p-1 text-slate-400 hover:text-slate-600" onClick={() => setSidebarOpen(false)}>
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Connection summary */}
        <div className="px-3 py-4 border-b border-slate-100/50 space-y-1.5">
          <div className="flex items-center gap-2 text-xs">
            <span className={`w-2 h-2 rounded-full ${shopify?.connected ? "bg-emerald-400" : "bg-slate-300"}`} />
            <span className="font-semibold text-slate-600">Shopify</span>
            <span className="text-slate-400">{shopify?.connected ? "Connected" : "Not connected"}</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className={`w-2 h-2 rounded-full ${stores.some((s) => s.status === "connected") ? "bg-emerald-400" : "bg-slate-300"}`} />
            <span className="font-semibold text-slate-600">WooCommerce</span>
            <span className="text-slate-400">
              {stores.some((s) => s.status === "connected")
                ? `${stores.filter((s) => s.status === "connected").length} connected`
                : "Not connected"}
            </span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-4 space-y-1">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => {
                setActiveTab(item.id);
                setSidebarOpen(false);
              }}
              className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all duration-300 ${
                activeTab === item.id
                  ? "bg-gradient-to-r from-violet-600/10 to-indigo-600/10 text-violet-700 border border-violet-200/50 shadow-sm"
                  : "text-slate-500 hover:bg-slate-100/50 hover:text-slate-700"
              }`}
            >
              <span className={activeTab === item.id ? "text-violet-600" : "text-slate-400"}>{item.icon}</span>
              <span className="text-sm font-medium">{item.label}</span>
              {activeTab === item.id && (
                <span className="ml-auto w-1.5 h-6 rounded-full bg-gradient-to-b from-violet-500 to-indigo-600" />
              )}
            </button>
          ))}
        </nav>

        <button
          onClick={onLogout}
          className="flex items-center gap-3 px-4 py-2.5 rounded-xl text-slate-500 hover:bg-red-50 hover:text-red-600 transition-all duration-300 border-t border-slate-100/50 pt-4"
        >
          <LogOut className="w-4 h-4" />
          <span className="text-sm font-medium">Log Out</span>
        </button>
      </aside>

      {/* ─── Main content ─── */}
      <div className="flex-1 flex flex-col bg-white/60 backdrop-blur-sm border border-white/20 rounded-3xl shadow-2xl min-w-0">
        {/* Header */}
        <header className="flex items-center justify-between gap-3 px-5 sm:px-6 py-4 border-b border-slate-100/60">
          <div className="flex items-center gap-3 min-w-0">
            <button
              className="lg:hidden p-2 rounded-lg text-slate-500 hover:bg-slate-100"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open menu"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="min-w-0">
              <h2 className="text-lg sm:text-xl font-extrabold text-slate-900 truncate">
                {activeTab === "dashboard" && "📊 Dashboard"}
                {activeTab === "inventory" && "📦 Inventory"}
                {activeTab === "products" && "📦 Products & Inventory"}
                {activeTab === "orders" && "🛒 Orders"}
                {activeTab === "stores" && "🔗 Store Connections"}
                {activeTab === "reports" && "📊 Reports"}
                {activeTab === "alerts" && "⚠️ Alerts"}
                {activeTab === "ai-agents" && "🤖 AI Agents"}
                {activeTab === "settings" && "⚙️ Settings"}
              </h2>
              <p className="text-xs sm:text-sm text-slate-500 truncate">
                {displayName ? `Welcome back, ${displayName}` : "Welcome back"} — here's how your business is doing
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5 shrink-0">
            {stores.length > 1 && (
              <select
                value={selectedStoreId}
                onChange={(e) => setSelectedStoreId(e.target.value)}
                className="hidden sm:block text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-slate-50 focus:outline-none focus:ring-2 focus:ring-violet-500/30 max-w-[180px]"
                aria-label="Choose store"
              >
                {stores.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.store_name}
                  </option>
                ))}
              </select>
            )}
            <LanguageSwitcher className="hidden sm:flex" />
            <button
              onClick={refreshAll}
              title="Refresh data"
              className="p-2 rounded-lg text-slate-500 hover:bg-slate-100 hover:text-violet-600 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              onClick={() => goTo("alerts")}
              className="relative p-2 rounded-lg text-slate-500 hover:bg-slate-100 hover:text-violet-600 transition-colors"
              title="Alerts"
            >
              <Bell className="w-4 h-4" />
              <span className="absolute top-1 right-1 w-2 h-2 bg-rose-500 rounded-full" />
            </button>
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white font-bold shadow-lg shadow-violet-500/20">
              {userEmail?.charAt(0).toUpperCase() || "U"}
            </div>
          </div>
        </header>

        {/* Pages */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          {activeTab === "inventory" && (
            <InventoryHub onNavigateToStores={() => goTo("stores")} />
          )}
          {activeTab === "ai-agents" && (
            <AIAgentsHub />
          )}
          {activeTab === "dashboard" && (
            <DashboardPage
              storeId={selectedStoreId}
              hasStores={hasStores}
              storesLoading={storesLoading}
              storeName={storeName(stores, selectedStoreId)}
              onNavigate={goTo}
            />
          )}
          {activeTab === "products" && (
            <ProductsPage
              storeId={selectedStoreId}
              hasStores={hasStores}
              storesLoading={storesLoading}
              storeName={storeName(stores, selectedStoreId)}
              filter={productFilter}
              onFilterChange={setProductFilter}
            />
          )}
          {activeTab === "orders" && (
            <OrdersPage
              storeId={selectedStoreId}
              hasStores={hasStores}
              storesLoading={storesLoading}
              storeName={storeName(stores, selectedStoreId)}
            />
          )}
          {activeTab === "stores" && (
            <StoresPage
              stores={stores}
              storesLoading={storesLoading}
              storesError={storesError}
              shopify={shopify}
              shopifyLoading={shopifyLoading}
              onRefresh={refreshAll}
            />
          )}
          {activeTab === "reports" && (
            <ReportsPage
              storeId={selectedStoreId}
              hasStores={hasStores}
              storesLoading={storesLoading}
              storeName={storeName(stores, selectedStoreId)}
              onNavigate={goTo}
            />
          )}
          {activeTab === "alerts" && (
            <AlertsPage
              storeId={selectedStoreId}
              hasStores={hasStores}
              storesLoading={storesLoading}
              storeName={storeName(stores, selectedStoreId)}
              onNavigate={goTo}
            />
          )}
          {activeTab === "settings" && (
            <SettingsPage
              storeId={selectedStoreId}
              hasStores={hasStores}
              storesLoading={storesLoading}
              stores={stores}
              shopify={shopify}
              userEmail={userEmail}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Shared UI bits
// ═══════════════════════════════════════════════════════════════════

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

function NoStoreCard({ onNavigate }: { onNavigate?: (tab: TabId) => void }) {
  return (
    <EmptyBlock
      icon={<Store className="w-7 h-7" />}
      title="Connect your store to get started"
      subtitle="Once you connect Shopify or WooCommerce, your products, orders and stock levels will appear here automatically."
      action={
        <button
          onClick={() => onNavigate?.("stores")}
          className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg hover:shadow-violet-500/25 hover:scale-[1.02] transition-all"
        >
          Connect Store
        </button>
      }
    />
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

// ═══════════════════════════════════════════════════════════════════
// DASHBOARD PAGE
// ═══════════════════════════════════════════════════════════════════

function DashboardPage({ storeId, hasStores, storesLoading, storeName, onNavigate }: {
  storeId: string;
  hasStores: boolean;
  storesLoading: boolean;
  storeName: string;
  onNavigate: (tab: TabId, filter?: ProductFilter) => void;
}) {
  const [dash, setDash] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!storeId) {
      setDash(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await dashboardApi.get(storeId);
      setDash(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load your dashboard.");
      setDash(null);
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    load();
  }, [load]);

  if (storesLoading) return <LoadingBlock />;
  if (!hasStores) return <NoStoreCard onNavigate={(t) => onNavigate(t)} />;
  if (loading) return <LoadingBlock />;
  if (error || !dash) return <ErrorBlock message={error ?? "No data yet."} onRetry={load} />;

  const { stats } = dash;
  const inStock = Math.max(stats.total_products - stats.low_stock_count - stats.out_of_stock_count, 0);

  const attention: { icon: React.ReactNode; tone: string; text: string; action: string; tab: TabId; filter?: ProductFilter }[] = [];
  if (stats.low_stock_count > 0)
    attention.push({
      icon: <AlertTriangle className="w-5 h-5 text-amber-500" />, tone: "bg-amber-50 border-amber-100", text: `${stats.low_stock_count} product${stats.low_stock_count === 1 ? " is" : "s are"} low in stock`,
      action: "View Products", tab: "products", filter: "low",
    });
  if (stats.out_of_stock_count > 0)
    attention.push({
      icon: <AlertCircle className="w-5 h-5 text-rose-500" />, tone: "bg-rose-50 border-rose-100", text: `${stats.out_of_stock_count} product${stats.out_of_stock_count === 1 ? " is" : "s are"} out of stock`,
      action: "View Products", tab: "products", filter: "out",
    });
  if (stats.active_alerts > 0)
    attention.push({
      icon: <Bell className="w-5 h-5 text-violet-500" />, tone: "bg-violet-50 border-violet-100", text: `You have ${stats.active_alerts} open alert${stats.active_alerts === 1 ? "" : "s"}`,
      action: "View Alerts", tab: "alerts",
    });
  if (stats.last_sync_at) {
    const hours = (Date.now() - new Date(stats.last_sync_at).getTime()) / 3600000;
    if (hours > 3)
      attention.push({
        icon: <RefreshCw className="w-5 h-5 text-slate-400" />, tone: "bg-slate-50 border-slate-200", text: "Your store information hasn't updated recently",
        action: "Check Store", tab: "stores",
      });
  }
  if (attention.length === 0)
    attention.push({
      icon: <CheckCircle2 className="w-5 h-5 text-emerald-500" />, tone: "bg-emerald-50 border-emerald-100", text: "Everything looks good — nothing needs your attention right now",
      action: "View Products", tab: "products",
    });

  return (
    <div className="space-y-6">
      {/* Greeting */}
      <div className="p-5 rounded-2xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white shadow-lg shadow-violet-500/20">
        <p className="text-sm font-semibold text-violet-100">{storeName}</p>
        <h3 className="text-xl font-extrabold mt-1">Here's how your business is doing</h3>
        <p className="text-xs text-violet-200 mt-1">
          Last updated {timeAgo(stats.last_sync_at)}
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        <StatCard label="Total Products" value={stats.total_products} icon={<Package className="w-5 h-5" />} tone="from-violet-500 to-indigo-600" />
        <StatCard label="In Stock" value={inStock} icon={<CheckCircle2 className="w-5 h-5" />} tone="from-emerald-400 to-green-500" />
        <StatCard label="Low Stock" value={stats.low_stock_count} icon={<AlertTriangle className="w-5 h-5" />} tone="from-amber-400 to-orange-500" />
        <StatCard label="Out of Stock" value={stats.out_of_stock_count} icon={<AlertCircle className="w-5 h-5" />} tone="from-rose-400 to-red-500" />
        <StatCard label="Revenue" value={money(stats.total_revenue)} icon={<DollarSign className="w-5 h-5" />} tone="from-emerald-400 to-teal-500" />
        <StatCard label="Orders" value={stats.total_orders} icon={<ShoppingBag className="w-5 h-5" />} tone="from-blue-400 to-cyan-500" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Needs your attention */}
        <div className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-sm font-bold text-slate-900">Needs Your Attention</h4>
            <span className="text-[10px] text-slate-400">What to do next</span>
          </div>
          <div className="space-y-2.5">
            {attention.map((a, i) => (
              <div key={i} className={`flex items-center justify-between gap-3 p-3 rounded-xl border ${a.tone} hover:shadow-sm transition-shadow`}>
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className="flex shrink-0 items-center justify-center">{a.icon}</span>
                  <p className="text-xs font-medium text-slate-700">{a.text}</p>
                </div>
                <button
                  onClick={() => onNavigate(a.tab, a.filter)}
                  className="shrink-0 px-3 py-1.5 bg-white border border-slate-200 rounded-lg text-[11px] font-bold text-violet-700 hover:bg-violet-50 transition-colors"
                >
                  {a.action}
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Recent orders */}
        <div className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-sm font-bold text-slate-900">🛒 Recent Orders</h4>
            <button onClick={() => onNavigate("orders")} className="text-[11px] font-bold text-violet-600 hover:underline">
              View All
            </button>
          </div>
          {dash.recent_orders.length === 0 ? (
            <p className="text-xs text-slate-400 py-6 text-center">No orders yet — they'll show up here once customers start buying.</p>
          ) : (
            <div className="space-y-2">
              {dash.recent_orders.slice(0, 5).map((o) => (
                <div key={o.id} className="flex items-center justify-between p-2.5 bg-slate-50/70 rounded-xl border border-slate-100/60 hover:bg-violet-50/40 transition-colors">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-800">#{o.number}</p>
                    <p className="text-[10px] text-slate-400 truncate">
                      {customerName(o)} · {timeAgo(o.created_at)}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-sm font-bold text-slate-900">{money(o.total)}</p>
                    <span className="text-[10px] font-semibold text-slate-500">{humanOrderStatus(o.status)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// PRODUCTS & INVENTORY PAGE
// ═══════════════════════════════════════════════════════════════════

function ProductsPage({ storeId, hasStores, storesLoading, storeName, filter, onFilterChange }: {
  storeId: string;
  hasStores: boolean;
  storesLoading: boolean;
  storeName: string;
  filter: ProductFilter;
  onFilterChange: (f: ProductFilter) => void;
}) {
  const [products, setProducts] = useState<WooCommerceProduct[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    if (!storeId) {
      setProducts([]);
      setTotal(0);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string | number | boolean | undefined> = { page_size: 100, search: search || undefined };
      if (filter === "in") params.stock_status = "instock";
      if (filter === "out") params.stock_status = "outofstock";
      if (filter === "low") params.low_stock_only = true;
      const data = await productApi.list(storeId, params);
      setProducts(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load your products.");
    } finally {
      setLoading(false);
    }
  }, [storeId, filter, search]);

  useEffect(() => {
    load();
  }, [load]);

  const filters: { id: ProductFilter; label: string }[] = [
    { id: "all", label: "All" },
    { id: "in", label: "In Stock" },
    { id: "low", label: "Low Stock" },
    { id: "out", label: "Out of Stock" },
  ];

  if (storesLoading) return <LoadingBlock />;
  if (!hasStores) return <NoStoreCard />;

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold text-slate-900">Products & Inventory</h3>
          <p className="text-xs text-slate-500">
            {total} product{total === 1 ? "" : "s"} in {storeName}
          </p>
        </div>
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search products…"
            className="pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg bg-slate-50 focus:outline-none focus:ring-2 focus:ring-violet-500/30 w-full sm:w-64"
          />
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        {filters.map((f) => (
          <button
            key={f.id}
            onClick={() => onFilterChange(f.id)}
            className={`px-4 py-2 rounded-xl text-sm font-semibold transition-all ${
              filter === f.id
                ? "bg-violet-600 text-white shadow-md shadow-violet-500/20"
                : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <LoadingBlock />
      ) : error ? (
        <ErrorBlock message={error} onRetry={load} />
      ) : products.length === 0 ? (
        <EmptyBlock
          icon={<Package className="w-7 h-7" />}
          title={filter === "all" ? "No products yet" : "Nothing here"}
          subtitle={
            filter === "all"
              ? "Products from your store will appear here once it's connected and up to date."
              : "Try a different filter — there are no products in this category right now."
          }
        />
      ) : (
        <div className="bg-white/80 border border-slate-200/60 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-3 text-left font-bold">Product</th>
                  <th className="px-4 py-3 text-left font-bold">SKU</th>
                  <th className="px-4 py-3 text-left font-bold">Available</th>
                  <th className="px-4 py-3 text-left font-bold">Status</th>
                  <th className="px-4 py-3 text-left font-bold">Store</th>
                  <th className="px-4 py-3 text-left font-bold hidden md:table-cell">Last Updated</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {products.map((p) => {
                  const status = stockLabel(p);
                  return (
                    <tr key={p.id} className="hover:bg-violet-50/30 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3 min-w-0">
                          {p.featured_image_url ? (
                            <img src={p.featured_image_url} alt="" className="w-10 h-10 rounded-lg object-cover bg-slate-100 shrink-0" />
                          ) : (
                            <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
                              <Package className="w-4 h-4 text-slate-400" />
                            </div>
                          )}
                          <span className="font-medium text-slate-900 truncate max-w-[180px]">{p.name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-slate-500">{p.sku || "—"}</td>
                      <td className="px-4 py-3 font-semibold text-slate-800">{p.stock_quantity ?? "N/A"}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-bold rounded-full border ${status.cls}`}>{status.icon} {status.text}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-500">{storeName}</td>
                      <td className="px-4 py-3 text-slate-400 hidden md:table-cell">{timeAgo(p.last_synced_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// ORDERS PAGE
// ═══════════════════════════════════════════════════════════════════

function OrdersPage({ storeId, hasStores, storesLoading, storeName }: {
  storeId: string;
  hasStores: boolean;
  storesLoading: boolean;
  storeName: string;
}) {
  const [orders, setOrders] = useState<WooCommerceOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!storeId) {
      setOrders([]);
      setTotal(0);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await orderApi.list(storeId, { page_size: 25 });
      setOrders(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load your orders.");
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    load();
  }, [load]);

  if (storesLoading) return <LoadingBlock />;
  if (!hasStores) return <NoStoreCard />;

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-slate-900">Orders</h3>
        <p className="text-xs text-slate-500">
          {total} order{total === 1 ? "" : "s"} in {storeName}
        </p>
      </div>

      {loading ? (
        <LoadingBlock />
      ) : error ? (
        <ErrorBlock message={error} onRetry={load} />
      ) : orders.length === 0 ? (
        <EmptyBlock
          icon={<ShoppingCart className="w-7 h-7" />}
          title="No orders yet"
          subtitle="When customers place orders, they'll appear here with their status so you can keep on top of everything."
        />
      ) : (
        <div className="bg-white/80 border border-slate-200/60 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-3 text-left font-bold">Order</th>
                  <th className="px-4 py-3 text-left font-bold">Customer</th>
                  <th className="px-4 py-3 text-left font-bold">Date</th>
                  <th className="px-4 py-3 text-left font-bold">Items</th>
                  <th className="px-4 py-3 text-left font-bold">Total</th>
                  <th className="px-4 py-3 text-left font-bold">Status</th>
                  <th className="px-4 py-3 text-left font-bold">Store</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {orders.map((o) => {
                  const statusText = humanOrderStatus(o.status);
                  const statusCls =
                    statusText === "Completed"
                      ? "bg-emerald-100 text-emerald-800"
                      : statusText === "Processing"
                      ? "bg-blue-100 text-blue-800"
                      : statusText === "Cancelled" || statusText === "Failed" || statusText === "Refunded"
                      ? "bg-rose-100 text-rose-800"
                      : "bg-amber-100 text-amber-800";
                  return (
                    <tr key={o.id} className="hover:bg-violet-50/30 transition-colors">
                      <td className="px-4 py-3 font-semibold text-slate-900">#{o.number}</td>
                      <td className="px-4 py-3 text-slate-600">{customerName(o)}</td>
                      <td className="px-4 py-3 text-slate-500">{new Date(o.created_at).toLocaleDateString()}</td>
                      <td className="px-4 py-3 text-slate-500">{o.items.reduce((sum, i) => sum + i.quantity, 0)}</td>
                      <td className="px-4 py-3 font-bold text-slate-900">{money(o.total)}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2.5 py-1 text-[11px] font-bold rounded-full ${statusCls}`}>{statusText}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-500">{storeName}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// STORE CONNECTIONS PAGE
// ═══════════════════════════════════════════════════════════════════

function StoresPage({ stores, storesLoading, storesError, shopify, shopifyLoading, onRefresh }: {
  stores: WooCommerceStore[];
  storesLoading: boolean;
  storesError: string | null;
  shopify: (ShopifyStatus & { inventory?: ShopifyInventorySnapshot }) | null;
  shopifyLoading: boolean;
  onRefresh: () => void;
}) {
  const [wooModal, setWooModal] = useState(false);
  const [shopifyModal, setShopifyModal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [notice, setNotice] = useState<{ tone: "ok" | "err"; text: string } | null>(null);

  // Sync products & inventory straight from the Shopify store.
  const handleShopifySync = async () => {
    setSyncing(true);
    setNotice(null);
    try {
      await shopifyApi.sync();
      setNotice({ tone: "ok", text: "Inventory synced with your Shopify store." });
      await onRefresh();
    } catch (err) {
      setNotice({
        tone: "err",
        text: err instanceof Error ? err.message : "We couldn't sync with Shopify right now.",
      });
    } finally {
      setSyncing(false);
    }
  };

  if (storesLoading || shopifyLoading) return <LoadingBlock />;

  // Only stores that are actually connected count — integrations that are
  // available but not connected are shown separately below.
  const wooConnected = stores.filter((s) => s.status === "connected");
  const wooInactive = stores.filter((s) => s.status !== "connected");
  const connectedCount = (shopify?.connected ? 1 : 0) + wooConnected.length;
  const hasAvailableIntegrations = !shopify?.connected || wooConnected.length === 0;

  return (
    <div className="space-y-6">
      {notice && (
        <div
          className={`p-3 rounded-xl border text-sm ${
            notice.tone === "ok"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-rose-50 border-rose-200 text-rose-800"
          }`}
        >
          {notice.text}
        </div>
      )}

      {/* Heading + prominent connected-store count */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold text-slate-900">Store Connections</h3>
          <p className="text-xs text-slate-500">
            Connect the stores you sell on — everything else in your dashboard updates automatically.
          </p>
        </div>
        <div className="inline-flex items-center gap-2.5 self-start sm:self-auto px-4 py-2 rounded-xl bg-emerald-50 border border-emerald-200 shadow-sm">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-semibold text-slate-500">Connected Stores</span>
          <span className="text-xl font-black text-emerald-700 leading-none">{connectedCount}</span>
        </div>
      </div>

      {/* Connected stores */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">Connected Stores</h4>
          {wooConnected.length > 0 && (
            <button
              onClick={() => setWooModal(true)}
              className="text-xs font-bold text-violet-600 hover:text-violet-800 hover:underline transition-colors"
            >
              + Add WooCommerce store
            </button>
          )}
        </div>

        {connectedCount === 0 ? (
          <EmptyBlock
            icon={<Store className="w-7 h-7" />}
            title="No stores connected yet"
            subtitle="Pick an integration below to start syncing your products, orders and stock levels."
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* Connected Shopify store */}
            {shopify?.connected && (
              <StoreCard
                platform="Shopify"
                icon={<Globe className="w-6 h-6" />}
                connected
                storeLabel={shopify.shopify_domain ?? "Shopify store"}
                productCount={shopify.inventory?.total_products}
                lastSync={shopify.inventory?.last_sync_at}
                onConnect={() => setShopifyModal(true)}
                connectLabel="Connect Shopify"
                onRefresh={onRefresh}
                onSync={handleShopifySync}
                syncing={syncing}
                connectedDetail={
                  shopify.inventory
                    ? `🟢 ${shopify.inventory.low_stock_count} low · 🔴 ${shopify.inventory.out_of_stock_count} out of stock`
                    : undefined
                }
              />
            )}

            {/* Connected WooCommerce stores */}
            {wooConnected.map((s) => (
              <StoreCard
                key={s.id}
                platform="WooCommerce"
                icon={<ShoppingBag className="w-6 h-6" />}
                connected
                storeLabel={s.store_name}
                storeUrl={s.store_url}
                productCount={undefined}
                lastSync={s.last_sync_at}
                onConnect={() => setWooModal(true)}
                connectLabel="Connect WooCommerce"
                onRefresh={onRefresh}
              />
            ))}
          </div>
        )}
      </section>

      {/* Available integrations */}
      {hasAvailableIntegrations && (
        <section className="space-y-3">
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">Available Integrations</h4>
            <p className="text-xs text-slate-500">Not connected yet — pick one to get started.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* Shopify integration */}
            {!shopify?.connected && (
              <StoreCard
                platform="Shopify"
                icon={<Globe className="w-6 h-6" />}
                connected={false}
                storeLabel="Not connected"
                productCount={undefined}
                lastSync={null}
                onConnect={() => setShopifyModal(true)}
                connectLabel="Connect Shopify"
                onRefresh={onRefresh}
              />
            )}

            {/* WooCommerce integration */}
            {wooConnected.length === 0 &&
              (wooInactive.length > 0 ? (
                wooInactive.map((s) => (
                  <StoreCard
                    key={s.id}
                    platform="WooCommerce"
                    icon={<ShoppingBag className="w-6 h-6" />}
                    connected={false}
                    storeLabel={s.store_name}
                    storeUrl={s.store_url}
                    productCount={undefined}
                    lastSync={s.last_sync_at}
                    onConnect={() => setWooModal(true)}
                    connectLabel="Connect"
                    onRefresh={onRefresh}
                    connectedDetail={
                      s.status === "error" ? "There's a connection issue — click refresh to check." : undefined
                    }
                  />
                ))
              ) : (
                <StoreCard
                  platform="WooCommerce"
                  icon={<ShoppingBag className="w-6 h-6" />}
                  connected={false}
                  storeLabel="Not connected"
                  productCount={undefined}
                  lastSync={null}
                  onConnect={() => setWooModal(true)}
                  connectLabel="Connect WooCommerce"
                  onRefresh={onRefresh}
                />
              ))}
          </div>
        </section>
      )}

      {storesError && (
        <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-sm text-amber-800">
          {storesError}
          <button onClick={onRefresh} className="ml-2 underline font-bold">Retry</button>
        </div>
      )}

      {wooModal && (
        <WooCommerceConnectModal
          onClose={() => setWooModal(false)}
          onDone={async () => {
            setBusy(true);
            try {
              await onRefresh();
              setNotice({ tone: "ok", text: "Store connected successfully. Your products will appear here soon." });
              setWooModal(false);
            } catch {
              setNotice({ tone: "err", text: "We couldn't refresh your stores. Please try again." });
            } finally {
              setBusy(false);
            }
          }}
          busy={busy}
        />
      )}
      {shopifyModal && (
        <ShopifyConnectModal
          onClose={() => setShopifyModal(false)}
          onDone={async () => {
            setBusy(true);
            try {
              await onRefresh();
              setNotice({ tone: "ok", text: "Shopify connected successfully. Your inventory is on its way." });
              setShopifyModal(false);
            } catch {
              setNotice({ tone: "err", text: "We couldn't refresh your store. Please try again." });
            } finally {
              setBusy(false);
            }
          }}
          busy={busy}
        />
      )}
    </div>
  );
}

function StoreCard({ platform, icon, connected, storeLabel, storeUrl, productCount, lastSync, onConnect, connectLabel, onRefresh, onSync, syncing, connectedDetail }: {
  platform: string;
  icon: React.ReactNode;
  connected: boolean;
  storeLabel: string | null;
  storeUrl?: string | null;
  productCount?: number | null;
  lastSync?: string | null;
  onConnect: () => void;
  connectLabel: string;
  onRefresh: () => void;
  onSync?: () => void;
  syncing?: boolean;
  connectedDetail?: string;
}) {
  return (
    <div className={`p-6 rounded-2xl border transition-all duration-300 hover:shadow-xl ${
      connected ? "bg-white/80 border-emerald-200/70" : "bg-white/70 border-slate-200/60"
    }`}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ${
            connected ? "bg-emerald-50 text-emerald-600" : "bg-slate-100 text-slate-400"
          }`}>
            {icon}
          </div>
          <div>
            <h4 className="font-bold text-slate-900">{platform}</h4>
            <p className="text-xs text-slate-500">{storeLabel ?? "Not connected"}</p>
          </div>
        </div>
        <span className={`px-3 py-1 text-[11px] font-bold rounded-full border ${
          connected ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-slate-50 text-slate-500 border-slate-200"
        }`}>
          {connected ? "● Connected" : "○ Not Connected"}
        </span>
      </div>

      {connected ? (
        <div className="mt-5 space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-slate-500">Products</span>
            <span className="font-bold text-slate-800">{productCount != null ? productCount : "—"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Last updated</span>
            <span className="font-semibold text-slate-700">{timeAgo(lastSync)}</span>
          </div>
          {storeUrl && (
            <div className="flex justify-between items-center gap-2">
              <span className="text-slate-500">Store</span>
              <a
                href={storeUrl.startsWith("http") ? storeUrl : `https://${storeUrl}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 font-semibold text-violet-600 hover:underline"
              >
                View store <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          )}
          {connectedDetail && <p className="text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-lg p-2">{connectedDetail}</p>}
          <div className="pt-3 grid grid-cols-2 gap-2">
            {onSync && (
              <button
                onClick={onSync}
                disabled={syncing}
                className="py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg transition-all disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {syncing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                {syncing ? "Syncing…" : "Sync now"}
              </button>
            )}
            <button
              onClick={onRefresh}
              className="py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-sm font-bold text-slate-700 hover:bg-slate-100 transition-colors"
            >
              Refresh
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-5">
          <p className="text-xs text-slate-500">
            {platform === "Shopify"
              ? "Connect your Shopify store to keep track of your products and stock."
              : "Connect your WooCommerce store to keep track of your products, stock and orders."}
          </p>
          <button
            onClick={onConnect}
            className="mt-4 w-full py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg hover:shadow-violet-500/25 hover:scale-[1.01] transition-all"
          >
            {connectLabel}
          </button>
        </div>
      )}
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
      <div className="w-full max-w-md bg-white rounded-3xl shadow-2xl p-6 animate-fade-in" onClick={(e) => e.stopPropagation()}>
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

function WooCommerceConnectModal({ onClose, onDone, busy }: {
  onClose: () => void;
  onDone: () => Promise<void>;
  busy: boolean;
}) {
  const [form, setForm] = useState({ store_name: "", store_url: "", consumer_key: "", consumer_secret: "" });
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await storeApi.connect(form);
      await onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't connect your store. Please check the details and try again.");
    }
  };

  const inputCls = "w-full p-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/30";

  return (
    <Modal
      title="Connect your WooCommerce store"
      subtitle="You'll find these details in your store's WooCommerce settings, under REST API."
      onClose={onClose}
    >
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label className="block text-xs font-bold text-slate-600 mb-1">Store name</label>
          <input required value={form.store_name} onChange={(e) => setForm({ ...form, store_name: e.target.value })} placeholder="My Store" className={inputCls} />
        </div>
        <div>
          <label className="block text-xs font-bold text-slate-600 mb-1">Store website</label>
          <input required type="url" value={form.store_url} onChange={(e) => setForm({ ...form, store_url: e.target.value })} placeholder="https://yourstore.com" className={inputCls} />
        </div>
        <div>
          <label className="block text-xs font-bold text-slate-600 mb-1">Consumer key</label>
          <input required value={form.consumer_key} onChange={(e) => setForm({ ...form, consumer_key: e.target.value })} placeholder="ck_…" className={inputCls} />
        </div>
        <div>
          <label className="block text-xs font-bold text-slate-600 mb-1">Consumer secret</label>
          <input required type="password" value={form.consumer_secret} onChange={(e) => setForm({ ...form, consumer_secret: e.target.value })} placeholder="cs_…" className={inputCls} />
        </div>
        {error && <p className="text-xs text-rose-600 bg-rose-50 border border-rose-100 rounded-lg p-2">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {busy && <Loader2 className="w-4 h-4 animate-spin" />} Connect Store
        </button>
      </form>
    </Modal>
  );
}

function ShopifyConnectModal({ onClose, onDone, busy }: {
  onClose: () => void;
  onDone: () => Promise<void>;
  busy: boolean;
}) {
  const [form, setForm] = useState({ shop_domain: "", access_token: "" });
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await shopifyApi.connect({
        shop_domain: form.shop_domain.replace(/^https?:\/\//, "").replace(/\/$/, ""),
        access_token: form.access_token,
      });
      await onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't connect your store. Please check the details and try again.");
    }
  };

  const inputCls = "w-full p-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/30";

  return (
    <Modal
      title="Connect your Shopify store"
      subtitle="You can find these details in your Shopify admin, under Settings → Apps."
      onClose={onClose}
    >
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label className="block text-xs font-bold text-slate-600 mb-1">Store address</label>
          <input required value={form.shop_domain} onChange={(e) => setForm({ ...form, shop_domain: e.target.value })} placeholder="yourstore.myshopify.com" className={inputCls} />
        </div>
        <div>
          <label className="block text-xs font-bold text-slate-600 mb-1">Access token</label>
          <input required type="password" value={form.access_token} onChange={(e) => setForm({ ...form, access_token: e.target.value })} placeholder="shpat_…" className={inputCls} />
        </div>
        {error && <p className="text-xs text-rose-600 bg-rose-50 border border-rose-100 rounded-lg p-2">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {busy && <Loader2 className="w-4 h-4 animate-spin" />} Connect Store
        </button>
      </form>
    </Modal>
  );
}

// ═══════════════════════════════════════════════════════════════════
// REPORTS PAGE
// ═══════════════════════════════════════════════════════════════════

function ReportsPage({ storeId, hasStores, storesLoading, storeName, onNavigate }: {
  storeId: string;
  hasStores: boolean;
  storesLoading: boolean;
  storeName: string;
  onNavigate: (tab: TabId, filter?: ProductFilter) => void;
}) {
  const [dash, setDash] = useState<DashboardData | null>(null);
  const [products, setProducts] = useState<WooCommerceProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!storeId) {
      setDash(null);
      setProducts([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [d, p] = await Promise.all([
        dashboardApi.get(storeId),
        productApi.list(storeId, { page_size: 100 }),
      ]);
      setDash(d);
      setProducts(p.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load your reports.");
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    load();
  }, [load]);

  if (storesLoading) return <LoadingBlock />;
  if (!hasStores) return <NoStoreCard />;
  if (loading) return <LoadingBlock />;
  if (error || !dash) return <ErrorBlock message={error ?? "No data yet."} onRetry={load} />;

  const { stats } = dash;
  const lowStock = products.filter((p) => stockTone(p) === "low");
  const outOfStock = products.filter((p) => stockTone(p) === "out");
  const inStock = products.filter((p) => stockTone(p) === "in");
  const totalUnits = products.reduce((sum, p) => sum + (p.stock_quantity ?? 0), 0);

  const bar = (label: string, value: number, max: number, cls: string) => (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="font-semibold text-slate-600">{label}</span>
        <span className="font-bold text-slate-800">{value}</span>
      </div>
      <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
        <div className={`h-2.5 rounded-full ${cls}`} style={{ width: `${max > 0 ? Math.round((value / max) * 100) : 0}%` }} />
      </div>
    </div>
  );

  const maxBar = Math.max(inStock.length, lowStock.length, outOfStock.length, 1);

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-bold text-slate-900">Business Reports</h3>
        <p className="text-xs text-slate-500">A simple overview of {storeName}</p>
      </div>

      {/* Inventory overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Products" value={stats.total_products} icon={<Package className="w-5 h-5" />} tone="from-violet-500 to-indigo-600" />
        <StatCard label="Units in stock" value={totalUnits} icon={<TrendingUp className="w-5 h-5" />} tone="from-blue-400 to-cyan-500" />
        <StatCard label="Total revenue" value={money(stats.total_revenue)} icon={<DollarSign className="w-5 h-5" />} tone="from-emerald-400 to-teal-500" sub="All time" />
        <StatCard label="Orders" value={stats.total_orders} icon={<ShoppingBag className="w-5 h-5" />} tone="from-amber-400 to-orange-500" />
      </div>

      {/* Revenue Dashboard / Advanced Analytics (Phase 3) */}
      <div className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
        <RevenueAnalytics storeId={storeId} storeName={storeName} hasStores={hasStores} storesLoading={storesLoading} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Stock breakdown */}
        <div className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
          <h4 className="text-sm font-bold text-slate-900 mb-4">Stock Health</h4>
          <div className="space-y-4">
            {bar("In Stock", inStock.length, maxBar, "bg-gradient-to-r from-emerald-400 to-green-500")}
            {bar("Low Stock", lowStock.length, maxBar, "bg-gradient-to-r from-amber-400 to-orange-500")}
            {bar("Out of Stock", outOfStock.length, maxBar, "bg-gradient-to-r from-rose-400 to-red-500")}
          </div>
          <p className="text-[10px] text-slate-400 mt-4">
            Based on the most recent product information from {storeName}.
          </p>
        </div>

        {/* Order summary */}
        <div className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
          <h4 className="text-sm font-bold text-slate-900 mb-4">Order Summary</h4>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-500">Total orders</span>
              <span className="font-bold text-slate-800">{stats.total_orders}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Total revenue</span>
              <span className="font-bold text-slate-800">{money(stats.total_revenue)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Customers</span>
              <span className="font-bold text-slate-800">{stats.total_customers}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Last order</span>
              <span className="font-semibold text-slate-700">
                {dash.recent_orders[0] ? timeAgo(dash.recent_orders[0].created_at) : "No orders yet"}
              </span>
            </div>
          </div>
          <button onClick={() => onNavigate("orders")} className="mt-4 text-xs font-bold text-violet-600 hover:underline">
            View all orders →
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Low stock list */}
        <div className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-bold text-slate-900">Products Running Low</h4>
            <button onClick={() => onNavigate("products", "low")} className="text-[11px] font-bold text-violet-600 hover:underline">
              View all
            </button>
          </div>
          {lowStock.length === 0 ? (
            <p className="text-xs text-slate-400 py-4 text-center">Great news — no products are running low.</p>
          ) : (
            <div className="space-y-2">
              {lowStock.slice(0, 5).map((p) => (
                <div key={p.id} className="flex items-center justify-between p-2.5 bg-amber-50/70 rounded-xl border border-amber-100">
                  <span className="text-sm font-medium text-slate-800 truncate">{p.name}</span>
                  <span className="text-sm font-bold text-amber-700">{p.stock_quantity ?? 0} left</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Out of stock list */}
        <div className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-bold text-slate-900">Out of Stock</h4>
            <button onClick={() => onNavigate("products", "out")} className="text-[11px] font-bold text-violet-600 hover:underline">
              View all
            </button>
          </div>
          {outOfStock.length === 0 ? (
            <p className="text-xs text-slate-400 py-4 text-center">No products are out of stock right now.</p>
          ) : (
            <div className="space-y-2">
              {outOfStock.slice(0, 5).map((p) => (
                <div key={p.id} className="flex items-center justify-between p-2.5 bg-rose-50/70 rounded-xl border border-rose-100">
                  <span className="text-sm font-medium text-slate-800 truncate">{p.name}</span>
                  <span className="text-sm font-bold text-rose-600">Unavailable</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// ALERTS PAGE
// ═══════════════════════════════════════════════════════════════════

function AlertsPage({ storeId, hasStores, storesLoading, storeName, onNavigate }: {
  storeId: string;
  hasStores: boolean;
  storesLoading: boolean;
  storeName: string;
  onNavigate: (tab: TabId, filter?: ProductFilter) => void;
}) {
  const [dash, setDash] = useState<DashboardData | null>(null);
  const [backendAlerts, setBackendAlerts] = useState<DashboardData["recent_alerts"]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!storeId) {
      setDash(null);
      setBackendAlerts([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [d, a] = await Promise.all([
        dashboardApi.get(storeId),
        alertApi.list(storeId, { unresolved_only: true, page_size: 50 }),
      ]);
      setDash(d);
      setBackendAlerts(a.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load your alerts.");
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    load();
  }, [load]);

  const markResolved = async (id: string) => {
    try {
      await alertApi.mark(storeId, { alert_ids: [id], mark_as_resolved: true });
      setBackendAlerts((prev) => prev.filter((a) => a.id !== id));
    } catch {
      // Keep it simple: leave the alert if marking fails.
    }
  };

  if (storesLoading) return <LoadingBlock />;
  if (!hasStores) return <NoStoreCard />;
  if (loading) return <LoadingBlock />;
  if (error || !dash) return <ErrorBlock message={error ?? "No alerts."} onRetry={load} />;

  const { stats } = dash;

  // Actionable business alerts with plain-language WHAT / WHY / DO.
  const businessAlerts: {
    id: string; severity: string; title: string; why: string; action: string; tab: TabId; filter?: ProductFilter;
  }[] = [];

  if (stats.low_stock_count > 0) {
    businessAlerts.push({
      id: "biz-low",
      severity: "warning",
      title: `${stats.low_stock_count} product${stats.low_stock_count === 1 ? " is" : "s are"} running low`,
      why: "These products are close to selling out, so customers may soon be unable to buy them.",
      action: "View Products", tab: "products", filter: "low",
    });
  }
  if (stats.out_of_stock_count > 0) {
    businessAlerts.push({
      id: "biz-out",
      severity: "critical",
      title: `${stats.out_of_stock_count} product${stats.out_of_stock_count === 1 ? " is" : "s are"} out of stock`,
      why: "Customers can't buy these products right now, which means lost sales.",
      action: "Restock", tab: "products", filter: "out",
    });
  }
  if (stats.last_sync_at && (Date.now() - new Date(stats.last_sync_at).getTime()) / 3600000 > 24) {
    businessAlerts.push({
      id: "biz-stale",
      severity: "warning",
      title: "Your store hasn't updated in over a day",
      why: "Your product and order information may be out of date.",
      action: "Check Store", tab: "stores",
    });
  }
  if (!stats.last_sync_at) {
    businessAlerts.push({
      id: "biz-nosync",
      severity: "info",
      title: "Your store hasn't been updated yet",
      why: "Once your store is connected and updated, everything you see here stays current automatically.",
      action: "Check Store", tab: "stores",
    });
  }

  const severityCls = (severity: string) =>
    severity === "critical"
      ? "bg-rose-50 border-rose-200"
      : severity === "warning"
      ? "bg-amber-50 border-amber-200"
      : "bg-blue-50 border-blue-200";

  const allAlerts = [
    ...businessAlerts.map((a) => ({
      id: a.id, severity: a.severity, title: a.title, message: a.why, created_at: null as string | null,
      action: a.action, tab: a.tab, filter: a.filter, backend: false,
    })),
    ...backendAlerts.map((a) => ({
      id: a.id, severity: a.severity || "info", title: a.title, message: a.message, created_at: a.created_at,
      action: a.alert_type?.includes("stock") ? "View Products" : a.alert_type?.includes("order") ? "View Orders" : "Check Store",
      tab: (a.alert_type?.includes("stock") ? "products" : a.alert_type?.includes("order") ? "orders" : "stores") as TabId,
      filter: a.alert_type?.includes("stock") ? ("low" as ProductFilter) : undefined,
      backend: true,
    })),
  ];

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-slate-900">Alerts</h3>
        <p className="text-xs text-slate-500">
          What's happening in {storeName}, why it matters, and what to do about it.
        </p>
      </div>

      {allAlerts.length === 0 ? (
        <EmptyBlock
          icon={<CheckCircle2 className="w-7 h-7" />}
          title="You're all caught up 🎉"
          subtitle="No alerts right now. We'll let you know if something needs your attention."
        />
      ) : (
        <div className="space-y-3">
          {allAlerts.map((a) => (
            <div key={a.id} className={`p-4 rounded-2xl border ${severityCls(a.severity)} hover:shadow-sm transition-shadow`}>
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full ${
                      a.severity === "critical" ? "bg-rose-200 text-rose-800" : a.severity === "warning" ? "bg-amber-200 text-amber-800" : "bg-blue-200 text-blue-800"
                    }`}>
                      {a.severity === "critical" ? "Action needed" : a.severity === "warning" ? "Heads up" : "Good to know"}
                    </span>
                    {a.created_at && <span className="text-[10px] text-slate-400">{timeAgo(a.created_at)}</span>}
                  </div>
                  <p className="text-sm font-bold text-slate-900 mt-2">{a.title}</p>
                  <p className="text-xs text-slate-600 mt-1">{a.message}</p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => onNavigate(a.tab, a.filter)}
                    className="px-3.5 py-2 bg-white border border-slate-200 rounded-lg text-xs font-bold text-violet-700 hover:bg-violet-50 transition-colors"
                  >
                    {a.action}
                  </button>
                  {a.backend && (
                    <button
                      onClick={() => markResolved(a.id)}
                      className="px-3.5 py-2 bg-white border border-slate-200 rounded-lg text-xs font-bold text-slate-500 hover:bg-slate-50 transition-colors"
                    >
                      Done
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// SETTINGS PAGE
// ═══════════════════════════════════════════════════════════════════

function SettingsPage({ storeId, hasStores, storesLoading, stores, shopify, userEmail }: {
  storeId: string;
  hasStores: boolean;
  storesLoading: boolean;
  stores: WooCommerceStore[];
  shopify: (ShopifyStatus & { inventory?: ShopifyInventorySnapshot }) | null;
  userEmail?: string | null;
}) {
  const [settings, setSettings] = useState<StoreSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!storeId) {
      setSettings(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await settingsApi.get(storeId);
      setSettings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load your settings.");
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    if (!settings) return;
    setSaving(true);
    setSaved(false);
    try {
      await settingsApi.update(storeId, {
        low_stock_alerts: settings.low_stock_alerts,
        email_alerts: settings.email_alerts,
        alert_email: settings.alert_email,
        sync_failure_alerts: settings.sync_failure_alerts,
        low_stock_threshold: settings.low_stock_threshold,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save your settings.");
    } finally {
      setSaving(false);
    }
  };

  const selectedStore = stores.find((s) => s.id === storeId);
  const Toggle = ({ label, desc, value, onChange }: {
    label: string; desc?: string; value: boolean; onChange: (v: boolean) => void;
  }) => (
    <div className="flex items-center justify-between gap-4 py-3">
      <div>
        <p className="text-sm font-semibold text-slate-800">{label}</p>
        {desc && <p className="text-xs text-slate-500">{desc}</p>}
      </div>
      <button
        onClick={() => onChange(!value)}
        className={`w-10 h-5 rounded-full transition-all shrink-0 ${value ? "bg-violet-600" : "bg-slate-300"}`}
        aria-pressed={value}
      >
        <div className={`w-4 h-4 bg-white rounded-full shadow-sm transform transition-all ${value ? "translate-x-5" : "translate-x-0.5"} mt-0.5`} />
      </button>
    </div>
  );

  if (storesLoading) return <LoadingBlock />;
  if (!hasStores) return <NoStoreCard />;
  if (loading) return <LoadingBlock />;

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h3 className="text-lg font-bold text-slate-900">Settings</h3>
        <p className="text-xs text-slate-500">Your account, store details and notification preferences.</p>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-sm text-rose-700">{error}</div>
      )}

      {/* Profile */}
      <section className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
        <h4 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2">
          <User className="w-4 h-4 text-violet-500" /> Profile
        </h4>
        <div className="flex items-center gap-3">
          <div className="w-11 h-11 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center text-white font-bold">
            {userEmail?.charAt(0).toUpperCase() || "U"}
          </div>
          <div>
            <p className="text-sm font-bold text-slate-800">
              {userEmail?.split("@")[0].replace(/[._-]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) || "Store Owner"}
            </p>
            <p className="text-xs text-slate-500 flex items-center gap-1">
              <Mail className="w-3 h-3" /> {userEmail || "—"}
            </p>
          </div>
        </div>
      </section>

      {/* Business info */}
      <section className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
        <h4 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2">
          <Store className="w-4 h-4 text-violet-500" /> Business & Store
        </h4>
        <div className="space-y-3 text-sm">
          {selectedStore && (
            <div className="flex justify-between">
              <span className="text-slate-500">Store</span>
              <span className="font-semibold text-slate-800">{selectedStore.store_name}</span>
            </div>
          )}
          {selectedStore?.store_url && (
            <div className="flex justify-between">
              <span className="text-slate-500">Website</span>
              <a href={selectedStore.store_url} target="_blank" rel="noreferrer" className="font-semibold text-violet-600 hover:underline">
                {selectedStore.store_url}
              </a>
            </div>
          )}
          {shopify?.connected && (
            <div className="flex justify-between">
              <span className="text-slate-500">Shopify</span>
              <span className="font-semibold text-slate-800">{shopify.shopify_domain}</span>
            </div>
          )}
        </div>
      </section>

      {/* Notifications */}
      <section className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
        <h4 className="text-sm font-bold text-slate-900 mb-1 flex items-center gap-2">
          <Bell className="w-4 h-4 text-violet-500" /> Notifications
        </h4>
        <p className="text-xs text-slate-500 mb-2">Choose what you'd like to hear about.</p>
        <div className="divide-y divide-slate-100">
          <Toggle
            label="Low stock alerts"
            desc="Tell me when products are running low"
            value={settings?.low_stock_alerts ?? false}
            onChange={(v) => setSettings(settings ? { ...settings, low_stock_alerts: v } : settings)}
          />
          <Toggle
            label="Email notifications"
            desc="Send alerts to my email"
            value={settings?.email_alerts ?? false}
            onChange={(v) => setSettings(settings ? { ...settings, email_alerts: v } : settings)}
          />
          {settings?.email_alerts && (
            <div className="py-3">
              <label className="block text-xs font-bold text-slate-600 mb-1">Alert email</label>
              <input
                type="email"
                value={settings.alert_email ?? ""}
                onChange={(e) => setSettings({ ...settings, alert_email: e.target.value || null })}
                placeholder="you@example.com"
                className="w-full p-2.5 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/30"
              />
            </div>
          )}
          <Toggle
            label="Something went wrong alerts"
            desc="Let me know if a sync or update fails"
            value={settings?.sync_failure_alerts ?? false}
            onChange={(v) => setSettings(settings ? { ...settings, sync_failure_alerts: v } : settings)}
          />
        </div>
      </section>

      {/* Preferences */}
      <section className="p-5 rounded-2xl bg-white/70 border border-slate-200/60">
        <h4 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-violet-500" /> Preferences
        </h4>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-800">Low stock alert level</p>
            <p className="text-xs text-slate-500">Warn me when a product drops to this many items</p>
          </div>
          <input
            type="number"
            min={0}
            value={settings?.low_stock_threshold ?? 10}
            onChange={(e) => setSettings(settings ? { ...settings, low_stock_threshold: Math.max(0, Number(e.target.value)) } : settings)}
            className="w-20 p-2 border border-slate-200 rounded-xl text-sm text-center focus:outline-none focus:ring-2 focus:ring-violet-500/30"
          />
        </div>
      </section>

      <div className="flex items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-bold hover:shadow-lg hover:shadow-violet-500/25 transition-all disabled:opacity-50 flex items-center gap-2"
        >
          {saving && <Loader2 className="w-4 h-4 animate-spin" />} Save Changes
        </button>
        {saved && (
          <span className="text-xs font-bold text-emerald-600 flex items-center gap-1">
            <CheckCircle2 className="w-4 h-4" /> Saved
          </span>
        )}
      </div>
    </div>
  );
}
