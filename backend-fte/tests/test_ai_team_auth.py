"""
Tests for Phase 4 — 4.6B Team-Level Agent Authorization.

Authorization model:
  User → Organization → Team → Agent → Capability → Approval → Execution

Rules:
- Org OWNER/ADMIN can access any agent in their org (org-level management)
- Teamless agents (team_id=None) are accessible to all org members
- Users must be members of the agent's team to access it
- Unauthorized access raises TeamAccessDeniedError
- Cross-tenant access remains impossible
- Team authorization is an ADDITIONAL boundary — does not replace RBAC
"""

import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.ai.models import AIAgent
from app.ai.constants import AgentType, AgentStatus
from app.ai.service import AIService
from app.ai.team_service import TeamService
from app.ai.exceptions import (
    TeamAccessDeniedError,
    AgentNotFoundError,
    CrossTenantTeamError,
)
from app.organizations.models import (
    Organization, Team, OrganizationMember, MembershipRole,
)
from app.models import RegisteredStudent


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def org_id():
    return uuid.uuid4()


@pytest.fixture
def other_org_id():
    return uuid.uuid4()


@pytest.fixture
def user_id():
    return uuid.uuid4()


@pytest.fixture
def other_user_id():
    return uuid.uuid4()


@pytest.fixture
def team_id():
    return uuid.uuid4()


@pytest.fixture
def other_team_id():
    return uuid.uuid4()


@pytest_asyncio.fixture
async def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_result(obj):
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r


def _make_count_result(count=0):
    r = MagicMock()
    r.scalar.return_value = count
    return r


# ═══════════════════════════════════════════════════════════════════
# TEAM-LEVEL ACCESS CONTROL — can_user_access_agent
# ═══════════════════════════════════════════════════════════════════

class TestCanUserAccessAgent:
    """Tests for TeamService.can_user_access_agent()."""

    @pytest.mark.asyncio
    async def test_org_owner_can_access_any_agent(self, mock_db, org_id, user_id, team_id):
        """Org OWNER can access any agent regardless of team assignment."""
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Team Agent", team_id=team_id,
            agent_type=AgentType.INVENTORY,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.OWNER, is_active=True,
        )

        mock_db.execute.side_effect = [
            _make_result(agent),      # _get_agent_by_id
            _make_result(org_member), # _get_org_member
        ]

        result = await team_svc.can_user_access_agent(user_id, agent.id)
        assert result is True

    @pytest.mark.asyncio
    async def test_org_admin_can_access_any_agent(self, mock_db, org_id, user_id, team_id):
        """Org ADMIN can access any agent regardless of team assignment."""
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Team Agent", team_id=team_id,
            agent_type=AgentType.INVENTORY,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.ADMIN, is_active=True,
        )

        mock_db.execute.side_effect = [
            _make_result(agent),
            _make_result(org_member),
        ]

        result = await team_svc.can_user_access_agent(user_id, agent.id)
        assert result is True

    @pytest.mark.asyncio
    async def test_team_member_can_access_team_agent(self, mock_db, org_id, user_id, team_id):
        """Team member can access an agent assigned to their team."""
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Team Agent", team_id=team_id,
            agent_type=AgentType.INVENTORY,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.OPERATOR, is_active=True,
        )
        team_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, team_id=team_id,
            role=MembershipRole.OPERATOR, is_active=True,
        )

        mock_db.execute.side_effect = [
            _make_result(agent),
            _make_result(org_member),
            _make_result(team_member),
        ]

        result = await team_svc.can_user_access_agent(user_id, agent.id)
        assert result is True

    @pytest.mark.asyncio
    async def test_non_member_cannot_access_team_agent(self, mock_db, org_id, user_id, other_team_id, team_id):
        """Non-member cannot access an agent assigned to a different team."""
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Team Agent", team_id=team_id,
            agent_type=AgentType.INVENTORY,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.OPERATOR, is_active=True,
        )

        # User is NOT in the agent's team
        mock_db.execute.side_effect = [
            _make_result(agent),
            _make_result(org_member),
            _make_result(None),  # No team membership
        ]

        result = await team_svc.can_user_access_agent(user_id, agent.id)
        assert result is False

    @pytest.mark.asyncio
    async def test_teamless_agent_accessible_to_all_org_members(self, mock_db, org_id, user_id):
        """Teamless agents (team_id=None) are accessible to all org members."""
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Teamless Agent", team_id=None,
            agent_type=AgentType.CUSTOM,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.VIEWER, is_active=True,
        )

        mock_db.execute.side_effect = [
            _make_result(agent),
            _make_result(org_member),
        ]

        result = await team_svc.can_user_access_agent(user_id, agent.id)
        assert result is True

    @pytest.mark.asyncio
    async def test_viewer_with_no_team_membership_denied(self, mock_db, org_id, user_id, team_id):
        """VIEWER not in the team is denied access to team agent."""
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Team Agent", team_id=team_id,
            agent_type=AgentType.INVENTORY,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.VIEWER, is_active=True,
        )

        mock_db.execute.side_effect = [
            _make_result(agent),
            _make_result(org_member),
            _make_result(None),  # Not in the team
        ]

        result = await team_svc.can_user_access_agent(user_id, agent.id)
        assert result is False

    @pytest.mark.asyncio
    async def test_non_org_member_denied(self, mock_db, org_id, other_user_id, team_id):
        """Non-org member cannot access any agent."""
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=other_user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Team Agent", team_id=team_id,
            agent_type=AgentType.INVENTORY,
        )

        mock_db.execute.side_effect = [
            _make_result(agent),
            _make_result(None),  # Not an org member
            _make_result(None),  # Not a team member
        ]

        result = await team_svc.can_user_access_agent(other_user_id, agent.id)
        assert result is False

    @pytest.mark.asyncio
    async def test_cross_org_agent_denied(self, mock_db, org_id, other_org_id, user_id):
        """User cannot access agent from a different organization."""
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=other_org_id,
            name="Other Org Agent", team_id=None,
            agent_type=AgentType.INVENTORY,
        )

        # _get_agent_by_id finds the agent, but _ensure_org_owns_agent raises
        mock_db.execute.side_effect = [_make_result(agent)]

        with pytest.raises(AgentNotFoundError):
            await team_svc.can_user_access_agent(user_id, agent.id)

    @pytest.mark.asyncio
    async def test_manager_in_team_can_access(self, mock_db, org_id, user_id, team_id):
        """MANAGER who is a team member can access the team agent."""
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Team Agent", team_id=team_id,
            agent_type=AgentType.INVENTORY,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.MANAGER, is_active=True,
        )
        team_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, team_id=team_id,
            role=MembershipRole.MANAGER, is_active=True,
        )

        mock_db.execute.side_effect = [
            _make_result(agent),
            _make_result(org_member),
            _make_result(team_member),
        ]

        result = await team_svc.can_user_access_agent(user_id, agent.id)
        assert result is True


