import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RegisteredStudent, PostComment, GeneratedPost
from app.dependencies import get_current_user
from app.comments.schemas import CommentOut, ManualReplyRequest
from app.comments import service

router = APIRouter(prefix="/comments", tags=["Comments"])


@router.get("/{post_id}", response_model=list[CommentOut])
async def list_post_comments(
    post_id: uuid.UUID,
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post_res = await db.execute(
        select(GeneratedPost).where(GeneratedPost.id == post_id, GeneratedPost.student_id == current_user.id)
    )
    post = post_res.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found or unauthorized")

    result = await db.execute(
        select(PostComment).where(PostComment.post_id == post_id).order_by(PostComment.created_at.desc())
    )
    comments = result.scalars().all()
    return [CommentOut.model_validate(c) for c in comments]


@router.post("/simulate-incoming", response_model=CommentOut)
async def simulate_incoming_comment(
    post_id: uuid.UUID,
    comment_id: str,
    commenter_username: str,
    comment_text: str,
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    comment = await service.process_incoming_comment(
        db=db,
        post_id=post_id,
        comment_id=comment_id,
        commenter_username=commenter_username,
        comment_text=comment_text,
    )
    return CommentOut.model_validate(comment)
