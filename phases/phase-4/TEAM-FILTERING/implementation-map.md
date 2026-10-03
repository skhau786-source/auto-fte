# 4.6C Team/Task/Workflow Visibility — Implementation Map

## Backend — `backend-fte/app/ai/service.py` (`AIService`)

| Method | Line | Purpose |
|---|---|---|
| `get_visible_agent_ids` | 548 | Set of agent IDs visible to the current user |
| `get_visible_team_ids` | 573 | Sibling helper added by the 4.6D fix, see `../TEAM-AUDIT/` |
| `list_tasks` (filtering block) | ~665-670 | Filters the task list to visible agents |
| `check_task_access` | 599 | Per-task enforcement, raises `TaskNotFoundError` if denied |
| `get_task` | 675 | Calls `check_task_access` |
| `approve_task` / `reject_task` | 703 / 759 | Call `check_task_access` |
| `execute_capability` | 1267 | Calls `check_task_access` |
| `handoff_task` | 1357 | Calls `check_task_access` on parent task |

(Line numbers as of 2026-08-26, after the 4.6D audit-trail fix.)

## Depends on

- `TeamService.get_user_accessible_agent_ids` and `can_access_agent` — see
  `../TEAM-AUTHORIZATION/implementation-map.md`.

## Tests — `backend-fte/tests/test_ai_team_filtering.py` (967 lines)

| Test class | Line | Covers |
|---|---|---|
| `TestGetUserAccessibleAgentIds` | 138 | `get_user_accessible_agent_ids` |
| `TestListTasksTeamFiltering` | 249 | Task list filtering |
| `TestGetTaskTeamAccess` | 390 | Single-task access |
| `TestCrossOrgIsolation` | 508 | Org boundary enforcement |
| `TestRBACEnforcement` | 529 | RBAC + team interaction |
| `TestWorkflowTeamFiltering` | 625 | Workflow visibility |
| `TestCheckTaskAccess` | 703 | `check_task_access` directly |
| `TestNoInformationLeakage` | 816 | 404-not-403 behavior |
| `TestEdgeCases` | 856 | Edge cases |
