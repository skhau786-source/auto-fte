# PROGRESS — saved state when work was paused

Date saved: 2026-10-03. Working folder: `D:\Digital-FTE\Digital-Fte-merged` (a git worktree of the repo in `D:\Digital-FTE\Digital-Fte-Startup`), branch `merged-all`.
**Nothing has been pushed to GitHub.** All work is local.

## Git state
- Branch `merged-all`, last commit `72c9979` ("Add LLM fallback to the support chat bot").
- Working tree clean, no merge in progress, **0 unresolved conflicts**.
- `main`, `kulsoom` and the `collaboration/*` branches were not modified.

## Branches
| Branch | Status |
|---|---|
| `collaboration/bilal` | **Merged** (all conflicts resolved) |
| `kulsoom` (= `origin/kulsoom`, `collaboration/kulsoom`) | **Merged** (all conflicts resolved) |
| `collaboration/main` | **Not merged** (on purpose): unrelated history, separate `Backend/` + `frontend/` layout (5 commits) |
| `collaboration/sync-backend` | **Not merged** (on purpose): older part of `collaboration/main` (2 commits) |

The `collaboration` remote could not be fetched (private / needs credentials), so its branches are older local copies (latest 2026-09-11).

## Conflicts still to resolve
**None.** Every conflict from the two merges is resolved and committed. See `MERGED_PROJECT.md` section 2 for each file and which side was kept.
Only if `collaboration/main` is merged later will new conflicts appear (expected: many add/add, since it is a second copy of the app).

## What is done
- bilal + kulsoom merged; one Alembic head (`rag_support_chat_001`); local DB already migrated to it.
- Organization routes, support chat bot (English + Roman Urdu), chat widget on `/chat` and inside the dashboard, owner inbox `/chat/inbox`.
- LLM fallback for the chat bot (code + 30 tests; not run against a real model, no API key yet).
- Frontend `npm run build` and `tsc --noEmit` pass; backend starts cleanly.
- Final report: `MERGED_PROJECT.md`.

## Next steps (in order)
1. Start everything again (commands below) and check http://localhost:3000 and http://localhost:8000/docs.
2. Add `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` to `backend-fte/.env`, restart the backend, and try the chat bot with real questions (English + Roman Urdu); tune the prompt in `backend-fte/app/support_chat/llm.py`.
3. Review `backend-fte/.env.production` and `.env.staging` (tracked in git on `main`): make sure no real passwords are in them.
4. Decide about `collaboration/main` (merge / port selected features / skip). If you want its latest version, give git access to the `collaboration` repo and run `git fetch collaboration`.
5. Remaining ideas: per-IP rate limiting on `/support-chat/message`, owner notification (email) on handoff, store picker in the dashboard widget, real Shopify order lookup, embed snippet for customers' sites.
6. When happy: decide yourself whether and where to push `merged-all` (not done, needs your OK).

## Start again later
```powershell
# 1. Open Docker Desktop, then:
docker start digital-fte-postgres           # Postgres on port 5433, data is kept
docker start dapr_redis                      # Redis on 6379 (only if it is not already running)

# 2. Backend
cd D:\Digital-FTE\Digital-Fte-merged\backend-fte
D:\Digital-FTE\Digital-Fte-Startup\backend-fte\venv\Scripts\python.exe -m alembic upgrade head
D:\Digital-FTE\Digital-Fte-Startup\backend-fte\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# 3. Frontend (new terminal)
cd D:\Digital-FTE\Digital-Fte-merged\frontend-fte
npm run dev
```
Notes
- `backend-fte/.env` and `frontend-fte/.env.local` in this folder are copies (git-ignored, never committed). The frontend's `node_modules` here is a junction to `D:\Digital-FTE\Digital-Fte-Startup\frontend-fte\node_modules`, so keep that folder.
- The virtualenv used is the one in `D:\Digital-FTE\Digital-Fte-Startup\backend-fte\venv`.
- The original folder `D:\Digital-FTE\Digital-Fte-Startup` is on branch `kulsoom` and untouched.

## URLs
- Dashboard: http://localhost:3000
- Social / Instagram UI: http://localhost:3000/social
- Customer chat: http://localhost:3000/chat?store=d4566c88-33c7-4ecb-8a76-8b871e876a28
- Owner chat inbox: http://localhost:3000/chat/inbox
- API docs: http://localhost:8000/docs

## Test data left in the local database
- User `t17627@example.com` with organization "Test Shop" (one test AI agent "Stock watcher", one knowledge base "FAQ" with a shipping-policy document). Created while testing; safe to delete.
