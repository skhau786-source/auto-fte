/**
 * API Service Layer for Digital FTE WooCommerce Integration.
 *
 * Provides typed API functions for all WooCommerce operations.
 * Uses Axios for HTTP requests with JWT authentication interceptors.
 */

import axios, { AxiosInstance, AxiosRequestConfig, AxiosError } from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Create configured Axios instance with auth interceptor.
 * Backend routes are mounted at: /auth, /woocommerce, /woocommerce/webhooks, etc.
 * No /api prefix is added because FastAPI routers don't use one.
 */
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
});

// ─── Token helpers ───

export const tokenStore = {
  get: (): string | null =>
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null,
  set: (token: string): void => {
    if (typeof window !== "undefined") localStorage.setItem("access_token", token);
  },
  clear: (): void => {
    if (typeof window !== "undefined") localStorage.removeItem("access_token");
  },
};

/** True when an error is a 401 — the session expired or the token is invalid. */
export function isUnauthorized(err: unknown): boolean {
  return (
    (err as { status?: number })?.status === 401 ||
    (err as { response?: { status?: number } })?.response?.status === 401
  );
}

// Request interceptor: attach JWT token
apiClient.interceptors.request.use((config) => {
  const token = tokenStore.get();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: standardized error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: unknown; message?: string }>) => {
    // Expired/invalid session — drop the token and notify the app so it
    // can redirect to the login screen.
    if (error.response?.status === 401) {
      tokenStore.clear();
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("auth:unauthorized"));
      }
    }
    // Backend errors come in two shapes: a plain string detail (auth) or a
    // { message, error_code } object (inventory/woocommerce/shopify).
    const rawDetail = error.response?.data?.detail;
    const detailMessage =
      typeof rawDetail === "string"
        ? rawDetail
        : (rawDetail as { message?: string } | undefined)?.message;
    const message =
      detailMessage || error.response?.data?.message || error.message || "An unexpected error occurred";
    // Keep the HTTP status and machine error code so callers can react
    // to 401s and to specific business states (e.g. no store connected).
    const err = new Error(message) as Error & { status?: number; errorCode?: string };
    err.status = error.response?.status;
    err.errorCode = (rawDetail as { error_code?: string } | undefined)?.error_code;
    return Promise.reject(err);
  }
);

type ApiParams = Record<string, string | number | boolean | undefined>;

async function apiGet<T>(path: string, params?: ApiParams): Promise<T> {
  const config: AxiosRequestConfig = {};
  if (params) {
    // Remove undefined values
    const cleanParams: Record<string, string | number | boolean> = {};
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "") cleanParams[k] = v;
    });
    config.params = cleanParams;
  }
  const response = await apiClient.get<T>(path, config);
  return response.data;
}

async function apiPost<T>(path: string, data?: unknown): Promise<T> {
  const response = await apiClient.post<T>(path, data);
  return response.data;
}

async function apiPut<T>(path: string, data?: unknown): Promise<T> {
  const response = await apiClient.put<T>(path, data);
  return response.data;
}

async function apiDelete<T>(path: string): Promise<T> {
  const response = await apiClient.delete<T>(path);
  return response.data;
}

// ─── Auth ───

export interface AuthUser {
  id: string;
  username: string;
  email: string;
  full_name: string | null;
  auth_provider: string;
  is_verified: boolean;
  created_at: string;
}

export interface AuthResponse {
  message: string;
  user: AuthUser;
  access_token: string | null;
  token_type: string;
}

export interface SignupRequest {
  username: string;
  email: string;
  password: string;
  full_name?: string;
}

export const authApi = {
  login: (email: string, password: string) =>
    apiPost<AuthResponse>("/auth/login", { email, password }),
  signup: (data: SignupRequest) => apiPost<AuthResponse>("/auth/signup", data),
  google: (idToken: string) => apiPost<AuthResponse>("/auth/google", { id_token: idToken }),
  me: () => apiGet<AuthResponse>("/auth/me"),
};

// ─── WooCommerce Stores ───

export interface WooCommerceStore {
  id: string;
  store_name: string;
  store_url: string;
  status: "connected" | "disconnected" | "error" | "pending_verification";
  is_active: boolean;
  wc_version: string | null;
  last_sync_at: string | null;
  webhooks_registered: boolean;
  created_at: string;
  updated_at: string;
}

