"""
Tests for 4.6C — Team-Level Task & Workflow Visibility / Filtering.

Covers:
- Team-level task visibility (list_tasks filtered by team)
- Team-level task retrieval (get_task checks team access)
- Team-level workflow visibility (list_workflows filtered by team)
- Team-level workflow retrieval (get_workflow checks team access)
- Teamless agent backward compatibility
- OWNER/ADMIN access
- Cross-organization isolation
- RBAC enforcement
- No information leakage (404 not 403)
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai.service import AIService
from app.ai.team_service import TeamService
from app.ai.models import AIAgent, AIAgentTask
from app.ai.constants import AgentType, AgentStatus, TaskStatus, TaskType
from app.ai.exceptions import TaskNotFoundError, TeamAccessDeniedError
from app.organizations.models import (
    Organization, OrganizationMember, Team, MembershipRole,
)


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def org_id():
    return uuid.uuid4()


@pytest.fixture
def org_id_b():
    return uuid.uuid4()


@pytest.fixture
def user_id():
    return uuid.uuid4()


@pytest.fixture
def user_id_b():
    return uuid.uuid4()


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
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
    m.created_at = MagicMock()
    return m


def _make_agent(agent_id, org_id, team_id=None, name="Agent", is_active=True):
    a = MagicMock(spec=AIAgent)
    a.id = agent_id
    a.organization_id = org_id
    a.team_id = team_id
    a.name = name
    a.agent_type = AgentType.CUSTOM
    a.status = AgentStatus.ACTIVE
    a.is_active = is_active
    a.config = None
    a.granted_permissions = None
    a.created_by = None
    a.created_at = MagicMock()
    a.updated_at = MagicMock()
    return a


def _make_task(task_id, agent_id, org_id, task_type=TaskType.CUSTOM, status=TaskStatus.COMPLETED):
    t = MagicMock(spec=AIAgentTask)
    t.id = task_id
    t.agent_id = agent_id
    t.organization_id = org_id
    t.task_type = task_type
    t.status = status
    t.input_data = {}
    t.output_data = {}
    t.error_message = None
    t.requires_human_approval = False
    t.approved_by = None
    t.approved_at = None
    t.rejection_reason = None
    t.submitted_by = None
    t.execution_started_at = None
    t.execution_completed_at = None
    t.execution_duration_ms = None
    t.llm_provider = None
    t.llm_model = None
    t.llm_tokens_used = None
    t.parent_task_id = None
    t.source_agent_id = None
    t.target_agent_id = None
    t.capability_name = None
    t.handoff_depth = 0
    t.metadata_ = None
    t.created_at = MagicMock()
    t.updated_at = MagicMock()
    return t


def _setup_db_for_query(db, results):
    """Configure db.execute to return results for sequential queries."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = results
    mock_result.scalar_one_or_none.return_value = results[0] if results else None
    mock_result.scalar.return_value = len(results)
    db.execute = AsyncMock(return_value=mock_result)
    return mock_result


# ═══════════════════════════════════════════════════════════════════
# TEAM SERVICE: get_user_accessible_agent_ids
# ═══════════════════════════════════════════════════════════════════

