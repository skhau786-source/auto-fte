import uuid
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.ai_posts import service
from app.ai_posts.schemas import GeneratePostRequest, GeneratedPostOut
from app.brand.service import get_brand_profile, build_brand_system_prompt

router = APIRouter(prefix="/posts", tags=["AI Post Generation"])


@router.post("/generate", response_model=GeneratedPostOut)
async def generate_post(
    payload: GeneratePostRequest,
    request: Request,
    student_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    brand_profile = await get_brand_profile(db, student_id)
    system_prompt = build_brand_system_prompt(
        brand_profile,
        "You write short, catchy Instagram captions with relevant hashtags for e-commerce brands.",
    )

    caption = await service.generate_caption(payload.prompt, system_prompt=system_prompt)
    image_path = await service.generate_image(
        payload.prompt, model=payload.image_model, aspect_ratio=payload.aspect_ratio
    )

    post = await service.save_generated_post(
        db, student_id, payload.prompt, caption, image_path, payload.image_model, payload.aspect_ratio
    )

    # Build a full, browser-usable URL from the relative path
    base_url = str(request.base_url).rstrip("/")
    image_url = f"{base_url}/{post.image_path}"

    return GeneratedPostOut(
        id=post.id,
        prompt=post.prompt,
        caption=post.caption,
        image_url=image_url,
        image_model=post.image_model,
        aspect_ratio=post.aspect_ratio,
        status=post.status,
        created_at=post.created_at,
    )