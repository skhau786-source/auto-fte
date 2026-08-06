# Digital FTE — Backend API Testing Frontend

A minimal React + Vite + TypeScript + TailwindCSS + Axios app for manually testing the
Digital FTE backend APIs. Simple forms and tables only — no state management, no charts, no AI.

## Pages

| Page | API call |
|---|---|
| Login | `POST /auth/login` |
| Register | `POST /auth/signup` |
| Dashboard | `GET /dashboard/unified` (auth) |
| Products | `GET /inventory` (auth) |
| Inventory | `GET/POST /inventory`, `PUT/DELETE /inventory/{id}` (auth) |
| Orders | `GET /orders/dashboard`, `GET/POST /orders/{id}/allocation|reservations|allocate|commit|release` |
| API Health | `GET /health`, `/live`, `/version`, `/ready`, `/metrics` |

## Requirements

- Node.js ≥ 20 (tested with v24)
- FastAPI backend running on `http://localhost:8000`

## Run

```bash
# 1. Backend (from backend-fte/)
cd backend-fte
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. This frontend (from testing-frontend/)
cd testing-frontend
npm install
npm run dev
```

Then open **http://localhost:3000** in the browser.

> ⚠️ Use `http://localhost:3000` (not `127.0.0.1:3000`). The backend's CORS allowlist
> (`CORS_ORIGINS` in `backend-fte/.env`) currently contains `http://localhost:3000`
> but not the loopback IP form. Change `VITE_API_URL` in `.env` if the backend is on another host.

## Build / typecheck

```bash
npm run build     # tsc --noEmit && vite build
npm run preview   # serve the production build
```

## Notes on current backend behavior (as of 2026-08-06 verification)

- `/health`, `/live`, `/version`, `/metrics` return 200; `/ready` returns 503 until the
  project's PostgreSQL is reachable (port 5432 was occupied by an unrelated container).
- `/auth/signup` and `/auth/login` return 500 until the database is reachable, and there is a
  known `passlib 1.7.4` + `bcrypt 5.0.0` incompatibility (`hash_password()` crashes) that must
  be fixed for auth to work even with a healthy DB.
- The backend currently issues no JWT (`create_access_token` is never called), so protected
  endpoints always return 401 unless you paste a token via the header field.
- The Bearer token box in the top bar saves a token to `localStorage` and attaches it to every
  request via an Axios interceptor.
