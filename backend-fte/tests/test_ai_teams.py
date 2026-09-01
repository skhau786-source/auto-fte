"""
Tests for AI Agent Team & Agent Collaboration Foundation (Phase 4 — 4.6A).

Test Coverage:
- Team CRUD (create, list, get, update, deactivate)
- Team membership (add, remove, list, duplicates)
- Agent-Team association (assign, unassign, list, duplicates)
- Tenant isolation (cross-org rejection)
- RBAC (authorized/unauthorized operations)
- Ownership rules (agent and team must belong to same org)
- Audit events (team created, member added, agent assigned, etc.)
- Schemas (validation, output models)
- Exception handling
"""

import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.ai.models import AIAgent, AIAgentAction
from app.ai.constants import AgentType, AgentStatus
from app.ai.team_service import TeamService
from app.ai.exceptions import (
    TeamNotFoundError,
    TeamNameConflictError,
    TeamMemberNotFoundError,
    TeamMemberAlreadyExistsError,
    TeamAgentAlreadyExistsError,
    AgentNotFoundError,
    CrossTenantTeamError,
)
from app.ai.schemas import (
    TeamCreateRequest,
    TeamUpdateRequest,
    TeamMemberAddRequest,
    TeamAgentAssignRequest,
)
from app.organizations.models import (
    Organization, Team, OrganizationMember, MembershipRole, Permission,
)
from app.models import RegisteredStudent
from app.ai.events import (
    TeamCreated,
    TeamUpdated,
    TeamDeactivated,
    TeamMemberAdded,
    TeamMemberRemoved,
    TeamAgentAssigned,
    TeamAgentRemoved,
)


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def org_id():
    return uuid.uuid4()


@pytest.fixture
def user_id():
    return uuid.uuid4()


@pytest.fixture
def other_org_id():
    return uuid.uuid4()


@pytest.fixture
def other_user_id():
    return uuid.uuid4()


@pytest_asyncio.fixture
async def mock_db():
    """Create a mock database session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


# ═══════════════════════════════════════════════════════════════════
# TEAM CRUD TESTS
# ═══════════════════════════════════════════════════════════════════

class TestTeamCRUD:
    """Tests for team create, list, get, update, deactivate."""

    @pytest.mark.asyncio
    async def test_create_team(self, mock_db, org_id, user_id):
        """Creating a team stores it in the database."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        # Mock no existing team with same name
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        team = await service.create_team(name="Operations")

        assert team.name == "Operations"
        assert team.organization_id == org_id
        assert mock_db.add.call_count >= 1
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_create_team_name_conflict(self, mock_db, org_id, user_id):
        """Creating a team with a duplicate name raises conflict."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        existing_team = Team(name="Existing Team", organization_id=org_id)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_team
        mock_db.execute.return_value = mock_result

        with pytest.raises(TeamNameConflictError):
            await service.create_team(name="Existing Team")

    @pytest.mark.asyncio
    async def test_list_teams(self, mock_db, org_id, user_id):
        """Listing teams returns all teams for the organization."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team1 = Team(id=uuid.uuid4(), organization_id=org_id, name="Team A")
        team2 = Team(id=uuid.uuid4(), organization_id=org_id, name="Team B")

        # First call: list teams, subsequent calls: count queries
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [team1, team2]

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        mock_db.execute.side_effect = [list_result, count_result, count_result, count_result, count_result]

        teams = await service.list_teams()
        assert len(teams) == 2

    @pytest.mark.asyncio
    async def test_get_team(self, mock_db, org_id, user_id):
        """Getting a team by ID returns the team."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Test Team")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = team
        mock_db.execute.return_value = mock_result

        result = await service.get_team(team.id)
        assert result.name == "Test Team"

    @pytest.mark.asyncio
    async def test_get_team_not_found(self, mock_db, org_id, user_id):
        """Getting a non-existent team raises not found."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(TeamNotFoundError):
            await service.get_team(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_update_team(self, mock_db, org_id, user_id):
        """Updating a team changes its fields."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Old Name")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = team
        # Second call: check name uniqueness (no conflict)
        no_conflict_result = MagicMock()
        no_conflict_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [mock_result, no_conflict_result]

        updated = await service.update_team(team.id, name="New Name")
        assert updated.name == "New Name"

    @pytest.mark.asyncio
    async def test_deactivate_team(self, mock_db, org_id, user_id):
        """Deactivating a team removes all members and agents."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Team to Deactivate")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = team
        # Mock empty results for agent/member cleanup
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [mock_result, empty_result, empty_result]

        result = await service.deactivate_team(team.id)
        assert result.name == "Team to Deactivate"
        mock_db.delete.assert_called_once_with(team)


