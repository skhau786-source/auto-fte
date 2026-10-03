import uuid
from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, Request
from app.database import get_db
from app.instagram import service
from app.instagram.schemas import InstagramConnectResponse, InstagramAccountOut,PublishPostRequest,PublishPostResponse

router = APIRouter(prefix="/instagram", tags=["Instagram"])


@router.get("/connect")
async def connect_instagram():
    return {"auth_url": service.get_instagram_auth_url()}


@router.get("/callback", response_model=InstagramConnectResponse)
async def instagram_callback(
    code: str = Query(...),
    student_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    short_token, _ = await service.exchange_code_for_short_token(code)
    long_token, expires_in = await service.get_long_lived_token(short_token)
    profile = await service.get_instagram_profile(long_token)

    account = await service.save_instagram_account(db, student_id, profile, long_token, expires_in)

    return InstagramConnectResponse(
        message="Instagram account connected successfully",
        account=InstagramAccountOut.model_validate(account),
    )


@router.post("/publish", response_model=PublishPostResponse)
async def publish_to_instagram(
    payload: PublishPostRequest,
    request: Request,
    student_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Publishes a previously generated post (caption + image) to the connected
    Instagram account. Requires the image to be reachable via a PUBLIC URL
    (e.g. through ngrok) since Instagram's servers fetch it directly.
    """
    base_url = str(request.base_url).rstrip("/")

    from sqlalchemy import select
    from app.models import GeneratedPost
    post_result = await db.execute(select(GeneratedPost).where(GeneratedPost.id == payload.post_id))
    post = post_result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    public_image_url = f"{base_url}/{post.image_path}"

    media_id = await service.publish_post(db, payload.post_id, student_id, public_image_url)

    return PublishPostResponse(
        message="Post published to Instagram successfully",
        instagram_media_id=media_id,
        post_id=payload.post_id,
    )