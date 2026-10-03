"""Organization routes: create your organization and read the ones you belong to."""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent
from app.organizations.models import Organization
from app.organizations.service import OrganizationService

router = APIRouter(prefix="/organizations", tags=["Organizations"])


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str | None = Field(default=None, max_length=255)
    description: str | None = None


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    subscription_plan: str
    subscription_status: str

    model_config = {"from_attributes": True}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "org"


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: OrganizationCreate,
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create an organization; the caller becomes its owner. A user may own only one."""
    svc = OrganizationService(db)
    if await svc.get_user_organizations(user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "You already belong to an organization")

    slug = _slugify(body.slug or body.name)
    taken = await db.execute(select(Organization.id).where(Organization.slug == slug))
    if taken.first():
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    try:
        return await svc.create_organization(
            name=body.name, slug=slug, owner_id=user.id, description=body.description
        )
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Organization slug already taken")


@router.get("/me", response_model=list[OrganizationOut])
async def my_organizations(
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Organizations the current user belongs to."""
    return await OrganizationService(db).get_user_organizations(user.id)
