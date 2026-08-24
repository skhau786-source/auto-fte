"""
Team Service — business logic for team management, membership, and agent assignment.

All operations are organization-scoped for tenant isolation.
Team membership reuses the existing OrganizationMember model.
Agent-team association uses the team_id FK on AIAgent.

Domain exceptions are raised here (never HTTPException).
The router layer catches and converts them to HTTP responses.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import RegisteredStudent
from app.organizations.models import Organization, OrganizationMember, Team, MembershipRole
from app.ai.models import AIAgent, AIAgentAction
from app.ai.constants import AgentStatus
from app.ai.exceptions import (
    AgentError,
    TeamNotFoundError,
    TeamNameConflictError,
    TeamMemberNotFoundError,
    TeamMemberAlreadyExistsError,
    TeamAgentNotFoundError,
    TeamAgentAlreadyExistsError,
    AgentNotFoundError,
    CrossTenantTeamError,
)
from app.ai.events import (
    TeamCreated,
    TeamUpdated,
    TeamDeactivated,
    TeamMemberAdded,
    TeamMemberRemoved,
    TeamAgentAssigned,
    TeamAgentRemoved,
)
from app.events.event_dispatcher import get_dispatcher

logger = logging.getLogger(__name__)


class TeamService:
    """
    Manages teams within an organization.

    Usage:
        service = TeamService(db=db, organization_id=org.id, user_id=user.id)
        team = await service.create_team(name="Operations")
    """

    def __init__(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ):
        self.db = db
        self.organization_id = organization_id
        self.user_id = user_id
        self.logger = logging.getLogger(f"{__name__}.TeamService")

    # ═══════════════════════════════════════════════════════════════
    # TEAM CRUD
    # ═══════════════════════════════════════════════════════════════

    async def create_team(
        self,
        name: str,
        description: Optional[str] = None,
    ) -> Team:
        """Create a new team in the organization."""
        # Check name uniqueness within org
        existing = await self._get_team_by_name(name)
        if existing:
            raise TeamNameConflictError(name)

        team = Team(
            organization_id=self.organization_id,
            name=name,
            description=description,
        )
        self.db.add(team)

        # Audit log (before commit so it's in the same transaction)
        await self._log_action(
            action_type="team_created",
            target_resource="team",
            target_id=str(team.id),
            details={"name": name, "description": description},
        )

        await self.db.commit()
        await self.db.refresh(team)

        # Dispatch event
        dispatcher = get_dispatcher()
        await dispatcher.dispatch(TeamCreated(
            team_id=team.id,
            organization_id=self.organization_id,
            name=name,
            created_by=self.user_id or uuid.UUID(int=0),
        ))

        self.logger.info(
            "Team created: %s (org=%s)", name, self.organization_id
        )
        return team

    async def list_teams(self) -> list[Team]:
        """List all teams for the organization."""
        result = await self.db.execute(
            select(Team)
            .where(Team.organization_id == self.organization_id)
            .order_by(Team.created_at.desc())
        )
        teams = list(result.scalars().all())

        # Annotate with member and agent counts
        for team in teams:
            team._member_count = await self._count_team_members(team.id)
            team._agent_count = await self._count_team_agents(team.id)

        return teams

    async def get_team(self, team_id: uuid.UUID) -> Team:
        """Get a single team by ID, validating org ownership."""
        team = await self._get_team_by_id(team_id)
        self._ensure_org_owns_team(team)
        return team

    async def update_team(
        self,
        team_id: uuid.UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Team:
        """Partially update a team (PATCH semantics)."""
        team = await self._get_team_by_id(team_id)
        self._ensure_org_owns_team(team)

        updated_fields = []
        if name is not None:
            if name != team.name:
                existing = await self._get_team_by_name(name)
                if existing:
                    raise TeamNameConflictError(name)
            team.name = name
            updated_fields.append("name")
        if description is not None:
            team.description = description
            updated_fields.append("description")

        if updated_fields:
            # Audit log (before commit so it's in the same transaction)
            await self._log_action(
                action_type="team_updated",
                target_resource="team",
                target_id=str(team.id),
                details={"updated_fields": updated_fields, "name": team.name},
            )

            await self.db.commit()
            await self.db.refresh(team)

            # Dispatch event
            dispatcher = get_dispatcher()
            await dispatcher.dispatch(TeamUpdated(
                team_id=team.id,
                organization_id=self.organization_id,
                updated_fields=updated_fields,
            ))

        return team

    async def deactivate_team(self, team_id: uuid.UUID) -> Team:
        """
        Deactivate a team.

        This disassociates all agents from the team and removes all
        team memberships. The team record is preserved for audit.
        """
        team = await self._get_team_by_id(team_id)
        self._ensure_org_owns_team(team)

        # Remove all agents from this team
        await self._remove_all_team_agents(team.id)

        # Remove all team memberships
        await self._remove_all_team_members(team.id)

        # Delete the team record (soft approach: just delete it)
        await self.db.delete(team)

        # Audit log (before commit so it's in the same transaction)
        await self._log_action(
            action_type="team_deactivated",
            target_resource="team",
            target_id=str(team.id),
            details={"name": team.name},
        )

        await self.db.commit()

        # Dispatch event
        dispatcher = get_dispatcher()
        await dispatcher.dispatch(TeamDeactivated(
            team_id=team.id,
            organization_id=self.organization_id,
        ))

        self.logger.info(
            "Team deactivated: %s (org=%s)", team.name, self.organization_id
        )
        return team

    # ═══════════════════════════════════════════════════════════════
    # TEAM MEMBERSHIP
    # ═══════════════════════════════════════════════════════════════

    async def add_member(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
        role: Optional[str] = None,
    ) -> OrganizationMember:
        """Add a user to a team. The user must be a member of the organization."""
        team = await self._get_team_by_id(team_id)
        self._ensure_org_owns_team(team)

        # Verify user is an org member
        org_member = await self._get_org_member(user_id)
        if org_member is None:
            raise AgentError(
                message=f"User '{user_id}' is not a member of this organization",
                detail={"error_code": "USER_NOT_ORG_MEMBER"},
            )

        # Check if already a team member
        existing = await self._get_team_member(team_id, user_id)
        if existing:
            raise TeamMemberAlreadyExistsError(str(team_id), str(user_id))

        # Update the org member's team assignment
        org_member.team_id = team_id
        if role:
            try:
                org_member.role = MembershipRole(role)
            except ValueError:
                pass  # Keep existing role if invalid

        # Audit log (before commit so it's in the same transaction)
        await self._log_action(
            action_type="team_member_added",
            target_resource="team",
            target_id=str(team.id),
            details={"user_id": str(user_id), "role": org_member.role.value},
        )

        await self.db.commit()
        await self.db.refresh(org_member)

        # Dispatch event
        dispatcher = get_dispatcher()
        await dispatcher.dispatch(TeamMemberAdded(
            team_id=team.id,
            user_id=user_id,
            organization_id=self.organization_id,
            role=org_member.role.value,
        ))

        self.logger.info(
            "Team member added: user=%s to team=%s", user_id, team.name
        )
        return org_member

    async def remove_member(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Remove a user from a team."""
        team = await self._get_team_by_id(team_id)
        self._ensure_org_owns_team(team)

        org_member = await self._get_team_member(team_id, user_id)
        if org_member is None:
            raise TeamMemberNotFoundError(str(team_id), str(user_id))

        # Remove team assignment (set team_id to None)
        org_member.team_id = None

        # Audit log (before commit so it's in the same transaction)
        await self._log_action(
            action_type="team_member_removed",
            target_resource="team",
            target_id=str(team.id),
            details={"user_id": str(user_id)},
        )

        await self.db.commit()

        # Dispatch event
        dispatcher = get_dispatcher()
        await dispatcher.dispatch(TeamMemberRemoved(
            team_id=team.id,
            user_id=user_id,
            organization_id=self.organization_id,
        ))

        self.logger.info(
            "Team member removed: user=%s from team=%s", user_id, team.name
        )

    async def list_members(self, team_id: uuid.UUID) -> list[dict]:
        """List all members of a team."""
        team = await self._get_team_by_id(team_id)
        self._ensure_org_owns_team(team)

        result = await self.db.execute(
            select(OrganizationMember)
            .join(RegisteredStudent, OrganizationMember.user_id == RegisteredStudent.id)
            .where(
                OrganizationMember.organization_id == self.organization_id,
                OrganizationMember.team_id == team_id,
                OrganizationMember.is_active == True,  # noqa: E712
            )
            .order_by(OrganizationMember.created_at)
        )
        members = list(result.scalars().all())

        member_list = []
        for m in members:
            # Fetch user details
            user_result = await self.db.execute(
                select(RegisteredStudent).where(RegisteredStudent.id == m.user_id)
            )
            user = user_result.scalar_one_or_none()
            member_list.append({
                "user_id": str(m.user_id),
                "username": user.username if user else None,
                "email": user.email if user else None,
                "full_name": user.full_name if user else None,
                "role": m.role.value,
                "is_active": m.is_active,
                "joined_at": m.created_at,
            })

        return member_list

    # ═══════════════════════════════════════════════════════════════
    # AGENT-TEAM ASSOCIATION
    # ═══════════════════════════════════════════════════════════════

    async def assign_agent(
        self,
        team_id: uuid.UUID,
        agent_id: uuid.UUID,
    ) -> AIAgent:
        """Assign an agent to a team. Both must belong to the same organization."""
        team = await self._get_team_by_id(team_id)
        self._ensure_org_owns_team(team)

        agent = await self._get_agent_by_id(agent_id)
        self._ensure_org_owns_agent(agent)

        # Cross-tenant check: verify agent and team are in the same org
        if agent.organization_id != self.organization_id:
            raise CrossTenantTeamError(
                "Agent does not belong to this organization"
            )

        if agent.team_id == team_id:
            raise TeamAgentAlreadyExistsError(str(team_id), str(agent_id))

        # Assign agent to team
        agent.team_id = team_id

        # Audit log (before commit so it's in the same transaction)
        await self._log_action(
            action_type="team_agent_assigned",
            target_resource="team",
            target_id=str(team.id),
            details={"agent_id": str(agent.id), "agent_name": agent.name},
        )

        await self.db.commit()
        await self.db.refresh(agent)

        # Dispatch event
        dispatcher = get_dispatcher()
        await dispatcher.dispatch(TeamAgentAssigned(
            team_id=team.id,
            agent_id=agent.id,
            organization_id=self.organization_id,
        ))

        self.logger.info(
            "Agent assigned to team: agent=%s team=%s", agent.name, team.name
        )
        return agent

    async def unassign_agent(
        self,
        team_id: uuid.UUID,
        agent_id: uuid.UUID,
    ) -> AIAgent:
        """Remove an agent from a team."""
        team = await self._get_team_by_id(team_id)
        self._ensure_org_owns_team(team)

        agent = await self._get_agent_by_id(agent_id)
        self._ensure_org_owns_agent(agent)

        if agent.team_id != team_id:
            raise TeamAgentNotFoundError(str(team_id), str(agent_id))

        # Remove from team
        agent.team_id = None

        # Audit log (before commit so it's in the same transaction)
        await self._log_action(
            action_type="team_agent_unassigned",
            target_resource="team",
            target_id=str(team.id),
            details={"agent_id": str(agent.id), "agent_name": agent.name},
        )

        await self.db.commit()
        await self.db.refresh(agent)

        # Dispatch event
        dispatcher = get_dispatcher()
        await dispatcher.dispatch(TeamAgentRemoved(
            team_id=team.id,
            agent_id=agent.id,
            organization_id=self.organization_id,
        ))

        self.logger.info(
            "Agent unassigned from team: agent=%s team=%s", agent.name, team.name
        )
        return agent

    async def list_team_agents(self, team_id: uuid.UUID) -> list[AIAgent]:
        """List all agents assigned to a team."""
        team = await self._get_team_by_id(team_id)
        self._ensure_org_owns_team(team)

        result = await self.db.execute(
            select(AIAgent)
            .where(
                AIAgent.organization_id == self.organization_id,
                AIAgent.team_id == team_id,
                AIAgent.is_active == True,  # noqa: E712
            )
            .order_by(AIAgent.created_at.desc())
        )
        return list(result.scalars().all())

    # ═══════════════════════════════════════════════════════════════
    # TEAM AUTHORIZATION HELPERS
    # ═══════════════════════════════════════════════════════════════

    async def user_is_team_member(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Check if a user is a member of a specific team."""
        member = await self._get_team_member(team_id, user_id)
        return member is not None

    async def user_can_manage_team(
        self,
        team_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Check if a user can manage a team (owner or admin)."""
        member = await self._get_org_member(user_id)
        if member is None:
            return False
        return member.role in (MembershipRole.OWNER, MembershipRole.ADMIN)

    async def agent_belongs_to_team(
        self,
        team_id: uuid.UUID,
        agent_id: uuid.UUID,
    ) -> bool:
        """Check if an agent is assigned to a specific team."""
        agent = await self._get_agent_by_id(agent_id)
        return agent.team_id == team_id

    async def can_access_agent(
        self,
        agent: AIAgent,
        user_id: uuid.UUID,
    ) -> bool:
        """
        Check if a user is authorized to access a specific agent.

        Accepts an already-loaded AIAgent object to avoid a redundant
        DB query. This is the preferred entry point when the caller
        already has the agent (e.g. from check_task_access).

        Authorization rules:
        1. Organization OWNER or ADMIN → always allowed (org-level management)
        2. Agent has no team_id (teamless) → allowed (backward compatible)
        3. User is a member of the agent's team → allowed
        4. Otherwise → denied

        This is the central team-level authorization decision point.
        It does NOT replace org-level RBAC — it adds an additional boundary.
        """
        self._ensure_org_owns_agent(agent)

        # Rule 1: Org OWNER/ADMIN can access any agent in their org
        org_member = await self._get_org_member(user_id)
        if org_member and org_member.role in (
            MembershipRole.OWNER, MembershipRole.ADMIN,
        ):
            return True

        # Rule 2: Teamless agents are accessible to all org members
        if agent.team_id is None:
            return org_member is not None

        # Rule 3: User must be a member of the agent's team
        team_member = await self._get_team_member(agent.team_id, user_id)
        return team_member is not None

    async def can_user_access_agent(
        self,
        user_id: uuid.UUID,
        agent_id: uuid.UUID,
    ) -> bool:
        """
        Check if a user is authorized to access a specific agent.

        Fetches the agent by ID and delegates to can_access_agent().
        Use can_access_agent() directly when the agent is already loaded.
        """
        agent = await self._get_agent_by_id(agent_id)
        return await self.can_access_agent(agent=agent, user_id=user_id)

    async def get_user_accessible_agent_ids(self) -> set[uuid.UUID]:
        """
        Return the set of agent IDs the current user may access within
        the organization, based on team-level authorization.

        Used by AIService to filter task and workflow queries efficiently.

        Rules:
        1. Org OWNER/ADMIN → all active agents in the org
        2. Org member with no team → only teamless agents
        3. Org member on team(s) → teamless agents + agents on their team(s)
        4. Non-org-member → empty set (should never happen upstream)
        """
        if self.user_id is None:
            return set()

        org_member = await self._get_org_member(self.user_id)
        if org_member is None:
            return set()

        # OWNER/ADMIN: unrestricted within org
        if org_member.role in (MembershipRole.OWNER, MembershipRole.ADMIN):
            result = await self.db.execute(
                select(AIAgent.id).where(
                    AIAgent.organization_id == self.organization_id,
                    AIAgent.is_active == True,  # noqa: E712
                )
            )
            return set(result.scalars().all())

        # Collect user's team IDs
        user_team_ids: list[uuid.UUID] = []
        if org_member.team_id is not None:
            user_team_ids.append(org_member.team_id)

        # Base query: all active agents in the org
        agent_query = select(AIAgent.id).where(
            AIAgent.organization_id == self.organization_id,
            AIAgent.is_active == True,  # noqa: E712
        )

        if user_team_ids:
            # Allow: teamless agents + agents on user's team(s)
            from sqlalchemy import or_
            agent_query = agent_query.where(
                or_(
                    AIAgent.team_id.is_(None),
                    AIAgent.team_id.in_(user_team_ids),
                )
            )
        else:
            # User has no team: only teamless agents
            agent_query = agent_query.where(AIAgent.team_id.is_(None))

        result = await self.db.execute(agent_query)
        return set(result.scalars().all())

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ═══════════════════════════════════════════════════════════════

    async def _get_team_by_id(self, team_id: uuid.UUID) -> Team:
        """Fetch a team by ID."""
        result = await self.db.execute(
            select(Team).where(Team.id == team_id)
        )
        team = result.scalar_one_or_none()
        if team is None:
            raise TeamNotFoundError(str(team_id))
        return team

    async def _get_team_by_name(self, name: str) -> Optional[Team]:
        """Fetch a team by name within the organization."""
        result = await self.db.execute(
            select(Team).where(
                Team.organization_id == self.organization_id,
                Team.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def _get_agent_by_id(self, agent_id: uuid.UUID) -> AIAgent:
        """Fetch an agent by ID."""
        result = await self.db.execute(
            select(AIAgent).where(AIAgent.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            raise AgentNotFoundError(str(agent_id))
        return agent

    async def _get_org_member(self, user_id: uuid.UUID) -> Optional[OrganizationMember]:
        """Fetch an org member by user ID."""
        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == self.organization_id,
                OrganizationMember.user_id == user_id,
                OrganizationMember.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def _get_team_member(
        self, team_id: uuid.UUID, user_id: uuid.UUID
    ) -> Optional[OrganizationMember]:
        """Fetch a team member by user ID."""
        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == self.organization_id,
                OrganizationMember.team_id == team_id,
                OrganizationMember.user_id == user_id,
                OrganizationMember.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def _count_team_members(self, team_id: uuid.UUID) -> int:
        """Count members in a team."""
        result = await self.db.execute(
            select(func.count()).select_from(OrganizationMember).where(
                OrganizationMember.organization_id == self.organization_id,
                OrganizationMember.team_id == team_id,
                OrganizationMember.is_active == True,  # noqa: E712
            )
        )
        return result.scalar() or 0

    async def _count_team_agents(self, team_id: uuid.UUID) -> int:
        """Count agents in a team."""
        result = await self.db.execute(
            select(func.count()).select_from(AIAgent).where(
                AIAgent.organization_id == self.organization_id,
                AIAgent.team_id == team_id,
                AIAgent.is_active == True,  # noqa: E712
            )
        )
        return result.scalar() or 0

    def _ensure_org_owns_team(self, team: Team) -> None:
        """Raise if the team does not belong to the current organization."""
        if str(team.organization_id) != str(self.organization_id):
            raise TeamNotFoundError(str(team.id))

    def _ensure_org_owns_agent(self, agent: AIAgent) -> None:
        """Raise if the agent does not belong to the current organization."""
        if str(agent.organization_id) != str(self.organization_id):
            raise AgentNotFoundError(str(agent.id))

    async def _remove_all_team_agents(self, team_id: uuid.UUID) -> None:
        """Remove all agents from a team (set team_id to None)."""
        result = await self.db.execute(
            select(AIAgent).where(
                AIAgent.organization_id == self.organization_id,
                AIAgent.team_id == team_id,
            )
        )
        agents = list(result.scalars().all())
        for agent in agents:
            agent.team_id = None

    async def _remove_all_team_members(self, team_id: uuid.UUID) -> None:
        """Remove all team memberships (set team_id to None)."""
        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == self.organization_id,
                OrganizationMember.team_id == team_id,
            )
        )
        members = list(result.scalars().all())
        for m in members:
            m.team_id = None

    # ═══════════════════════════════════════════════════════════════
    # AUDIT LOGGING
    # ═══════════════════════════════════════════════════════════════

    async def _log_action(
        self,
        action_type: str,
        target_resource: Optional[str] = None,
        target_id: Optional[str] = None,
        details: Optional[dict] = None,
        result_status: str = "success",
    ) -> AIAgentAction:
        """Create an immutable audit log entry for team operations."""
        action = AIAgentAction(
            agent_id=uuid.uuid4(),  # placeholder — team actions are not agent-specific
            organization_id=self.organization_id,
            action_type=action_type,
            target_resource=target_resource,
            target_id=target_id,
            result_status=result_status,
            details=details,
            performed_by=self.user_id,
        )
        self.db.add(action)
        await self.db.flush()  # Flush but don't commit — let the caller commit
        return action
