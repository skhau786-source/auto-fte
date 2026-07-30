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

// Request interceptor: attach JWT token
apiClient.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Response interceptor: standardized error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string; message?: string }>) => {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      "An unexpected error occurred";
    return Promise.reject(new Error(message));
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

export const authApi = {
  login: (email: string, password: string) =>
    apiPost<{ access_token: string; token_type: string }>("/auth/login", { email, password }),
  register: (data: { username: string; email: string; password: string; full_name?: string }) =>
    apiPost<{ id: string; email: string }>("/auth/register", data),
  me: () => apiGet<{ id: string; email: string; username: string }>("/auth/me"),
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
