import uuid
import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GeneratedPost, PostAnalytics, InstagramAccount, RegisteredStudent
from app.analytics.schemas import AnalyticsSummaryOut, PostAnalyticsOut

IG_GRAPH_URL = "https://graph.instagram.com"


async def fetch_post_insights(media_id: str, access_token: str) -> dict:
    """Fetches like count, comment count, reach, and impressions from IG Graph API."""
    async with httpx.AsyncClient(timeout=20) as client:
        media_resp = await client.get(
            f"{IG_GRAPH_URL}/v21.0/{media_id}",
            params={"fields": "like_count,comments_count", "access_token": access_token},
        )
        insights_resp = await client.get(
            f"{IG_GRAPH_URL}/v21.0/{media_id}/insights",
            params={"metric": "reach,impressions", "access_token": access_token},
        )

    like_count = 0
    comment_count = 0
    reach = 0
    impressions = 0

    if media_resp.status_code == 200:
        mdata = media_resp.json()
        like_count = mdata.get("like_count", 0)
        comment_count = mdata.get("comments_count", 0)

    if insights_resp.status_code == 200:
        idata = insights_resp.json().get("data", [])
        for metric in idata:
            if metric.get("name") == "reach":
                reach = metric.get("values", [{}])[0].get("value", 0)
            elif metric.get("name") == "impressions":
                impressions = metric.get("values", [{}])[0].get("value", 0)

    return {
        "likes": like_count,
        "comments": comment_count,
        "reach": reach,
        "impressions": impressions,
    }


async def refresh_post_analytics(db: AsyncSession, post: GeneratedPost, ig_account: InstagramAccount) -> PostAnalytics | None:
    if not post.instagram_media_id:
        return None

    stats = await fetch_post_insights(post.instagram_media_id, ig_account.access_token)

    analytics_record = PostAnalytics(
        post_id=post.id,
        likes=stats["likes"],
        comments=stats["comments"],
        reach=stats["reach"],
        impressions=stats["impressions"],
    )
    db.add(analytics_record)
    await db.commit()
    await db.refresh(analytics_record)
    return analytics_record


async def get_user_analytics_summary(db: AsyncSession, user_id: uuid.UUID) -> AnalyticsSummaryOut:
    posts_res = await db.execute(select(GeneratedPost).where(GeneratedPost.student_id == user_id))
    all_posts = posts_res.scalars().all()
    published_posts = [p for p in all_posts if p.status == "published"]

    published_ids = [p.id for p in published_posts]

    total_likes = 0
    total_comments = 0
    total_reach = 0
    total_impressions = 0
    latest_records = []

    if published_ids:
        for pid in published_ids:
            res = await db.execute(
                select(PostAnalytics)
                .where(PostAnalytics.post_id == pid)
                .order_by(PostAnalytics.fetched_at.desc())
                .limit(1)
            )
            rec = res.scalar_one_or_none()
            if rec:
                total_likes += rec.likes
                total_comments += rec.comments
                total_reach += rec.reach
                total_impressions += rec.impressions
                latest_records.append(PostAnalyticsOut.model_validate(rec))

    return AnalyticsSummaryOut(
        total_posts=len(all_posts),
        published_posts=len(published_posts),
        total_likes=total_likes,
        total_comments=total_comments,
        total_reach=total_reach,
        total_impressions=total_impressions,
        latest_analytics=latest_records,
    )
