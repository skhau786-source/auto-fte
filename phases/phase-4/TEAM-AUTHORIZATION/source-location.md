# 4.6B Team-Level Authorization — Canonical Source Location

**Canonical implementation — edit only here:**

```
backend-fte/app/ai/team_service.py   (lines 471-612, the auth-check methods)
backend-fte/app/ai/service.py        (check_team_agent_access, line 1539)
backend-fte/app/ai/router.py         (9 call sites, see implementation-map.md)
```

**Do not duplicate.** This is the same `TeamService` instance documented in
`../TEAM-COLLABORATION/` — different methods on one class, not a separate
implementation. `check_team_agent_access` is the one checkpoint nearly
every agent-facing endpoint calls; adding a second, parallel check
elsewhere would create an inconsistent authorization surface.

No snapshot exists.
