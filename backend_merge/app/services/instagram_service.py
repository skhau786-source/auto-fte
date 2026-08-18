import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models.generated_post import GeneratedPost
from app.models.instagram_account import InstagramAccount

IG_OAUTH_AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
IG_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
IG_GRAPH_URL = "https://graph.instagram.com"


def get_instagram_auth_url() -> str:
    """Builds the URL for Instagram authorization."""
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
    """Exchanges auth code for short-lived access token + IG user id."""
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Instagram token exchange failed: {data}",
        )
    return data["access_token"], str(data.get("user_id", ""))


async def get_long_lived_token(short_token: str) -> tuple[str, int]:
    """Exchanges short-lived token for long-lived token (~60 days)."""
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Long-lived token exchange failed: {data}",
        )
    return data["access_token"], data.get("expires_in", 5184000)


async def get_instagram_profile(long_token: str) -> dict:
    """Fetches connected Instagram profile details."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{IG_GRAPH_URL}/v21.0/me",
            params={"fields": "user_id,username,account_type", "access_token": long_token},
        )
    data = resp.json()
    if "user_id" not in data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch IG profile: {data}",
        )
    return data


def save_instagram_account(
    db: Session,
    user_id: int,
    profile: dict,
    long_token: str,
    expires_in: int,
) -> InstagramAccount:
    """Saves or updates connected Instagram Account for user."""
    existing = db.query(InstagramAccount).filter(InstagramAccount.user_id == user_id).first()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    if existing:
        existing.ig_user_id = str(profile["user_id"])
        existing.ig_username = profile["username"]
        existing.account_type = profile.get("account_type")
        existing.access_token = long_token
        existing.token_expires_at = expires_at
        db.commit()
        db.refresh(existing)
        return existing

    account = InstagramAccount(
        user_id=user_id,
        ig_user_id=str(profile["user_id"]),
        ig_username=profile["username"],
        account_type=profile.get("account_type"),
        access_token=long_token,
        token_expires_at=expires_at,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


async def create_media_container(
    ig_user_id: str, access_token: str, image_url: str, caption: str
) -> str:
    """Uploads image + caption, returns creation_id."""
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create media container: {data}",
        )
    return data["id"]


async def publish_media_container(
    ig_user_id: str, access_token: str, creation_id: str
) -> str:
    """Publishes created container to Instagram feed."""
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to publish media: {data}",
        )
    return data["id"]


async def publish_post(
    db: Session,
    post_id: uuid.UUID,
    user_id: int,
    public_image_url: str,
) -> str:
    """Full publish flow: fetch post + IG account, publish to IG, update DB."""
    ig_account = db.query(InstagramAccount).filter(InstagramAccount.user_id == user_id).first()
    if not ig_account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Instagram account connected for this user",
        )

    post = db.query(GeneratedPost).filter(GeneratedPost.id == post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generated post not found",
        )
    if not post.image_path or not post.caption:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Post is missing image or caption",
        )

    creation_id = await create_media_container(
        ig_account.ig_user_id, ig_account.access_token, public_image_url, post.caption
    )
    media_id = await publish_media_container(
        ig_account.ig_user_id, ig_account.access_token, creation_id
    )

    post.status = "published"
    post.instagram_media_id = media_id
    post.published_at = datetime.now(timezone.utc)
    db.commit()

    return media_id
