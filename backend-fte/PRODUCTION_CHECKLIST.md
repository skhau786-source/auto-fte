# Production Readiness Checklist

## ⚙️ Configuration

- [ ] `SECRET_KEY` is a random 64-char hex string (`openssl rand -hex 32`)
- [ ] `DATABASE_URL` uses a strong password
- [ ] `REDIS_URL` uses a strong password
- [ ] `CORS_ORIGINS` set to exact app domain(s), not `*`
- [ ] `TRUSTED_HOSTS` set to exact domain(s)
- [ ] `DEBUG=false`
- [ ] `ENV=production`
- [ ] `LOG_LEVEL=INFO` (or `WARNING` for high traffic)
- [ ] `LOG_FORMAT=json`

## 🔐 Security

- [ ] HTTPS enforced (TLS termination at reverse proxy / load balancer)
- [ ] `SHOPIFY_API_SECRET` is a real secret (not default/empty)
- [ ] Shopify webhook HMAC verification enabled and tested
- [ ] Database passwords rotated from defaults
- [ ] `.env` file excluded from version control (`.gitignore` has `.env`)
- [ ] Rate limiting configured on reverse proxy (nginx, Cloudflare, etc.)
- [ ] Security headers verified: `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security`

## 🗄️ Database

- [ ] All migrations have been applied (`alembic upgrade head`)
- [ ] Database backup strategy in place (daily + transaction logs)
- [ ] Connection pooling configured (pool_size=10, max_overflow=20 in config)
- [ ] Indexes created for all query patterns (migrations verified)

## 🌐 Shopify

- [ ] App listed in Shopify Partners dashboard
- [ ] Webhook URLs configured in Shopify admin
- [ ] Webhook HMAC verification tested with real Shopify events
- [ ] Store `access_token` and `shopify_location_id` populated after OAuth
- [ ] Webhook registration service tested

## 🐳 Docker

- [ ] Multi-stage build produces minimal image (~200MB)
- [ ] Non-root user (`appuser`) used in container
- [ ] Health checks configured for all services
- [ ] Resource limits set (CPU/memory)
- [ ] Log driver configured with rotation (`max-size=10m`, `max-file=3`)

## 📊 Monitoring

- [ ] Health endpoint returns 200
- [ ] Readiness endpoint verifies DB + Redis connectivity
- [ ] Liveness endpoint configured in orchestrator
- [ ] Structured JSON logging enabled
- [ ] Logs ingested into centralized logging system (e.g., Datadog, ELK, CloudWatch)

## 🧪 Testing

- [ ] All unit/integration tests pass: `pytest tests/ -v`
- [ ] Coverage >= 90%: `pytest --cov=app.inventory --cov-report=term`
- [ ] Shopify sync flow tested end-to-end with real products
- [ ] Webhook endpoints tested with real Shopify payloads

## 🚀 Deployment

- [ ] CI/CD pipeline passing (lint → test → build → deploy)
- [ ] Staging environment deployed and verified
- [ ] Rollback procedure documented and tested
- [ ] Database migration runs automatically in CI/CD
- [ ] Worker container configured for background retries

## 📝 Documentation

- [ ] `DEPLOYMENT.md` updated with latest instructions
- [ ] `OPERATIONS.md` reviewed by team
- [ ] `BACKUP_AND_RECOVERY.md` reviewed by team
- [ ] On-call runbook created (if applicable)
