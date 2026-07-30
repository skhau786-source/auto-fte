# Deployment Guide — Digital FTE Inventory Management

## Prerequisites

- Docker & Docker Compose v3.9+
- PostgreSQL 16+
- Redis 7+
- Shopify Partner Account (for API credentials)
- Google OAuth Client ID (for auth)

---

## Quick Start (Development)

```bash
# 1. Clone and configure
cd backend-fte
cp .env.example .env
# Edit .env with your local credentials

# 2. Start services
docker compose up -d

# 3. Run migrations
docker compose exec api alembic upgrade head

# 4. Check health
curl http://localhost:8000/health
```

---

## Production Deployment

### 1. Environment Setup

```bash
# Create production env
cp .env.production .env
# Edit ALL values — especially SECRET_KEY, DATABASE_URL, SHOPIFY_API_SECRET
```

### 2. Infrastructure

```bash
# Start production stack
docker compose -f docker-compose.prod.yml up -d

# Run migrations
docker compose -f docker-compose.prod.yml exec api alembic upgrade head

# Verify
docker compose -f docker-compose.prod.yml ps
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### 3. Scale Workers

```bash
# Scale API replicas
docker compose -f docker-compose.prod.yml up -d --scale api=4

# Scale the retry worker (max 1)
docker compose -f docker-compose.prod.yml up -d worker
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ | PostgreSQL async connection string |
| `SECRET_KEY` | ✅ | JWT signing secret (generate with `openssl rand -hex 32`) |
| `SHOPIFY_API_KEY` | ✅ | From Shopify Partners dashboard |
| `SHOPIFY_API_SECRET` | ✅ | From Shopify Partners dashboard |
| `GOOGLE_CLIENT_ID` | ✅ | From Google Cloud Console |
| `REDIS_URL` | ✅ | Redis connection string |
| `CORS_ORIGINS` | ✅ | Comma-separated allowed origins |
| `TRUSTED_HOSTS` | ✅ | Comma-separated allowed hosts |
| `LOG_LEVEL` | ❌ | Default: INFO |
| `LOG_FORMAT` | ❌ | Default: json |

---

## Database Migrations

```bash
# Create a new migration
docker compose exec api alembic revision --autogenerate -m "description"

# Apply pending migrations
docker compose exec api alembic upgrade head

# Rollback one step
docker compose exec api alembic downgrade -1

# View history
docker compose exec api alembic history
```

---

## Monitoring

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Basic health check (always returns 200 if process is alive) |
| `GET /ready` | Readiness probe (checks DB + Redis) |
| `GET /live` | Liveness probe (K8s pod health) |
| `GET /version` | App version and env info |

---

## Backup & Restore

```bash
# Backup database
docker compose exec db pg_dump -U postgres digital_fte > backup_$(date +%Y%m%d).sql

# Restore database
docker compose exec -T db psql -U postgres digital_fte < backup.sql
```

---

## Rollback Procedure

```bash
# 1. Roll back database migration
docker compose exec api alembic downgrade -1

# 2. Roll back Docker image to previous version
docker compose -f docker-compose.prod.yml up -d api=previous-tag

# 3. Verify rollback
curl http://localhost:8000/health
```
