# 4.6A Team & Agent Collaboration — 🟢 COMPLETE

Teams that group agents and human members together.

## What it does (`app/ai/team_service.py`, `TeamService`, 749 lines)

- `create_team` (73), `list_teams` (116), `get_team` (132), `update_team`
  (138), `deactivate_team` (182) — team lifecycle is soft-delete
  (`deactivate`), team record preserved for audit (docstring, line ~187).
- `add_member` (227), `remove_member` (283), `list_members` (321) — human
  membership.
- `assign_agent` (361), `unassign_agent` (409), `list_team_agents` (451) —
  agent membership.
- Endpoints for all of the above in `app/ai/router.py:1160-1434`.

## Status detail

| Piece | Status | Evidence |
|---|---|---|
| Team CRUD | 🟢 | `team_service.py:73-230` |
| Member management | 🟢 | `team_service.py:231-366` |
| Agent assignment | 🟢 | `team_service.py:367-475` |
| Endpoints | 🟢 | `router.py:1160-1434` (team CRUD, member add/remove/list, agent assign/unassign/list) |
| Tests | 🟢 | `tests/test_ai_teams.py` (1,220 lines) |

## Full detail

- [`implementation-map.md`](./implementation-map.md)
- [`source-location.md`](./source-location.md)
