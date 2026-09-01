# 4.6A Team & Agent Collaboration — Implementation Map

(Line numbers as of 2026-08-26, after the 4.6D audit-trail fix added
`get_user_accessible_team_ids` and `team_id=team.id` arguments throughout
`team_service.py`, and expanded `list_actions` in `router.py` — see
`../TEAM-AUDIT/README.md`.)

## Backend — `backend-fte/app/ai/team_service.py` (`TeamService`)

| Method | Line | Purpose |
|---|---|---|
| `create_team` | 73 | Create a team |
| `list_teams` | 118 | List org's teams |
| `get_team` | 134 | Get one team |
| `update_team` | 140 | Update name/description |
| `deactivate_team` | 185 | Soft-delete; record preserved for audit |
| `add_member` | 231 | Add a human member |
| `remove_member` | 288 | Remove a human member |
| `list_members` | 327 | List a team's human members |
| `assign_agent` | 367 | Assign an AI agent to a team |
| `unassign_agent` | 416 | Remove an AI agent from a team |
| `list_team_agents` | 459 | List a team's agents |
| `_get_team_by_id` / `_get_team_by_name` | 654 / 664 | Lookups |
| `_ensure_org_owns_team` / `_ensure_org_owns_agent` | 731 / 736 | Tenant isolation guards |

## Router (`app/ai/router.py`)

| Endpoint | Line |
|---|---|
| `POST /ai/teams` (create) | 1175 |
| `GET /ai/teams` (list) | 1203 |
| `GET /ai/teams/{id}` (get) | 1230 |
| `PATCH /ai/teams/{id}` (update) | 1255 |
| `DELETE /ai/teams/{id}` (deactivate) | 1284 |
| `POST /ai/teams/{id}/members` (add) | 1304 |
| `DELETE /ai/teams/{id}/members/{uid}` (remove) | 1331 |
| `GET /ai/teams/{id}/members` (list) | 1349 |
| `POST /ai/teams/{id}/agents` (assign) | 1383 |
| `DELETE /ai/teams/{id}/agents/{aid}` (unassign) | 1411 |
| `GET /ai/teams/{id}/agents` (list) | 1429 |

## Models

- `Team` — `app/organizations/models.py:184` (org-scoped, `organization_id` FK).
- Human membership — `OrganizationMember.team_id` (`app/organizations/models.py:226`, nullable FK to `teams.id`); no separate junction table.
- Agent membership — `AIAgent.team_id` (`app/ai/models.py:46`, nullable FK to `teams.id`); also no separate junction table.

Teams are an organization-level concept (`app/organizations/`) that both
`OrganizationMember` and `AIAgent` attach to directly via a `team_id`
column — `team_service.py` (in `app/ai/`) is the orchestration layer over
both.

## Migrations

| File | Lines |
|---|---|
| `alembic/versions/ai_team_agents.py` | 34 |

## Tests

| File | Lines |
|---|---|
| `tests/test_ai_teams.py` | 1,220 |
