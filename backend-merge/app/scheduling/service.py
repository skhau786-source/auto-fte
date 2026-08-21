import uuid
from datetime import datetime, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models import ScheduledPost, GeneratedPost, RegisteredStudent, InstagramAccount, Notification
from app.scheduling.schemas import SchedulePostCreate
from app.instagram import service as ig_service


async def schedule_post(db: AsyncSession, user: RegisteredStudent, data: SchedulePostCreate) -> ScheduledPost:
    post_res = await db.execute(
        select(GeneratedPost).where(GeneratedPost.id == data.post_id, GeneratedPost.student_id == user.id)
    )
    post = post_res.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found or unauthorized")

    existing_res = await db.execute(select(ScheduledPost).where(ScheduledPost.post_id == data.post_id))
    existing = existing_res.scalar_one_or_none()

    if existing:
        existing.scheduled_time = data.scheduled_time
        existing.status = "pending"
        existing.error_message = None
        item = existing
    else:
        item = ScheduledPost(
            post_id=data.post_id,
            student_id=user.id,
            scheduled_time=data.scheduled_time,
            status="pending",
        )
        db.add(item)

    post.status = "scheduled"
    await db.commit()
    await db.refresh(item)
    return item


async def get_user_schedule(
    db: AsyncSession, user_id: uuid.UUID, start_time: datetime | None = None, end_time: datetime | None = None
) -> list[ScheduledPost]:
    query = select(ScheduledPost).where(ScheduledPost.student_id == user_id)
    if start_time:
        query = query.where(ScheduledPost.scheduled_time >= start_time)
    if end_time:
        query = query.where(ScheduledPost.scheduled_time <= end_time)

    query = query.order_by(ScheduledPost.scheduled_time.asc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def delete_scheduled_post(db: AsyncSession, user_id: uuid.UUID, schedule_id: uuid.UUID) -> None:
    res = await db.execute(
        select(ScheduledPost).where(ScheduledPost.id == schedule_id, ScheduledPost.student_id == user_id)
    )
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled post not found")

    post_res = await db.execute(select(GeneratedPost).where(GeneratedPost.id == item.post_id))
    post = post_res.scalar_one_or_none()
    if post:
        post.status = "draft"

    await db.delete(item)
    await db.commit()


async def process_due_scheduled_posts(db: AsyncSession, base_url: str = "") -> int:
    """Worker function executed by APScheduler every minute to publish due posts."""
    now = datetime.now(timezone.utc)
    due_query = select(ScheduledPost).where(
        and_(ScheduledPost.status == "pending", ScheduledPost.scheduled_time <= now)
    )
    result = await db.execute(due_query)
    due_posts = result.scalars().all()

    processed_count = 0
    for sched in due_posts:
        try:
            post_res = await db.execute(select(GeneratedPost).where(GeneratedPost.id == sched.post_id))
            post = post_res.scalar_one_or_none()
            if not post:
                sched.status = "failed"
                sched.error_message = "Associated GeneratedPost record missing"
                continue

            public_url = f"{base_url.rstrip('/')}/{post.image_path}" if base_url else post.image_path
            media_id = await ig_service.publish_post(db, sched.post_id, sched.student_id, public_url)

            sched.status = "published"

            # Create Notification
            notif = Notification(
                student_id=sched.student_id,
                type="scheduled_post_success",
                message=f"Scheduled post '{post.prompt[:30]}...' published successfully! IG Media ID: {media_id}",
            )
            db.add(notif)
            processed_count += 1

        except Exception as e:
            sched.status = "failed"
            sched.error_message = str(e)
            notif = Notification(
                student_id=sched.student_id,
                type="scheduled_post_failed",
                message=f"Scheduled post failed to publish: {str(e)}",
            )
            db.add(notif)

    await db.commit()
    return processed_count
