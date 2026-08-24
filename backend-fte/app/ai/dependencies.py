"""
AI Agent dependencies — tenant isolation and RBAC permission checking.

Reuses the existing organization dependency architecture:
- get_current_organization for tenant scoping
- require_permission for RBAC checks
"""

import uuid
import logging

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent
from app.organizations.dependencies import get_current_organization
from app.organizations.models import Organization, Permission
from app.organizations.service import OrganizationService

logger = logging.getLogger(__name__)


async def require_agent_manage(
    org: Organization = Depends(get_current_organization),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Require AGENT_MANAGE permission for the current user's organization."""
    svc = OrganizationService(db)
    has_perm = await svc.user_has_permission(
        user_id=user.id,
        org_id=org.id,
        permission=Permission.AGENT_MANAGE.value,
    )
    if not has_perm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage AI agents",
        )
    return org


async def require_agent_execute(
    org: Organization = Depends(get_current_organization),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Require AGENT_EXECUTE permission for the current user's organization."""
    svc = OrganizationService(db)
    has_perm = await svc.user_has_permission(
        user_id=user.id,
        org_id=org.id,
        permission=Permission.AGENT_EXECUTE.value,
    )
    if not has_perm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to execute AI agent tasks",
        )
    return org


async def require_agent_approve(
    org: Organization = Depends(get_current_organization),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Require AGENT_APPROVE permission for the current user's organization."""
    svc = OrganizationService(db)
    has_perm = await svc.user_has_permission(
        user_id=user.id,
        org_id=org.id,
        permission=Permission.AGENT_APPROVE.value,
    )
    if not has_perm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to approve AI agent tasks",
        )
    return org