# ═══════════════════════════════════════════════════════════════════
# AISERVICE TEAM AUTHORIZATION INTEGRATION
# ═══════════════════════════════════════════════════════════════════

class TestAIServiceTeamAuth:
    """Tests for AIService.check_team_agent_access()."""

    @pytest.mark.asyncio
    async def test_check_team_agent_access_allowed(self, mock_db, org_id, user_id, team_id):
        """Team member can access team agent via AIService."""
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Team Agent", team_id=team_id,
            agent_type=AgentType.INVENTORY,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.OPERATOR, is_active=True,
        )
        team_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, team_id=team_id,
            role=MembershipRole.OPERATOR, is_active=True,
        )

        mock_db.execute.side_effect = [
            _make_result(org_member), # can_access_agent → _get_org_member (OPERATOR)
            _make_result(team_member),# can_access_agent → _get_team_member (same team)
        ]

        # Should not raise — can_access_agent uses the passed agent directly
        await service.check_team_agent_access(agent)

    @pytest.mark.asyncio
    async def test_check_team_agent_access_denied(self, mock_db, org_id, user_id, team_id):
        """Non-member is denied via AIService."""
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Team Agent", team_id=team_id,
            agent_type=AgentType.INVENTORY,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.OPERATOR, is_active=True,
        )

        mock_db.execute.side_effect = [
            _make_result(org_member), # can_access_agent → _get_org_member (OPERATOR)
            _make_result(None),       # can_access_agent → _get_team_member (not in team)
        ]

        with pytest.raises(TeamAccessDeniedError):
            await service.check_team_agent_access(agent)

    @pytest.mark.asyncio
    async def test_check_teamless_agent_allowed(self, mock_db, org_id, user_id):
        """Teamless agent is accessible to all org members."""
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Teamless Agent", team_id=None,
            agent_type=AgentType.CUSTOM,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.VIEWER, is_active=True,
        )

        mock_db.execute.side_effect = [
            _make_result(org_member),
        ]

        # Should not raise — can_access_agent uses the passed agent directly
        await service.check_team_agent_access(agent)

    @pytest.mark.asyncio
    async def test_check_no_user_context_skips_check(self, mock_db, org_id):
        """No user_id context (internal execution) skips team check."""
        service = AIService(db=mock_db, organization_id=org_id, user_id=None)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Agent", team_id=uuid.uuid4(),
            agent_type=AgentType.CUSTOM,
        )

        # Should not raise — user_id is None, so check is skipped
        await service.check_team_agent_access(agent)


