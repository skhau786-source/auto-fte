# Digital-Fte-all — merge, port and feature report

Branch: `all-merged` (git worktree `D:\Digital-FTE\Digital-Fte-all`), created from `collaboration/main`
(Hassan's repo, commit `51515e4`). Everything is local. **Nothing has been pushed.**

Last verified: 2026-10-05 — backend tests **81 passed**, `next build` **passes**.

---

## 1. Branches

The `collaboration` remote (`HassanAliJunejo/Digital-Fte-Startup`) could not be fetched during this work
("Repository not found": the stored git credential has no access). Everything below is based on the four
branches that were already cached locally (their last commits are dated 2026-08-22 … 2026-09-22), so branches or
commits created after that are **not** covered.

| Branch | Author (last commit) | Structure | Result |
|---|---|---|---|
| `main` | Laiba Jabbar | `Backend/` + `frontend/` | **Base** of `all-merged` |
| `sync-backend` | Tehamee10 | `Backend/` + `frontend/` | **Skipped — duplicate.** Already contained in `main` (PR #3), nothing to add |
| `kulsoom` | code0324 | `backend-fte/`, `frontend-fte/`, `phases/`, `testing-frontend/` — **unrelated history**, different app layout (UUID ids, organizations) | **Not merged.** Merging would have put a second backend and a second frontend next to `Backend/`/`frontend/`. Its unique features were ported by hand instead (section 2) |
| `bilal` | Bilal-Rafique-coder | `backend-fte/`, `backend-merge/`, `backend_merge/`, `frontend-fte/` — **unrelated history**, three more backend copies | **Skipped.** Same reason; nothing was ported |
| `fix/workers-and-auth` (local, from Digital-Fte-Startup) | — | same layout as `main` | Fast-forward merged: worker fixes + email/Google login |

`Digital-Fte-Startup` and `Digital-Fte-merged` were not modified.

## 2. What was ported from `kulsoom`

Only what `Backend/` did not already have, adapted to its structure (integer ids, `sdk/models`, `domains/…`).
No `backend-fte/` folder exists in this branch.

| Feature | Where | Notes |
|---|---|---|
| RAG knowledge bases (documents, chunking, retrieval, audit) | `sdk/models/rag.py`, `domains/chatbot/rag_*.py` | kulsoom's version was unfinished: embeddings were a placeholder, similarity was always `1.0`, uploads crashed on a bad kwarg, chunks were not deleted. Fixed. Retrieval is **keyword overlap**, not embeddings |
| Stock ledger + manual/bulk adjustments + history | `sdk/models/inventory.py`, `domains/ecommerce/inventory_*.py` | row-locked, rejects negative stock, refreshes low-stock alerts |
| Stock reservations (reserve / commit / release / expire / cancel order) | `domains/ecommerce/reservation_*.py` | 60 s expiry sweep in the app lifespan; double-release prevented by row locks (kulsoom's partial release dropped) |
| Inventory aggregation + report | `domains/ecommerce/aggregation_*.py` | fast movers / dead stock now come from real order items (kulsoom derived them from stock level) |
| Not ported | — | warehouse allocation (kulsoom removed warehouses itself), admin/retry queue (tied to its Shopify queue), embeddings (placeholder) |

## 3. Features and commits (oldest → newest)

| Area | Commit | What |
|---|---|---|
| Workers | `5f37219` | Worker startup fixes across 7 agent workers, `agent_base`, layout |
| Auth | `c408902` | Email login/signup and Google `id_token` flow connected to `/auth/*` |
| RAG | `d31bd44` | Knowledge-base API under `/chatbot/rag` |
| RAG | `7d58d2a` | Stopword filtering; `/inventory/items` endpoint |
| Inventory | `da10f59` | Stock ledger, adjust, bulk adjust, history |
| Inventory | `fec0c78` | Reservation engine |
| Inventory | `2e7e77e` | Aggregation and reports |
| Bug fix | `f5ac53b` | `/products`, `/products/{id}`, `/orders` returned 500 (`MissingGreenlet`) |
| UI | `c62f721` | `/inventory` (overview, stock + adjust dialog, reservations, history) and `/knowledge-base` |
| UI | `d139674` | Dashboard sidebar "Live tools" links and banner |
| Chatbot | `8ad04df` | Customer chatbot answers from the owner's knowledge base |
| Chatbot | `1f25702` | Refund / return **policy questions** answered from the knowledge base; real refund requests still go to a human |
| Chatbot | `0e76650` | "Did not understand" reply instead of showing an arbitrary product |
| Chatbot | `4786e63` | That reply now lists topics to ask about and offers "talk to human" |
| Inbox | `5edae8c` | Owner support-inbox API (list, thread, reply, status), store-scoped |
| Inbox | `c76c660` | `/inbox` UI (Needs you / With bot / Resolved, reply, resolve, hand back to bot) |
| Handoff | `a01e51f` | Bot stays silent while a chat is in handoff (one "team will reply" notice) |
| Handoff | `b3800f5` | A resolved chat reopens when the customer writes again |
| Polling | `a9e944d` | Widgets poll support replies ("Support team" label); fixes the pro widget that never loaded |
| Security | `96d4b86`, `1614dc4` | Ownership checks on `/api/v1/support/*` (section 4) |
| Public chat | `7a31492` | Anonymous website chat: public key, visitor sessions, rate limits, CORS; **also the 429 bug fix** |
| Public chat | `3aaa650` | Widget `data-store-key` mode + `frontend/public/demo-store.html` |
| Public chat | `7fd2be8` | Inbox "Website chat widget" panel (embed code, on/off, rotate key) |
| Cleanup | `ca6330c`, `f896803`, `5e73939` | Stop tracking `tsbuildinfo`; fix `next build`; env examples |

## 4. Security

| Before | Now |
|---|---|
| `POST /api/v1/support/conversations/{id}/human-reply`, `/close`, `GET /conversations`, `GET /conversations/{id}`: any **logged-in** user could read, answer or close **any store's** chats | 404 unless the store belongs to the caller; 401 without login (`96d4b86`) |
| `GET /api/v1/support/handoffs` ignored `store_id` and returned handoffs of **all stores** | Filters by store; with no filter returns only the caller's own stores |
| `POST /api/v1/support/chat` accepted any `store_id` | 404 for a store the caller does not own (`1614dc4`) |
| Chat `conversation_id` was accepted for any store (a user could inject messages into another store's conversation) | The conversation must belong to the same store, otherwise a new one is started (`a01e51f`) |
| Widgets read the token from `access_token`/`token`/`jwt` while the app stores `digital-fte-token`, so the widget never saw the login | `digital-fte-token` is read too (`a9e944d`) |
| `HTTPException(429)` crashed slowapi's handler → **500** instead of 429 (the existing login limiter too) | A wrapper handles slowapi's and plain 429s, with `Retry-After` (`7a31492`) |
| Anonymous visitors had no safe path | Public endpoint: visitor sees only their own chat (session token bound to one store and one conversation, hash stored, 404 otherwise); order lookup and cart are closed in public mode and handed to a human; per-IP and per-session limits; `X-Forwarded-For` ignored unless `TRUST_PROXY_HEADERS` |

**Still open (not changed in this branch):**
- `domains/security/rate_limiter.py` (login limiter) trusts the first `X-Forwarded-For` value, so the 5-attempt limit can be bypassed by sending a different header each time. `security/sliding_window.client_ip` is the safe replacement.
- `frontend/public/demo-store.html` is a developer test page that would be served in production; remove it or move it to docs before release.
- Public CORS is `*` for `/api/v1/public/*` only (no cookies are used). The rest of the API keeps `CORS_ORIGINS`.
- The public key is an identifier, not a secret (it appears in page source). Rotate it from the inbox panel if abused.
- The unmerged `kulsoom` branch tracks `backend-fte/.env.production` and `.env.staging`. No secret-looking values were found, but if they ever held real ones, rotate them.

## 5. Tests

Backend, `cd Backend && python -m pytest -q` → **81 passed** (re-run on 2026-10-05).

| File | Tests |
|---|---|
| `test_llm_client.py` (existing) | 7 |
| `test_seo_insights.py` (existing) | 5 |
| `test_rag_chunking.py` | 9 |
| `test_support_knowledge.py` | 36 |
| `test_support_handoff.py` | 9 |
| `test_public_chat.py` | 15 |

Frontend: `npx tsc --noEmit` clean, `npm run build` succeeds (3 new routes). There are no frontend unit tests.

**What the tests do not cover:** they are unit tests with fakes. The HTTP behaviour (ownership 404/401, session isolation,
429s, owner inbox ↔ visitor widget, key rotation, CORS) was checked with live end-to-end runs against a real database and
in a real browser, but those scripts are **not in the repo**. There are no DB-backed integration tests yet.

## 6. Known limitations

- **Rate limiter is in-memory, per process.** With several workers each has its own counters; a restart resets them. Use a Redis-backed limiter for production.
- **`visitor_sessions` is never cleaned up.** Sessions older than 30 days stop working, but the rows stay.
- **Widget welcome text** still says "…platform and your connected store", which reads oddly to a store visitor.
- **Google sign-in:** `NEXT_PUBLIC_GOOGLE_CLIENT_ID` is empty in the local `frontend/.env.local`, so the Google button does not work locally.
- **`GEMINI_API_KEY` is empty:** the bot answers extractively (best passage / catalog data). The LLM paths (knowledge answers, `NOT_COVERED` fallthrough) are unit-tested with fakes but were **never run against a real model**.
- Knowledge-base retrieval is keyword-based (no synonyms: "refund" ≠ "money back").
- Stock adjustments and reservations are local only; platform connectors are read-only, so the next platform sync can overwrite them.
- No Alembic migrations exist in the repo; tables are created by `init_db()` at startup. This branch only adds **new** tables (`knowledge_bases`, `rag_*`, `stock_movements`, `stock_reservations`, `store_public_keys`, `visitor_sessions`), no changes to existing ones.
- The widget exists twice (`Backend/chatbot_*` and `frontend/public/chatbot_*`) and the copies differ; the one the app loads is `frontend/public/`.
- The cached `collaboration` branches are old; `all-merged` has not been compared with Hassan's current `main`.

## 7. Environment keys (names only)

**Backend** (`Backend/.env`, template: `Backend/.env.example`)
- Needed to run locally: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ENCRYPTION_KEY`, `CORS_ORIGINS`, `FRONTEND_URL`, `ENV`, `DEBUG`
- Google sign-in: `GOOGLE_CLIENT_ID`
- LLM: `GEMINI_API_KEY` (support agent) and `LLM_API_KEY` / `LLM_MODEL` (shared SDK), `IMAGE_MODEL_DEFAULT`, `DALLE_API_KEY`
- Email: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`
- Platforms: `SHOPIFY_API_KEY`, `SHOPIFY_API_SECRET`, `SHOPIFY_SCOPES`, `SHOPIFY_REDIRECT_URI`, `WOOCOMMERCE_REDIRECT_URI`, `BIGCOMMERCE_CLIENT_ID`, `BIGCOMMERCE_CLIENT_SECRET`, `BIGCOMMERCE_REDIRECT_URI`, `AMAZON_CLIENT_ID`, `AMAZON_CLIENT_SECRET`, `AMAZON_REDIRECT_URI`, `AMAZON_REFRESH_TOKEN`, `DARAZ_APP_KEY`, `DARAZ_APP_SECRET`, `DARAZ_REDIRECT_URI`, `BACKEND_PUBLIC_URL`, `FRONTEND_SUCCESS_URL`
- Social: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`
- Other: `APP_NAME`, `APP_VERSION`, `REDIS_PASSWORD`, `ORCHESTRATOR_URL`, `AGENT_TOKEN`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `RATE_LIMIT_LOGIN_MAX_ATTEMPTS`, `RATE_LIMIT_LOGIN_WINDOW_SECONDS`, `LOW_STOCK_THRESHOLD`, `ORDERS_SYNC_DAYS`
- Public website chat (all optional): `PUBLIC_CHAT_ENABLED`, `PUBLIC_CHAT_MAX_QUERY_CHARS`, `PUBLIC_CHAT_SESSION_TTL_DAYS`, `PUBLIC_CHAT_CHAT_PER_IP_PER_MINUTE`, `PUBLIC_CHAT_CHAT_PER_SESSION_PER_MINUTE`, `PUBLIC_CHAT_POLL_PER_IP_PER_MINUTE`, `PUBLIC_CHAT_POLL_PER_SESSION_PER_MINUTE`, `PUBLIC_CHAT_NEW_SESSIONS_PER_IP_PER_HOUR`, `TRUST_PROXY_HEADERS`
- `ENV=production` additionally requires a strong `SECRET_KEY` (32+ chars) and `CORS_ORIGINS` other than `*`.

**Frontend** (`frontend/.env.local`, template: `frontend/.env.example`)
`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_GOOGLE_CLIENT_ID`, `NEXT_PUBLIC_CHATBOT_PLAN` (optional)

`.env` and `.env.local` are git-ignored and were never committed.

## 8. How to run it (Windows, PowerShell)

Prerequisites: Docker Desktop, Python 3.11, Node 20+.

1. **Config**
   ```powershell
   cd Digital-Fte-all
   Copy-Item Backend\.env.example Backend\.env        # then set SECRET_KEY, ENCRYPTION_KEY (and keys you need)
   Copy-Item frontend\.env.example frontend\.env.local
   ```
2. **Postgres + Redis (Docker)** — ports 5434 / 6380, database `digital_fte`
   ```powershell
   cd Backend
   docker compose up -d postgres redis
   ```
   Never run `docker compose down -v` — it deletes the database volume.
3. **Backend** (tables are created on startup; no migration step)
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   .\.venv\Scripts\python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
   ```
   Health: http://127.0.0.1:8000/health — API docs: http://127.0.0.1:8000/docs
4. **Workers** start automatically inside the backend process (the log shows `Worker started: …` for inventory_sync,
   content_scheduling, content_generation, comment_engagement, customer_support, analytics_insights,
   collaboration_orchestrator, seo_insights, customers), plus the 60 s reservation-expiry sweep.
   One worker can also run alone: `python -m src.domains.agents.inventory_sync.worker` (the same pattern exists for
   analytics_insights, collaboration_orchestrator, comment_engagement, content_generation, content_scheduling, customer_support).
5. **Frontend**
   ```powershell
   cd ..\frontend
   npm install
   npm run dev          # http://localhost:3000   (production: npm run build; npm start)
   ```
6. **Tests**: `cd Backend; .\.venv\Scripts\python -m pytest -q`
7. **Try it**: sign up on the site, connect/seed a store, then open `/inventory`, `/knowledge-base`, `/inbox`.
   For the anonymous visitor chat open `/inbox` → "Website chat widget" → copy the embed code, or use
   `http://localhost:3000/demo-store.html?key=<public key>&api=http://127.0.0.1:8000`.

Windows tip: use `127.0.0.1` rather than `localhost` for scripts and API calls; `localhost` falls back from IPv6 and adds ~2 s per request.

Embed code for a store website:
```html
<script src="https://YOUR-APP/chatbot_free/chatbot.js"
        data-store-key="pk_…" data-api-url="https://YOUR-API" async></script>
```
