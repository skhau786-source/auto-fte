# Digital FTE — Frontend

AI-powered E-commerce Autonomous Employee platform. Frontend built with Next.js + TypeScript + Tailwind CSS.

**Connected to the real backend** (`backend-fte/`, FastAPI on port 8000). No mock data — all business screens call live APIs:

| Screen | Backend API |
|---|---|
| Sign up / Sign in / Logout | `/auth/signup`, `/auth/login`, `/auth/me` |
| Google sign-in | `/auth/google` (Google ID token) |
| Business dashboard, Reports, Settings, Alerts | `/woocommerce/stores/{id}/dashboard`, `/settings`, `/alerts` |
| Products & Inventory, Orders | `/woocommerce/stores/{id}/products`, `/orders` |
| My Stores (connect Shopify / WooCommerce) | `/shopify/*`, `/woocommerce/stores/*` |

Features without a backend implementation (social-media connections, AI post generator, post scheduling, comments, SEO, password reset) are shown as honest **"not available yet"** states — never fake data.

## Run Locally

Requires the backend running first (see `backend-fte/README.md` and the backend `.env` setup).

```bash
# 1. backend (from backend-fte/)
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
docker compose up -d postgres redis               # or a local PostgreSQL + Redis
# (fresh DB: see "Database setup" below)
uvicorn app.main:app --reload                     # → http://localhost:8000

# 2. frontend (from frontend-fte/)
npm install
npm run dev                                       # → http://localhost:3000
```

### Environment variables
Create `.env.local` in this folder:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
# Optional — leave empty to disable Google sign-in:
NEXT_PUBLIC_GOOGLE_CLIENT_ID=
```

- `NEXT_PUBLIC_API_URL` — where the backend runs.
- `NEXT_PUBLIC_GOOGLE_CLIENT_ID` — required only for Google sign-in. The Google button shows a friendly "not configured" message when it's missing. Get one from [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials → Create OAuth Client ID (Web application; authorize `http://localhost:3000`).

### Database setup (fresh database only)
The Alembic chain currently fails on a *brand-new* database because the WooCommerce migration creates enum types both standalone and inline in `create_table` (pre-existing migration bug — left untouched). Until that's fixed upstream, provision the schema from the app models and stamp Alembic:

```bash
cd backend-fte
./venv/Scripts/python.exe -c "import asyncio;from app.database import Base,engine;from app import models;from app.woocommerce import models as wc;exec('async def m():\n async with engine.begin() as c:\n  await c.run_sync(Base.metadata.create_all)\nasyncio.run(m())')"
./venv/Scripts/python.exe -m alembic stamp head
```

(If you have an existing database that already migrated fine, just run `alembic upgrade head`.)

## Notes

- Session handling: JWT stored in `localStorage` under `access_token`; expired sessions (HTTP 401) automatically return you to the login screen.
- The legacy developer dashboard at `components/woocommerce/WooCommerceDashboard.tsx` is superseded by the business dashboard (`app/components/BusinessDashboard.tsx`) and is excluded from the build.