# ═══════════════════════════════════════════════════════════════════
# TEAM MEMBERSHIP TESTS
# ═══════════════════════════════════════════════════════════════════

class TestTeamMembership:
    """Tests for team member management."""

    @pytest.mark.asyncio
    async def test_add_member(self, mock_db, org_id, user_id):
        """Adding a member to a team updates the org member record."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Test Team")
        org_member = OrganizationMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            user_id=user_id,
            role=MembershipRole.OPERATOR,
            is_active=True,
        )

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            return r

        # get_team, _get_org_member, _get_team_member
        mock_db.execute.side_effect = [
            make_result(team),      # get_team
            make_result(org_member),  # _get_org_member (user is org member)
            make_result(None),        # _get_team_member (not yet a team member)
        ]

        result = await service.add_member(team_id=team.id, user_id=user_id)
        assert result.team_id == team.id

    @pytest.mark.asyncio
    async def test_add_member_already_exists(self, mock_db, org_id, user_id):
        """Adding a user who is already a team member raises error."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Test Team")
        org_member = OrganizationMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            user_id=user_id,
            team_id=team.id,
            role=MembershipRole.OPERATOR,
            is_active=True,
        )

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            return r

        mock_db.execute.side_effect = [
            make_result(team),       # get_team
            make_result(org_member),  # _get_org_member
            make_result(org_member),  # _get_team_member (already a member)
        ]

        with pytest.raises(TeamMemberAlreadyExistsError):
            await service.add_member(team_id=team.id, user_id=user_id)

    @pytest.mark.asyncio
    async def test_remove_member(self, mock_db, org_id, user_id):
        """Removing a member from a team clears the team_id."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Test Team")
        org_member = OrganizationMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            user_id=user_id,
            team_id=team.id,
            role=MembershipRole.OPERATOR,
            is_active=True,
        )

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            return r

        mock_db.execute.side_effect = [
            make_result(team),       # get_team
            make_result(org_member),  # _get_team_member
        ]

        await service.remove_member(team_id=team.id, user_id=user_id)
        assert org_member.team_id is None

    @pytest.mark.asyncio
    async def test_remove_member_not_found(self, mock_db, org_id, user_id):
        """Removing a non-existent member raises error."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Test Team")

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            return r

        mock_db.execute.side_effect = [
            make_result(team),  # get_team
            make_result(None),  # _get_team_member (not found)
        ]

        with pytest.raises(TeamMemberNotFoundError):
            await service.remove_member(team_id=team.id, user_id=user_id)

    @pytest.mark.asyncio
    async def test_add_member_user_not_org_member(self, mock_db, org_id, user_id):
        """Adding a user who is not an org member raises error."""
        from app.ai.exceptions import AgentError

        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Test Team")

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            return r

        mock_db.execute.side_effect = [
            make_result(team),  # get_team
            make_result(None),  # _get_org_member (not found)
        ]

        with pytest.raises(AgentError):
            await service.add_member(team_id=team.id, user_id=user_id)