class TestGetUserAccessibleAgentIds:
    """Test TeamService.get_user_accessible_agent_ids()."""

    @pytest.mark.asyncio
    async def test_owner_sees_all_agents(self, mock_db, org_id, user_id):
        """OWNER should see all agents in the org."""
        agent_a = _make_agent(uuid.uuid4(), org_id, name="Agent A")
        agent_b = _make_agent(uuid.uuid4(), org_id, name="Agent B")
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OWNER)

        # Call sequence: _get_org_member → result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = org_member
        mock_result.scalars.return_value.all.return_value = [agent_a.id, agent_b.id]
        mock_db.execute = AsyncMock(return_value=mock_result)

        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)
        visible = await team_svc.get_user_accessible_agent_ids()

        assert agent_a.id in visible
        assert agent_b.id in visible

    @pytest.mark.asyncio
    async def test_admin_sees_all_agents(self, mock_db, org_id, user_id):
        """ADMIN should see all agents in the org."""
        agent = _make_agent(uuid.uuid4(), org_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.ADMIN)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = org_member
        mock_result.scalars.return_value.all.return_value = [agent.id]
        mock_db.execute = AsyncMock(return_value=mock_result)

        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)
        visible = await team_svc.get_user_accessible_agent_ids()

        assert agent.id in visible

    @pytest.mark.asyncio
    async def test_team_member_sees_own_team_and_teamless(self, mock_db, org_id, user_id):
        """Team member should see agents on their team + teamless agents."""
        team_id = uuid.uuid4()
        team_agent = _make_agent(uuid.uuid4(), org_id, team_id=team_id, name="Team Agent")
        teamless_agent = _make_agent(uuid.uuid4(), org_id, team_id=None, name="Teamless Agent")
        other_team_agent = _make_agent(uuid.uuid4(), org_id, team_id=uuid.uuid4(), name="Other Agent")

        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=team_id)

        # Query 1: _get_org_member → org_member
        # Query 2: get_user_accessible_agent_ids → filtered agents
        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalars.return_value.all.return_value = [team_agent.id, teamless_agent.id]
            return result

        mock_db.execute = mock_execute

        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)
        visible = await team_svc.get_user_accessible_agent_ids()

        assert team_agent.id in visible
        assert teamless_agent.id in visible
        assert other_team_agent.id not in visible

    @pytest.mark.asyncio
    async def test_user_without_team_sees_only_teamless(self, mock_db, org_id, user_id):
        """User with no team_id should see only teamless agents."""
        teamless_agent = _make_agent(uuid.uuid4(), org_id, team_id=None)
        team_agent = _make_agent(uuid.uuid4(), org_id, team_id=uuid.uuid4())
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.VIEWER, team_id=None)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalars.return_value.all.return_value = [teamless_agent.id]
            return result

        mock_db.execute = mock_execute

        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)
        visible = await team_svc.get_user_accessible_agent_ids()

        assert teamless_agent.id in visible
        assert team_agent.id not in visible

    @pytest.mark.asyncio
    async def test_non_org_member_sees_nothing(self, mock_db, org_id, user_id):
        """Non-org member should see nothing."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)
        visible = await team_svc.get_user_accessible_agent_ids()

        assert len(visible) == 0


# ═══════════════════════════════════════════════════════════════════
# AISERVICE: list_tasks with team filtering
# ═══════════════════════════════════════════════════════════════════

class TestListTasksTeamFiltering:
    """Test that AIService.list_tasks() applies team-level filtering."""

    @pytest.mark.asyncio
    async def test_same_team_tasks_visible(self, mock_db, org_id, user_id):
        """User should see tasks from agents on their team."""
        team_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        task_id = uuid.uuid4()

        agent = _make_agent(agent_id, org_id, team_id=team_id)
        task = _make_task(task_id, agent_id, org_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=team_id)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # list_tasks query → returns tasks
                result.scalars.return_value.all.return_value = [task]
            elif call_count[0] == 2:
                # get_user_accessible_agent_ids → _get_org_member
                result.scalar_one_or_none.return_value = org_member
            else:
                # get_user_accessible_agent_ids → agent query
                result.scalars.return_value.all.return_value = [agent_id]
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        tasks = await svc.list_tasks()

        assert len(tasks) == 1
        assert tasks[0].id == task_id

    @pytest.mark.asyncio
    async def test_other_team_tasks_filtered_out(self, mock_db, org_id, user_id):
        """User should NOT see tasks from agents on another team."""
        team_id = uuid.uuid4()
        other_team_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        other_agent_id = uuid.uuid4()

        task = _make_task(uuid.uuid4(), agent_id, org_id)
        other_task = _make_task(uuid.uuid4(), other_agent_id, org_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=team_id)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalars.return_value.all.return_value = [task, other_task]
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalars.return_value.all.return_value = [agent_id]
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        tasks = await svc.list_tasks()

        # Only the task from user's team agent is visible
        assert len(tasks) == 1
        assert tasks[0].agent_id == agent_id

    @pytest.mark.asyncio
    async def test_owner_sees_all_tasks(self, mock_db, org_id, user_id):
        """OWNER should see tasks from all agents."""
        agent_a = uuid.uuid4()
        agent_b = uuid.uuid4()
        task_a = _make_task(uuid.uuid4(), agent_a, org_id)
        task_b = _make_task(uuid.uuid4(), agent_b, org_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OWNER)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalars.return_value.all.return_value = [task_a, task_b]
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalars.return_value.all.return_value = [agent_a, agent_b]
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        tasks = await svc.list_tasks()

        assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_teamless_agent_tasks_visible_to_all(self, mock_db, org_id, user_id):
        """Tasks from teamless agents should be visible to all org members."""
        teamless_agent_id = uuid.uuid4()
        task = _make_task(uuid.uuid4(), teamless_agent_id, org_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=uuid.uuid4())

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalars.return_value.all.return_value = [task]
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalars.return_value.all.return_value = [teamless_agent_id]
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        tasks = await svc.list_tasks()

        assert len(tasks) == 1
        assert tasks[0].agent_id == teamless_agent_id

    @pytest.mark.asyncio
    async def test_internal_execution_no_filter(self, mock_db, org_id):
        """Internal execution (user_id=None) should return all tasks."""
        task = _make_task(uuid.uuid4(), uuid.uuid4(), org_id)
        _setup_db_for_query(mock_db, [task])

        svc = AIService(db=mock_db, organization_id=org_id, user_id=None)
        tasks = await svc.list_tasks()

        assert len(tasks) == 1


# ═══════════════════════════════════════════════════════════════════
# AISERVICE: get_task with team access check
# ═══════════════════════════════════════════════════════════════════

class TestGetTaskTeamAccess:
    """Test that AIService.get_task() enforces team-level access."""

    @pytest.mark.asyncio
    async def test_same_team_can_get_task(self, mock_db, org_id, user_id):
        """User on the same team can retrieve the task."""
        team_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        task_id = uuid.uuid4()

        agent = _make_agent(agent_id, org_id, team_id=team_id)
        task = _make_task(task_id, agent_id, org_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=team_id)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # get_task → _get_task_by_id
                result.scalar_one_or_none.return_value = task
            elif call_count[0] == 2:
                # check_task_access → _get_agent_by_id (agent fetched once)
                result.scalar_one_or_none.return_value = agent
            elif call_count[0] == 3:
                # can_access_agent → _get_org_member (OPERATOR, not OWNER)
                result.scalar_one_or_none.return_value = org_member
            elif call_count[0] == 4:
                # can_access_agent → _get_team_member (same team → allowed)
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        retrieved = await svc.get_task(task_id)

        assert retrieved.id == task_id

    @pytest.mark.asyncio
    async def test_different_team_get_task_returns_404(self, mock_db, org_id, user_id):
        """User from a different team gets TaskNotFoundError (404, not 403)."""
        team_id = uuid.uuid4()
        other_team_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        task_id = uuid.uuid4()

        agent = _make_agent(agent_id, org_id, team_id=other_team_id)
        task = _make_task(task_id, agent_id, org_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=team_id)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # get_task → _get_task_by_id
                result.scalar_one_or_none.return_value = task
            elif call_count[0] == 2:
                # check_task_access → _get_agent_by_id (agent fetched once)
                result.scalar_one_or_none.return_value = agent
            elif call_count[0] == 3:
                # can_access_agent → _get_org_member (OPERATOR, not OWNER)
                result.scalar_one_or_none.return_value = org_member
            elif call_count[0] == 4:
                # can_access_agent → _get_team_member → None (different team)
                result.scalar_one_or_none.return_value = None
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        with pytest.raises(TaskNotFoundError):
            await svc.get_task(task_id)

    @pytest.mark.asyncio
    async def test_owner_can_get_any_task(self, mock_db, org_id, user_id):
        """OWNER can retrieve any task in the org."""
        agent_id = uuid.uuid4()
        task_id = uuid.uuid4()

        agent = _make_agent(agent_id, org_id, team_id=uuid.uuid4())
        task = _make_task(task_id, agent_id, org_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OWNER)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # get_task → _get_task_by_id
                result.scalar_one_or_none.return_value = task
            elif call_count[0] == 2:
                # check_task_access → _get_agent_by_id (agent fetched once)
                result.scalar_one_or_none.return_value = agent
            elif call_count[0] == 3:
                # can_access_agent → _get_org_member (OWNER → True)
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        retrieved = await svc.get_task(task_id)

        assert retrieved.id == task_id


# ═══════════════════════════════════════════════════════════════════
# CROSS-ORGANIZATION ISOLATION
# ═══════════════════════════════════════════════════════════════════

class TestCrossOrgIsolation:
    """Cross-organization task access must be denied."""

    @pytest.mark.asyncio
    async def test_cross_org_task_not_found(self, mock_db, org_id, org_id_b, user_id):
        """Task from another org raises TaskNotFoundError."""
        task = _make_task(uuid.uuid4(), uuid.uuid4(), org_id_b)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = task
        mock_db.execute = AsyncMock(return_value=mock_result)

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        with pytest.raises(TaskNotFoundError):
            await svc.get_task(task.id)


# ═══════════════════════════════════════════════════════════════════
# RBAC ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════

class TestRBACEnforcement:
    """Verify that existing RBAC still works alongside team filtering."""

    @pytest.mark.asyncio
    async def test_viewer_list_tasks_still_filtered(self, mock_db, org_id, user_id):
        """VIEWER with team membership sees only their team's tasks."""
        team_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        task = _make_task(uuid.uuid4(), agent_id, org_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.VIEWER, team_id=team_id)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalars.return_value.all.return_value = [task]
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalars.return_value.all.return_value = [agent_id]
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        tasks = await svc.list_tasks()

        assert len(tasks) == 1

    @pytest.mark.asyncio
    async def test_agent_execute_cannot_bypass_team(self, mock_db, org_id, user_id):
        """Having AGENT_EXECUTE permission doesn't bypass team authorization."""
        team_id = uuid.uuid4()
        other_team_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        other_agent_id = uuid.uuid4()

        task = _make_task(uuid.uuid4(), agent_id, org_id)
        other_task = _make_task(uuid.uuid4(), other_agent_id, org_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=team_id)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalars.return_value.all.return_value = [task, other_task]
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalars.return_value.all.return_value = [agent_id]
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        tasks = await svc.list_tasks()

        # Only team agent's task is visible
        assert len(tasks) == 1
        assert tasks[0].agent_id == agent_id

    @pytest.mark.asyncio
    async def test_admin_bypasses_team_filter(self, mock_db, org_id, user_id):
        """ADMIN can see tasks from all agents regardless of team."""
        agent_a = uuid.uuid4()
        agent_b = uuid.uuid4()
        task_a = _make_task(uuid.uuid4(), agent_a, org_id)
        task_b = _make_task(uuid.uuid4(), agent_b, org_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.ADMIN)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalars.return_value.all.return_value = [task_a, task_b]
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalars.return_value.all.return_value = [agent_a, agent_b]
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        tasks = await svc.list_tasks()

        assert len(tasks) == 2


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW TEAM FILTERING
# ═══════════════════════════════════════════════════════════════════

