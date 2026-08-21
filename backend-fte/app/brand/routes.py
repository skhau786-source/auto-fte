import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.brand import service
from app.brand.schemas import BrandProfileCreate, BrandProfileUpdate, BrandProfileOut

router = APIRouter(prefix="/brand-profile", tags=["Brand Profile"])


@router.get("", response_model=BrandProfileOut)
async def get_brand_profile(
    student_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    profile = await service.get_brand_profile(db, student_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand profile not found for this user",
        )
    return BrandProfileOut.model_validate(profile)


@router.post("", response_model=BrandProfileOut, status_code=status.HTTP_201_CREATED)
async def create_brand_profile(
    payload: BrandProfileCreate,
    student_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    profile = await service.create_or_update_brand_profile(db, student_id, payload)
    return BrandProfileOut.model_validate(profile)


@router.put("", response_model=BrandProfileOut)
async def update_brand_profile(
    payload: BrandProfileUpdate,
    student_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    profile = await service.create_or_update_brand_profile(db, student_id, payload)
    return BrandProfileOut.model_validate(profile)
