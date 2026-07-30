"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  LayoutDashboard, Package, ShoppingCart, Users, Tags,
  Ticket, AlertTriangle, Settings, RefreshCw,
  Store, Search, Plus, Download, Upload, ChevronDown,
  ArrowUp, ArrowDown, TrendingUp, DollarSign,
  Bell, LogOut, Menu, X, Loader2, CheckCircle2,
} from "lucide-react";
import { storeApi, productApi, orderApi, customerApi, categoryApi, couponApi, inventoryApi, dashboardApi, settingsApi, alertApi } from "@/lib/api";

// ─── Types ───

type TabType = "dashboard" | "products" | "orders" | "inventory" | "customers" | "categories" | "coupons" | "alerts" | "settings" | "stores";

interface Store {
  id: string;
  store_name: string;
  store_url: string;
  status: string;
  is_active: boolean;
  last_sync_at: string | null;
}

// ─── Props ───

interface DashboardProps {
  onLogout?: () => void;
  userEmail?: string;
}

// ─── Main Component ───

export default function WooCommerceDashboard({ onLogout, userEmail }: DashboardProps) {
  const [activeTab, setActiveTab] = useState<TabType>("dashboard");
  const [stores, setStores] = useState<Store[]>([]);
  const [selectedStoreId, setSelectedStoreId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [syncLoading, setSyncLoading] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);

  // Fetch stores on mount
  useEffect(() => {
    loadStores();
  }, []);

  const loadStores = async () => {
    try {
      const data = await storeApi.list();
      setStores(data.items);
      if (data.items.length > 0 && !selectedStoreId) {
        setSelectedStoreId(data.items[0].id);
      }
    } catch (err) {
      console.error("Failed to load stores:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleSync = async (resource: string) => {
    if (!selectedStoreId) return;
    setSyncLoading(resource);
    try {
      switch (resource) {
        case "products":
          await productApi.sync(selectedStoreId);
          break;
        case "orders":
          await orderApi.sync(selectedStoreId);
          break;
        case "customers":
          await customerApi.sync(selectedStoreId);
          break;
        case "categories":
          await categoryApi.sync(selectedStoreId);
          break;
        case "coupons":
          await couponApi.sync(selectedStoreId);
          break;
        case "all":
          await Promise.all([
            productApi.sync(selectedStoreId),
            orderApi.sync(selectedStoreId),
            customerApi.sync(selectedStoreId),
            categoryApi.sync(selectedStoreId),
            couponApi.sync(selectedStoreId),
          ]);
          break;
      }
    } catch (err) {
      console.error(`Sync failed for ${resource}:`, err);
    } finally {
      setSyncLoading(null);
    }
  };

  const navItems = [
    { id: "dashboard" as TabType, label: "Dashboard", icon: <LayoutDashboard className="w-5 h-5" /> },
    { id: "stores" as TabType, label: "Stores", icon: <Store className="w-5 h-5" /> },
    { id: "products" as TabType, label: "Products", icon: <Package className="w-5 h-5" /> },
    { id: "inventory" as TabType, label: "Inventory", icon: <TrendingUp className="w-5 h-5" /> },
    { id: "orders" as TabType, label: "Orders", icon: <ShoppingCart className="w-5 h-5" /> },
    { id: "customers" as TabType, label: "Customers", icon: <Users className="w-5 h-5" /> },
    { id: "categories" as TabType, label: "Categories", icon: <Tags className="w-5 h-5" /> },
    { id: "coupons" as TabType, label: "Coupons", icon: <Ticket className="w-5 h-5" /> },
    { id: "alerts" as TabType, label: "Alerts", icon: <AlertTriangle className="w-5 h-5" /> },
    { id: "settings" as TabType, label: "Settings", icon: <Settings className="w-5 h-5" /> },
  ];

  return (
    <div className="flex h-screen bg-slate-50">
      {/* Sidebar */}
      <aside className={`${sidebarOpen ? "w-64" : "w-16"} bg-white border-r border-slate-200 flex flex-col transition-all duration-300`}>
        <div className="p-4 border-b border-slate-100">
          <div className="flex items-center justify-between">
            <div className={`flex items-center gap-3 ${!sidebarOpen && "hidden"}`}>
              <div className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center">
                <TrendingUp className="w-4 h-4 text-white" />
              </div>
              <span className="font-bold text-slate-900">Digital FTE</span>
            </div>
            <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-1.5 rounded-lg hover:bg-slate-100">
              {sidebarOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
            </button>
          </div>
        </div>

        <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === item.id
                  ? "bg-violet-50 text-violet-700 border border-violet-200"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              {item.icon}
              {sidebarOpen && <span>{item.label}</span>}
            </button>
          ))}
        </nav>

        <div className="p-3 border-t border-slate-100">
          <button
            onClick={onLogout}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-600 hover:bg-red-50 hover:text-red-600 transition-all"
          >
            <LogOut className="w-5 h-5" />
            {sidebarOpen && <span>Logout</span>}
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-lg font-bold text-slate-900">WooCommerce Dashboard</h1>
            {selectedStoreId && (
              <select
                value={selectedStoreId}
                onChange={(e) => setSelectedStoreId(e.target.value)}
                className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-slate-50"
              >
                {stores.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.store_name} ({s.status})
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className="flex items-center gap-3">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Search..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-4 py-1.5 text-sm border border-slate-200 rounded-lg bg-slate-50 focus:outline-none focus:ring-2 focus:ring-violet-500"
              />
            </div>
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Bell className="w-4 h-4" />
              <span className="w-2 h-2 rounded-full bg-red-500" />
            </div>
            <div className="w-8 h-8 rounded-full bg-violet-600 flex items-center justify-center text-white text-sm font-bold">
              {userEmail?.charAt(0).toUpperCase() || "U"}
            </div>
          </div>
        </header>

        {/* Page Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === "dashboard" && selectedStoreId && <DashboardPage storeId={selectedStoreId} onSync={handleSync} syncLoading={syncLoading} />}
          {activeTab === "stores" && <StoresPage stores={stores} onRefresh={loadStores} />}
          {activeTab === "products" && selectedStoreId && <ProductsPage storeId={selectedStoreId} searchQuery={searchQuery} onSync={handleSync} syncLoading={syncLoading} />}
          {activeTab === "inventory" && selectedStoreId && <InventoryPage storeId={selectedStoreId} />}
          {activeTab === "orders" && selectedStoreId && <OrdersPage storeId={selectedStoreId} searchQuery={searchQuery} onSync={handleSync} syncLoading={syncLoading} />}
          {activeTab === "customers" && selectedStoreId && <CustomersPage storeId={selectedStoreId} searchQuery={searchQuery} onSync={handleSync} syncLoading={syncLoading} />}
          {activeTab === "categories" && selectedStoreId && <CategoriesPage storeId={selectedStoreId} onSync={handleSync} syncLoading={syncLoading} />}
          {activeTab === "coupons" && selectedStoreId && <CouponsPage storeId={selectedStoreId} onSync={handleSync} syncLoading={syncLoading} />}
          {activeTab === "alerts" && selectedStoreId && <AlertsPage storeId={selectedStoreId} />}
          {activeTab === "settings" && selectedStoreId && <SettingsPage storeId={selectedStoreId} />}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// DASHBOARD PAGE
// ═══════════════════════════════════════════════════════════════════

function DashboardPage({ storeId, onSync, syncLoading }: {
  storeId: string;
  onSync: (resource: string) => Promise<void>;
  syncLoading: string | null;
}) {
  const [data, setData] = useState<{
    stats: { total_products: number; total_orders: number; total_customers: number; total_revenue: number; low_stock_count: number; out_of_stock_count: number; active_alerts: number; last_sync_at: string | null; sync_status: string };
    recent_orders: unknown[];
    low_stock_items: unknown[];
    recent_alerts: unknown[];
    recent_syncs: unknown[];
  } | null>(null);

  useEffect(() => {
    loadDashboard();
  }, [storeId]);

  const loadDashboard = async () => {
    try {
      const result = await dashboardApi.get(storeId);
      setData(result as typeof data);
    } catch (err) {
      console.error("Dashboard load failed:", err);
    }
  };

  if (!data) return <div className="flex items-center justify-center h-64"><Loader2 className="w-8 h-8 animate-spin text-violet-600" /></div>;

  const { stats } = data;
  const statCards = [
    { label: "Total Products", value: stats.total_products, icon: <Package className="w-5 h-5" />, color: "from-violet-500 to-indigo-600" },
    { label: "Total Orders", value: stats.total_orders, icon: <ShoppingCart className="w-5 h-5" />, color: "from-blue-400 to-cyan-500" },
    { label: "Customers", value: stats.total_customers, icon: <Users className="w-5 h-5" />, color: "from-emerald-400 to-green-500" },
    { label: "Revenue", value: `$${Number(stats.total_revenue).toLocaleString()}`, icon: <DollarSign className="w-5 h-5" />, color: "from-amber-400 to-orange-500" },
    { label: "Low Stock", value: stats.low_stock_count, icon: <AlertTriangle className="w-5 h-5" />, color: "from-rose-400 to-red-500" },
    { label: "Active Alerts", value: stats.active_alerts, icon: <Bell className="w-5 h-5" />, color: "from-purple-400 to-pink-500" },
  ];

  return (
    <div className="space-y-6">
      {/* Quick Actions */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => onSync("all")}
          disabled={syncLoading === "all"}
          className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white rounded-lg text-sm font-medium hover:bg-violet-700 transition-all disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${syncLoading === "all" ? "animate-spin" : ""}`} />
          {syncLoading === "all" ? "Syncing..." : "Sync All"}
        </button>
        {["products", "orders", "customers", "categories", "coupons"].map((res) => (
          <button
            key={res}
            onClick={() => onSync(res)}
            disabled={syncLoading === res}
            className="px-3 py-2 bg-white border border-slate-200 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-50 transition-all disabled:opacity-50"
          >
            {syncLoading === res ? <Loader2 className="w-3 h-3 animate-spin inline" /> : null}
            Sync {res}
          </button>
        ))}
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {statCards.map((card, i) => (
          <div key={i} className="p-4 bg-white rounded-xl border border-slate-200 hover:shadow-lg transition-all">
            <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${card.color} flex items-center justify-center text-white mb-3`}>
              {card.icon}
            </div>
            <p className="text-2xl font-bold text-slate-900">{card.value}</p>
            <p className="text-xs text-slate-500 mt-1">{card.label}</p>
          </div>
        ))}
      </div>

      {/* Sync Status */}
      <div className="p-4 bg-white rounded-xl border border-slate-200">
        <h3 className="text-sm font-bold text-slate-900 mb-3">Sync Status</h3>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-slate-500">Last sync:</span>
          <span className="font-medium">{stats.last_sync_at ? new Date(stats.last_sync_at).toLocaleString() : "Never"}</span>
          <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
            stats.sync_status === "connected" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
          }`}>
            {stats.sync_status}
          </span>
        </div>
      </div>

      {/* Recent Orders & Low Stock */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="p-4 bg-white rounded-xl border border-slate-200">
          <h3 className="text-sm font-bold text-slate-900 mb-3">Recent Orders</h3>
          {data.recent_orders.length === 0 ? (
            <p className="text-sm text-slate-400">No orders synced yet</p>
          ) : (
            <div className="space-y-2">
              {(data.recent_orders as Array<{ number: string; total: number; status: string; created_at: string }>).slice(0, 5).map((order, i) => (
                <div key={i} className="flex items-center justify-between p-2 bg-slate-50 rounded-lg">
                  <div>
                    <p className="text-sm font-medium text-slate-900">{order.number}</p>
                    <p className="text-xs text-slate-400">{new Date(order.created_at).toLocaleDateString()}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold text-slate-900">${Number(order.total).toFixed(2)}</p>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                      order.status === "completed" ? "bg-emerald-100 text-emerald-800" :
                      order.status === "processing" ? "bg-blue-100 text-blue-800" : "bg-slate-100 text-slate-600"
                    }`}>{order.status}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="p-4 bg-white rounded-xl border border-slate-200">
          <h3 className="text-sm font-bold text-slate-900 mb-3">Low Stock Items</h3>
          {data.low_stock_items.length === 0 ? (
            <p className="text-sm text-slate-400">No low stock items</p>
          ) : (
            <div className="space-y-2">
              {(data.low_stock_items as Array<{ product_name: string; sku: string | null; stock_quantity: number }>).slice(0, 5).map((item, i) => (
                <div key={i} className="flex items-center justify-between p-2 bg-amber-50 rounded-lg border border-amber-100">
                  <div>
                    <p className="text-sm font-medium text-slate-900">{item.product_name}</p>
                    <p className="text-xs text-slate-400">SKU: {item.sku || "N/A"}</p>
                  </div>
                  <span className="text-sm font-bold text-amber-700">{item.stock_quantity} remaining</span>
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
// STORES PAGE
// ═══════════════════════════════════════════════════════════════════

function StoresPage({ stores, onRefresh }: { stores: Store[]; onRefresh: () => void }) {
  const [showConnect, setShowConnect] = useState(false);
  const [form, setForm] = useState({ store_name: "", store_url: "", consumer_key: "", consumer_secret: "" });
  const [connecting, setConnecting] = useState(false);

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    setConnecting(true);
    try {
      await storeApi.connect(form);
      setShowConnect(false);
      setForm({ store_name: "", store_url: "", consumer_key: "", consumer_secret: "" });
      onRefresh();
    } catch (err) {
      console.error("Connect failed:", err);
    } finally {
      setConnecting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-900">Connected Stores</h2>
        <button
          onClick={() => setShowConnect(!showConnect)}
          className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white rounded-lg text-sm font-medium hover:bg-violet-700"
        >
          <Plus className="w-4 h-4" /> Connect Store
        </button>
      </div>

      {showConnect && (
        <form onSubmit={handleConnect} className="p-6 bg-white rounded-xl border border-slate-200 space-y-4">
          <h3 className="font-bold text-slate-900">Connect WooCommerce Store</h3>
          <div className="grid grid-cols-2 gap-4">
            <input type="text" placeholder="Store Name" value={form.store_name} onChange={(e) => setForm({ ...form, store_name: e.target.value })} className="p-2 border border-slate-200 rounded-lg text-sm" required />
            <input type="url" placeholder="Store URL (https://example.com)" value={form.store_url} onChange={(e) => setForm({ ...form, store_url: e.target.value })} className="p-2 border border-slate-200 rounded-lg text-sm" required />
            <input type="text" placeholder="Consumer Key" value={form.consumer_key} onChange={(e) => setForm({ ...form, consumer_key: e.target.value })} className="p-2 border border-slate-200 rounded-lg text-sm" required />
            <input type="password" placeholder="Consumer Secret" value={form.consumer_secret} onChange={(e) => setForm({ ...form, consumer_secret: e.target.value })} className="p-2 border border-slate-200 rounded-lg text-sm" required />
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={connecting} className="px-4 py-2 bg-violet-600 text-white rounded-lg text-sm font-medium hover:bg-violet-700 disabled:opacity-50">
              {connecting ? <Loader2 className="w-4 h-4 animate-spin inline" /> : null} Connect & Verify
            </button>
            <button type="button" onClick={() => setShowConnect(false)} className="px-4 py-2 bg-slate-100 rounded-lg text-sm font-medium hover:bg-slate-200">Cancel</button>
          </div>
        </form>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {stores.map((store) => (
          <div key={store.id} className="p-4 bg-white rounded-xl border border-slate-200 hover:shadow-lg transition-all">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-bold text-slate-900">{store.store_name}</h3>
                <p className="text-xs text-slate-400">{store.store_url}</p>
              </div>
              <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full ${
                store.status === "connected" ? "bg-emerald-100 text-emerald-800" :
                store.status === "error" ? "bg-red-100 text-red-800" : "bg-slate-100 text-slate-600"
              }`}>{store.status}</span>
            </div>
            <div className="text-xs text-slate-500 space-y-1">
              <p>Version: {store.wc_version || "Unknown"}</p>
              <p>Last sync: {store.last_sync_at ? new Date(store.last_sync_at).toLocaleString() : "Never"}</p>
              <p>Webhooks: {store.webhooks_registered ? "✅ Registered" : "❌ Not registered"}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// PRODUCTS PAGE
// ═══════════════════════════════════════════════════════════════════

function ProductsPage({ storeId, searchQuery, onSync, syncLoading }: {
  storeId: string;
  searchQuery: string;
  onSync: (resource: string) => Promise<void>;
  syncLoading: string | null;
}) {
  const [products, setProducts] = useState<Array<{ id: string; name: string; sku: string | null; price: number; stock_quantity: number | null; stock_status: string; featured_image_url: string | null; status: string }>>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadProducts();
  }, [storeId, searchQuery]);

  const loadProducts = async () => {
    setLoading(true);
    try {
      const data = await productApi.list(storeId, { search: searchQuery || undefined, page_size: 50 });
      setProducts(data.items);
      setTotal(data.total);
    } catch (err) {
      console.error("Failed to load products:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-900">Products ({total})</h2>
        <button onClick={() => onSync("products")} disabled={syncLoading === "products"} className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white rounded-lg text-sm font-medium hover:bg-violet-700 disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${syncLoading === "products" ? "animate-spin" : ""}`} />
          {syncLoading === "products" ? "Syncing..." : "Sync Products"}
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-64"><Loader2 className="w-8 h-8 animate-spin text-violet-600" /></div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Product</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">SKU</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Price</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Stock</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {products.map((p) => (
                <tr key={p.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      {p.featured_image_url ? (
                        <img src={p.featured_image_url} alt="" className="w-10 h-10 rounded-lg object-cover bg-slate-100" />
                      ) : (
                        <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center"><Package className="w-4 h-4 text-slate-400" /></div>
                      )}
                      <span className="font-medium text-slate-900">{p.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-500">{p.sku || "-"}</td>
                  <td className="px-4 py-3 font-medium">${Number(p.price).toFixed(2)}</td>
                  <td className="px-4 py-3">
                    <span className={`font-medium ${(p.stock_quantity ?? 0) <= 0 ? "text-red-600" : (p.stock_quantity ?? 0) <= 10 ? "text-amber-600" : "text-slate-900"}`}>
                      {p.stock_quantity ?? "N/A"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full ${
                      p.stock_status === "instock" ? "bg-emerald-100 text-emerald-800" :
                      p.stock_status === "outofstock" ? "bg-red-100 text-red-800" : "bg-amber-100 text-amber-800"
                    }`}>{p.stock_status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// INVENTORY PAGE
// ═══════════════════════════════════════════════════════════════════

function InventoryPage({ storeId }: { storeId: string }) {
  const [lowStock, setLowStock] = useState<Array<{ product_name: string; sku: string | null; stock_quantity: number }>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadInventory();
  }, [storeId]);

  const loadInventory = async () => {
    try {
      const data = await inventoryApi.lowStock(storeId, { threshold: 10 });
      setLowStock(data.items);
    } catch (err) {
      console.error("Failed to load inventory:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-slate-900">Inventory Management</h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 bg-white rounded-xl border border-slate-200">
          <p className="text-xs text-slate-500">Low Stock Items</p>
          <p className="text-2xl font-bold text-amber-600">{lowStock.length}</p>
        </div>
        <div className="p-4 bg-white rounded-xl border border-slate-200">
          <p className="text-xs text-slate-500">Threshold</p>
          <p className="text-2xl font-bold text-slate-900">10</p>
        </div>
        <div className="p-4 bg-white rounded-xl border border-slate-200">
          <p className="text-xs text-slate-500">Status</p>
          <p className="text-sm font-bold text-emerald-600">● Monitoring Active</p>
        </div>
      </div>

      {loading ? <div className="flex justify-center p-8"><Loader2 className="w-6 h-6 animate-spin text-violet-600" /></div> : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b">
              <tr>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Product</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">SKU</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Stock</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {lowStock.length === 0 ? (
                <tr><td colSpan={3} className="px-4 py-8 text-center text-slate-400">No low stock items found</td></tr>
              ) : lowStock.map((item, i) => (
                <tr key={i} className="hover:bg-amber-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-slate-900">{item.product_name}</td>
                  <td className="px-4 py-3 text-slate-500">{item.sku || "-"}</td>
                  <td className="px-4 py-3"><span className="font-bold text-amber-700">{item.stock_quantity} remaining</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// ORDERS PAGE
// ═══════════════════════════════════════════════════════════════════

function OrdersPage({ storeId, searchQuery, onSync, syncLoading }: {
  storeId: string; searchQuery: string; onSync: (resource: string) => Promise<void>; syncLoading: string | null;
}) {
  const [orders, setOrders] = useState<Array<{ id: string; number: string; status: string; total: number; billing: { first_name: string; last_name: string } | null; created_at: string }>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadOrders(); }, [storeId]);

  const loadOrders = async () => {
    setLoading(true);
    try {
      const data = await orderApi.list(storeId, { page_size: 25 });
      setOrders(data.items);
    } catch (err) {
      console.error("Failed to load orders:", err);
    } finally { setLoading(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-900">Orders</h2>
        <button onClick={() => onSync("orders")} disabled={syncLoading === "orders"} className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white rounded-lg text-sm font-medium hover:bg-violet-700 disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${syncLoading === "orders" ? "animate-spin" : ""}`} /> Sync Orders
        </button>
      </div>
      {loading ? <div className="flex justify-center p-8"><Loader2 className="w-6 h-6 animate-spin text-violet-600" /></div> : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b">
              <tr>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Order</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Customer</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Status</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Total</th>
                <th className="px-4 py-3 text-left font-semibold text-slate-600">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {orders.map((o) => (
                <tr key={o.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-slate-900">{o.number}</td>
                  <td className="px-4 py-3 text-slate-500">{o.billing ? `${o.billing.first_name} ${o.billing.last_name}` : "-"}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full ${
                      o.status === "completed" ? "bg-emerald-100 text-emerald-800" :
                      o.status === "processing" ? "bg-blue-100 text-blue-800" :
                      o.status === "cancelled" ? "bg-red-100 text-red-800" : "bg-slate-100 text-slate-600"
                    }`}>{o.status}</span>
                  </td>
                  <td className="px-4 py-3 font-medium">${Number(o.total).toFixed(2)}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{new Date(o.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// CUSTOMERS PAGE
// ═══════════════════════════════════════════════════════════════════

function CustomersPage({ storeId, searchQuery, onSync, syncLoading }: {
  storeId: string; searchQuery: string; onSync: (resource: string) => Promise<void>; syncLoading: string | null;
}) {
  const [customers, setCustomers] = useState<Array<{ id: string; email: string; first_name: string | null; last_name: string | null; orders_count: number; total_spent: number }>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadCustomers(); }, [storeId]);

  const loadCustomers = async () => {
    setLoading(true);
    try {
      const data = await customerApi.list(storeId, { search: searchQuery || undefined, page_size: 25 });
      setCustomers(data.items);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-900">Customers</h2>
        <button onClick={() => onSync("customers")} disabled={syncLoading === "customers"} className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white rounded-lg text-sm font-medium hover:bg-violet-700 disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${syncLoading === "customers" ? "animate-spin" : ""}`} /> Sync Customers
        </button>
      </div>
      {loading ? <div className="flex justify-center p-8"><Loader2 className="w-6 h-6 animate-spin text-violet-600" /></div> : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b">
              <tr><th className="px-4 py-3 text-left font-semibold text-slate-600">Name</th><th className="px-4 py-3 text-left font-semibold text-slate-600">Email</th><th className="px-4 py-3 text-left font-semibold text-slate-600">Orders</th><th className="px-4 py-3 text-left font-semibold text-slate-600">Total Spent</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {customers.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-slate-900">{c.first_name || ""} {c.last_name || ""}</td>
                  <td className="px-4 py-3 text-slate-500">{c.email}</td>
                  <td className="px-4 py-3">{c.orders_count}</td>
                  <td className="px-4 py-3 font-medium">${Number(c.total_spent).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// CATEGORIES PAGE
// ═══════════════════════════════════════════════════════════════════

function CategoriesPage({ storeId, onSync, syncLoading }: { storeId: string; onSync: (resource: string) => Promise<void>; syncLoading: string | null }) {
  const [categories, setCategories] = useState<Array<{ id: string; name: string; slug: string; product_count: number }>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadCategories(); }, [storeId]);

  const loadCategories = async () => {
    try {
      const data = await categoryApi.list(storeId);
      setCategories(data.items);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-900">Categories</h2>
        <button onClick={() => onSync("categories")} disabled={syncLoading === "categories"} className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white rounded-lg text-sm font-medium hover:bg-violet-700 disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${syncLoading === "categories" ? "animate-spin" : ""}`} /> Sync Categories
        </button>
      </div>
      {loading ? <div className="flex justify-center p-8"><Loader2 className="w-6 h-6 animate-spin text-violet-600" /></div> : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {categories.map((c) => (
            <div key={c.id} className="p-4 bg-white rounded-xl border border-slate-200 hover:shadow-lg transition-all">
              <h3 className="font-bold text-slate-900">{c.name}</h3>
              <p className="text-xs text-slate-400">{c.slug}</p>
              <p className="text-xs text-slate-500 mt-2">{c.product_count} products</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// COUPONS PAGE
// ═══════════════════════════════════════════════════════════════════

function CouponsPage({ storeId, onSync, syncLoading }: { storeId: string; onSync: (resource: string) => Promise<void>; syncLoading: string | null }) {
  const [coupons, setCoupons] = useState<Array<{ id: string; code: string; amount: number; discount_type: string; usage_count: number; date_expires: string | null }>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadCoupons(); }, [storeId]);

  const loadCoupons = async () => {
    try {
      const data = await couponApi.list(storeId);
      setCoupons(data.items);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-slate-900">Coupons</h2>
        <button onClick={() => onSync("coupons")} disabled={syncLoading === "coupons"} className="flex items-center gap-2 px-4 py-2 bg-violet-600 text-white rounded-lg text-sm font-medium hover:bg-violet-700 disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${syncLoading === "coupons" ? "animate-spin" : ""}`} /> Sync Coupons
        </button>
      </div>
      {loading ? <div className="flex justify-center p-8"><Loader2 className="w-6 h-6 animate-spin text-violet-600" /></div> : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b">
              <tr><th className="px-4 py-3 text-left font-semibold text-slate-600">Code</th><th className="px-4 py-3 text-left font-semibold text-slate-600">Type</th><th className="px-4 py-3 text-left font-semibold text-slate-600">Amount</th><th className="px-4 py-3 text-left font-semibold text-slate-600">Usage</th><th className="px-4 py-3 text-left font-semibold text-slate-600">Expires</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {coupons.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-violet-700">{c.code}</td>
                  <td className="px-4 py-3 text-slate-500">{c.discount_type}</td>
                  <td className="px-4 py-3 font-medium">{c.discount_type === "percent" ? `${c.amount}%` : `$${c.amount}`}</td>
                  <td className="px-4 py-3">{c.usage_count}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">{c.date_expires ? new Date(c.date_expires).toLocaleDateString() : "Never"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// ALERTS PAGE
// ═══════════════════════════════════════════════════════════════════

function AlertsPage({ storeId }: { storeId: string }) {
  const [alerts, setAlerts] = useState<Array<{ id: string; alert_type: string; severity: string; title: string; message: string; is_read: boolean; created_at: string }>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadAlerts(); }, [storeId]);

  const loadAlerts = async () => {
    try {
      const data = await alertApi.list(storeId, { unresolved_only: true });
      setAlerts(data.items);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  const markRead = async (ids: string[]) => {
    try {
      await alertApi.mark(storeId, { alert_ids: ids, mark_as_read: true });
      loadAlerts();
    } catch (err) { console.error(err); }
  };

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold text-slate-900">Alerts</h2>
      {loading ? <div className="flex justify-center p-8"><Loader2 className="w-6 h-6 animate-spin text-violet-600" /></div> : (
        <div className="space-y-3">
          {alerts.length === 0 ? <p className="text-sm text-slate-400 p-4 bg-white rounded-xl border">No unresolved alerts</p> : alerts.map((a) => (
            <div key={a.id} className={`p-4 rounded-xl border transition-all ${a.severity === "critical" ? "bg-red-50 border-red-200" : a.severity === "warning" ? "bg-amber-50 border-amber-200" : "bg-blue-50 border-blue-200"}`}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`px-2 py-0.5 text-[10px] font-bold rounded-full ${
                      a.severity === "critical" ? "bg-red-200 text-red-800" :
                      a.severity === "warning" ? "bg-amber-200 text-amber-800" : "bg-blue-200 text-blue-800"
                    }`}>{a.severity}</span>
                    <span className="text-xs text-slate-400">{a.alert_type}</span>
                  </div>
                  <h3 className="font-bold text-slate-900">{a.title}</h3>
                  <p className="text-sm text-slate-600 mt-1">{a.message}</p>
                  <p className="text-xs text-slate-400 mt-2">{new Date(a.created_at).toLocaleString()}</p>
                </div>
                {!a.is_read && (
                  <button onClick={() => markRead([a.id])} className="px-3 py-1 bg-white border border-slate-200 rounded-lg text-xs font-medium hover:bg-slate-50">Dismiss</button>
                )}
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

function SettingsPage({ storeId }: { storeId: string }) {
  const [settings, setSettings] = useState<{
    auto_sync_enabled: boolean; sync_interval_hours: number;
    sync_products: boolean; sync_orders: boolean; sync_customers: boolean;
    sync_categories: boolean; sync_coupons: boolean;
    low_stock_threshold: number; low_stock_alerts: boolean;
    sync_failure_alerts: boolean; email_alerts: boolean; alert_email: string | null;
    retention_days: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => { loadSettings(); }, [storeId]);

  const loadSettings = async () => {
    try {
      const data = await settingsApi.get(storeId);
      setSettings(data as typeof settings);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    try {
      await settingsApi.update(storeId, settings);
    } catch (err) { console.error(err); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="flex justify-center p-8"><Loader2 className="w-6 h-6 animate-spin text-violet-600" /></div>;
  if (!settings) return <p className="text-slate-400">No settings found</p>;

  return (
    <div className="max-w-2xl space-y-6">
      <h2 className="text-xl font-bold text-slate-900">Store Settings</h2>

      <div className="p-6 bg-white rounded-xl border border-slate-200 space-y-6">
        <section>
          <h3 className="text-sm font-bold text-slate-900 mb-3">Synchronization</h3>
          <div className="space-y-3">
            <Toggle label="Auto Sync" value={settings.auto_sync_enabled} onChange={(v) => setSettings({ ...settings, auto_sync_enabled: v })} />
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-700">Sync Interval (hours)</span>
              <input type="number" value={settings.sync_interval_hours} onChange={(e) => setSettings({ ...settings, sync_interval_hours: parseInt(e.target.value) })} className="w-20 p-1.5 border border-slate-200 rounded-lg text-sm text-center" min={1} max={168} />
            </div>
          </div>
        </section>

        <section>
          <h3 className="text-sm font-bold text-slate-900 mb-3">Resources to Sync</h3>
          <div className="space-y-2">
            <Toggle label="Products" value={settings.sync_products} onChange={(v) => setSettings({ ...settings, sync_products: v })} />
            <Toggle label="Orders" value={settings.sync_orders} onChange={(v) => setSettings({ ...settings, sync_orders: v })} />
            <Toggle label="Customers" value={settings.sync_customers} onChange={(v) => setSettings({ ...settings, sync_customers: v })} />
            <Toggle label="Categories" value={settings.sync_categories} onChange={(v) => setSettings({ ...settings, sync_categories: v })} />
            <Toggle label="Coupons" value={settings.sync_coupons} onChange={(v) => setSettings({ ...settings, sync_coupons: v })} />
          </div>
        </section>

        <section>
          <h3 className="text-sm font-bold text-slate-900 mb-3">Alerts</h3>
          <div className="space-y-3">
            <Toggle label="Low Stock Alerts" value={settings.low_stock_alerts} onChange={(v) => setSettings({ ...settings, low_stock_alerts: v })} />
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-700">Low Stock Threshold</span>
              <input type="number" value={settings.low_stock_threshold} onChange={(e) => setSettings({ ...settings, low_stock_threshold: parseInt(e.target.value) })} className="w-20 p-1.5 border border-slate-200 rounded-lg text-sm text-center" min={0} />
            </div>
            <Toggle label="Sync Failure Alerts" value={settings.sync_failure_alerts} onChange={(v) => setSettings({ ...settings, sync_failure_alerts: v })} />
            <Toggle label="Email Alerts" value={settings.email_alerts} onChange={(v) => setSettings({ ...settings, email_alerts: v })} />
            {settings.email_alerts && (
              <input type="email" placeholder="alert@example.com" value={settings.alert_email || ""} onChange={(e) => setSettings({ ...settings, alert_email: e.target.value })} className="w-full p-2 border border-slate-200 rounded-lg text-sm" />
            )}
          </div>
        </section>

        <section>
          <h3 className="text-sm font-bold text-slate-900 mb-3">Data Retention</h3>
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-700">Retention Period (days)</span>
            <input type="number" value={settings.retention_days} onChange={(e) => setSettings({ ...settings, retention_days: parseInt(e.target.value) })} className="w-20 p-1.5 border border-slate-200 rounded-lg text-sm text-center" min={1} max={365} />
          </div>
        </section>

        <button onClick={handleSave} disabled={saving} className="w-full py-2.5 bg-violet-600 text-white rounded-lg font-medium hover:bg-violet-700 transition-all disabled:opacity-50">
          {saving ? <><Loader2 className="w-4 h-4 animate-spin inline" /> Saving...</> : "💾 Save Settings"}
        </button>
      </div>
    </div>
  );
}

// ─── Toggle Component ───

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-slate-700">{label}</span>
      <button
        onClick={() => onChange(!value)}
        className={`w-10 h-5 rounded-full transition-all ${value ? "bg-violet-600" : "bg-slate-300"}`}
      >
        <div className={`w-4 h-4 bg-white rounded-full shadow-sm transform transition-all ${value ? "translate-x-5" : "translate-x-0.5"} mt-0.5`} />
      </button>
    </div>
  );
}
