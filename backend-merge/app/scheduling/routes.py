import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import RegisteredStudent
from app.dependencies import get_current_user
from app.scheduling.schemas import SchedulePostCreate, SchedulePostOut
from app.scheduling import service

router = APIRouter(prefix="/schedule", tags=["Scheduling"])


@router.post("", response_model=SchedulePostOut, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    payload: SchedulePostCreate,
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await service.schedule_post(db, current_user, payload)
    return SchedulePostOut.model_validate(item)


@router.get("", response_model=list[SchedulePostOut])
async def get_calendar_schedule(
    start_time: datetime | None = Query(None, description="Start date filter for calendar view"),
    end_time: datetime | None = Query(None, description="End date filter for calendar view"),
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items = await service.get_user_schedule(db, current_user.id, start_time, end_time)
    return [SchedulePostOut.model_validate(item) for item in items]


@router.delete("/{schedule_id}", status_code=status.HTTP_200_OK)
async def cancel_schedule(
    schedule_id: uuid.UUID,
    current_user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await service.delete_scheduled_post(db, current_user.id, schedule_id)
    return {"message": "Scheduled post cancelled successfully"}
