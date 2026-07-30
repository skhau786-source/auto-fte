# Upgrade Guide — RC1 → RC2

**Applies to:** v1.0.0-RC1 → v1.0.0-RC2

---

## Overview

RC2 adds monitoring, alerting, caching, export, admin APIs, and scheduled jobs without breaking any existing RC1 functionality. The upgrade is backward-compatible.

---

## Step 1: Pull Latest Code

```bash
git checkout main
git pull origin main
```

---

## Step 2: Install New Dependencies

```bash
pip install -r requirements.txt
# Installs: prometheus-client (metrics)
# Optional: openpyxl (Excel export), aiosmtplib (email alerts), locust (load testing)
```

---

## Step 3: Run Database Migrations

```bash
alembic upgrade head
```

No schema changes are required. This step verifies that the existing migration is current.

---

## Step 4: Update Environment Variables

Copy the new variables from `.env.example` to your `.env.production`:

```bash
# See MIGRATION_GUIDE.md for all new variables
```

---

## Step 5: Restart Services

```bash
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build
```

---

## Step 6: Verify New Endpoints

```bash
# Dashboard
curl http://localhost:8000/dashboard

# Admin stats
curl http://localhost:8000/admin/stats

# Export
curl http://localhost:8000/export/products?format=json

# Health check
curl http://localhost:8000/health
```

---

## Step 7: Run Tests

```bash
pytest tests/ -v --cov=app.inventory
```

---

## Rollback

To return to RC1:

```bash
git checkout v1.0.0-RC1
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build
```

No database rollback is needed (no schema changes).

---

## Need Help?

- See `DEPLOYMENT.md` for full deployment instructions
- See `MIGRATION_GUIDE.md` for detailed migration steps
- See `OPERATIONS.md` for production operations runbook
