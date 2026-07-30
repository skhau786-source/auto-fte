# Operations Guide — Digital FTE Inventory Management

## Architecture Overview

```
Internet → Load Balancer → FastAPI (uvicorn, 4+ workers)
                              ├── PostgreSQL (primary data store)
                              ├── Redis (token blacklist, caching)
                              └── Shopify Admin API (product/inventory sync)

Background Worker (retry_worker.py) → polls unsynced transactions → Shopify API
```

---

## Logging

All logs are structured JSON with the following fields:

```json
{
  "timestamp": "2026-07-21T10:00:00.000Z",
  "level": "INFO",
  "logger": "app.inventory.service",
  "message": "Syncing variant ... to Shopify",
  "request_id": "abc-123",
  "user_id": "uuid-here",
  "store_id": "uuid-here",
  "endpoint": "POST /inventory/update-stock",
  "extra": { ... }
}
```

### Log Levels by Environment

| Environment | Console Level | File Level |
|-------------|--------------|------------|
| Development | DEBUG | DEBUG |
| Staging | DEBUG | INFO |
| Production | INFO | WARNING |

### Log Location

Logs are written to `logs/app.log` with automatic rotation (10 MB per file, 5 backups).

---

## Monitoring Endpoints

| Endpoint | Expected Status | Purpose | Checked By |
|----------|----------------|---------|------------|
| `GET /health` | `{"status": "ok"}` | App is running | Load balancer |
| `GET /ready` | `{"status": "ok", "checks": {"database": "ok", "redis": "ok"}}` | Dependencies available | Docker/K8s readiness probe |
| `GET /live` | `{"status": "alive"}` | Process not hung | K8s liveness probe |

### Response Codes

- **200**: All healthy
- **503**: Readiness check failed (DB or Redis down)

---

## Background Worker

The retry worker runs as a separate container and polls for failed Shopify
synchronizations every 60 seconds.

### Health

Check worker logs:
```bash
docker compose -f docker-compose.prod.yml logs worker
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNC_RETRY_MINUTES` | 5 | Base retry interval |
| `MAX_RETRY_ATTEMPTS` | 5 | Maximum retries before dead letter |

---

## Common Issues

### Inventory not syncing to Shopify

1. Check worker logs for Shopify API errors
2. Verify `store.access_token` is valid (not expired)
3. Verify `store.shopify_location_id` is set
4. Check unsynced transaction count:
   ```sql
   SELECT COUNT(*) FROM inventory_transactions WHERE synced_to_shopify = false;
   ```

### Webhooks not being received

1. Verify webhook URLs are registered in Shopify Admin
2. Check webhook HMAC verification logs
3. Verify `SHOPIFY_API_SECRET` matches Shopify Partners settings
4. Ensure the store is active (`is_active = true`)

### High memory usage

1. Check connection pool settings in `app/database.py`
2. Verify `pool_size` and `max_overflow` are appropriate
3. Check for unclosed HTTPX sessions in ShopifyClient
4. Monitor with `docker stats`

---

## Performance Tips

- Keep `SYNC_INTERVAL_HOURS` at 6+ for production to avoid rate limiting
- Batch inventory updates where possible (use `bulk_adjust_inventory`)
- Monitor Shopify API quota: `X-Shopify-Shop-Api-Call-Limit` response header
- Set `DEBUG=false` in production to disable SQL echo
