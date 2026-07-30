"""Organization service for multi-tenant operations."""

import uuid
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import RegisteredStudent
from app.organizations.models import (
    Organization, OrganizationMember, Team, MembershipRole, Permission,
)

logger = logging.getLogger(__name__)


class OrganizationService:
    """Manages organizations, teams, members, and tenant isolation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_organization(
        self, name: str, slug: str, owner_id: uuid.UUID,
        description: Optional[str] = None,
    ) -> Organization:
        """Create a new organization with the creator as owner."""
        org = Organization(name=name, slug=slug, description=description)
        self.db.add(org)
        await self.db.flush()

        member = OrganizationMember(
            organization_id=org.id,
            user_id=owner_id,
            role=MembershipRole.OWNER,
        )
        self.db.add(member)
        await self.db.commit()
        return org

    async def get_organization(self, org_id: uuid.UUID) -> Optional[Organization]:
        result = await self.db.execute(
            select(Organization).where(Organization.id == org_id)
        )
        return result.scalar_one_or_none()

    async def get_user_organizations(self, user_id: uuid.UUID) -> list[Organization]:
        result = await self.db.execute(
            select(Organization)
            .join(OrganizationMember)
            .where(
                OrganizationMember.user_id == user_id,
                OrganizationMember.is_active == True,
                Organization.is_active == True,
            )
        )
        return list(result.scalars().all())

    async def add_member(
        self, org_id: uuid.UUID, user_id: uuid.UUID,
        role: MembershipRole = MembershipRole.VIEWER,
        team_id: Optional[uuid.UUID] = None,
    ) -> OrganizationMember:
        member = OrganizationMember(
            organization_id=org_id, user_id=user_id,
            role=role, team_id=team_id,
        )
        self.db.add(member)
        await self.db.commit()
        return member

    async def get_member_permissions(
        self, user_id: uuid.UUID, org_id: uuid.UUID
    ) -> list[str]:
        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
                OrganizationMember.is_active == True,
            )
        )
        member = result.scalar_one_or_none()
        if member is None:
            return []
        return member.get_permissions()

    async def user_has_permission(
        self, user_id: uuid.UUID, org_id: uuid.UUID, permission: str
    ) -> bool:
        permissions = await self.get_member_permissions(user_id, org_id)
        return permission in permissions
