# Digital FTE — merged project report

Branch: `merged-all` (local only, nothing was pushed to GitHub).
Built from `main`, then `collaboration/bilal` and `kulsoom` merged in with `--no-ff`.

## 1. What was merged

| Order | Branch | What it brought |
|---|---|---|
| base | `main` | `backend-fte` (FastAPI) + `frontend-fte` (Next.js) |
| 1 | `collaboration/bilal` | Instagram connect/publish, AI post generation, brand profile, notifications, scheduler, social UI |
| 2 | `kulsoom` | Inventory on real PostgreSQL, RAG system, subscriptions/Stripe, AI agent modules |

**Not merged**

- `collaboration/main` and `collaboration/sync-backend`: a separate project history (`Backend/`, `frontend/` folders, no common ancestor with `main`). Merging would put a second copy of the app next to this one.
- `backend-merge/` and `backend_merge/` folders inside bilal's branch (duplicate copies of `backend-fte`).
- The `collaboration` remote could not be fetched (private / needs credentials), so those branches are the copies that were already on disk (latest from 2026-09-11).

## 2. Conflicts and what was kept

| File | Kept | Why |
|---|---|---|
| `auth/routes.py`, `auth/service.py`, `security.py`, `schemas.py` | `main` | JWT access tokens and password rules live in `main`'s version |
| `alembic/versions/694d38b99c0b_init.py` | `main` | Every other migration chains off it |
| `Dockerfile`, `docker-compose.yml`, `README.md`, `commands_for_sql.txt`, frontend `.gitignore`/`README` | `main` | Production setup is `main`'s |
| `frontend-fte/app/page.tsx` | `main` at `/`; bilal's UI moved to `/social` | Two unrelated UIs (828 vs 2052 lines) |
| `app/models.py` | `main` + bilal's social models + kulsoom's RAG imports | Both sets of tables are needed |
| `app/config.py` | `main` + bilal's settings + kulsoom's Stripe settings | Bilal's keys made optional (default empty) so the app starts without them |
| `app/main.py` | `main` + bilal's routers + kulsoom's RAG/billing routers | Also includes the `brand` router, which bilal's own `main.py` never registered |
| `requirements.txt` | union | `huggingface_hub` raised to `>=0.28` (bilal's code needs the `provider=` argument; his pin of 0.26.2 did not support it) |
| `.gitignore` | union | |
| Compiled `.pyc` files | removed from tracking | |

Migration chain: bilal's chain was re-parented onto `remove_warehouse` (`37675f9e7c59`), then a merge revision `merge_bilal_kulsoom` joins it with kulsoom's heads. `alembic heads` shows exactly one head.

## 3. Added after the merge

- **Organizations:** `POST /organizations`, `GET /organizations/me`. Without these, agents, RAG and subscriptions all answered "User is not a member of any organization".
- **Support chat bot** (`/support-chat`): English + Roman Urdu. Rules answer price/stock from the store's products, look up order status and hand the customer over to the owner (exact numbers, no model involved). Owner endpoints list and resolve handoffs.
- **LLM fallback for the chat bot** (`app/support_chat/llm.py`): when the rules cannot help (unclear message, or no product matched) and `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` is set, the model answers from the store's real data only (matching products, a catalog sample, and FAQ snippets from the owner's RAG knowledge bases). It replies in the customer's language, can ask for a human handoff, ignores instructions inside customer messages, times out after 15 s, and is limited to 20 calls per chat session per hour. Without a key, or on any model error, the rule-based reply is used. The API response has a `source` field (`rules` or `llm`).
- **Chat widget:** public page `/chat?store=<store id>`, owner inbox `/chat/inbox`, and a widget plus "customers waiting" badge inside the owner dashboard.
- **Migration `rag_support_chat_001`:** creates the RAG tables (they had no migration) and `support_handoffs`.
- **Bug fixes:** ORM enums now use the lowercase values stored in the database (organization role, plan tier, subscription status, AI agent/task enums); creating an organization used to fail with a 500. `requirements.txt` had two lines glued together. `app/social/page.tsx` type errors fixed.

## 4. Status

### Works (tested)
- Backend starts cleanly; all merged routers register (auth, inventory, Shopify, WooCommerce, AI, RAG, subscriptions, Instagram, AI posts, brand, organizations, support chat).
- Signup and login; inventory list, search, low-stock and unified dashboard against PostgreSQL.
- Create organization, create AI agent, create knowledge base, upload a document and search it (keyword search).
- Support chat via API and in a real browser: English and Roman Urdu price/stock, "not found" answers, handoff, saving the customer's phone number, owner inbox, resolve, and owner-only access.
- `npm install`, `npx tsc --noEmit` and `npm run build` all pass.
- `pip check` reports no broken requirements; `alembic heads` shows one head.

