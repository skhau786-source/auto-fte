import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BrandProfile, RegisteredStudent
from app.brand_profile.schemas import BrandProfileCreate, BrandProfileUpdate


async def get_brand_profile_by_user(db: AsyncSession, user_id: uuid.UUID) -> BrandProfile | None:
    result = await db.execute(select(BrandProfile).where(BrandProfile.student_id == user_id))
    return result.scalar_one_or_none()


async def upsert_brand_profile(
    db: AsyncSession, user: RegisteredStudent, data: BrandProfileCreate
) -> BrandProfile:
    profile = await get_brand_profile_by_user(db, user.id)
    if profile:
        profile.tone = data.tone
        profile.sample_captions = data.sample_captions
        profile.prohibited_words = data.prohibited_words
        profile.emoji_preference = data.emoji_preference
        profile.target_audience = data.target_audience
    else:
        profile = BrandProfile(
            student_id=user.id,
            tone=data.tone,
            sample_captions=data.sample_captions,
            prohibited_words=data.prohibited_words,
            emoji_preference=data.emoji_preference,
            target_audience=data.target_audience,
        )
        db.add(profile)

    await db.commit()
    await db.refresh(profile)
    return profile