# ═══════════════════════════════════════════════════════════════════
# AGENT-TEAM ASSOCIATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAgentTeamAssociation:
    """Tests for agent-team assignment."""

    @pytest.mark.asyncio
    async def test_assign_agent_to_team(self, mock_db, org_id, user_id):
        """Assigning an agent to a team sets the team_id."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Test Team")
        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Test Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
            team_id=None,
        )

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            return r

        mock_db.execute.side_effect = [
            make_result(team),  # get_team
            make_result(agent),  # get_agent
        ]

        result = await service.assign_agent(team_id=team.id, agent_id=agent.id)
        assert result.team_id == team.id

    @pytest.mark.asyncio
    async def test_assign_agent_already_on_team(self, mock_db, org_id, user_id):
        """Assigning an agent that is already on the team raises error."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Test Team")
        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Test Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
            team_id=team.id,  # Already on this team
        )

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            return r

        mock_db.execute.side_effect = [
            make_result(team),  # get_team
            make_result(agent),  # get_agent
        ]

        with pytest.raises(TeamAgentAlreadyExistsError):
            await service.assign_agent(team_id=team.id, agent_id=agent.id)

    @pytest.mark.asyncio
    async def test_unassign_agent_from_team(self, mock_db, org_id, user_id):
        """Unassigning an agent from a team clears the team_id."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Test Team")
        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Test Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
            team_id=team.id,
        )

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            return r

        mock_db.execute.side_effect = [
            make_result(team),  # get_team
            make_result(agent),  # get_agent
        ]

        result = await service.unassign_agent(team_id=team.id, agent_id=agent.id)
        assert result.team_id is None

    @pytest.mark.asyncio
    async def test_unassign_agent_not_on_team(self, mock_db, org_id, user_id):
        """Unassigning an agent that is not on the team raises error."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Test Team")
        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Test Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
            team_id=None,  # Not on any team
        )

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            return r

        mock_db.execute.side_effect = [
            make_result(team),  # get_team
            make_result(agent),  # get_agent
        ]

        from app.ai.exceptions import TeamAgentNotFoundError
        with pytest.raises(TeamAgentNotFoundError):
            await service.unassign_agent(team_id=team.id, agent_id=agent.id)

    @pytest.mark.asyncio
    async def test_assign_agent_cross_tenant(self, mock_db, org_id, other_org_id, user_id):
        """Assigning an agent from another org raises cross-tenant error."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="My Team")
        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=other_org_id,  # Different org!
            name="Other Org Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
        )

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            return r

        mock_db.execute.side_effect = [
            make_result(team),  # get_team
            make_result(agent),  # get_agent
        ]

        with pytest.raises(AgentNotFoundError):
            await service.assign_agent(team_id=team.id, agent_id=agent.id)


# ═══════════════════════════════════════════════════════════════════
# TENANT ISOLATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestTenantIsolation:
    """Tests for organization-scoped access control."""

    @pytest.mark.asyncio
    async def test_get_team_wrong_org(self, mock_db, org_id, other_org_id, user_id):
        """Getting a team from a different org raises not found."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=other_org_id, name="Other Org Team")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = team
        mock_db.execute.return_value = mock_result

        with pytest.raises(TeamNotFoundError):
            await service.get_team(team.id)

    @pytest.mark.asyncio
    async def test_update_team_wrong_org(self, mock_db, org_id, other_org_id, user_id):
        """Updating a team from a different org raises not found."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=other_org_id, name="Other Org Team")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = team
        mock_db.execute.return_value = mock_result

        with pytest.raises(TeamNotFoundError):
            await service.update_team(team.id, name="Hacked")

    @pytest.mark.asyncio
    async def test_create_team_different_orgs(self, mock_db, org_id, other_org_id, user_id):
        """Teams in different orgs are isolated."""
        service_a = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)
        service_b = TeamService(db=mock_db, organization_id=other_org_id, user_id=user_id)

        # Both should be able to create a team with the same name
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        team_a = await service_a.create_team(name="Operations")
        team_b = await service_b.create_team(name="Operations")

        assert team_a.organization_id == org_id
        assert team_b.organization_id == other_org_id


# ═══════════════════════════════════════════════════════════════════
# OWNERSHIP RULES TESTS
# ═══════════════════════════════════════════════════════════════════

class TestOwnershipRules:
    """Tests for clear ownership boundaries."""

    @pytest.mark.asyncio
    async def test_agent_must_belong_to_same_org(self, mock_db, org_id, other_org_id, user_id):
        """An agent from a different org cannot be assigned to a team."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="My Team")
        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=other_org_id,
            name="Other Org Agent",
            agent_type=AgentType.INVENTORY,
        )

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            return r

        mock_db.execute.side_effect = [
            make_result(team),
            make_result(agent),
        ]

        with pytest.raises(AgentNotFoundError):
            await service.assign_agent(team_id=team.id, agent_id=agent.id)

    @pytest.mark.asyncio
    async def test_user_can_only_manage_own_org_teams(self, mock_db, org_id, other_org_id, user_id):
        """A user cannot manage teams in another organization."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=other_org_id, name="Other Org Team")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = team
        mock_db.execute.return_value = mock_result

        with pytest.raises(TeamNotFoundError):
            await service.get_team(team.id)


# ═══════════════════════════════════════════════════════════════════
# TEAM AUTHORIZATION HELPER TESTS
# ═══════════════════════════════════════════════════════════════════

class TestTeamAuthorization:
    """Tests for team authorization helpers."""

    @pytest.mark.asyncio
    async def test_user_is_team_member(self, mock_db, org_id, user_id):
        """Checking if a user is a team member returns correct result."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team_id = uuid.uuid4()
        org_member = OrganizationMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            user_id=user_id,
            team_id=team_id,
            is_active=True,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = org_member
        mock_db.execute.return_value = mock_result

        result = await service.user_is_team_member(team_id, user_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_user_is_not_team_member(self, mock_db, org_id, user_id):
        """Checking if a non-member is a team member returns False."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.user_is_team_member(uuid.uuid4(), user_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_owner_can_manage_team(self, mock_db, org_id, user_id):
        """An org owner can manage any team."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        org_member = OrganizationMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            user_id=user_id,
            role=MembershipRole.OWNER,
            is_active=True,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = org_member
        mock_db.execute.return_value = mock_result

        result = await service.user_can_manage_team(uuid.uuid4(), user_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_viewer_cannot_manage_team(self, mock_db, org_id, user_id):
        """A viewer cannot manage teams."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        org_member = OrganizationMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            user_id=user_id,
            role=MembershipRole.VIEWER,
            is_active=True,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = org_member
        mock_db.execute.return_value = mock_result

        result = await service.user_can_manage_team(uuid.uuid4(), user_id)
        assert result is False


# ═══════════════════════════════════════════════════════════════════
# EVENT TESTS
# ═══════════════════════════════════════════════════════════════════

class TestTeamEvents:
    """Tests for team domain events."""

    def test_team_created_event(self):
        """TeamCreated event has correct fields."""
        event = TeamCreated(
            team_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            name="Test Team",
            created_by=uuid.uuid4(),
        )
        assert event.name == "Test Team"
        assert event.event_id  # Auto-generated

    def test_team_updated_event(self):
        """TeamUpdated event has correct fields."""
        event = TeamUpdated(
            team_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            updated_fields=["name", "description"],
        )
        assert event.updated_fields == ["name", "description"]
        assert event.event_id

    def test_team_deactivated_event(self):
        """TeamDeactivated event has correct fields."""
        event = TeamDeactivated(
            team_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
        )
        assert event.event_id

    def test_team_member_added_event(self):
        """TeamMemberAdded event has correct fields."""
        event = TeamMemberAdded(
            team_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            role="operator",
        )
        assert event.role == "operator"
        assert event.event_id

    def test_team_member_removed_event(self):
        """TeamMemberRemoved event has correct fields."""
        event = TeamMemberRemoved(
            team_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
        )
        assert event.event_id

    def test_team_agent_assigned_event(self):
        """TeamAgentAssigned event has correct fields."""
        event = TeamAgentAssigned(
            team_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
        )
        assert event.event_id

    def test_team_agent_removed_event(self):
        """TeamAgentRemoved event has correct fields."""
        event = TeamAgentRemoved(
            team_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
        )
        assert event.event_id


# ═══════════════════════════════════════════════════════════════════
# SCHEMA TESTS
# ═══════════════════════════════════════════════════════════════════

class TestTeamSchemas:
    """Tests for Pydantic schemas."""

    def test_team_create_request(self):
        """TeamCreateRequest validates correctly."""
        req = TeamCreateRequest(name="Operations Team")
        assert req.name == "Operations Team"
        assert req.description is None

    def test_team_create_request_empty_name_fails(self):
        """TeamCreateRequest rejects empty name."""
        with pytest.raises(Exception):
            TeamCreateRequest(name="")

    def test_team_update_request(self):
        """TeamUpdateRequest validates correctly."""
        req = TeamUpdateRequest(name="New Name", description="New description")
        assert req.name == "New Name"
        assert req.description == "New description"

    def test_team_member_add_request(self):
        """TeamMemberAddRequest validates correctly."""
        req = TeamMemberAddRequest(user_id=str(uuid.uuid4()))
        assert req.user_id

    def test_team_agent_assign_request(self):
        """TeamAgentAssignRequest validates correctly."""
        req = TeamAgentAssignRequest(agent_id=str(uuid.uuid4()))
        assert req.agent_id


# ═══════════════════════════════════════════════════════════════════
# EXCEPTION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestTeamExceptions:
    """Tests for team-specific exceptions."""

    def test_team_not_found_error(self):
        """TeamNotFoundError has correct message and detail."""
        exc = TeamNotFoundError("test-team-id")
        assert "test-team-id" in exc.message
        assert exc.detail["error_code"] == "TEAM_NOT_FOUND"

    def test_team_name_conflict_error(self):
        """TeamNameConflictError has correct message and detail."""
        exc = TeamNameConflictError("Existing Team")
        assert "Existing Team" in exc.message
        assert exc.detail["error_code"] == "TEAM_NAME_CONFLICT"

    def test_team_member_not_found_error(self):
        """TeamMemberNotFoundError has correct message and detail."""
        exc = TeamMemberNotFoundError("team-123", "user-456")
        assert "team-123" in exc.message
        assert "user-456" in exc.message
        assert exc.detail["error_code"] == "TEAM_MEMBER_NOT_FOUND"

    def test_team_member_already_exists_error(self):
        """TeamMemberAlreadyExistsError has correct message."""
        exc = TeamMemberAlreadyExistsError("team-123", "user-456")
        assert "already" in exc.message.lower()

    def test_team_agent_already_exists_error(self):
        """TeamAgentAlreadyExistsError has correct message."""
        exc = TeamAgentAlreadyExistsError("team-123", "agent-456")
        assert "already" in exc.message.lower()

    def test_cross_tenant_team_error(self):
        """CrossTenantTeamError has correct error code."""
        exc = CrossTenantTeamError()
        assert exc.detail["error_code"] == "CROSS_TENANT_TEAM_ERROR"


# ═══════════════════════════════════════════════════════════════════
# AGENT TEAM ID INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAgentTeamIdIntegration:
    """Tests for agent team_id field in AIService."""

    @pytest.mark.asyncio
    async def test_create_agent_with_team_id(self, mock_db, org_id, user_id):
        """Creating an agent with a team_id sets the team_id."""
        from app.ai.service import AIService

        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)

        team_id = uuid.uuid4()

        # Mock no existing agent with same name
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        agent = await service.create_agent(
            name="Team Agent",
            agent_type=AgentType.INVENTORY,
            team_id=team_id,
        )

        assert agent.team_id == team_id

    @pytest.mark.asyncio
    async def test_create_agent_without_team_id(self, mock_db, org_id, user_id):
        """Creating an agent without a team_id leaves it None."""
        from app.ai.service import AIService

        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        agent = await service.create_agent(name="Standalone Agent")

        assert agent.team_id is None


# ═══════════════════════════════════════════════════════════════════
# LIST TEAM AGENTS TESTS
# ═══════════════════════════════════════════════════════════════════

class TestListTeamAgents:
    """Tests for listing agents in a team."""

    @pytest.mark.asyncio
    async def test_list_team_agents(self, mock_db, org_id, user_id):
        """Listing team agents returns agents assigned to that team."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Test Team")
        agent1 = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Agent 1",
            agent_type=AgentType.INVENTORY,
            team_id=team.id,
        )
        agent2 = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Agent 2",
            agent_type=AgentType.SOCIAL,
            team_id=team.id,
        )

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            r.scalars.return_value.all.return_value = obj if isinstance(obj, list) else [obj]
            return r

        mock_db.execute.side_effect = [
            make_result(team),           # get_team
            make_result([agent1, agent2]),  # list_team_agents
        ]

        agents = await service.list_team_agents(team.id)
        assert len(agents) == 2

    @pytest.mark.asyncio
    async def test_list_team_agents_empty(self, mock_db, org_id, user_id):
        """Listing team agents returns empty list when no agents assigned."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Empty Team")

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            r.scalars.return_value.all.return_value = []
            return r

        mock_db.execute.side_effect = [
            make_result(team),  # get_team
            make_result([]),    # list_team_agents
        ]

        agents = await service.list_team_agents(team.id)
        assert len(agents) == 0


# ═══════════════════════════════════════════════════════════════════
# COMPREHENSIVE INTEGRATION SCENARIO
# ═══════════════════════════════════════════════════════════════════

class TestTeamIntegrationScenario:
    """Integration test: full team lifecycle."""

    @pytest.mark.asyncio
    async def test_full_team_lifecycle(self, mock_db, org_id, user_id):
        """Test create team → assign agent → unassign agent."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        # Step 1: Create team with explicit id
        team_id = uuid.uuid4()
        team = Team(id=team_id, organization_id=org_id, name="Operations", description="Ops team")

        # Step 2: Assign agent
        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Inventory Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
            team_id=None,
        )

        team_result = MagicMock()
        team_result.scalar_one_or_none.return_value = team
        agent_result = MagicMock()
        agent_result.scalar_one_or_none.return_value = agent

        mock_db.execute.side_effect = [team_result, agent_result]
        assigned = await service.assign_agent(team_id=team.id, agent_id=agent.id)
        assert assigned.team_id == team.id

        # Step 3: Unassign agent
        mock_db.execute.side_effect = [team_result, agent_result]
        unassigned = await service.unassign_agent(team_id=team.id, agent_id=agent.id)
        assert unassigned.team_id is None


