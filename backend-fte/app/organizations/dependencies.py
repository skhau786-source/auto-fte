"""Dependencies for multi-tenant organization access and RBAC permission checking."""

import logging

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent
from app.organizations.service import OrganizationService
from app.organizations.models import Organization, Permission

logger = logging.getLogger(__name__)


async def get_current_organization(
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Resolve the current user's primary organization."""
    svc = OrganizationService(db)
    orgs = await svc.get_user_organizations(user.id)
    if not orgs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User is not a member of any organization",
        )
    return orgs[0]


def require_permission(required_permission: Permission):
    """Dependency factory that checks a specific permission."""
    async def _check_permission(
        org: Organization = Depends(get_current_organization),
        user: RegisteredStudent = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> bool:
        svc = OrganizationService(db)
        has_perm = await svc.user_has_permission(
            user_id=user.id,
            org_id=org.id,
            permission=required_permission.value,
        )
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {required_permission.value}",
            )
        return True
    return _check_permission