# ═══════════════════════════════════════════════════════════════════
# TEAM-TO-AGENT AUTHORIZATION SCENARIOS
# ═══════════════════════════════════════════════════════════════════

class TestTeamAgentAuthScenarios:
    """Full authorization scenarios matching the spec."""

    @pytest.mark.asyncio
    async def test_user_a_accesses_agent_a1_allowed(self, mock_db, org_id, team_id):
        """User A in Team A → Agent A1 in Team A = ALLOW."""
        user_id = uuid.uuid4()
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Agent A1", team_id=team_id,
            agent_type=AgentType.INVENTORY,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.OPERATOR, is_active=True,
        )
        team_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, team_id=team_id,
            role=MembershipRole.OPERATOR, is_active=True,
        )

        mock_db.execute.side_effect = [
            _make_result(agent), _make_result(org_member), _make_result(team_member),
        ]

        assert await team_svc.can_user_access_agent(user_id, agent.id) is True

    @pytest.mark.asyncio
    async def test_user_a_accesses_agent_a2_denied(self, mock_db, org_id, team_id, other_team_id):
        """User A in Team A → Agent A2 in Team B = DENY."""
        user_id = uuid.uuid4()
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Agent A2", team_id=other_team_id,
            agent_type=AgentType.INVENTORY,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.OPERATOR, is_active=True,
        )

        mock_db.execute.side_effect = [
            _make_result(agent), _make_result(org_member), _make_result(None),
        ]

        assert await team_svc.can_user_access_agent(user_id, agent.id) is False

    @pytest.mark.asyncio
    async def test_user_b_accesses_agent_a1_denied(self, mock_db, org_id, team_id):
        """User B (different org) → Agent A1 = DENY (cross-tenant)."""
        other_user = uuid.uuid4()
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=other_user)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Agent A1", team_id=team_id,
            agent_type=AgentType.INVENTORY,
        )

        # User B is not an org member
        mock_db.execute.side_effect = [
            _make_result(agent), _make_result(None), _make_result(None),
        ]

        assert await team_svc.can_user_access_agent(other_user, agent.id) is False

    @pytest.mark.asyncio
    async def test_owner_bypasses_team_restriction(self, mock_db, org_id, team_id, other_team_id):
        """Org OWNER can access agent in any team."""
        user_id = uuid.uuid4()
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Other Team Agent", team_id=other_team_id,
            agent_type=AgentType.INVENTORY,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.OWNER, is_active=True,
        )

        mock_db.execute.side_effect = [
            _make_result(agent), _make_result(org_member),
        ]

        assert await team_svc.can_user_access_agent(user_id, agent.id) is True

    @pytest.mark.asyncio
    async def test_admin_bypasses_team_restriction(self, mock_db, org_id, team_id, other_team_id):
        """Org ADMIN can access agent in any team."""
        user_id = uuid.uuid4()
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Other Team Agent", team_id=other_team_id,
            agent_type=AgentType.INVENTORY,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.ADMIN, is_active=True,
        )

        mock_db.execute.side_effect = [
            _make_result(agent), _make_result(org_member),
        ]

        assert await team_svc.can_user_access_agent(user_id, agent.id) is True


# ═══════════════════════════════════════════════════════════════════
# EXCEPTION TESTS
# ═══════════════════════════════════════════════════════════════════

class TestTeamAccessDeniedError:
    """Tests for TeamAccessDeniedError exception."""

    def test_error_message_and_detail(self):
        exc = TeamAccessDeniedError(agent_id="agent-123", team_id="team-456")
        assert "agent-123" in exc.message
        assert exc.detail["error_code"] == "TEAM_ACCESS_DENIED"
        assert exc.detail["agent_id"] == "agent-123"
        assert exc.detail["team_id"] == "team-456"

    def test_error_with_no_team(self):
        exc = TeamAccessDeniedError(agent_id="agent-789", team_id="none")
        assert "agent-789" in exc.message
        assert exc.detail["team_id"] == "none"


# ═══════════════════════════════════════════════════════════════════
# TEAMLESS AGENT BACKWARD COMPATIBILITY
# ═══════════════════════════════════════════════════════════════════

