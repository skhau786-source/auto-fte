# Phases — Documentation & Organization Index

This directory is **documentation only**. It does not contain a second copy of
the application. `backend-fte/` and `frontend-fte/` remain the one and only
canonical, running codebase. Every file in here either:

1. Describes what already exists in `backend-fte/` or `frontend-fte/`
   (`README.md`, `implementation-map.md`, `source-location.md`), or
2. Is an explicitly-labelled `snapshot/` (none exist yet — see
   "Snapshots" below) that is never imported or executed.

Nothing was moved out of `backend-fte/` or `frontend-fte/` to build this
index. See `PHASE_ORGANIZATION_REPORT.md` at the repo root (or the chat
transcript that produced this directory) for the audit that backs these
documents.

## ⚠️ Important: two unrelated "Phase" numbering schemes exist in this repo

Before reading anything under `phase-3/` or `phase-4/`, understand that this
codebase already uses "Phase N" for something else, and it is **not** the
same numbering as this directory:

| Where | What "Phase N" means there |
|---|---|
| `backend-fte/README.md` (top of repo) | **Build order of the inventory subsystem**: Phase 1 = Inventory Management, Phase 3 = Reservation Engine, Phase 4 = Task/Allocation Engine, Phase 5 = WooCommerce Order Integration, Phase 6 = Aggregation Engine, Phase 7 = Unified Dashboard. Phase 2 was removed in the SaaS pivot. |
| `backend-fte/app/dashboard/unified_service.py` docstring | Same internal numbering as above (Phase 1/3/4/5/6), reused as source-code comments. |
| **This directory (`phases/`)** | The **product roadmap** phases the project owner uses: **Phase 3** = Inventory, Revenue Dashboard, Payment Integration, Advanced Analytics, Multi-language, WooCommerce. **Phase 4** = AI Agents, Capabilities, Agent Runtime, NL Tasks, Automation Workflows, Team Collaboration/Authorization/Filtering/Audit. |

These two schemes overlap in number only by coincidence — e.g. code-comment
"Phase 4" (Task Assignment/Allocation Engine, an inventory feature) is
**not** the same thing as roadmap "Phase 4" (AI Agents) documented here.
Where a source file's own comments use the internal numbering, the
`implementation-map.md` files below call that out explicitly so the two are
never conflated.

## Structure

```
phases/
├── README.md                  ← this file
├── phase-3/
│   ├── README.md               overview + status summary
│   ├── MANIFEST.md             feature/status/location table
│   ├── INVENTORY/
│   ├── REVENUE-DASHBOARD/
│   ├── PAYMENT-INTEGRATION/
│   ├── ADVANCED-ANALYTICS/
│   ├── MULTI-LANGUAGE/
│   └── WOOCOMMERCE/
└── phase-4/
    ├── README.md
    ├── MANIFEST.md
    ├── AI-AGENTS/
    ├── CAPABILITIES/
    ├── AGENT-RUNTIME/
    ├── NL-TASKS/
    ├── AUTOMATION-WORKFLOWS/
    ├── TEAM-COLLABORATION/
    ├── TEAM-AUTHORIZATION/
    ├── TEAM-FILTERING/
    └── TEAM-AUDIT/
```

Each feature folder contains:

- `README.md` — what the feature does, its status (🟢/🟡/🔴), and how it's used.
- `implementation-map.md` — every backend/frontend/test/migration file involved, with line-number anchors.
- `source-location.md` — the single canonical path(s) to edit; explicit "do not duplicate this" note for anything shared across features.

## Snapshots

Per the audit instructions, a phase folder may optionally contain a
`snapshot/` directory holding a **frozen, read-only copy** of a file for
reference, clearly separate from the canonical source. **No snapshots were
created in this pass** — none of the audited code was judged unstable or
hard enough to find that a frozen copy was worth the duplication risk. If
you want one for a specific file, ask and it will be added under
`snapshot/` with a banner comment, never mixed into `backend-fte/`.

## Status legend

🟢 COMPLETE — implemented, wired into the router/UI, and covered by passing tests.
🟡 PARTIAL — real code exists but is incomplete, untested end-to-end, or has a known gap (documented in that folder's README).
🔴 NOT IMPLEMENTED — no functional implementation found, regardless of how related the surrounding infrastructure looks.
