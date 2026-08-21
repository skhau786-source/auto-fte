import uuid
from fastapi import APIRouter, Query, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RegisteredStudent, GeneratedPost, InstagramAccount
from app.dependencies import get_current_user
from app.instagram import service
from app.instagram.schemas import InstagramAccountOut, InstagramPublishRequest

router = APIRouter(prefix="/instagram", tags=["Instagram"])


@router.get("/connect")
async def connect_instagram():
    return {"auth_url": service.get_instagram_auth_url()}


@router.get("/callback")
async def instagram_callback(
    code: str = Query(...),
    student_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    short_token, _ = await service.exchange_code_for_short_token(code)
    long_token, expires_in = await service.get_long_lived_token(short_token)
    profile = await service.get_instagram_profile(long_token)

    account = await service.save_instagram_account(db, student_id, profile, long_token, expires_in)

    return {
        "message": "Instagram account connected successfully",
        "account": InstagramAccountOut.model_validate(account),
    }


@router.get("/account", response_model=InstagramAccountOut)
async def get_connected_account(
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(InstagramAccount).where(InstagramAccount.student_id == current_user.id))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="No connected Instagram account found.")
    return InstagramAccountOut.model_validate(account)


@router.post("/publish")
async def publish_to_instagram(
    payload: InstagramPublishRequest,
    request: Request,
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    base_url = str(request.base_url).rstrip("/")
    post_result = await db.execute(
        select(GeneratedPost).where(GeneratedPost.id == payload.post_id, GeneratedPost.student_id == current_user.id)
    )
    post = post_result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    public_image_url = payload.public_image_url or f"{base_url}/{post.image_path}"
    media_id = await service.publish_post(db, payload.post_id, current_user.id, public_image_url)

    return {
        "message": "Post published to Instagram successfully",
        "instagram_media_id": media_id,
        "post_id": payload.post_id,
    }
