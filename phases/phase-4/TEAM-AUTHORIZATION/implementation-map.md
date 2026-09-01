# 4.6B Team-Level Authorization — Implementation Map

## Backend — `backend-fte/app/ai/team_service.py` (`TeamService`)

| Method | Line | Purpose |
|---|---|---|
| `user_is_team_member` | 479 | Membership check |
| `user_can_manage_team` | 488 | Management-rights check |
| `agent_belongs_to_team` | 499 | Agent-team relationship check |
| `can_access_agent` | 508 | Core access check |
| `can_user_access_agent` | 546 | User-facing wrapper of the above |
| `get_user_accessible_agent_ids` | 560 | Set of accessible agent IDs — foundation for `../TEAM-FILTERING/` |
| `_get_org_member` | 684 | Resolve `OrganizationMember` for role lookups |
| `_get_team_member` | 695 | Resolve team membership row |

(Line numbers as of 2026-08-26, after the 4.6D audit-trail fix — see
`../TEAM-AUDIT/README.md` — added `get_user_accessible_team_ids` and
`team_id=team.id` arguments throughout this file.)

## Backend — `backend-fte/app/ai/service.py`

| Method | Line | Purpose |
|---|---|---|
| `check_team_agent_access` | 1627 | Raises if the current user cannot act on the given agent; delegates to `TeamService` |

## Router call sites (`app/ai/router.py`)

| Endpoint | Line |
|---|---|
| `get_agent` | 226 |
| `update_agent` | 247 |
| `deactivate_agent` | 275 |
| `submit_task` | 302 |
| `list_agent_tasks` | 339 |
| `runtime_execute` | 595 |
| `create_nl_task` | 689 |
| `create_and_execute_workflow` | 888 |
| `list_workflows` | 1049 |

## Tests

| File | Lines |
|---|---|
| `tests/test_ai_team_auth.py` | 684 |
