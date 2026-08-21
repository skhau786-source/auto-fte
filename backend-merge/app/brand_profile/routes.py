from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RegisteredStudent
from app.dependencies import get_current_user
from app.brand_profile.schemas import BrandProfileCreate, BrandProfileOut
from app.brand_profile import service

router = APIRouter(prefix="/brand-profile", tags=["Brand Profile"])


@router.get("", response_model=BrandProfileOut)
async def get_my_brand_profile(
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await service.get_brand_profile_by_user(db, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand profile not found for this user. Please create one.",
        )
    return BrandProfileOut.model_validate(profile)


@router.post("", response_model=BrandProfileOut, status_code=status.HTTP_200_OK)
async def create_or_update_my_brand_profile(
    payload: BrandProfileCreate,
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await service.upsert_brand_profile(db, current_user, payload)
    return BrandProfileOut.model_validate(profile)
