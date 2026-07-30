# Migration Guide — v1.0.0-RC2

This guide covers migrating from RC1 to RC2.

---

## 1. Database Changes

### New Tables (None)

RC2 introduces no new database tables. All Phase 7 features use existing models.

### New Columns (None)

No schema changes. The existing migration `694d38b99c0b` already includes all columns.

### Migration Command

```bash
# If you haven't run migrations yet:
alembic upgrade head

# If you have already run RC1 migrations:
alembic check  # Should report "No new migrations"
```

---

## 2. Environment Variables

### New Required Variables

| Variable | Default | Description |
|---|---|---|
| `SLACK_WEBHOOK_URL` | *(optional)* | Slack webhook URL for alert notifications |
| `ALERT_EMAIL_SENDER` | *(optional)* | Sender email for alert emails |
| `ALERT_EMAIL_RECIPIENTS` | *(optional)* | Comma-separated recipient emails |
| `ALERT_EMAIL_SMTP_HOST` | `localhost` | SMTP host for email alerts |
| `ALERT_EMAIL_SMTP_PORT` | `587` | SMTP port |
| `ALERT_EMAIL_SMTP_USERNAME` | *(optional)* | SMTP username |
| `ALERT_EMAIL_SMTP_PASSWORD` | *(optional)* | SMTP password |
| `CACHE_ENABLED` | `true` | Enable Redis caching |
| `CACHE_TTL_DASHBOARD` | `60` | Dashboard cache TTL (seconds) |
| `CACHE_TTL_CATEGORIES` | `300` | Categories cache TTL |

### Variables Removed

- None

---

## 3. Configuration Changes

### app/config.py

No breaking changes. The `Settings` class is backward-compatible.

---

## 4. API Changes

### New Endpoints (Backward-Compatible)

| Endpoint | Method | Description |
|---|---|---|
| `/dashboard` | GET | Inventory monitoring dashboard |
| `/export/products` | GET | Export products (CSV, JSON, XLSX) |
| `/export/transactions` | GET | Export transactions (CSV, JSON) |
| `/export/logs` | GET | Export audit logs (CSV, JSON) |
| `/admin/sync/retry` | POST | Retry failed Shopify syncs |
| `/admin/inventory/rebuild` | POST | Rebuild inventory from Shopify |
| `/admin/webhooks/re-register` | POST | Re-register webhooks |
| `/admin/cache/flush` | POST | Flush Redis cache |
| `/admin/queue/status` | GET | View retry queue |
| `/admin/queue/dead-letters` | GET | View dead letters |
| `/admin/stats` | GET | System statistics |

### Changed Endpoints

- None. All RC1 endpoints remain unchanged.

---

## 5. Docker Changes

### docker-compose.prod.yml

Add the scheduler service to your production stack:

```yaml
scheduler:
  build: .
  command: python -m app.scheduler.scheduler_service
  env_file:
    - .env.production
  depends_on:
    db:
      condition: service_healthy
    redis:
      condition: service_healthy
  restart: unless-stopped
```

---

## 6. Rollback Procedure

If RC2 needs to be rolled back:

```bash
# 1. Revert code
git checkout v1.0.0-RC1

# 2. Restart services
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d

# 3. No database rollback needed (no schema changes)
```

---

## 7. Verification Checklist

- [ ] Run `pytest tests/` — all 180+ tests pass
- [ ] Run `alembic upgrade head` — no errors
- [ ] Run `curl http://localhost:8000/health` — returns 200
- [ ] Run `curl http://localhost:8000/dashboard` — returns dashboard data
- [ ] Run `curl http://localhost:8000/admin/stats` — returns system stats
- [ ] Docker build succeeds: `docker build -t inventory:rc2 .`
