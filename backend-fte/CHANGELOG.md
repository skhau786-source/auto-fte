# Changelog — Digital FTE Inventory Management

All notable changes to the Inventory Management module are documented here.

---

## [1.0.0-RC2] — 2026-07-22

### Added

- **Dashboard Module** (`app/dashboard/`): `/dashboard` endpoint with inventory summary, sync health, webhook health, and recent errors
- **Alerting System** (`app/alerts/`): Abstract notifier with Email, Slack, and SMS interfaces; alert conditions for low inventory, Shopify failures, webhook failures, retry exhaustion, and high error rate
- **Enhanced Audit Service** (`app/inventory/audit_service.py`): Full context capture (user, store, IP, request ID, correlation ID), before/after snapshots, CSV and JSON export
- **Data Export Service** (`app/export/`): Export products, variants, transactions, and logs in CSV, JSON, and Excel formats with streaming download
- **Scheduler Service** (`app/scheduler/`): Nightly Shopify sync, log cleanup (90-day retention), token cleanup, dead letter monitoring, daily inventory reports
- **Admin Router** (`app/inventory/admin_router.py`): Retry failed syncs, rebuild inventory, re-register webhooks, flush cache, view queue/dead letters, system statistics
- **Redis Caching** (`app/cache/`): Cache service with TTL-based expiration, pattern-based invalidation, graceful Redis fallback
- **End-to-End Tests** (`tests/test_end_to_end.py`): 9 integration tests covering happy path, failed sync, retry success, webhook idempotency, rollback, and metrics

### Changed

- Updated `app/main.py` with new router registrations (dashboard, export, admin)
- Added `prometheus-client` to `requirements.txt`

### Documentation

- `PERFORMANCE_OPTIMIZATION.md` — Database, query, caching, and async performance review
- `FINAL_PRODUCTION_REVIEW.md` — Comprehensive architecture, security, and production readiness audit
- `RELEASE_NOTES_RC2.md` — Release notes for v1.0.0-RC2
- `MIGRATION_GUIDE.md` — Database and configuration migration steps
- `UPGRADE_GUIDE.md` — RC1 to RC2 upgrade instructions

---

## [1.0.0-RC1] — 2026-07-20

### Added

- **Production Docker Setup**: Multi-stage Dockerfile, docker-compose.prod.yml, .dockerignore
- **Environment Configuration**: .env.example, .env.production, .env.staging with Pydantic v2 validation
- **Structured Logging**: JSON formatter with contextvars, rotating file handler, sensitive data masking
- **Monitoring Endpoints**: `/health`, `/ready` (DB + Redis check), `/live`, `/version`
- **Retry Worker**: Background process polling unsynced transactions with exponential backoff and dead letter detection
- **Webhook Registration Service**: Automatic registration of products/update, inventory_levels/update, app/uninstalled webhooks
- **CI/CD Pipeline**: GitHub Actions workflow with lint, test, build, security scan, and deploy stages
- **Deployment Documentation**: DEPLOYMENT.md, PRODUCTION_CHECKLIST.md, OPERATIONS.md, BACKUP_AND_RECOVERY.md
- **Security Hardening**: CORS, TrustedHostMiddleware, security headers, rate limiting (in-memory sliding window)
- **Prometheus Metrics**: Request counters, duration histograms, inventory operation metrics with graceful fallback

### Changed

- Refactored `adjust_inventory()` transaction lifecycle for commit-first Shopify sync strategy
- Fixed stale relationship issue in `create_product()` by adding `db.refresh(product)` call
- Updated `config.py` with `@model_validator` for production environment validation
- Cleaned up unused imports and dead code

---

## [1.0.0-beta] — 2026-07-15

### Added

- **Inventory Module** (`app/inventory/`): Complete Clean Architecture with Repository → Service → Router
- **9 REST APIs**: CRUD products, inventory adjustment, low stock detection, transaction history, product search
- **Shopify Client**: Async GraphQL + REST client with retry logic, pagination, and HMAC webhook verification
- **Shopify Sync**: Full product import from Shopify with upsert logic
- **Webhook Handlers**: inventory_levels/update, products/update, app/uninstalled with HMAC verification
- **Test Suite**: 171 tests across Repository, Service, Router, Shopify Client, and Webhook layers
- **Database Models**: Product, ProductVariant, InventoryTransaction, InventoryLog, Category with SQLAlchemy async

---

## [0.1.0] — 2026-07-01

### Added

- Initial project setup
- User authentication (JWT)
- Shopify OAuth integration
- Store connection management
