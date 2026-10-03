import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BrandProfile
from app.brand.schemas import BrandProfileCreate, BrandProfileUpdate


async def get_brand_profile(db: AsyncSession, student_id: uuid.UUID) -> BrandProfile | None:
    result = await db.execute(select(BrandProfile).where(BrandProfile.student_id == student_id))
    return result.scalar_one_or_none()


async def create_or_update_brand_profile(
    db: AsyncSession, student_id: uuid.UUID, data: BrandProfileCreate | BrandProfileUpdate
) -> BrandProfile:
    profile = await get_brand_profile(db, student_id)

    if profile:
        update_dict = data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(profile, key, value)
        await db.commit()
        await db.refresh(profile)
        return profile

    new_profile = BrandProfile(
        student_id=student_id,
        tone=getattr(data, "tone", "professional"),
        sample_captions=getattr(data, "sample_captions", None),
        prohibited_words=getattr(data, "prohibited_words", None),
        emoji_preference=getattr(data, "emoji_preference", "moderate"),
        target_audience=getattr(data, "target_audience", None),
    )
    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)
    return new_profile


def build_brand_system_prompt(profile: BrandProfile | None, task_description: str) -> str:
    """
    Constructs a rich Groq system prompt incorporating user's brand voice & tone settings.
    """
    prompt = f"{task_description}\n"
    if not profile:
        return prompt + "Maintain a clean, engaging, and professional brand tone."

    prompt += f"\n--- BRAND VOICE INSTRUCTIONS ---"
    prompt += f"\n- Tone of Voice: {profile.tone}"
    prompt += f"\n- Emoji Usage Level: {profile.emoji_preference}"

    if profile.target_audience:
        prompt += f"\n- Target Audience: {profile.target_audience}"

    if profile.prohibited_words:
        prompt += f"\n- PROHIBITED WORDS/PHRASES (DO NOT USE THESE): {profile.prohibited_words}"

    if profile.sample_captions:
        prompt += f"\n- Brand Reference Examples:\n{profile.sample_captions}"

    prompt += "\n--- END INSTRUCTIONS ---"
    return prompt
