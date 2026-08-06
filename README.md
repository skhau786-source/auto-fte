# Digital FTE — Backend

A production-grade store-centric inventory management system with WooCommerce integration, a reservation engine, and an intelligent allocation engine.

Built with **FastAPI**, **PostgreSQL**, **Redis**, and **SQLAlchemy**.

---

## Architecture

```
                      ┌──────────────────┐
                      │   FastAPI App     │
                      │   (REST API)      │
                      └──────┬───────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                   ▼
   ┌────────────┐    ┌──────────────┐    ┌──────────────┐
   │ Inventory  │    │ Reservation  │    │ Allocation   │
   │ Service    │    │ Engine       │    │ Engine       │
   └────────────┘    └──────────────┘    └──────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
   ┌────────────┐    ┌──────────────┐    ┌──────────────┐
   │ WooComm.   │    │ Order        │    │ Aggregation  │
   │ Sync       │    │ Integration  │    │ Engine       │
   └────────────┘    └──────────────┘    └──────────────┘
          │                  │                  │
          └──────────────────┴──────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   PostgreSQL     │
                    │   + Redis Cache  │
                    └──────────────────┘
```

---

## Features

### ✅ Phase 1 — Inventory Management
- Product & variant CRUD with Shopify API integration
- Category management
- Inventory transactions with full audit trail
- Low stock alerts and notifications

### Phase 2 — (Removed in the SaaS pivot)
The multi-location storage management module was retired when the platform
pivoted to a store-centric SaaS model. Store settings, reservations, and
allocation are now configured directly per store.

### ✅ Phase 3 — Reservation Engine
- Inventory reservation with `SELECT ... FOR UPDATE` row locking
- Reservation lifecycle: PENDING → ACTIVE → COMMITTED / RELEASED / EXPIRED
- Automatic expiration of stale reservations
- Concurrent-safe reservation logic
- WooCommerce order → reservation integration

### ✅ Phase 4 — Task Assignment Engine (Inventory Allocation)
- Extensible Strategy Pattern for allocation strategy selection
- Built-in strategies: Default, Manual
- Store-level allocation settings (configurable per store)
- Preview allocation before committing

### ✅ Phase 5 — WooCommerce Order Integration
- Automatic order → allocation → reservation pipeline
- Order status event handling: pending, processing, completed, cancelled, refunded, failed
- Configurable behavior via store settings (auto-release, reserve-on-order)
- Failure isolation — sync errors never break WooCommerce integration
- Fulfillment summary (fully/partially/out-of-stock)

### ✅ Phase 6 — Inventory Aggregation Engine
- Real-time inventory visibility across the store
- Variant, Product, and Store-level aggregation
- In-memory TTL cache with automatic invalidation
- N+1 query elimination via SQL `GROUP BY` aggregates
- Dashboard and report endpoints
- Cache invalidation wired into all mutation services

### ✅ Phase 7 — Unified Dashboard
- Single `GET /dashboard/unified` endpoint combining metrics from all phases
- Per-phase error isolation — one phase failure never blocks others
- 40+ widgets: inventory summary, reservation metrics, allocation usage, order integration, aggregation totals

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI (Python 3.12) |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Database | PostgreSQL 16 |
| Cache | Redis (token blacklist + aggregation cache) |
| Auth | JWT + Google OAuth |
| Task Queue | Celery + Redis broker |
| Container | Docker + Docker Compose |
| Orchestration | Kubernetes (configs included) |
| Testing | pytest + pytest-asyncio |

---

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16+
- Redis 7+
- Docker (optional)

### Clone and Install

```bash
git clone https://github.com/kulsoom0324/digital-fte-backend.git
cd digital-fte-backend/backend-fte

python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configure Environment

```bash
cp .env.example .env
# Edit .env with your database URL, secrets, etc.
```

### Run Migrations

```bash
alembic upgrade head
```

### Start the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Visit [http://localhost:8000/docs](http://localhost:8000/docs) for interactive API docs.

---

## Project Structure

```
backend-fte/
├── app/
│   ├── auth/           # JWT + Google OAuth
│   ├── inventory/      # Inventory CRUD, reservations, allocation, aggregation, Shopify sync
│   ├── woocommerce/    # WooCommerce sync + order integration
│   ├── dashboard/      # Unified dashboard (Phase 7)
│   ├── alerts/         # Low stock + failure alerts
│   ├── cache/          # Redis cache client
│   ├── events/         # Domain event dispatcher
│   ├── export/         # CSV/JSON export
│   ├── organizations/  # Multi-tenant support
│   ├── scheduler/      # Celery task scheduling
│   └── subscriptions/  # Billing integration
├── alembic/            # Database migrations
├── tests/              # 233+ passing tests
├── k8s/                # Kubernetes manifests
└── nginx/              # Nginx reverse proxy config

frontend-fte/
├── app/                # Next.js app directory
├── components/         # React components
└── lib/                # API client
```

---

## API Endpoints

| Prefix | Description |
|--------|-------------|
| `/auth` | Registration, login, Google OAuth |
| `/inventory` | Products, variants, categories, stores |
| `/reservations` | Reservation lifecycle |
| `/allocation` | Allocation settings, preview, execute |
| `/orders` | WooCommerce order integration |
| `/inventory/aggregate` | Aggregation engine |
| `/dashboard/unified` | All-in-one dashboard |
| `/woocommerce` | WooCommerce sync & webhooks |
| `/metrics` | Prometheus metrics |

---

## Testing

```bash
cd backend-fte
python -m pytest tests/ -v
```

300+ tests covering all phases, run against a PostgreSQL test database.

---

## Deployment

See [DEPLOYMENT.md](backend-fte/DEPLOYMENT.md) for production deployment instructions including Docker, Kubernetes, and monitoring setup.

---

## License

[MIT](LICENSE)

---

## Status

**Production Ready** — All active phases implemented and validated (Phase 2 removed in the SaaS pivot).
# Digital-Fte-Startup
