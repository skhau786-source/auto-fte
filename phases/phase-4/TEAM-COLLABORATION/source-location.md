# 4.6A Team & Agent Collaboration — Canonical Source Location

**Canonical implementation — edit only here:**

```
backend-fte/app/ai/team_service.py
backend-fte/app/ai/router.py             (lines 1160-1442)
backend-fte/app/organizations/models.py  (Team, OrganizationMember.team_id)
backend-fte/app/ai/models.py             (AIAgent.team_id)
backend-fte/alembic/versions/ai_team_agents.py
```

**Do not duplicate.** `team_service.py` is the single implementation shared
by `../TEAM-AUTHORIZATION/` and `../TEAM-FILTERING/` — those are different
*aspects* of the same file's methods, not different code. See those
folders' `README.md` for which methods belong to which aspect.

No snapshot exists.
