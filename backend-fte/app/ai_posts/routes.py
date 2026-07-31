import uuid
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.ai_posts import service
from app.ai_posts.schemas import GeneratePostRequest, GeneratedPostOut

router = APIRouter(prefix="/posts", tags=["AI Post Generation"])


@router.post("/generate", response_model=GeneratedPostOut)
async def generate_post(
    payload: GeneratePostRequest,
    request: Request,
    student_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    caption = await service.generate_caption(payload.prompt)
    image_path = await service.generate_image(payload.prompt, payload.image_model)

    post = await service.save_generated_post(
        db, student_id, payload.prompt, caption, image_path, payload.image_model
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
        status=post.status,
        created_at=post.created_at,
    )