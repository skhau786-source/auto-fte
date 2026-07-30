# Performance Report — Inventory Management Module

**Date:** July 21, 2026

---

## 1. Database Query Review

### Eager Loading Audit

| Repository Method | Loading Strategy | Status |
|------------------|-----------------|--------|
| `ProductRepository.get_by_id` | `selectinload(Product.variants)` | ✅ Optimal |
| `ProductRepository.get_by_shopify_id` | `selectinload(Product.variants)` | ✅ Optimal |
| `ProductRepository.list_products` | `selectinload(Product.variants)` | ✅ Optimal |
| `ProductRepository.update` | Calls `get_by_id` → `selectinload` | ✅ Optimal |
| `ProductRepository.delete` | Calls `get_by_id` → `selectinload` | ✅ Optimal |
| `VariantRepository.get_by_id` | `joinedload(ProductVariant.product)` | ✅ Optimal |
| `VariantRepository.get_by_shopify_id` | `joinedload(ProductVariant.product)` | ✅ Optimal |
| `VariantRepository.get_by_inventory_item_id` | `joinedload(ProductVariant.product)` | ✅ Optimal |
| `VariantRepository.get_low_stock` | `joinedload(ProductVariant.product)` | ✅ Optimal |

**Finding:** All read operations use appropriate eager loading. No N+1 queries exist in the read path.

### N+1 Analysis

The following operations involve loops that could cause N+1 queries under heavy load:

| Operation | Queries per Item | Impact |
|-----------|-----------------|--------|
| Shopify sync (per product) | 1 for product lookup + 1 per variant | Acceptable for sync frequency (every 6h) |
| Bulk update variants | 2 per variant (get + update) | Acceptable for batch sizes ≤ 100 |
| Dashboard stats | 5 independent queries | Acceptable for infrequent dashboard loads |

**Recommendation:** None needed at this scale. Monitor in production.

---

## 2. Database Indexes

### Existing Indexes

| Table | Index | Column(s) |
|-------|-------|-----------|
| `registered_students` | Primary | `id` |
| | Unique | `username`, `email` |
| `stores` | Primary | `id` |
| | Unique | `shopify_domain` |
| | Index | `owner_id` |
| `products` | Primary | `id` |
| | Unique | `shopify_product_id` |
| | Index | `store_id` |
| `product_variants` | Primary | `id` |
| | Unique | `shopify_variant_id`, `shopify_inventory_item_id` |
| | Index | `product_id`, `sku` |
| `inventory_transactions` | Primary | `id` |
| | Index | `variant_id` |
| `inventory_logs` | Primary | `id` |
| | Index | `variant_id`, `action` |

### Recommended Additions

| Table | Index | Rationale |
|-------|-------|-----------|
| `products` | Composite: `(store_id, status)` | Used by `list_products` with status filter |
| `inventory_transactions` | Index: `created_at` | Used by `list_history` with `ORDER BY created_at DESC` |
| `inventory_transactions` | Composite: `(variant_id, created_at)` | Most common query pattern for variant history |

**Recommendation:** Add these indexes in a future migration if query performance degrades in production.

---

## 3. Connection Pooling

| Setting | Value | Rationale |
|---------|-------|-----------|
| `pool_size` | 10 | Matches 4 API workers × ~2 concurrent queries |
| `max_overflow` | 20 | Burst capacity for sync/webhook spikes |
| `pool_pre_ping` | True | Ensures connections are alive before use |
| `pool_recycle` | 1800s (30min) | Prevents connection stale after idle |

**Finding:** Settings are appropriate for expected traffic levels.

---

## 4. Performance Benchmark (Expected)

Based on code analysis, expected performance:

| Operation | Expected Latency (P50) | Expected Latency (P95) |
|-----------|----------------------|----------------------|
| `GET /health` | < 5ms | < 10ms |
| `GET /inventory` (20 items) | < 50ms | < 150ms |
| `GET /inventory/search` | < 80ms | < 200ms |
| `POST /inventory` (create) | < 100ms | < 300ms |
| `POST /inventory/update-stock` | < 200ms | < 500ms |
| `GET /inventory/low-stock` | < 50ms | < 150ms |
| `GET /inventory/history` | < 100ms | < 250ms |

Run `python benchmark.py` to measure actual performance against these targets.

---

## 5. Optimization Recommendations

| Priority | Recommendation | Impact |
|----------|---------------|--------|
| 🟢 Low | Add composite index `(store_id, status)` on `products` | Speeds up filtered listing (migration pending) |
| 🟢 Low | Add composite index `(variant_id, created_at)` on `inventory_transactions` | Speeds up history pagination (migration pending) |
| 🟢 Low | Consider Redis caching for dashboard stats | Reduces dashboard query time |
| 🟢 Low | Batch Shopify syncs (reduce individual webhook calls) | Reduces API quota consumption |

**Conclusion:** No performance bottlenecks identified at current scale. Key queries are indexed. Monitoring in production will reveal any optimization opportunities.