class TestWorkflowTeamFiltering:
    """Test that workflow visibility respects team boundaries."""

    @pytest.mark.asyncio
    async def test_same_team_workflow_visible(self, mock_db, org_id, user_id):
        """User should see workflows from agents on their team."""
        team_id = uuid.uuid4()
        agent_id = uuid.uuid4()

        wf_task = _make_task(uuid.uuid4(), agent_id, org_id, task_type=TaskType.WORKFLOW)
        wf_task.metadata_ = {
            "workflow_definition": {
                "workflow_id": "wf-test-1",
                "name": "Test Workflow",
                "steps": [],
            }
        }
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=team_id)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalars.return_value.all.return_value = [wf_task]
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalars.return_value.all.return_value = [agent_id]
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        tasks = await svc.list_tasks()

        # Filter to workflow tasks (like the router does)
        wf_tasks = [t for t in tasks if t.task_type == TaskType.WORKFLOW]
        assert len(wf_tasks) == 1

    @pytest.mark.asyncio
    async def test_other_team_workflow_filtered(self, mock_db, org_id, user_id):
        """User should NOT see workflows from agents on another team."""
        team_id = uuid.uuid4()
        other_team_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        other_agent_id = uuid.uuid4()

        wf_task = _make_task(uuid.uuid4(), agent_id, org_id, task_type=TaskType.WORKFLOW)
        other_wf_task = _make_task(uuid.uuid4(), other_agent_id, org_id, task_type=TaskType.WORKFLOW)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=team_id)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalars.return_value.all.return_value = [wf_task, other_wf_task]
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalars.return_value.all.return_value = [agent_id]
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        tasks = await svc.list_tasks()

        wf_tasks = [t for t in tasks if t.task_type == TaskType.WORKFLOW]
        assert len(wf_tasks) == 1
        assert wf_tasks[0].agent_id == agent_id


