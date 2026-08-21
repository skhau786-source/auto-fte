import uuid as uuid_lib
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GeneratedPost, InstagramAccount
from app.config import settings

IG_OAUTH_AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
IG_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
IG_GRAPH_URL = "https://graph.instagram.com"


def get_instagram_auth_url() -> str:
    """Builds the URL the frontend redirects the user to for Instagram Business login."""
    scopes = (
        "instagram_business_basic,"
        "instagram_business_content_publish,"
        "instagram_business_manage_comments,"
        "instagram_business_manage_messages"
    )
    return (
        f"{IG_OAUTH_AUTHORIZE_URL}"
        f"?client_id={settings.INSTAGRAM_APP_ID}"
        f"&redirect_uri={settings.INSTAGRAM_REDIRECT_URI}"
        f"&scope={scopes}"
        f"&response_type=code"
    )


async def exchange_code_for_short_token(code: str) -> tuple[str, str]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            IG_TOKEN_URL,
            data={
                "client_id": settings.INSTAGRAM_APP_ID,
                "client_secret": settings.INSTAGRAM_APP_SECRET,
                "grant_type": "authorization_code",
                "redirect_uri": settings.INSTAGRAM_REDIRECT_URI,
                "code": code,
            },
        )
    data = resp.json()
    if "access_token" not in data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Instagram token exchange failed: {data}")
    return data["access_token"], str(data.get("user_id", ""))


async def get_long_lived_token(short_token: str) -> tuple[str, int]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{IG_GRAPH_URL}/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": settings.INSTAGRAM_APP_SECRET,
                "access_token": short_token,
            },
        )
    data = resp.json()
    if "access_token" not in data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Long-lived token exchange failed: {data}")
    return data["access_token"], data.get("expires_in", 5184000)


async def get_instagram_profile(long_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{IG_GRAPH_URL}/v21.0/me",
            params={"fields": "user_id,username,account_type", "access_token": long_token},
        )
    data = resp.json()
    if "user_id" not in data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to fetch IG profile: {data}")
    return data


async def save_instagram_account(
    db: AsyncSession, student_id: uuid_lib.UUID, profile: dict, long_token: str, expires_in: int
) -> InstagramAccount:
    result = await db.execute(select(InstagramAccount).where(InstagramAccount.student_id == student_id))
    existing = result.scalar_one_or_none()

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    if existing:
        existing.ig_user_id = str(profile["user_id"])
        existing.ig_username = profile["username"]
        existing.account_type = profile.get("account_type")
        existing.access_token = long_token
        existing.token_expires_at = expires_at
        await db.commit()
        await db.refresh(existing)
        return existing

    account = InstagramAccount(
        student_id=student_id,
        ig_user_id=str(profile["user_id"]),
        ig_username=profile["username"],
        account_type=profile.get("account_type"),
        access_token=long_token,
        token_expires_at=expires_at,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def create_media_container(ig_user_id: str, access_token: str, image_url: str, caption: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{IG_GRAPH_URL}/v21.0/{ig_user_id}/media",
            data={
                "image_url": image_url,
                "caption": caption,
                "access_token": access_token,
            },
        )
    data = resp.json()
    if "id" not in data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to create media container: {data}")
    return data["id"]


async def publish_media_container(ig_user_id: str, access_token: str, creation_id: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{IG_GRAPH_URL}/v21.0/{ig_user_id}/media_publish",
            data={
                "creation_id": creation_id,
                "access_token": access_token,
            },
        )
    data = resp.json()
    if "id" not in data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to publish media: {data}")
    return data["id"]


async def publish_post(db: AsyncSession, post_id: uuid_lib.UUID, student_id: uuid_lib.UUID, public_image_url: str) -> str:
    ig_result = await db.execute(select(InstagramAccount).where(InstagramAccount.student_id == student_id))
    ig_account = ig_result.scalar_one_or_none()
    if not ig_account:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No Instagram account connected for this user")

    post_result = await db.execute(select(GeneratedPost).where(GeneratedPost.id == post_id))
    post = post_result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated post not found")
    if not post.image_path or not post.caption:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Post is missing image or caption")

    creation_id = await create_media_container(
        ig_account.ig_user_id, ig_account.access_token, public_image_url, post.caption
    )
    media_id = await publish_media_container(ig_account.ig_user_id, ig_account.access_token, creation_id)

    post.status = "published"
    post.instagram_media_id = media_id
    post.published_at = datetime.now(timezone.utc)
    await db.commit()

    return media_id
