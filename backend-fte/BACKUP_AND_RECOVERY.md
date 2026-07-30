# Backup & Recovery — Digital FTE Inventory Management

## Backup Strategy

### Database (PostgreSQL)

**Frequency:** Daily full backup + continuous WAL archiving

```bash
# Full backup
pg_dump -U postgres -h localhost -d digital_fte -F c -f backup_$(date +%Y%m%d).dump

# Restore from full backup
pg_restore -U postgres -h localhost -d digital_fte -c backup_20260721.dump

# Backup via Docker
docker compose exec db pg_dump -U postgres -F c digital_fte > backup_$(date +%Y%m%d).dump

# Restore via Docker
docker compose exec -T db pg_restore -U postgres -d digital_fte -c < backup_20260721.dump
```

### Retention Policy

| Type | Retention | Storage |
|------|-----------|---------|
| Daily backups | 30 days | Local disk |
| Weekly backups | 90 days | S3 / GCS |
| Monthly backups | 1 year | S3 / GCS (Glacier) |

### What Gets Backed Up

- All database tables (products, variants, transactions, logs, stores, users)
- Environment configuration (`.env.production` stored in vault)
- Shopify access tokens (in database, backed up with DB)

### What Does NOT Get Backed Up

- Shopify product data (can be re-synced from Shopify)
- Session tokens (users re-authenticate)
- Redis cache (ephemeral, auto-populates)

---

## Disaster Recovery

### Recovery Time Objective (RTO): 1 hour
### Recovery Point Objective (RPO): 24 hours

### Scenario 1: Database Corruption

```bash
# 1. Stop the app
docker compose -f docker-compose.prod.yml stop api

# 2. Restore database
docker compose exec -T db pg_restore -U postgres -d digital_fte -c < latest_backup.dump

# 3. Re-apply recent migrations (if backup is behind)
docker compose exec api alembic upgrade head

# 4. Re-sync Shopify data
docker compose exec api python -c "
from app.database import AsyncSessionLocal
from app.inventory.service import InventoryService
import asyncio
async def resync():
    async with AsyncSessionLocal() as db:
        from app.models import Store
        from sqlalchemy import select
        stores = await db.execute(select(Store).where(Store.is_active == True))
        for store in stores.scalars():
            svc = InventoryService(db=db, store=store)
            await svc.sync_from_shopify(force_full=True)
asyncio.run(resync())
"

# 5. Restart the app
docker compose -f docker-compose.prod.yml up -d
```

### Scenario 2: Full Infrastructure Failure

```bash
# 1. Provision new servers
# 2. Clone repository
git clone https://github.com/your-org/digital-fte.git
cd digital-fte/backend-fte

# 3. Restore .env.production from vault
# 4. Start services
docker compose -f docker-compose.prod.yml up -d

# 5. Restore database from S3
aws s3 cp s3://your-backup-bucket/digital_fte/latest.dump .
docker compose exec -T db pg_restore -U postgres -d digital_fte -c < latest.dump

# 6. Run migrations
docker compose exec api alembic upgrade head

# 7. Verify
curl https://your-app.com/health
```

### Scenario 3: Shopify API Token Expiry

- Tokens are stored in the `stores.access_token` column
- User must re-authenticate via Shopify OAuth
- The existing OAuth flow generates a new token
- No data loss — unsynced transactions are retried by the worker

---

## Monitoring Alerts

| Alert | Threshold | Action |
|-------|-----------|--------|
| Unsynced transactions > 100 | Warning | Check Shopify API status |
| Unsynced transactions > 1000 | Critical | Manual intervention |
| Worker not running | Critical | Restart worker container |
| Database size > 80% | Warning | Increase volume size |
| API 5xx rate > 1% | Critical | Check logs, rollback if needed |
