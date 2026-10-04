// Authenticated API helper for the workspace pages (inventory, knowledge base).
// Token page.tsx ke login flow se localStorage mein save hota hai.

import { buildApiUrl } from "./config";

export const AUTH_TOKEN_KEY = "digital-fte-token";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function getToken(): string | null {
  try {
    return window.localStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0] as { msg?: string; loc?: unknown[] };
      const field = Array.isArray(first.loc) ? String(first.loc[first.loc.length - 1]) : "";
      return field ? `${field}: ${first.msg}` : first.msg || fallback;
    }
  }
  return fallback;
}

export async function apiFetch<T>(
  path: string,
  options: { method?: string; body?: unknown } = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(buildApiUrl(path), {
      method: options.method || "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Cannot reach the backend. Is it running?");
  }

  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!response.ok) {
    throw new ApiError(response.status, errorMessage(data, `Request failed (${response.status})`));
  }
  return data as T;
}

// ─── Types: stores / inventory ───────────────────────────────

export interface Store {
  id: number;
  name: string;
  platform: string;
  is_active: boolean;
}

export interface VariantRow {
  id: number;
  title: string;
  sku: string;
  price: number;
  inventory_quantity: number;
  low_stock_threshold: number;
}

export interface ProductRow {
  id: number;
  title: string;
  vendor: string;
  status: string;
  image_url: string;
  variants: VariantRow[];
}

export interface ProductList {
  total: number;
  page: number;
  limit: number;
  items: ProductRow[];
}

export interface InventorySummary {
  product_count: number;
  variant_count: number;
  total_available_units: number;
  total_reserved_units: number;
  inventory_value: number;
  low_stock_variants: number;
  out_of_stock_variants: number;
  active_reservations: number;
}

export interface MoverRow {
  variant_id: number;
  sku: string;
  product_title: string;
  variant_title: string;
  available_quantity: number;
  units_sold: number;
}

export interface InventoryReport {
  window_days: number;
  out_of_stock_count: number;
  fast_movers: MoverRow[];
  dead_stock: MoverRow[];
  dead_stock_count: number;
}

export interface LowStockAlert {
  id: number;
  variant_id: number;
  product_title: string;
  variant_title: string;
  sku: string;
  current_stock: number;
  threshold: number;
}

export interface Reservation {
  id: number;
  variant_id: number;
  order_id: string | null;
  order_source: string;
  quantity: number;
  status: string;
  reason: string | null;
  expires_at: string | null;
  created_at: string;
}

export interface Movement {
  id: number;
  variant_id: number;
  movement_type: string;
  quantity_change: number;
  quantity_before: number;
  quantity_after: number;
  reason: string | null;
  reference_id: string | null;
  created_at: string;
}

// ─── Types: knowledge base ───────────────────────────────────

export interface KnowledgeBase {
  id: number;
  name: string;
  description: string | null;
  document_count: number;
  chunk_count: number;
  total_tokens: number;
  last_indexed_at: string | null;
  created_at: string;
}

export interface RagDocument {
  id: number;
  knowledge_base_id: number;
  title: string;
  filename: string | null;
  file_type: string;
  chunk_count: number;
  token_count: number;
  created_at: string;
}

export interface SearchChunk {
  id: number;
  document_id: number;
  document_title: string;
  content: string;
  chunk_index: number;
  similarity_score: number;
}

export interface SearchResult {
  query: string;
  chunks_retrieved: number;
  chunks: SearchChunk[];
  retrieval_time_ms: number;
}

export interface AugmentResult {
  context: string;
  source_documents: number;
  tokens_added: number;
}

export interface VariantLabelMap {
  [variantId: number]: string;
}