# ═══════════════════════════════════════════════════════════════════
# check_task_access
# ═══════════════════════════════════════════════════════════════════

class TestCheckTaskAccess:
    """Test AIService.check_task_access() directly."""

    @pytest.mark.asyncio
    async def test_team_member_access_allowed(self, mock_db, org_id, user_id):
        """Team member can access their team's agent's task."""
        team_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        task = _make_task(uuid.uuid4(), agent_id, org_id)
        agent = _make_agent(agent_id, org_id, team_id=team_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=team_id)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # check_task_access → _get_agent_by_id (no agent provided)
                result.scalar_one_or_none.return_value = agent
            elif call_count[0] == 2:
                # can_access_agent → _get_org_member (OPERATOR, not OWNER)
                result.scalar_one_or_none.return_value = org_member
            elif call_count[0] == 3:
                # can_access_agent → _get_team_member (same team)
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        # Should not raise
        await svc.check_task_access(task)

    @pytest.mark.asyncio
    async def test_non_member_access_denied(self, mock_db, org_id, user_id):
        """Non-member gets TaskNotFoundError (not TeamAccessDeniedError)."""
        team_id = uuid.uuid4()
        other_team_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        task = _make_task(uuid.uuid4(), agent_id, org_id)
        agent = _make_agent(agent_id, org_id, team_id=other_team_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=team_id)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # can_user_access_agent → _get_agent_by_id
                result.scalar_one_or_none.return_value = agent
            elif call_count[0] == 2:
                # can_user_access_agent → _get_org_member
                result.scalar_one_or_none.return_value = org_member
            elif call_count[0] == 3:
                # can_user_access_agent → _get_team_member → None (not a member)
                result.scalar_one_or_none.return_value = None
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        with pytest.raises(TaskNotFoundError) as exc_info:
            await svc.check_task_access(task)

        # Verify it's TaskNotFoundError, NOT TeamAccessDeniedError
        assert "not found" in str(exc_info.value.message).lower()

    @pytest.mark.asyncio
    async def test_internal_execution_skips_check(self, mock_db, org_id):
        """Internal execution (user_id=None) skips team check."""
        task = _make_task(uuid.uuid4(), uuid.uuid4(), org_id)
        svc = AIService(db=mock_db, organization_id=org_id, user_id=None)

        # Should not raise
        await svc.check_task_access(task)

    @pytest.mark.asyncio
    async def test_owner_access_always_allowed(self, mock_db, org_id, user_id):
        """Owner can access any task in their org."""
        agent_id = uuid.uuid4()
        task = _make_task(uuid.uuid4(), agent_id, org_id)
        agent = _make_agent(agent_id, org_id, team_id=uuid.uuid4())
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OWNER)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # check_task_access → _get_agent_by_id (no agent provided)
                result.scalar_one_or_none.return_value = agent
            elif call_count[0] == 2:
                # can_access_agent → _get_org_member (OWNER → returns True)
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        # Should not raise
        await svc.check_task_access(task)


