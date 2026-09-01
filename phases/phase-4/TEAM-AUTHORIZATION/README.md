# 4.6B Team-Level Authorization — 🟢 COMPLETE

Controls which users can manage which teams, and which agents a user is
allowed to act on based on team membership.

## What it does (`app/ai/team_service.py`, `TeamService`)

- `user_is_team_member` (479) — is this user a member of this team?
- `user_can_manage_team` (488) — does this user have management rights
  over this team (role-based, via `OrganizationMember`)?
- `agent_belongs_to_team` (499) — is this agent assigned to this team?
- `can_access_agent` (508) / `can_user_access_agent` (546) — the core
  authorization check: can this user act on this agent, considering team
  membership (not just org-level RBAC)?
- `get_user_accessible_agent_ids` (560) — set of agent IDs this user may
  access; this is also the foundation `../TEAM-FILTERING/` builds on.

Wired into the request path via `AIService.check_team_agent_access`
(`app/ai/service.py:1627`), which is called from **9 separate endpoints**
in `app/ai/router.py` — not just NL tasks: `get_agent` (226),
`update_agent` (247), `deactivate_agent` (275), `submit_task` (302),
`list_agent_tasks` (339), `runtime_execute` (595), `create_nl_task` (689),
`create_and_execute_workflow` (888), `list_workflows` (1049). This is the
single authorization checkpoint nearly every agent-touching endpoint routes
through. (Line numbers as of 2026-08-26, after the 4.6D audit-trail fix
added code earlier in both files — see `../TEAM-AUDIT/README.md`.)

## Status detail

| Piece | Status | Evidence |
|---|---|---|
| Membership check | 🟢 | `team_service.py:479` |
| Management-rights check | 🟢 | `team_service.py:488` |
| Agent-team check | 🟢 | `team_service.py:499` |
| Agent-access check | 🟢 | `team_service.py:508,546` |
| Accessible-agent-ids helper | 🟢 | `team_service.py:560` |
| Wired into 9 endpoints | 🟢 | `service.py:1627` (`check_team_agent_access`), called from `router.py` 9 call sites |
| Tests | 🟢 | `tests/test_ai_team_auth.py` (684 lines) |

## Full detail

- [`implementation-map.md`](./implementation-map.md)
- [`source-location.md`](./source-location.md)
