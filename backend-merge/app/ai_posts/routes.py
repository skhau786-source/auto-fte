import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RegisteredStudent, GeneratedPost
from app.dependencies import get_current_user
from app.ai_posts.schemas import PostGenerateRequest, PostOut, PostGenerateResponse
from app.ai_posts import service
from app.brand_profile import service as brand_service

router = APIRouter(prefix="/ai-posts", tags=["AI Posts"])


@router.post("/generate", response_model=PostGenerateResponse, status_code=status.HTTP_201_CREATED)
async def generate_post(
    payload: PostGenerateRequest,
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    brand_profile = await brand_service.get_brand_profile_by_user(db, current_user.id)
    system_prompt = service.build_brand_system_prompt(brand_profile)

    caption = await service.generate_caption(payload.prompt, system_prompt=system_prompt)
    image_path = await service.generate_image(
        payload.prompt, model=payload.model, aspect_ratio=payload.aspect_ratio, style_preset=payload.style_preset
    )

    post = await service.save_generated_post(
        db=db,
        student_id=current_user.id,
        prompt=payload.prompt,
        caption=caption,
        image_path=image_path,
        image_model=payload.model,
        aspect_ratio=payload.aspect_ratio,
    )

    return PostGenerateResponse(message="Post generated successfully", post=PostOut.model_validate(post))


@router.get("", response_model=list[PostOut])
async def list_user_posts(
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GeneratedPost)
        .where(GeneratedPost.student_id == current_user.id)
        .order_by(GeneratedPost.created_at.desc())
    )
    posts = result.scalars().all()
    return [PostOut.model_validate(p) for p in posts]


@router.get("/{post_id}", response_model=PostOut)
async def get_post_detail(
    post_id: uuid.UUID,
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GeneratedPost).where(GeneratedPost.id == post_id, GeneratedPost.student_id == current_user.id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return PostOut.model_validate(post)