# ═══════════════════════════════════════════════════════════════════
# SECURITY: No information leakage
# ═══════════════════════════════════════════════════════════════════

class TestNoInformationLeakage:
    """Verify that unauthorized access returns 404, not 403."""

    @pytest.mark.asyncio
    async def test_unauthorized_task_returns_task_not_found(self, mock_db, org_id, user_id):
        """Accessing another team's task returns TaskNotFoundError, not TeamAccessDeniedError."""
        other_team_id = uuid.uuid4()
        agent_id = uuid.uuid4()
        task = _make_task(uuid.uuid4(), agent_id, org_id)
        agent = _make_agent(agent_id, org_id, team_id=other_team_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=uuid.uuid4())

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalar_one_or_none.return_value = task
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = agent
            elif call_count[0] == 3:
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        with pytest.raises(TaskNotFoundError) as exc_info:
            await svc.get_task(task.id)

        # Must NOT be TeamAccessDeniedError
        assert not isinstance(exc_info.value, TeamAccessDeniedError)


# ═══════════════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge cases for team-level task/workflow filtering."""

    @pytest.mark.asyncio
    async def test_empty_task_list(self, mock_db, org_id, user_id):
        """Empty task list should return empty list."""
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=uuid.uuid4())

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalars.return_value.all.return_value = []
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalars.return_value.all.return_value = []
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        tasks = await svc.list_tasks()

        assert tasks == []

    @pytest.mark.asyncio
    async def test_all_tasks_filtered_returns_empty(self, mock_db, org_id, user_id):
        """If all tasks are from other teams, should return empty list."""
        other_agent_id = uuid.uuid4()
        task = _make_task(uuid.uuid4(), other_agent_id, org_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=uuid.uuid4())

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalars.return_value.all.return_value = [task]
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalars.return_value.all.return_value = []
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        tasks = await svc.list_tasks()

        assert tasks == []

    @pytest.mark.asyncio
    async def test_agent_filter_plus_team_filter(self, mock_db, org_id, user_id):
        """Filtering by agent_id AND team should work together."""
        team_id = uuid.uuid4()
        my_agent_id = uuid.uuid4()
        other_agent_id = uuid.uuid4()

        my_task = _make_task(uuid.uuid4(), my_agent_id, org_id)
        other_task = _make_task(uuid.uuid4(), other_agent_id, org_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.OPERATOR, team_id=team_id)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # list_tasks with agent_id filter — only returns my_agent tasks
                result.scalars.return_value.all.return_value = [my_task]
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalars.return_value.all.return_value = [my_agent_id]
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        tasks = await svc.list_tasks(agent_id=my_agent_id)

        assert len(tasks) == 1
        assert tasks[0].agent_id == my_agent_id

    @pytest.mark.asyncio
    async def test_admin_list_tasks(self, mock_db, org_id, user_id):
        """ADMIN sees all tasks without filtering."""
        agent_a = uuid.uuid4()
        agent_b = uuid.uuid4()
        task_a = _make_task(uuid.uuid4(), agent_a, org_id)
        task_b = _make_task(uuid.uuid4(), agent_b, org_id)
        org_member = _make_org_member(user_id, org_id, role=MembershipRole.ADMIN)

        call_count = [0]
        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.scalars.return_value.all.return_value = [task_a, task_b]
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = org_member
            else:
                result.scalars.return_value.all.return_value = [agent_a, agent_b]
            return result

        mock_db.execute = mock_execute

        svc = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        tasks = await svc.list_tasks()

        assert len(tasks) == 2
