from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.generated_post import GeneratedPost
from app.models.user import User
from app.schemas.instagram_schema import (
    InstagramAccountOut,
    InstagramConnectResponse,
    PublishPostRequest,
    PublishPostResponse,
)
from app.services import auth_service, instagram_service

router = APIRouter(prefix="/instagram", tags=["Instagram"])


@router.get("/connect")
def connect_instagram():
    """Generates and returns Instagram OAuth authorization URL."""
    return {"auth_url": instagram_service.get_instagram_auth_url()}


@router.get("/callback", response_model=InstagramConnectResponse)
async def instagram_callback(
    code: str = Query(...),
    user_id: Optional[int] = Query(None),
    current_user: Optional[User] = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Callback endpoint handling Instagram OAuth code exchange."""
    target_user_id = current_user.id if current_user else user_id
    if not target_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide Bearer token or user_id query param.",
        )

    short_token, _ = await instagram_service.exchange_code_for_short_token(code)
    long_token, expires_in = await instagram_service.get_long_lived_token(short_token)
    profile = await instagram_service.get_instagram_profile(long_token)

    account = instagram_service.save_instagram_account(
        db, target_user_id, profile, long_token, expires_in
    )

    return InstagramConnectResponse(
        message="Instagram account connected successfully",
        account=InstagramAccountOut.model_validate(account),
    )


@router.post("/publish", response_model=PublishPostResponse)
async def publish_to_instagram(
    payload: PublishPostRequest,
    request: Request,
    user_id: Optional[int] = Query(None),
    current_user: Optional[User] = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    """Publishes a generated post to the connected Instagram Business account."""
    target_user_id = current_user.id if current_user else user_id
    if not target_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide Bearer token or user_id query param.",
        )

    post = db.query(GeneratedPost).filter(GeneratedPost.id == payload.post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    base_url = str(request.base_url).rstrip("/")
    public_image_url = f"{base_url}/{post.image_path}"

    media_id = await instagram_service.publish_post(
        db, payload.post_id, target_user_id, public_image_url
    )

    return PublishPostResponse(
        message="Post published to Instagram successfully",
        instagram_media_id=media_id,
        post_id=payload.post_id,
    )