class TestTeamlessAgentBackwardCompatibility:
    """Teamless agents remain fully accessible — backward compatible."""

    @pytest.mark.asyncio
    async def test_viewer_can_access_teamless_agent(self, mock_db, org_id):
        """VIEWER can access a teamless agent."""
        user_id = uuid.uuid4()
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Legacy Agent", team_id=None,
            agent_type=AgentType.CUSTOM,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.VIEWER, is_active=True,
        )

        mock_db.execute.side_effect = [_make_result(agent), _make_result(org_member)]

        assert await team_svc.can_user_access_agent(user_id, agent.id) is True

    @pytest.mark.asyncio
    async def test_operator_can_access_teamless_agent(self, mock_db, org_id):
        """OPERATOR can access a teamless agent."""
        user_id = uuid.uuid4()
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Legacy Agent", team_id=None,
            agent_type=AgentType.INVENTORY,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.OPERATOR, is_active=True,
        )

        mock_db.execute.side_effect = [_make_result(agent), _make_result(org_member)]

        assert await team_svc.can_user_access_agent(user_id, agent.id) is True

    @pytest.mark.asyncio
    async def test_manager_can_access_teamless_agent(self, mock_db, org_id):
        """MANAGER can access a teamless agent."""
        user_id = uuid.uuid4()
        team_svc = TeamService(db=mock_db, organization_id=org_id, user_id=user_id)

        agent = AIAgent(
            id=uuid.uuid4(), organization_id=org_id,
            name="Legacy Agent", team_id=None,
            agent_type=AgentType.SALES,
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.MANAGER, is_active=True,
        )

        mock_db.execute.side_effect = [_make_result(agent), _make_result(org_member)]

        assert await team_svc.can_user_access_agent(user_id, agent.id) is True


# ═══════════════════════════════════════════════════════════════════
# RBAC + TEAM — CAPABILITY AUTHORIZATION NOT BYPASSED
# ═══════════════════════════════════════════════════════════════════

class TestRBACNotBypassedByTeam:
    """Team membership does NOT bypass existing RBAC or capability authorization."""

    @pytest.mark.asyncio
    async def test_team_member_still_needs_rbac_permission(self, mock_db, org_id, user_id, team_id):
        """
        Even though a user is a team member, they still need AGENT_EXECUTE
        permission for the existing RBAC check. Team auth is additive.
        """
        from app.organizations.service import OrganizationService

        # Simulate: user has team membership but no AGENT_EXECUTE permission
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.VIEWER, is_active=True,
        )

        svc = OrganizationService(mock_db)
        # VIEWER does NOT have AGENT_EXECUTE permission
        perms = svc.user_has_permission.__wrapped__ if hasattr(svc.user_has_permission, '__wrapped__') else None
        # Instead, test directly via the permission system
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = org_member
        mock_db.execute.return_value = mock_result

        member = await svc.get_member_permissions(user_id, org_id)
        # VIEWER permissions do NOT include AGENT_EXECUTE
        assert "agent:execute" not in member
        assert "agent:manage" not in member
        assert "agent:approve" not in member

    @pytest.mark.asyncio
    async def test_approval_not_bypassed_by_team_membership(self, mock_db, org_id, user_id, team_id):
        """
        Team authorization does NOT bypass the approval system.
        A capability requiring approval still requires approval.
        """
        from app.ai.capabilities.base import capability_registry
        from app.ai.capabilities.executor import CapabilityExecutor

        # Ensure capabilities are registered
        if not capability_registry.list_all():
            from app.ai.capabilities.inventory_capabilities import register_inventory_capabilities
            from app.ai.capabilities.social_capabilities import register_social_capabilities
            from app.ai.capabilities.sales_capabilities import register_sales_capabilities
            register_inventory_capabilities()
            register_social_capabilities()
            register_sales_capabilities()

        # inventory.adjust_stock requires approval
        cap = capability_registry.get("inventory.adjust_stock")
        assert cap is not None
        assert cap.requires_approval is True

        # Even with team membership, approval-gated capability returns pending_approval
        executor = CapabilityExecutor(db=mock_db, organization_id=org_id, user_id=user_id)
        result = await executor.execute_with_approval_check(
            capability_name="inventory.adjust_stock",
            input_data={"variant_id": str(uuid.uuid4()), "quantity_change": 10},
            is_approved=False,
            agent_type="inventory",
        )
        assert result["status"] == "pending_approval"
        assert result["requires_approval"] is True
