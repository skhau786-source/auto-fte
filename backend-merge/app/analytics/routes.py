import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RegisteredStudent, GeneratedPost, InstagramAccount
from app.dependencies import get_current_user
from app.analytics.schemas import AnalyticsSummaryOut, PostAnalyticsOut
from app.analytics import service

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary", response_model=AnalyticsSummaryOut)
async def get_analytics_summary(
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_user_analytics_summary(db, current_user.id)


@router.post("/refresh/{post_id}", response_model=PostAnalyticsOut)
async def refresh_post_metrics(
    post_id: uuid.UUID,
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post_res = await db.execute(
        select(GeneratedPost).where(GeneratedPost.id == post_id, GeneratedPost.student_id == current_user.id)
    )
    post = post_res.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    ig_res = await db.execute(select(InstagramAccount).where(InstagramAccount.student_id == current_user.id))
    ig_account = ig_res.scalar_one_or_none()
    if not ig_account:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No connected Instagram account")

    rec = await service.refresh_post_analytics(db, post, ig_account)
    if not rec:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Post has no published IG media ID")

    return PostAnalyticsOut.model_validate(rec)
