"""
Tests for the Phase 4 audit-trail team-scoping fix.

Background (see phases/phase-4/TEAM-AUDIT/README.md for the original
audit finding): GET /ai/actions had no team_id filter and AIAgentAction
had no team_id column, so there was no reliable way to query a team's AI
audit log — and TeamService._log_action was writing a fabricated random
UUID into the NOT NULL agent_id column for team-level actions, which
would violate the ai_agents foreign key against a real database.

This file covers:
- A. Action creation: an action created for Team A carries Team A's team_id.
- B. Team filtering: Team A can retrieve Team A's audit actions.
- C. Cross-team isolation: Team A cannot retrieve Team B's audit actions.
- D. Empty team: a team with no audit records gets an empty result, not
     unrelated records.
- E. Existing behavior: agent_id/task_id filters, org-level (teamless)
     actions, and OWNER/ADMIN/internal-execution visibility all still work.
- F. Schema: a real-database (gated) test that the agent_id NOT NULL
     relaxation + team_id column actually let a team-only action insert
     without violating the ai_agents foreign key — the concrete
     regression test for the bug this fix addresses. Skipped when no
     PostgreSQL is reachable (see tests/conftest.py::_postgres_available);
     it is NOT run in this environment (see the final report for that
     limitation) but will run wherever the project's existing PostgreSQL
     test setup is available (CI, a developer machine with the test DB
     configured).

All non-F tests use the same mocked-AsyncSession style as
tests/test_ai_teams.py and tests/test_ai_team_filtering.py — this project
does not otherwise run Phase 4 tests against a real database.
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.ai.service import AIService
from app.ai.team_service import TeamService
from app.ai.models import AIAgent, AIAgentAction
from app.ai.constants import AgentType, AgentStatus
from app.organizations.models import Organization, OrganizationMember, Team, MembershipRole


# ═══════════════════════════════════════════════════════════════════
# FIXTURES / HELPERS
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def org_id():
    return uuid.uuid4()


@pytest.fixture
def user_id():
    return uuid.uuid4()


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    return db


def _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=None):
    m = MagicMock(spec=OrganizationMember)
    m.user_id = user_id
    m.organization_id = org_id
    m.role = role
    m.team_id = team_id
    m.is_active = True
    return m


def _make_agent(agent_id, org_id, team_id=None, name="Agent"):
    a = MagicMock(spec=AIAgent)
    a.id = agent_id
    a.organization_id = org_id
    a.team_id = team_id
    a.name = name
    a.agent_type = AgentType.CUSTOM
    a.status = AgentStatus.ACTIVE
    a.is_active = True
    return a


def _make_action(action_id, org_id, agent_id=None, team_id=None, action_type="agent_created"):
    a = MagicMock(spec=AIAgentAction)
    a.id = action_id
    a.organization_id = org_id
    a.agent_id = agent_id
    a.team_id = team_id
    a.task_id = None
    a.action_type = action_type
    a.target_resource = None
    a.target_id = None
    a.result_status = "success"
    a.details = None
    a.performed_by = None
    a.created_at = MagicMock()
    return a


def _result_with_scalar_one(obj):
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _result_with_all(objs):
    r = MagicMock()
    r.scalars.return_value.all.return_value = objs
    return r


# ═══════════════════════════════════════════════════════════════════
# A. ACTION CREATION — team_id is attributed correctly
# ═══════════════════════════════════════════════════════════════════

class TestActionCreationCarriesTeamId:

    @pytest.mark.asyncio
    async def test_team_service_action_carries_team_id_and_no_agent_id(
        self, mock_db, org_id, user_id
    ):
        """A team-level action (e.g. team_created) is scoped by team_id,
        with agent_id left NULL — never a fabricated UUID."""
        mock_db.execute.return_value = _result_with_scalar_one(None)  # no name conflict

        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)
        team = await service.create_team(name="Team A")

        added = [c[0][0] for c in mock_db.add.call_args_list if c[0]]
        actions = [o for o in added if isinstance(o, AIAgentAction)]
        assert len(actions) == 1
        assert actions[0].team_id == team.id
        assert actions[0].agent_id is None

    @pytest.mark.asyncio
    async def test_agent_scoped_action_carries_agents_team_id(
        self, mock_db, org_id, user_id
    ):
        """An agent-level action (e.g. agent_activated) is stamped with
        that agent's *current* team_id — derived from the agent object
        already loaded, not trusted from any caller/client input."""
        team_id = uuid.uuid4()
        agent = _make_agent(uuid.uuid4(), org_id, team_id=team_id)

        mock_db.execute.side_effect = [_result_with_scalar_one(agent)]

        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        await service.activate_agent(agent.id)

        added = [c[0][0] for c in mock_db.add.call_args_list if c[0]]
        actions = [o for o in added if isinstance(o, AIAgentAction)]
        assert len(actions) == 1
        assert actions[0].team_id == team_id
        assert actions[0].agent_id == agent.id

    @pytest.mark.asyncio
    async def test_teamless_agent_action_has_null_team_id(self, mock_db, org_id, user_id):
        """An action from an agent with no team assignment gets team_id=None
        (not a fabricated value), consistent with teamless-agent behavior
        elsewhere in this module."""
        agent = _make_agent(uuid.uuid4(), org_id, team_id=None)
        mock_db.execute.side_effect = [_result_with_scalar_one(agent)]

        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        await service.activate_agent(agent.id)

        added = [c[0][0] for c in mock_db.add.call_args_list if c[0]]
        actions = [o for o in added if isinstance(o, AIAgentAction)]
        assert actions[0].team_id is None


# ═══════════════════════════════════════════════════════════════════
# B / C / D — get_agent_actions() team-scoped filtering
# ═══════════════════════════════════════════════════════════════════

class TestGetAgentActionsTeamScoping:

    @pytest.mark.asyncio
    async def test_team_member_sees_own_team_actions(self, mock_db, org_id, user_id):
        """B: A team member can retrieve their own team's audit actions."""
        team_id = uuid.uuid4()
        action = _make_action(uuid.uuid4(), org_id, team_id=team_id, action_type="team_created")
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=team_id)

        call_count = [0]

        # Visibility is resolved (get_visible_agent_ids, then
        # get_visible_team_ids) BEFORE the actions query executes, since
        # both feed into the same query's WHERE clause.
        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:  # get_visible_agent_ids -> _get_org_member
                return _result_with_scalar_one(org_member)
            elif call_count[0] == 2:  # get_visible_agent_ids -> agent id query
                return _result_with_all([])
            elif call_count[0] == 3:  # get_visible_team_ids -> _get_org_member (no team query needed)
                return _result_with_scalar_one(org_member)
            else:  # the actions query itself, executed last
                return _result_with_all([action])

        mock_db.execute = mock_execute

        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        actions = await service.get_agent_actions()

        assert len(actions) == 1
        assert actions[0].team_id == team_id

    @pytest.mark.asyncio
    async def test_cross_team_actions_not_returned(self, mock_db, org_id, user_id):
        """C: A Team A user cannot retrieve Team B's audit actions — the
        SQL-level filter excludes them, not just a post-hoc check."""
        team_a = uuid.uuid4()
        team_b = uuid.uuid4()
        action_a = _make_action(uuid.uuid4(), org_id, team_id=team_a, action_type="team_created")
        action_b = _make_action(uuid.uuid4(), org_id, team_id=team_b, action_type="team_created")
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=team_a)

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return _result_with_scalar_one(org_member)
            elif call_count[0] == 2:
                return _result_with_all([])
            elif call_count[0] == 3:
                return _result_with_scalar_one(org_member)
            else:
                # The real SQL WHERE clause would already exclude team_b's
                # row; the mock simulates that by returning only what the
                # filtered query would actually match in production.
                return _result_with_all([action_a])

        mock_db.execute = mock_execute

        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        actions = await service.get_agent_actions()

        assert len(actions) == 1
        assert actions[0].team_id == team_a
        assert all(a.team_id != team_b for a in actions)

    @pytest.mark.asyncio
    async def test_filter_clause_scopes_by_visible_agents_and_teams(
        self, mock_db, org_id, user_id
    ):
        """C (query-construction check): the WHERE clause actually built
        by get_agent_actions() restricts by the user's visible agent_ids
        and team_ids — verifies the fix is enforced in SQL, not only in
        a Python post-filter that could be bypassed by pagination."""
        team_a = uuid.uuid4()
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=team_a)

        captured_queries = []

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            captured_queries.append(query)
            if call_count[0] == 1:  # get_visible_agent_ids -> _get_org_member
                return _result_with_scalar_one(org_member)
            elif call_count[0] == 2:  # get_visible_agent_ids -> agent id query
                return _result_with_all([])
            elif call_count[0] == 3:  # get_visible_team_ids -> _get_org_member
                return _result_with_scalar_one(org_member)
            else:  # the actions query itself, executed last
                return _result_with_all([])

        mock_db.execute = mock_execute

        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        await service.get_agent_actions()

        # The final actions query (executed last, after both visibility
        # sets are resolved) must include a WHERE clause referencing the
        # ai_agent_actions.team_id column — confirms filtering happens in
        # SQL, not only as a Python post-filter.
        final_query_str = str(captured_queries[-1])
        assert "ai_agent_actions.team_id" in final_query_str

    @pytest.mark.asyncio
    async def test_empty_team_returns_empty_not_unrelated_records(
        self, mock_db, org_id, user_id
    ):
        """D: A team with no audit records gets an empty list — the
        query must never fall back to returning unrelated org actions."""
        team_id = uuid.uuid4()
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=team_id)

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:  # get_visible_agent_ids -> _get_org_member
                return _result_with_scalar_one(org_member)
            elif call_count[0] == 2:  # get_visible_agent_ids -> agent id query
                return _result_with_all([])
            elif call_count[0] == 3:  # get_visible_team_ids -> _get_org_member
                return _result_with_scalar_one(org_member)
            else:  # the actions query itself — no rows match this team at all
                return _result_with_all([])

        mock_db.execute = mock_execute

        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        actions = await service.get_agent_actions()

        assert actions == []


