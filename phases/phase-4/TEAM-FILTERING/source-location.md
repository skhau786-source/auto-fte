# 4.6C Team/Task/Workflow Visibility — Canonical Source Location

**Canonical implementation — edit only here:**

```
backend-fte/app/ai/service.py    (get_visible_agent_ids: 540, check_task_access: 565)
```

**Do not duplicate.** This filtering logic depends directly on
`TeamService` (`../TEAM-COLLABORATION/`, `../TEAM-AUTHORIZATION/`) — it is
not a standalone system. If you need visibility filtering somewhere new
(e.g. a future workflow-list endpoint with real query-level filtering
instead of the router-level `check_team_agent_access` gate it has today),
extend `AIService`, don't build a parallel filter.

No snapshot exists.
