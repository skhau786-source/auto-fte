# 4.6D Team-Level Audit Trail — Canonical Source Location

**Canonical implementation — edit only here:**

```
backend-fte/app/ai/models.py          (AIAgentAction, team_id/agent_id columns)
backend-fte/app/ai/team_service.py    (_log_action, get_user_accessible_team_ids)
backend-fte/app/ai/service.py         (_log_action, get_agent_actions, get_visible_team_ids)
backend-fte/app/ai/router.py          (GET /ai/actions)
backend-fte/app/ai/schemas.py         (AgentActionOut)
backend-fte/alembic/versions/ai_action_team_scope.py
frontend-fte/lib/api.ts               (AIAgentAction interface)
```

**Do not duplicate.** `AIAgentAction` and both `_log_action` methods
(`team_service.py` for team-level actions, `service.py` for agent-level
ones) are shared with `../AI-AGENTS/` (agent-level audit) — a schema or
behavior change here must not break agent-scoped audit rows, which still
have real, valid `agent_id` values.

No snapshot exists.