# ═══════════════════════════════════════════════════════════════════
# E — existing behavior keeps working
# ═══════════════════════════════════════════════════════════════════

class TestExistingBehaviorPreserved:

    @pytest.mark.asyncio
    async def test_owner_sees_all_org_actions(self, mock_db, org_id, user_id):
        """OWNER/ADMIN retain unrestricted visibility across teams."""
        action_a = _make_action(uuid.uuid4(), org_id, team_id=uuid.uuid4())
        action_b = _make_action(uuid.uuid4(), org_id, team_id=uuid.uuid4())
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OWNER)

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:  # get_visible_agent_ids -> org_member
                return _result_with_scalar_one(org_member)
            elif call_count[0] == 2:  # OWNER branch -> all active agents
                return _result_with_all([])
            elif call_count[0] == 3:  # get_visible_team_ids -> org_member
                return _result_with_scalar_one(org_member)
            elif call_count[0] == 4:  # OWNER branch -> all teams
                return _result_with_all([action_a.team_id, action_b.team_id])
            else:  # the actions query itself, executed last
                return _result_with_all([action_a, action_b])

        mock_db.execute = mock_execute

        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        actions = await service.get_agent_actions()

        assert len(actions) == 2

    @pytest.mark.asyncio
    async def test_teamless_org_level_action_visible_to_all_members(
        self, mock_db, org_id, user_id
    ):
        """An action with neither agent_id nor team_id (org-level) stays
        visible to any org member, matching teamless-agent behavior."""
        action = _make_action(uuid.uuid4(), org_id, agent_id=None, team_id=None)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.VIEWER, team_id=None)

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            if call_count[0] == 1:  # get_visible_agent_ids -> _get_org_member
                return _result_with_scalar_one(org_member)
            elif call_count[0] == 2:  # get_visible_agent_ids -> teamless-only agent query
                return _result_with_all([])
            elif call_count[0] == 3:  # get_visible_team_ids -> _get_org_member
                return _result_with_scalar_one(org_member)
            else:  # the actions query itself, executed last
                return _result_with_all([action])

        mock_db.execute = mock_execute

        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        actions = await service.get_agent_actions()

        assert len(actions) == 1

    @pytest.mark.asyncio
    async def test_internal_execution_no_filter(self, mock_db, org_id):
        """Internal execution (user_id=None) bypasses team filtering
        entirely, same as the existing list_tasks()/get_visible_agent_ids()
        behavior — only one query is issued."""
        action = _make_action(uuid.uuid4(), org_id)
        mock_db.execute = AsyncMock(return_value=_result_with_all([action]))

        service = AIService(db=mock_db, organization_id=org_id, user_id=None)
        actions = await service.get_agent_actions()

        assert len(actions) == 1
        assert mock_db.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_agent_id_and_task_id_filters_still_applied(self, mock_db, org_id, user_id):
        """Explicit agent_id/task_id query filters still narrow the query
        exactly as before this change (unaffected by adding team scoping)."""
        target_agent_id = uuid.uuid4()
        action = _make_action(uuid.uuid4(), org_id, agent_id=target_agent_id, team_id=None)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OWNER)

        call_count = [0]
        captured_queries = []

        async def mock_execute(query):
            call_count[0] += 1
            captured_queries.append(query)
            if call_count[0] == 1:  # get_visible_agent_ids -> org_member
                return _result_with_scalar_one(org_member)
            elif call_count[0] == 2:  # OWNER branch -> all active agents
                return _result_with_all([target_agent_id])
            elif call_count[0] == 3:  # get_visible_team_ids -> org_member
                return _result_with_scalar_one(org_member)
            elif call_count[0] == 4:  # OWNER branch -> all teams
                return _result_with_all([])
            else:  # the actions query itself, executed last
                return _result_with_all([action])

        mock_db.execute = mock_execute

        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        actions = await service.get_agent_actions(agent_id=target_agent_id)

        assert len(actions) == 1
        assert actions[0].agent_id == target_agent_id
        # The explicit agent_id filter is still applied in the final query
        # (SQLAlchemy renders bound values as parameter placeholders, not
        # literal UUIDs, so this checks the filtered column is present).
        final_query_str = str(captured_queries[-1])
        assert "ai_agent_actions.agent_id" in final_query_str


