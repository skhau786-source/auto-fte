import uuid
from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.instagram import service
from app.instagram.schemas import InstagramConnectResponse, InstagramAccountOut

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