### Does not work or is untested
- **AI agent tasks and the chat bot's LLM fallback** need `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`; none is set. The fallback is covered by 30 automated tests and an end-to-end run with a fake model, but has **not been run against a real model**. RAG uses keyword search because no embeddings key is set.
- **Chat bot order status** is only tested for "order not found": the database has no WooCommerce orders. There is no order table for Shopify, so order lookup works for WooCommerce orders only.
- **Without an LLM key the bot is keyword-based:** unusual wording can be mistaken for a product name and answered with "no product found".
- **Handoffs do not email or notify the owner;** the owner has to open the inbox (the dashboard badge refreshes every 30 s).
- **The chat endpoint is public** (anyone with a store id can use it) and has no rate limiting yet.
- **Instagram connect** returns a URL with an empty `client_id` until Instagram keys are set; `/posts/generate` and publishing were not run (need Groq/HuggingFace/Instagram credentials).
- **Stripe billing** was not exercised (no keys).
- The social scheduler (`app/scheduler/scheduler_service.py`) is a separate process and is not started by the app.
- The dashboard widget uses the owner's first Shopify store; there is no store picker. Dashboard "stores" are WooCommerce stores, while the chat bot answers from the Shopify `stores` table where the products live.
- Docker Compose, Celery workers and nginx were not started or tested.

## 5. What you still need to provide or build

**Environment variables** (copy `backend-fte/.env.example` to `backend-fte/.env`; never commit `.env`):

| Needed for | Variables |
|---|---|
| Required | `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY` (change the default) |
| AI agents + chat bot LLM fallback | `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` (optional: `SUPPORT_CHAT_LLM_ENABLED`, `SUPPORT_CHAT_LLM_TIMEOUT`, `SUPPORT_CHAT_LLM_PER_SESSION_HOUR`) |
| Instagram + AI posts | `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, `INSTAGRAM_REDIRECT_URI`, `GROQ_API_KEY`, `HUGGINGFACE_API_TOKEN` |
| Shopify | `SHOPIFY_API_KEY`, `SHOPIFY_API_SECRET`, `SHOPIFY_WEBHOOK_SECRET`, plus Admin API access for the store |
| Stripe | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` |
| Google sign-in | `GOOGLE_CLIENT_ID` (backend) and `NEXT_PUBLIC_GOOGLE_CLIENT_ID` (frontend) |
| Email | `SMTP_USER`, `SMTP_PASSWORD`, `EMAILS_FROM_EMAIL` |

Frontend: `frontend-fte/.env.local` with `NEXT_PUBLIC_API_URL=http://localhost:8000`.

**To build or decide**
- Check `backend-fte/.env.production` and `.env.staging`: they are tracked in git on `main`. Make sure they hold no real passwords, and consider untracking them.
- Try the chat bot's LLM fallback with a real key and tune the prompt on real conversations (the FAQ part reads the owner's organization knowledge bases, so upload shipping/returns documents there).
- Owner notification on handoff (email / push), and rate limiting on `/support-chat/message`.
- A store picker in the dashboard widget; embed snippet for customers' own websites.
- Real Shopify order lookup for the chat bot.
- Clean up bilal's `app/social/page.tsx` further (it still contains mock data) and decide whether to bring over anything from `collaboration/main`.
- If you want the latest `collaboration` branches, give git access to that repository and fetch again.

## 6. Run it again later

Prerequisites: Docker Desktop, Python 3.13 with a virtualenv, Node.js.

```powershell
# 1. Database and Redis
docker start digital-fte-postgres     # Postgres on port 5433 (container already exists)
#    Redis: the dapr_redis container on 6379 (or any Redis at REDIS_URL)

# 2. Backend (first time: create the venv and install)
cd backend-fte
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
copy .env.example .env                 # then fill in the values above
.\venv\Scripts\python -m alembic upgrade head
.\venv\Scripts\python -m uvicorn app.main:app --port 8000

# 3. Frontend (new terminal)
cd frontend-fte
npm install
npm run dev                            # http://localhost:3000
```

On Windows, if the frontend fails with `Cannot find module '../lightningcss.win32-x64-msvc.node'`, run
`npm install --no-save lightningcss-win32-x64-msvc@1.32.0` in `frontend-fte` (the lockfile does not list the Windows binary).

**URLs**

| What | URL |
|---|---|
| Dashboard (login, inventory, AI agents, chat widget) | http://localhost:3000 |
| Instagram / social UI | http://localhost:3000/social |
| Customer chat | http://localhost:3000/chat?store=`<store id>` |
| Owner chat inbox | http://localhost:3000/chat/inbox |
| API docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |

Store ids and chat links are listed on the inbox page after you sign in.

**Production build check:** `cd frontend-fte && npm run build`.