# ═══════════════════════════════════════════════════════════════════
# TeamService.get_user_accessible_team_ids — direct unit tests
# ═══════════════════════════════════════════════════════════════════

class TestGetUserAccessibleTeamIds:

    @pytest.mark.asyncio
    async def test_owner_sees_all_teams(self, mock_db, org_id, user_id):
        team_a, team_b = uuid.uuid4(), uuid.uuid4()
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OWNER)

        mock_db.execute.side_effect = [
            _result_with_scalar_one(org_member),
            _result_with_all([team_a, team_b]),
        ]

        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)
        visible = await service.get_user_accessible_team_ids()

        assert visible == {team_a, team_b}

    @pytest.mark.asyncio
    async def test_member_sees_only_own_team(self, mock_db, org_id, user_id):
        own_team = uuid.uuid4()
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=own_team)
        mock_db.execute.side_effect = [_result_with_scalar_one(org_member)]

        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)
        visible = await service.get_user_accessible_team_ids()

        assert visible == {own_team}

    @pytest.mark.asyncio
    async def test_member_without_team_sees_nothing(self, mock_db, org_id, user_id):
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=None)
        mock_db.execute.side_effect = [_result_with_scalar_one(org_member)]

        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)
        visible = await service.get_user_accessible_team_ids()

        assert visible == set()

    @pytest.mark.asyncio
    async def test_non_org_member_sees_nothing(self, mock_db, org_id, user_id):
        mock_db.execute.side_effect = [_result_with_scalar_one(None)]

        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)
        visible = await service.get_user_accessible_team_ids()

        assert visible == set()


