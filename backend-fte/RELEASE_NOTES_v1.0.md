# Release Notes — v1.0.0-RC1

**Release Date:** July 21, 2026
**Module:** Inventory Management Backend

---

## Overview

Production-ready inventory management backend for Shopify-integrated applications. Complete with FastAPI REST APIs, Shopify sync, webhook handling, background retry worker, and full DevOps infrastructure.

---

## Features

### Inventory Management
- ✅ Product CRUD (create, read, update, delete) with variant support
- ✅ Inventory stock adjustments with atomic transactions
- ✅ Bulk inventory adjustments (up to 100 items per batch)
- ✅ Low stock detection with configurable thresholds
- ✅ Paginated product listing with search, filter, and sort
- ✅ Inventory transaction history (immutable audit trail)
- ✅ Activity logging for all inventory events
- ✅ Dashboard statistics (total products, variants, inventory value, low/out-of-stock counts)

### Shopify Integration
- ✅ GraphQL product sync with cursor-based pagination
- ✅ Inventory level synchronization (commit-first strategy)
- ✅ Webhook handlers: `inventory_levels/update`, `products/update`, `app/uninstalled`
- ✅ HMAC-SHA256 webhook verification
- ✅ Automatic webhook registration service
- ✅ Background retry worker for failed syncs (exponential backoff, dead letter queue)

### API Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/inventory` | List products (paginated, filterable) |
| GET | `/inventory/search` | Advanced product search |
| GET | `/inventory/{id}` | Get single product |
| POST | `/inventory` | Create product |
| PUT | `/inventory/{id}` | Update product |
| DELETE | `/inventory/{id}` | Delete product |
| POST | `/inventory/update-stock` | Adjust inventory |
| GET | `/inventory/low-stock` | Low stock detection |
| GET | `/inventory/history` | Transaction history |

### Monitoring
- ✅ Health, readiness, liveness, version endpoints
- ✅ Prometheus metrics (`/metrics`)
- ✅ Request ID tracing (`X-Request-Id`, `X-Execution-Time-Ms`)
- ✅ Structured JSON logging with contextvars
- ✅ In-memory rate limiting (configurable)

### Security
- ✅ JWT authentication
- ✅ Store ownership validation
- ✅ HMAC webhook verification
- ✅ Production env validation (startup checks)
- ✅ Security headers (HSTS, X-Frame-Options, X-Content-Type-Options)
- ✅ CORS configuration
- ✅ Rate limiting

### DevOps
- ✅ Multi-stage Docker build (non-root user, ~200MB)
- ✅ Docker Compose production stack (API, DB, Redis, Worker)
- ✅ GitHub Actions CI/CD (lint → test → build → deploy)
- ✅ Alembic migrations (8 tables, all indexes)
- ✅ Environment validation at startup

---

## Test Summary

| Layer | Tests | Status |
|-------|-------|--------|
| Repository | 52 | ✅ Passing |
| Service | 45 | ✅ Passing |
| API/Router | 35 | ✅ Passing |
| Shopify Client | 22 | ✅ Passing |
| Webhooks | 17 | ✅ Passing |
| **Total** | **~171** | ✅ **All Passing** |

---

## Known Limitations

1. **Multi-location inventory**: Supports single-location stores. Multi-location requires `Location` ID mapping.
2. **Log metrics integration**: No Datadog/Prometheus push integration — metrics are pull-based via `/metrics`.
3. **Rate limiting**: In-memory (not Redis-backed). Rate limits reset on app restart.
4. **Cache**: No Redis caching for product listing — all queries hit PostgreSQL.

---

## Upgrade Notes

### From Previous Versions

- **Database migration required**: Run `alembic upgrade head` to create inventory tables
- **Environment variables**: New required vars: `SHOPIFY_API_KEY`, `SHOPIFY_API_SECRET`, `CORS_ORIGINS`, `TRUSTED_HOSTS`
- **API changes**: None — all existing endpoints preserved

---

## Deployment

```bash
# Production deployment
docker compose -f docker-compose.prod.yml up -d
docker compose exec api alembic upgrade head

# Verify
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

See `DEPLOYMENT.md` for full instructions.

---

## Rollback

```bash
# Rollback database
docker compose exec api alembic downgrade -1

# Rollback Docker image
docker compose -f docker-compose.prod.yml up -d api=previous-tag
```

---

## Credits

Built by the Inventory Management Team.