export interface StoreConnectRequest {
  store_name: string;
  store_url: string;
  consumer_key: string;
  consumer_secret: string;
}

export const storeApi = {
  list: () => apiGet<{ items: WooCommerceStore[]; total: number }>("/woocommerce/stores"),
  get: (id: string) => apiGet<WooCommerceStore>(`/woocommerce/stores/${id}`),
  connect: (data: StoreConnectRequest) =>
    apiPost<{ message: string; store: WooCommerceStore; verification: unknown }>(
      "/woocommerce/stores/connect", data
    ),
  update: (id: string, data: Partial<StoreConnectRequest>) =>
    apiPut<WooCommerceStore>(`/woocommerce/stores/${id}`, data),
  disconnect: (id: string) => apiDelete<{ message: string }>(`/woocommerce/stores/${id}`),
  verify: (id: string) =>
    apiPost<{ status: string; store_url: string; api_version: string }>(
      `/woocommerce/stores/${id}/verify`
    ),
};

// ─── WooCommerce Products ───

export interface WooCommerceProduct {
  id: string;
  store_id: string;
  wc_product_id: number;
  type: string;
  name: string;
  slug: string | null;
  sku: string | null;
  price: number;
  regular_price: number;
  sale_price: number | null;
  on_sale: boolean;
  featured_image_url: string | null;
  manage_stock: boolean;
  stock_quantity: number | null;
  stock_status: "instock" | "outofstock" | "onbackorder";
  total_sales: number;
  average_rating: string;
  status: string;
  category_ids: number[] | null;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProductListResponse {
  items: WooCommerceProduct[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export const productApi = {
  list: (storeId: string, params?: {
    page?: number; page_size?: number; search?: string;
    status?: string; stock_status?: string; category_id?: number;
    low_stock_only?: boolean; sort_by?: string; sort_order?: string;
  }) => apiGet<ProductListResponse>(`/woocommerce/stores/${storeId}/products`, params as Record<string, string | number | boolean | undefined>),
  get: (storeId: string, productId: string) =>
    apiGet<WooCommerceProduct>(`/woocommerce/stores/${storeId}/products/${productId}`),
  sync: (storeId: string, forceFull = false) =>
    apiPost<{ created: number; updated: number; failed: number; message: string }>(
      `/woocommerce/stores/${storeId}/products/sync`, { force_full: forceFull }
    ),
};

// ─── WooCommerce Orders ───

export interface WooCommerceOrder {
  id: string;
  store_id: string;
  wc_order_id: number;
  number: string;
  status: string;
  currency: string;
  customer_id: number;
  billing: Record<string, unknown> | null;
  shipping: Record<string, unknown> | null;
  payment_method_title: string | null;
  total: number;
  items: WooCommerceOrderItem[];
  created_at: string;
  updated_at: string;
}

export interface WooCommerceOrderItem {
  id: string;
  wc_order_item_id: number;
  wc_product_id: number;
  name: string;
  sku: string | null;
  quantity: number;
  price: number;
  total: number;
}

export const orderApi = {
  list: (storeId: string, params?: {
    page?: number; page_size?: number; status?: string;
    search?: string; sort_by?: string; sort_order?: string;
  }) => apiGet<{ items: WooCommerceOrder[]; total: number; page: number; page_size: number; total_pages: number }>(
    `/woocommerce/stores/${storeId}/orders`, params as Record<string, string | number | boolean | undefined>
  ),
  get: (storeId: string, orderId: string) =>
    apiGet<WooCommerceOrder>(`/woocommerce/stores/${storeId}/orders/${orderId}`),
  sync: (storeId: string, dateAfter?: string, status?: string) =>
    apiPost<{ created: number; updated: number; failed: number; sync_id: string }>(
      `/woocommerce/stores/${storeId}/orders/sync`, { date_after: dateAfter, status }
    ),
};

// ─── WooCommerce Customers ───

export interface WooCommerceCustomer {
  id: string;
  wc_customer_id: number;
  email: string;
  first_name: string | null;
  last_name: string | null;
  orders_count: number;
  total_spent: number;
  created_at: string;
}

export const customerApi = {
  list: (storeId: string, params?: { page?: number; page_size?: number; search?: string }) =>
    apiGet<{ items: WooCommerceCustomer[]; total: number }>(
      `/woocommerce/stores/${storeId}/customers`, params as Record<string, string | number | boolean | undefined>
    ),
  sync: (storeId: string) =>
    apiPost<{ created: number; updated: number; failed: number; sync_id: string }>(
      `/woocommerce/stores/${storeId}/customers/sync`
    ),
};

// ─── WooCommerce Categories ───

export interface WooCommerceCategory {
  id: string;
  wc_category_id: number;
  name: string;
  slug: string;
  description: string | null;
  parent_id: string | null;
  product_count: number;
  children?: WooCommerceCategory[];
}

export const categoryApi = {
  list: (storeId: string) =>
    apiGet<{ items: WooCommerceCategory[]; total: number }>(`/woocommerce/stores/${storeId}/categories`),
  tree: (storeId: string) =>
    apiGet<WooCommerceCategory[]>(`/woocommerce/stores/${storeId}/categories/tree`),
  sync: (storeId: string) =>
    apiPost<{ created: number; updated: number; sync_id: string }>(
      `/woocommerce/stores/${storeId}/categories/sync`
    ),
};

// ─── WooCommerce Coupons ───

export interface WooCommerceCoupon {
  id: string;
  wc_coupon_id: number;
  code: string;
  amount: number;
  discount_type: string;
  description: string | null;
  date_expires: string | null;
  usage_count: number;
  free_shipping: boolean;
  minimum_amount: string | null;
}

export const couponApi = {
  list: (storeId: string, params?: { page?: number; page_size?: number }) =>
    apiGet<{ items: WooCommerceCoupon[]; total: number }>(
      `/woocommerce/stores/${storeId}/coupons`, params as Record<string, string | number | boolean | undefined>
    ),
  sync: (storeId: string) =>
    apiPost<{ created: number; updated: number; failed: number; sync_id: string }>(
      `/woocommerce/stores/${storeId}/coupons/sync`
    ),
};

// ─── WooCommerce Inventory ───

export interface InventoryAdjustRequest {
  wc_product_id: number;
  quantity_change: number;
  reason?: string;
}

export const inventoryApi = {
  adjust: (storeId: string, data: InventoryAdjustRequest) =>
    apiPost<{ product_id: string; wc_product_id: number; quantity_before: number; quantity_after: number; message: string }>(
      `/woocommerce/stores/${storeId}/inventory/adjust`, data
    ),
  lowStock: (storeId: string, params?: { threshold?: number; page?: number; page_size?: number }) =>
    apiGet<{ items: Array<{ product_id: string; wc_product_id: number; product_name: string; sku: string | null; stock_quantity: number; low_stock_threshold: number }>; total: number }>(
      `/woocommerce/stores/${storeId}/inventory/low-stock`, params as Record<string, string | number | boolean | undefined>
    ),
  history: (storeId: string, params?: { product_id?: string; action?: string; page?: number; page_size?: number }) =>
    apiGet<{ items: unknown[]; total: number }>(
      `/woocommerce/stores/${storeId}/inventory/history`, params as Record<string, string | number | boolean | undefined>
    ),
};

// ─── WooCommerce Dashboard ───

export interface DashboardData {
  stats: {
    total_products: number;
    total_orders: number;
    total_customers: number;
    total_revenue: number;
    low_stock_count: number;
    out_of_stock_count: number;
    active_alerts: number;
    last_sync_at: string | null;
    sync_status: string;
  };
  recent_orders: WooCommerceOrder[];
  low_stock_items: Array<{
    product_id: string;
    wc_product_id: number;
    product_name: string;
    sku: string | null;
    stock_quantity: number;
  }>;
  recent_alerts: Array<{
    id: string;
    alert_type: string;
    severity: string;
    title: string;
    message: string;
    created_at: string;
  }>;
  recent_syncs: Array<{
    id: string;
    resource: string;
    status: string;
    created_items: number;
    updated_items: number;
    failed_items: number;
    created_at: string;
  }>;
}

export const dashboardApi = {
  get: (storeId: string) =>
    apiGet<DashboardData>(`/woocommerce/stores/${storeId}/dashboard`),
};

// ─── Analytics (Revenue Dashboard / Advanced Analytics) ───

export interface RevenueTrendPoint {
  date: string;
  revenue: number;
  orders: number;
}

export interface RevenueAnalytics {
  period_days: number;
  period_start: string;
  period_end: string;
  revenue: number;
  orders: number;
  average_order_value: number;
  previous_period_revenue: number;
  previous_period_orders: number;
  revenue_change_pct: number | null;
  order_change_pct: number | null;
  trend: RevenueTrendPoint[];
}

export interface TopProduct {
  wc_product_id: number;
  name: string;
  sku: string | null;
  revenue: number;
  units_sold: number;
}

export interface OrderStatusCount {
  status: string;
  count: number;
}

export interface OrderStatusBreakdown {
  period_days: number;
  breakdown: OrderStatusCount[];
}

export const analyticsApi = {
  getRevenue: (storeId: string, days = 30) =>
    apiGet<RevenueAnalytics>(`/woocommerce/stores/${storeId}/analytics/revenue`, { days }),
  getTopProducts: (storeId: string, days = 30, limit = 10) =>
    apiGet<{ products: TopProduct[] }>(`/woocommerce/stores/${storeId}/analytics/top-products`, { days, limit }),
  getOrderStatusBreakdown: (storeId: string, days = 30) =>
    apiGet<OrderStatusBreakdown>(`/woocommerce/stores/${storeId}/analytics/order-status`, { days }),
};

// ─── WooCommerce Settings ───

export interface StoreSettings {
  id: string;
  store_id: string;
  auto_sync_enabled: boolean;
  sync_interval_hours: number;
  sync_products: boolean;
  sync_orders: boolean;
  sync_customers: boolean;
  sync_categories: boolean;
  sync_coupons: boolean;
  low_stock_threshold: number;
  low_stock_alerts: boolean;
  sync_failure_alerts: boolean;
  email_alerts: boolean;
  alert_email: string | null;
  retention_days: number;
}

export const settingsApi = {
  get: (storeId: string) =>
    apiGet<StoreSettings>(`/woocommerce/stores/${storeId}/settings`),
  update: (storeId: string, data: Partial<StoreSettings>) =>
    apiPut<StoreSettings>(`/woocommerce/stores/${storeId}/settings`, data),
};

// ─── WooCommerce Alerts ───

export const alertApi = {
  list: (storeId: string, params?: { page?: number; page_size?: number; unread_only?: boolean; unresolved_only?: boolean }) =>
    apiGet<{ items: Array<{ id: string; alert_type: string; severity: string; title: string; message: string; is_read: boolean; created_at: string }>; total: number; unread_count: number }>(
      `/woocommerce/stores/${storeId}/alerts`, params as Record<string, string | number | boolean | undefined>
    ),
  mark: (storeId: string, data: { alert_ids: string[]; mark_as_read?: boolean; mark_as_resolved?: boolean }) =>
    apiPost<{ message: string }>(`/woocommerce/stores/${storeId}/alerts/mark`, data),
};

// ─── WooCommerce Webhooks ───

export const webhookApi = {
  register: (storeId: string, callbackUrl: string) =>
    apiPost<{ message: string; results: unknown[]; total: number; succeeded: number; failed: number }>(
      `/woocommerce/stores/${storeId}/webhooks/register?callback_url=${encodeURIComponent(callbackUrl)}`
    ),
};

// ─── Shopify (business-facing connection status only) ───

export interface ShopifyStatus {
  connected: boolean;
  shopify_domain: string | null;
  shopify_store_id: number | null;
  shopify_location_id: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ShopifyInventorySnapshot {
  total_products: number;
  total_variants: number;
  total_inventory_units: number;
  total_inventory_value: string;
  low_stock_count: number;
  out_of_stock_count: number;
  pending_syncs: number;
  failed_syncs: number;
  last_sync_at: string | null;
  last_sync_status: string | null;
}

export const shopifyApi = {
  /** Connection status of the authenticated user's Shopify store. */
  status: () => apiGet<ShopifyStatus>("/shopify/status"),
  /** Aggregate inventory snapshot for the Shopify store. */
  inventory: () => apiGet<ShopifyInventorySnapshot>("/shopify/inventory"),
  /** Connect a Shopify store (domain + access token from the Shopify admin). */
  connect: (data: { shop_domain: string; access_token: string }) =>
    apiPost<{ message: string; store: unknown; verification: unknown }>("/shopify/connect", data),
  /** Trigger a product/inventory update from Shopify. */
  sync: () => apiPost<{ status: string; store_id: string; results: unknown }>("/shopify/sync"),
};

// ─── Core Inventory (store-scoped) ───

export interface InventoryVariant {
  id: string;
  product_id: string;
  shopify_variant_id: number | null;
  shopify_inventory_item_id: number | null;
  title: string;
  sku: string | null;
  barcode: string | null;
  price: number;
  compare_at_price: number | null;
  inventory_quantity: number;
  requires_shipping: boolean;
  low_stock_threshold: number | null;
  created_at: string;
  updated_at: string;
}

export interface InventoryProduct {
  id: string;
  store_id: string;
  category_id: string | null;
  shopify_product_id: number | null;
  title: string;
  description: string | null;
  vendor: string | null;
  product_type: string | null;
  status: string;
  featured_image_url: string | null;
  created_at: string;
  updated_at: string;
  last_synced_at: string | null;
  variants: InventoryVariant[];
}

export interface InventoryListResponse {
  items: InventoryProduct[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface InventoryProductCreate {
  title: string;
  description?: string;
  vendor?: string;
  product_type?: string;
  status?: "active" | "archived" | "draft";
  featured_image_url?: string;
  variants?: {
    title: string;
    sku?: string;
    price?: number;
    inventory_quantity?: number;
    low_stock_threshold?: number;
  }[];
}

export interface StockAdjustRequest {
  variant_id: string;
  quantity_change: number;
  reason?: string;
}

export interface StockAdjustResponse {
  variant_id: string;
  quantity_before: number;
  quantity_after: number;
  quantity_change: number;
  transaction_id: string;
  synced_to_shopify: boolean;
  message: string;
}

export interface InventoryTransaction {
  id: string;
  variant_id: string;
  transaction_type: string;
  quantity_change: number;
  quantity_before: number;
  quantity_after: number;
  reason: string | null;
  reference_id: string | null;
  performed_by: string | null;
  synced_to_shopify: boolean;
  created_at: string;
}

export interface InventoryHistoryResponse {
  items: InventoryTransaction[];
  total: number;
  page: number;
  page_size: number;
}

export interface LowStockItem {
  variant_id: string;
  variant_title: string;
  sku: string | null;
  product_title: string;
  product_id: string;
  inventory_quantity: number;
  low_stock_threshold: number;
  days_until_out: number | null;
}

export interface LowStockResponse {
  items: LowStockItem[];
  total: number;
}

export interface StoreAggregation {
  store_id: string;
  total_available_inventory: number;
  total_reserved_inventory: number;
  inventory_value: number;
  product_count: number;
  variant_count: number;
  low_stock_variant_count: number;
  out_of_stock_variant_count: number;
  active_reservations_count: number;
  generated_at: string;
}

export interface AggregationDashboard {
  total_available_inventory: number;
  total_reserved_inventory: number;
  inventory_value: number;
  low_stock_variants: number;
  out_of_stock_variants: number;
  active_reservations: number;
  product_count: number;
  variant_count: number;
  store_id: string;
}

export interface VariantAggregation {
  variant_id: string;
  product_id: string;
  sku: string | null;
  title: string;
  available_quantity: number;
  reserved_quantity: number;
  committed_quantity: number;
  total_quantity: number;
  low_stock_threshold: number;
  status: "in_stock" | "low_stock" | "out_of_stock";
  inventory_value: number;
}

export interface ProductAggregation {
  product_id: string;
  title: string;
  store_id: string;
  total_available_inventory: number;
  total_reserved_inventory: number;
  total_committed_inventory: number;
  inventory_value: number;
  variant_count: number;
  variants: {
    variant_id: string;
    title: string;
    sku: string | null;
    available_quantity: number;
    reserved_quantity: number;
    inventory_value: number;
  }[];
}

/** Core inventory management client — products, stock, aggregation. */
export const coreInventoryApi = {
  list: (params?: Record<string, string | number | boolean | undefined>) =>
    apiGet<InventoryListResponse>("/inventory", params),
  get: (productId: string) => apiGet<InventoryProduct>(`/inventory/${productId}`),
  create: (data: InventoryProductCreate) => apiPost<InventoryProduct>("/inventory", data),
  adjust: (data: StockAdjustRequest) => apiPost<StockAdjustResponse>("/inventory/update-stock", data),
  lowStock: (params?: Record<string, string | number | boolean | undefined>) =>
    apiGet<LowStockResponse>("/inventory/low-stock", params),
  history: (params?: Record<string, string | number | boolean | undefined>) =>
    apiGet<InventoryHistoryResponse>("/inventory/history", params),
  aggregate: {
    store: () => apiGet<StoreAggregation>("/inventory/aggregate/store"),
    dashboard: () => apiGet<AggregationDashboard>("/inventory/aggregate/dashboard"),
    product: (productId: string) =>
      apiGet<ProductAggregation>(`/inventory/aggregate/product/${productId}`),
    variant: (variantId: string) =>
      apiGet<VariantAggregation>(`/inventory/aggregate/variant/${variantId}`),
    reports: () => apiGet<Record<string, unknown>>("/inventory/aggregate/reports"),
  },
};

// ─── Reservations ───

export interface Reservation {
  id: string;
  store_id: string;
  product_id: string;
  variant_id: string;
  order_id: string | null;
  order_source: string | null;
  quantity: number;
  status: string;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
  released_at: string | null;
  committed_at: string | null;
  metadata: Record<string, unknown> | null;
}

export interface ReservationListResponse {
  items: Reservation[];
  total: number;
  page: number;
  page_size: number;
  active_count: number;
}

export interface ReservationActionResponse {
  reservation_id: string;
  status: string;
  quantity: number;
  message: string;
}

export const reservationApi = {
  list: (params?: Record<string, string | number | boolean | undefined>) =>
    apiGet<ReservationListResponse>("/reservations", params),
  create: (data: { variant_id: string; quantity: number; order_id?: string; order_source?: string; expires_in_minutes?: number; reason?: string }) =>
    apiPost<Reservation>("/reservations", data),
  commit: (id: string) => apiPost<ReservationActionResponse>(`/reservations/${id}/commit`),
  release: (id: string, quantity?: number) =>
    apiPost<ReservationActionResponse>(`/reservations/${id}/release`, quantity ? { quantity } : undefined),
  cancel: (id: string) => apiDelete<ReservationActionResponse>(`/reservations/${id}`),
  dashboard: () => apiGet<Record<string, unknown>>("/reservations/dashboard"),
};

// ─── Allocations ───

export interface AllocationSettings {
  store_id: string;
  auto_allocate_inventory: boolean;
  allocation_strategy: string;
  allow_negative_stock: boolean;
  reserve_stock_on_order: boolean;
  auto_release_cancelled_orders: boolean;
  active_strategy: string;
  available_strategies: { name: string; description?: string }[];
}

export interface AllocationSettingsUpdate {
  auto_allocate_inventory?: boolean;
  allocation_strategy?: string;
  allow_negative_stock?: boolean;
  reserve_stock_on_order?: boolean;
  auto_release_cancelled_orders?: boolean;
}

export const allocationApi = {
  settings: () => apiGet<AllocationSettings>("/allocation/settings"),
  updateSettings: (data: AllocationSettingsUpdate) =>
    apiPut<AllocationSettings>("/allocation/settings", data),
  dashboard: () => apiGet<Record<string, unknown>>("/allocation/dashboard"),
};

// ─── Unified dashboard ───

export interface UnifiedDashboard {
  store_id: string;
  generated_at: string;
  inventory: {
    total_products: number;
    total_variants: number;
    total_inventory_units: number;
    total_inventory_value: number;
    low_stock_count: number;
    out_of_stock_count: number;
    category_count: number;
  };
  reservation: {
    active_reservations: number;
    reserved_stock_units: number;
    expired_today: number;
    reservation_success_rate: number;
    reservations_by_source: Record<string, number>;
  };
  allocation: {
    allocation_strategy: string;
    total_allocated_units: number;
    active_reservations: number;
    orders_allocated: number;
    allocation_success_rate: number;
  };
  order_integration: {
    orders_waiting_allocation: number;
    reserved_orders: number;
    partially_fulfilled_orders: number;
    committed_orders: number;
    released_reservations: number;
    allocation_success_rate: number;
    reservation_success_rate: number;
  };
  aggregation: {
    total_available_inventory: number;
    total_reserved_inventory: number;
    inventory_value: number;
    low_stock_variants: number;
    out_of_stock_variants: number;
    active_reservations_count: number;
  };
}

export const unifiedApi = {
  get: () => apiGet<UnifiedDashboard>("/dashboard/unified"),
};

// ─── AI Agents ───

export interface AIAgent {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  agent_type: string;
  status: string;
  config: Record<string, unknown> | null;
  granted_permissions: string[] | null;
  is_active: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  task_count: number;
  active_task_count: number;
}

export interface AIAgentListResponse {
  items: AIAgent[];
  total: number;
}

export interface AITask {
  id: string;
  agent_id: string;
  organization_id: string;
  task_type: string;
  status: string;
  input_data: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  error_message: string | null;
  requires_human_approval: boolean;
  approved_by: string | null;
  approved_at: string | null;
  rejection_reason: string | null;
  submitted_by: string | null;
  execution_started_at: string | null;
  execution_completed_at: string | null;
  execution_duration_ms: number | null;
  llm_provider: string | null;
  llm_model: string | null;
  llm_tokens_used: number | null;
  parent_task_id: string | null;
  source_agent_id: string | null;
  target_agent_id: string | null;
  capability_name: string | null;
  handoff_depth: number;
  metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface AITaskListResponse {
  items: AITask[];
  total: number;
  pending_approval_count: number;
}

export interface AIAgentAction {
  id: string;
  agent_id: string | null;
  team_id: string | null;
  task_id: string | null;
  organization_id: string;
  action_type: string;
  target_resource: string | null;
  target_id: string | null;
  result_status: string;
  details: Record<string, unknown> | null;
  performed_by: string | null;
  created_at: string;
}

export const agentApi = {
  // Agent CRUD
  list: () => apiGet<AIAgentListResponse>("/ai/agents"),
  get: (id: string) => apiGet<AIAgent>(`/ai/agents/${id}`),
  create: (data: { name: string; agent_type?: string; description?: string; config?: Record<string, unknown> }) =>
    apiPost<AIAgent>("/ai/agents", data),
  update: (id: string, data: { name?: string; description?: string; agent_type?: string; config?: Record<string, unknown> }) =>
    apiClient.patch<AIAgent>(`/ai/agents/${id}`, data).then((r) => r.data),
  deactivate: (id: string) => apiDelete<{ message: string }>(`/ai/agents/${id}`),

  // Tasks
  submitTask: (agentId: string, data: { task_type?: string; input_data?: Record<string, unknown>; requires_human_approval?: boolean }) =>
    apiPost<AITask>(`/ai/agents/${agentId}/tasks`, data),
  listTasks: (agentId: string, params?: { status?: string }) =>
    apiGet<AITaskListResponse>(`/ai/agents/${agentId}/tasks`, params as Record<string, string | number | boolean | undefined>),
  getTask: (taskId: string) => apiGet<AITask>(`/ai/tasks/${taskId}`),
  approveTask: (taskId: string, reason?: string) =>
    apiPost<AITask>(`/ai/tasks/${taskId}/approve`, reason ? { reason } : undefined),
  rejectTask: (taskId: string, reason?: string) =>
    apiPost<AITask>(`/ai/tasks/${taskId}/reject`, reason ? { reason } : undefined),

  // Audit
  listActions: (params?: { agent_id?: string; task_id?: string }) =>
    apiGet<{ items: AIAgentAction[]; total: number }>("/ai/actions", params as Record<string, string | number | boolean | undefined>),

  // Capabilities
  listCapabilities: (params?: { category?: string; agent_type?: string }) =>
    apiGet<{ items: AICapability[]; total: number }>("/ai/capabilities", params as Record<string, string | number | boolean | undefined>),

  // Execute capability
  executeCapability: (taskId: string, capabilityName: string) =>
    apiPost<{ capability: string; status: string; result?: Record<string, unknown> }>(
      `/ai/tasks/${taskId}/execute?capability_name=${encodeURIComponent(capabilityName)}`
    ),

  // Handoff
  handoffTask: (taskId: string, data: { target_agent_id: string; capability_name?: string; input_data?: Record<string, unknown> }) =>
    apiPost<AITask>(`/ai/tasks/${taskId}/handoff`, data),
};

// AI Capability type
export interface AICapability {
  name: string;
  display_name: string;
  description: string;
  capability_type: string;
  category: string;
  requires_approval: boolean;
  supported_agent_types: string[];
}