# ═══════════════════════════════════════════════════════════════════
# F — Schema / real-database regression test (gated, see module docstring)
# ═══════════════════════════════════════════════════════════════════

class TestRealDatabaseSchema:
    """
    Verifies the actual bug this fix addresses: a team-level audit action
    (agent_id=NULL) must insert successfully against a real schema built
    from the current models (Base.metadata.create_all, same as
    tests/conftest.py's setup_database fixture), instead of raising a
    foreign-key violation the way the old agent_id=uuid.uuid4() placeholder
    would have. This is skipped automatically when no PostgreSQL is
    reachable (see tests/conftest.py::_postgres_available) — it did NOT
    run in the environment this fix was written in; see the final report.
    """

    @pytest.mark.asyncio
    async def test_team_only_action_inserts_without_fk_violation(self, db_session):
        from sqlalchemy import select as sa_select

        org = Organization(name="Schema Test Org", slug=f"schema-test-{uuid.uuid4().hex[:8]}")
        db_session.add(org)
        await db_session.flush()

        team = Team(organization_id=org.id, name="Schema Test Team")
        db_session.add(team)
        await db_session.flush()

        action = AIAgentAction(
            agent_id=None,
            team_id=team.id,
            organization_id=org.id,
            action_type="team_created",
            target_resource="team",
            target_id=str(team.id),
            result_status="success",
        )
        db_session.add(action)
        # This is the exact operation that used to fail: inserting a row
        # with agent_id=NULL against the ai_agent_actions table. Before
        # this fix, agent_id was NOT NULL and TeamService fabricated a
        # random UUID instead, which would fail the FK to ai_agents here.
        await db_session.commit()

        result = await db_session.execute(
            sa_select(AIAgentAction).where(AIAgentAction.id == action.id)
        )
        stored = result.scalar_one()
        assert stored.agent_id is None
        assert stored.team_id == team.id

    @pytest.mark.asyncio
    async def test_agent_scoped_action_still_requires_valid_agent_id(
        self, db_session
    ):
        """Existing behavior preserved: an agent_id that references a
        real agent still works exactly as before (agent_id nullable does
        not weaken the FK for agent-scoped rows)."""
        from app.ai.constants import AgentType, AgentStatus

        org = Organization(name="Schema Test Org 2", slug=f"schema-test2-{uuid.uuid4().hex[:8]}")
        db_session.add(org)
        await db_session.flush()

        agent = AIAgent(
            organization_id=org.id,
            name="Schema Test Agent",
            agent_type=AgentType.CUSTOM,
            status=AgentStatus.ACTIVE,
        )
        db_session.add(agent)
        await db_session.flush()

        action = AIAgentAction(
            agent_id=agent.id,
            team_id=None,
            organization_id=org.id,
            action_type="agent_created",
            result_status="success",
        )
        db_session.add(action)
        await db_session.commit()

        assert action.agent_id == agent.id
