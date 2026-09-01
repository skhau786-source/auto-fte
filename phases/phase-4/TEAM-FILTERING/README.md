# 4.6C Team/Task/Workflow Visibility — 🟢 COMPLETE

Ensures a user only ever sees tasks, agents, and workflows belonging to
agents they have team access to — including a deliberate anti-leakage
design choice.

## What it does (`app/ai/service.py`, `AIService`)

- `get_visible_agent_ids` (548) — the set of agent IDs the current user may
  see; internal/system execution (`user_id is None`) bypasses filtering and
  sees all org agents, otherwise delegates to
  `TeamService.get_user_accessible_agent_ids` (see `../TEAM-AUTHORIZATION/`).
  Its sibling `get_visible_team_ids` (573), added by the 4.6D fix (see
  `../TEAM-AUDIT/`), follows the identical pattern for audit-action
  filtering rather than task filtering.
- List filtering: `list_tasks` (query starting line 640) fetches all
  org tasks then filters to `t.agent_id in visible_agent_ids` (around
  lines 665-670) — post-query filtering in Python, not a SQL-level
  `WHERE` (contrast with `get_agent_actions`'s SQL-level filtering,
  `../TEAM-AUDIT/`).
- `check_task_access` (599) — single-item enforcement for `get_task` (675),
  `approve_task`/`reject_task` (703, 759), `execute_capability` (1267),
  and `handoff_task` (1357).
- **Deliberate information-leakage prevention**: an unauthorized
  `get_task` raises `TaskNotFoundError` — the *same* exception as a
  genuinely nonexistent task — specifically so a user cannot distinguish
  "this task doesn't exist" from "this task exists but belongs to a team
  you can't see" (`service.py:599-610` docstring, confirmed in code at
  `check_task_access`'s caller in `get_task`).
- Workflow visibility reuses the same `check_team_agent_access` checkpoint
  at the router level (`create_and_execute_workflow` line 888,
  `list_workflows` line 1049 — see `../TEAM-AUTHORIZATION/`), rather than a
  separate workflow-specific filtering method.

(Line numbers as of 2026-08-26, after the 4.6D audit-trail fix added code
earlier in `service.py` — see `../TEAM-AUDIT/README.md`.)

## Status detail

| Piece | Status | Evidence |
|---|---|---|
| Task list filtering | 🟢 | `service.py:665-670` |
| Task single-item access check | 🟢 | `service.py:599-624`, called from 5 sites |
| Anti-leakage design (404 not 403) | 🟢 | `service.py:599-610` docstring + `get_task` implementation |
| Workflow visibility | 🟢 | via `check_team_agent_access` at router level, not a separate filter method |
| Cross-org isolation | 🟢 | `tests/test_ai_team_filtering.py::TestCrossOrgIsolation` (line 508) |
| No-information-leakage tests | 🟢 | `tests/test_ai_team_filtering.py::TestNoInformationLeakage` (line 816) |
| Tests | 🟢 | `tests/test_ai_team_filtering.py` (967 lines, 9 test classes) |

## Full detail

- [`implementation-map.md`](./implementation-map.md)
- [`source-location.md`](./source-location.md)