# ═══════════════════════════════════════════════════════════════════
# TEAM AUDIT LOGGING TESTS (Phase 4.6D)
# ═══════════════════════════════════════════════════════════════════

def _find_audit_actions(mock_db):
    """Extract all AIAgentAction objects added to the mock session."""
    actions = []
    for call in mock_db.add.call_args_list:
        obj = call[0][0] if call[0] else None
        if obj is not None and isinstance(obj, AIAgentAction):
            actions.append(obj)
    return actions


class TestTeamAuditLogging:
    """Tests that team operations create structured audit entries."""

    @pytest.mark.asyncio
    async def test_create_team_creates_audit(self, mock_db, org_id, user_id):
        """Creating a team creates an AIAgentAction with action_type=team_created."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        team = await service.create_team(name="Audit Team")

        audit_actions = _find_audit_actions(mock_db)
        assert len(audit_actions) >= 1
        audit = audit_actions[0]
        assert audit.action_type == "team_created"
        assert audit.target_resource == "team"
        assert audit.target_id == str(team.id)
        assert audit.organization_id == org_id
        assert audit.performed_by == user_id
        assert audit.result_status == "success"
        assert audit.details["name"] == "Audit Team"
        # 4.6D fix: team actions carry team_id and leave agent_id NULL
        # (never a fabricated agent_id, which used to violate the
        # ai_agents FK against a real database).
        assert audit.team_id == team.id
        assert audit.agent_id is None

    @pytest.mark.asyncio
    async def test_update_team_creates_audit(self, mock_db, org_id, user_id):
        """Updating a team creates an AIAgentAction with action_type=team_updated."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Old Name")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = team
        no_conflict = MagicMock()
        no_conflict.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [mock_result, no_conflict]

        await service.update_team(team.id, name="New Name")

        audit_actions = _find_audit_actions(mock_db)
        assert len(audit_actions) >= 1
        audit = audit_actions[0]
        assert audit.action_type == "team_updated"
        assert audit.target_resource == "team"
        assert audit.target_id == str(team.id)
        assert audit.organization_id == org_id
        assert "name" in audit.details["updated_fields"]

    @pytest.mark.asyncio
    async def test_deactivate_team_creates_audit(self, mock_db, org_id, user_id):
        """Deactivating a team creates an AIAgentAction with action_type=team_deactivated."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Team to Deactivate")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = team
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [mock_result, empty_result, empty_result]

        result = await service.deactivate_team(team.id)

        audit_actions = _find_audit_actions(mock_db)
        assert len(audit_actions) >= 1
        audit = audit_actions[0]
        assert audit.action_type == "team_deactivated"
        assert audit.target_resource == "team"
        assert audit.target_id == str(team.id)
        assert audit.organization_id == org_id
        assert audit.details["name"] == "Team to Deactivate"

    @pytest.mark.asyncio
    async def test_add_member_creates_audit(self, mock_db, org_id, user_id):
        """Adding a member creates an AIAgentAction with action_type=team_member_added."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Test Team")
        org_member = OrganizationMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            user_id=user_id,
            role=MembershipRole.OPERATOR,
            is_active=True,
        )

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            return r

        mock_db.execute.side_effect = [
            make_result(team),
            make_result(org_member),
            make_result(None),
        ]

        await service.add_member(team_id=team.id, user_id=user_id)

        audit_actions = _find_audit_actions(mock_db)
        assert len(audit_actions) >= 1
        audit = audit_actions[0]
        assert audit.action_type == "team_member_added"
        assert audit.target_resource == "team"
        assert audit.target_id == str(team.id)
        assert audit.organization_id == org_id
        assert audit.details["user_id"] == str(user_id)
        assert audit.details["role"] == "operator"

    @pytest.mark.asyncio
    async def test_remove_member_creates_audit(self, mock_db, org_id, user_id):
        """Removing a member creates an AIAgentAction with action_type=team_member_removed."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Test Team")
        org_member = OrganizationMember(
            id=uuid.uuid4(),
            organization_id=org_id,
            user_id=user_id,
            team_id=team.id,
            role=MembershipRole.OPERATOR,
            is_active=True,
        )

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            return r

        mock_db.execute.side_effect = [
            make_result(team),
            make_result(org_member),
        ]

        await service.remove_member(team_id=team.id, user_id=user_id)

        audit_actions = _find_audit_actions(mock_db)
        assert len(audit_actions) >= 1
        audit = audit_actions[0]
        assert audit.action_type == "team_member_removed"
        assert audit.target_resource == "team"
        assert audit.target_id == str(team.id)
        assert audit.organization_id == org_id
        assert audit.details["user_id"] == str(user_id)

    @pytest.mark.asyncio
    async def test_assign_agent_creates_audit(self, mock_db, org_id, user_id):
        """Assigning an agent creates an AIAgentAction with action_type=team_agent_assigned."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Test Team")
        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Test Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
            team_id=None,
        )

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            return r

        mock_db.execute.side_effect = [
            make_result(team),
            make_result(agent),
        ]

        await service.assign_agent(team_id=team.id, agent_id=agent.id)

        audit_actions = _find_audit_actions(mock_db)
        assert len(audit_actions) >= 1
        audit = audit_actions[0]
        assert audit.action_type == "team_agent_assigned"
        assert audit.target_resource == "team"
        assert audit.target_id == str(team.id)
        assert audit.organization_id == org_id
        assert audit.details["agent_id"] == str(agent.id)
        assert audit.details["agent_name"] == "Test Agent"
        # The audit row is scoped by the TEAM being assigned to, not the
        # (soon-to-be-reassigned) agent, and never fakes an agent_id.
        assert audit.team_id == team.id
        assert audit.agent_id is None

    @pytest.mark.asyncio
    async def test_unassign_agent_creates_audit(self, mock_db, org_id, user_id):
        """Unassigning an agent creates an AIAgentAction with action_type=team_agent_unassigned."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        team = Team(id=uuid.uuid4(), organization_id=org_id, name="Test Team")
        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Test Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
            team_id=team.id,
        )

        def make_result(obj):
            r = MagicMock()
            r.scalar_one_or_none.return_value = obj
            return r

        mock_db.execute.side_effect = [
            make_result(team),
            make_result(agent),
        ]

        await service.unassign_agent(team_id=team.id, agent_id=agent.id)

        audit_actions = _find_audit_actions(mock_db)
        assert len(audit_actions) >= 1
        audit = audit_actions[0]
        assert audit.action_type == "team_agent_unassigned"
        assert audit.target_resource == "team"
        assert audit.target_id == str(team.id)
        assert audit.organization_id == org_id
        assert audit.details["agent_id"] == str(agent.id)
        assert audit.details["agent_name"] == "Test Agent"

    @pytest.mark.asyncio
    async def test_audit_entries_contain_performed_by(self, mock_db, org_id, user_id):
        """All audit entries record the user who performed the action."""
        service = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        team = await service.create_team(name="Audit Check")

        audit_actions = _find_audit_actions(mock_db)
        assert len(audit_actions) >= 1
        for action in audit_actions:
            assert action.performed_by == user_id
            assert action.organization_id == org_id
            assert action.result_status == "success"
