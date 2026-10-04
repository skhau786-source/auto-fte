# NEXT_STEPS

State when work stopped (2026-10-05): branch `all-merged`, working tree clean, **nothing pushed**.
Full background: `REPORT.md`.

## Next task: Security PR

Branch to create: **`security/support-ownership-and-rate-limit`**, started from **`collaboration/main`**
(not from `all-merged`), so the PR is small and reviewable on its own.

What goes into it:

| Item | Source | Status |
|---|---|---|
| Ownership on `/api/v1/support/*` (human-reply, close, list/get conversations, handoffs; `/handoffs` filters by store) | commit `96d4b86` | ready to cherry-pick |
| Ownership on `/api/v1/support/chat` | commit `1614dc4` | ready to cherry-pick |
| Chat `conversation_id` only accepted for the same store | **mixed inside `a01e51f`** ("bot silent in handoff"): only the `Conversation.store_id == store_id` filter in `handler.process_message` belongs here | must be extracted by hand |
| **429 fix** (plain `HTTPException(429)` returned 500 because `main.py` routed 429 to slowapi's handler) | **mixed inside `7a31492`** ("public website chat"): `Backend/src/domains/security/rate_limit_handler.py`, the `handle_429` lines in `Backend/src/main.py`, and the two `handle_429` tests in `tests/test_public_chat.py` | must be extracted by hand (it is not a separate commit) |
| **X-Forwarded-For fix** for the login rate limiter | **not done yet** | to write: `domains/security/rate_limiter.py` trusts the first `X-Forwarded-For` value, so the 5-attempt limit can be bypassed with a different header each time. Use `client_ip()` from `domains/security/sliding_window.py` (rightmost entry, only when `TRUST_PROXY_HEADERS=True`); that helper and the `TRUST_PROXY_HEADERS` setting (`sdk/config.py`) currently live in `7a31492` |

Suggested order: create the branch from `collaboration/main` → cherry-pick `96d4b86`, `1614dc4` → hand-extract the
`conversation_id` store filter and the 429 handler (+ tests) → write the X-Forwarded-For fix with a test → run
`pytest` → open the PR from the fork, not directly on Hassan's repo.

Test to include: another user gets 404 on every support endpoint, no login gets 401, `/handoffs` returns only the
caller's stores, a plain 429 returns 429 with `Retry-After` (not 500), a spoofed `X-Forwarded-For` does not reset the
login limit.

## Other pending work

**Before any PR**
- Get access to Hassan's repo (`git fetch collaboration` failed: "Repository not found") and rebase on his current `main`; expect conflicts in `main.py`, `handler.py`, `app/page.tsx`, the widgets.
- Push target: `all-merged` tracks `collaboration/main`. Do **not** run a bare `git push`; push to the fork explicitly (`git push origin <branch>`). Fix the git credential first (earlier push to `origin` returned 403).
- Split the rest into PRs: (1) workers + auth fixes, (2) RAG + inventory, (3) chatbot, inbox, public chat and widgets.
- Put the end-to-end scripts into the repo (e.g. `Backend/tests/e2e/`). They were written in a temp folder and are not saved; only unit tests with fakes exist.
- Run once against a real LLM (`GEMINI_API_KEY`); the LLM paths were only tested with fakes.
- Remove `frontend/public/demo-store.html` (developer page) before release; add the public widget to `README` / `CHATBOT_SETUP.md`.

**Known gaps (see REPORT.md section 6)**
- In-memory rate limiter → Redis-backed limiter.
- `visitor_sessions` rows are never cleaned up.
- Widget welcome text still talks about "the platform and your connected store".
- `NEXT_PUBLIC_GOOGLE_CLIENT_ID` is empty in the local `frontend/.env.local` (Google sign-in does not work locally).
- Knowledge-base retrieval is keyword-only (no embeddings).
- Widget exists twice (`Backend/chatbot_*` and `frontend/public/chatbot_*`) with different code.
- Unmerged `bilal` / `kulsoom` branches: nothing more is planned.

## Resume checklist (local machine)

1. Start Docker Desktop, then `cd Backend; docker compose start` (or `docker compose up -d postgres redis`). **Never `docker compose down -v`** (deletes the database volume).
2. Backend: `cd Backend; <venv>\Scripts\python -m uvicorn src.main:app --host 127.0.0.1 --port 8000` (workers start with it). There is no `.venv` in this worktree; `Digital-Fte-Startup\Backend\.venv` was used so far.
3. Frontend: `cd frontend; npm run dev` (http://localhost:3000). Use `127.0.0.1` for scripts; `localhost` adds ~2 s per request on this Windows machine.
4. Local-only files, git-ignored, never committed: `Backend/.env`, `frontend/.env.local`.
5. The test database `digital_fte_all` was dropped and recreated empty (the real `digital_fte` was never touched). It will fill again on first backend start. Demo user/store data are gone and must be re-seeded if needed.
6. Browser: site data for `http://127.0.0.1:3000` may still hold a `dfte_visitor_session_*` test key; clear it in Chrome if wanted.
