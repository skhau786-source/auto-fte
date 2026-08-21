import uuid
from datetime import datetime, timezone
import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import PostComment, GeneratedPost, InstagramAccount, BrandProfile, Notification
from app.brand_profile import service as brand_service

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
IG_GRAPH_URL = "https://graph.instagram.com"


async def generate_ai_comment_reply(
    comment_text: str, post_caption: str | None, brand_profile: BrandProfile | None
) -> str:
    tone_str = brand_profile.tone if brand_profile else "friendly and professional"
    emoji_pref = brand_profile.emoji_preference if brand_profile else "moderate"
    prohibited = brand_profile.prohibited_words if brand_profile else "None"

    system_prompt = (
        f"You are an AI customer support assistant for an e-commerce brand on Instagram.\n"
        f"Brand Tone: {tone_str}\n"
        f"Emoji Preference: {emoji_pref}\n"
        f"Prohibited Words: {prohibited}\n"
        f"Rules:\n"
        f"- Write a concise, friendly, helpful response (1-2 sentences max) to the user's comment.\n"
        f"- Do NOT sound like a generic bot.\n"
        f"- Do NOT use prohibited words."
    )

    user_prompt = f"Instagram Post Context: '{post_caption or ''}'\nUser Comment: '{comment_text}'\nReply:"

    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 120,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(GROQ_URL, headers=headers, json=payload)

    if resp.status_code != 200:
        return "Thank you for your comment! 😊"

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


async def post_comment_reply_to_instagram(comment_id: str, reply_text: str, access_token: str) -> bool:
    url = f"{IG_GRAPH_URL}/v21.0/{comment_id}/replies"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            url,
            data={
                "message": reply_text,
                "access_token": access_token,
            },
        )
    return resp.status_code == 200


async def process_incoming_comment(
    db: AsyncSession,
    post_id: uuid.UUID,
    comment_id: str,
    commenter_username: str,
    comment_text: str,
) -> PostComment:
    # Check if comment already processed
    existing_res = await db.execute(select(PostComment).where(PostComment.comment_id == comment_id))
    existing = existing_res.scalar_one_or_none()
    if existing:
        return existing

    # Fetch post + user brand profile
    post_res = await db.execute(select(GeneratedPost).where(GeneratedPost.id == post_id))
    post = post_res.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found for comment")

    # Fetch IG account token
    ig_res = await db.execute(select(InstagramAccount).where(InstagramAccount.student_id == post.student_id))
    ig_account = ig_res.scalar_one_or_none()

    brand_profile = await brand_service.get_brand_profile_by_user(db, post.student_id)

    # Generate AI reply
    ai_reply = await generate_ai_comment_reply(comment_text, post.caption, brand_profile)

    # Post reply if token available
    posted_success = False
    if ig_account and ig_account.access_token:
        posted_success = await post_comment_reply_to_instagram(comment_id, ai_reply, ig_account.access_token)

    comment_obj = PostComment(
        post_id=post.id,
        comment_id=comment_id,
        commenter_username=commenter_username,
        comment_text=comment_text,
        ai_reply=ai_reply,
        status="replied" if posted_success else "pending",
        replied_at=datetime.now(timezone.utc) if posted_success else None,
    )
    db.add(comment_obj)

    # Create In-App Notification
    notification = Notification(
        student_id=post.student_id,
        type="comment_auto_replied" if posted_success else "comment_received",
        message=f"Auto-replied to @{commenter_username} on post: '{ai_reply}'",
        is_read=False,
    )
    db.add(notification)

    await db.commit()
    await db.refresh(comment_obj)
    return comment_obj
