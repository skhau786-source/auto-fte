# Release Notes — v1.0.0-RC2

**Release Date:** July 22, 2026  
**Module:** Inventory Management System  
**Previous Version:** v1.0.0-RC1

---

## New Features (Phase 7)

### 📊 Monitoring Dashboard
- New `/dashboard` endpoint with aggregate inventory summaries
- Today's transaction counts, sync health, webhook health, recent errors
- Real-time store-level monitoring

### 🔔 Alerting System
- Abstract notifier pattern with Email, Slack, and SMS interfaces
- Alert conditions: low inventory, Shopify failures, webhook failures, retry exhaustion, high error rate
- Ready for production integration — configure environment variables

### 📋 Enhanced Audit Logging
- Full context capture: user, store, IP, endpoint, request ID, correlation ID, duration
- Before/after value snapshots for all inventory operations
- CSV and JSON export support for audit logs and transactions

### 📦 Data Export Service
- Export products, variants, transactions, and logs
- Formats: CSV, JSON, Excel (.xlsx)
- Streaming download via FastAPI `StreamingResponse`

### ⏰ Scheduled Jobs
- Nightly Shopify sync for all active stores
- Automatic cleanup of old logs (90-day retention)
- Expired token cleanup (30-day threshold)
- Daily inventory report generation
- Dead letter monitoring

### 🔧 Admin APIs
- `POST /admin/sync/retry` — Retry all failed Shopify syncs
- `POST /admin/inventory/rebuild` — Force full re-sync from Shopify
- `POST /admin/webhooks/re-register` — Re-register all webhooks
- `POST /admin/cache/flush` — Flush Redis cache
- `GET /admin/queue/status` — View retry queue
- `GET /admin/queue/dead-letters` — View dead letters
- `GET /admin/stats` — System statistics

### ⚡ Redis Caching
- Dashboard, categories, products, inventory summary cached
- Automatic TTL per cache type (60s–600s)
- Manual purge by pattern or store
- Graceful fallback when Redis is unavailable

### ✅ End-to-End Integration Tests
- 9 comprehensive E2E tests covering the full workflow
- Happy path, failed sync, retry success, webhook replay, idempotency, rollback, metrics

---

## Improvements

- Performance optimization report generated (`PERFORMANCE_OPTIMIZATION.md`)
- Final production review completed (`FINAL_PRODUCTION_REVIEW.md`)
- Migration guide for existing deployments (`MIGRATION_GUIDE.md`)
- Upgrade guide from RC1 to RC2 (`UPGRADE_GUIDE.md`)

---

## Breaking Changes

- **None.** All existing APIs remain backward-compatible.
- New endpoints do not modify existing behavior.

---

## Migration Notes

- See `MIGRATION_GUIDE.md` for database and configuration changes.
- Redis is optional — the cache layer degrades gracefully.

---

## Known Issues

1. Offset pagination may be slow for stores with 10,000+ products
2. Rate limiter is per-worker (in-memory), not shared across instances
3. Excel export requires `openpyxl` (not in base requirements)

---

## Contributors

- Backend Inventory Management Team
- Shopify Integration Team
- QA & Testing Team

---

## Verification

```bash
# Run tests
pytest tests/ -v --cov=app.inventory

# Check migration
alembic upgrade head

# Build Docker
docker build -t digital-fte-inventory:rc2 .

# Start stack
docker compose -f docker-compose.prod.yml up -d
```
