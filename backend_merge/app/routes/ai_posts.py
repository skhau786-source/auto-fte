from typing import Optional
from fastapi import APIRouter, Depends, Query, Request, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.ai_post_schema import GeneratePostRequest, GeneratedPostOut
from app.services import ai_post_service, auth_service

router = APIRouter(prefix="/posts", tags=["AI Post Generation"])


@router.post("/generate", response_model=GeneratedPostOut)
async def generate_post(
    payload: GeneratePostRequest,
    request: Request,
    user_id: Optional[int] = Query(None, description="Optional explicit user_id fallback"),
    current_user: Optional[User] = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    target_user_id = current_user.id if current_user else user_id
    if not target_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide Bearer token or user_id query param.",
        )

    caption = await ai_post_service.generate_caption(payload.prompt)
    image_path = await ai_post_service.generate_image(payload.prompt, payload.image_model)

    post = ai_post_service.save_generated_post(
        db, target_user_id, payload.prompt, caption, image_path, payload.image_model
    )

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
