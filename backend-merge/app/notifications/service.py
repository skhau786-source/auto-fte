import uuid
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.config import settings
from app.models import Notification, RegisteredStudent, InstagramAccount

logger = logging.getLogger("notifications")


def send_smtp_email(to_email: str, subject: str, content: str) -> bool:
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning(f"[SMTP] Skipping email to {to_email} — SMTP_USER or SMTP_PASSWORD not set.")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = settings.EMAILS_FROM_EMAIL or settings.SMTP_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(content, "plain"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"[SMTP] Email sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.error(f"[SMTP] Failed to send email to {to_email}: {e}")
        return False


async def create_notification(
    db: AsyncSession, student_id: uuid.UUID, notif_type: str, message: str, send_email: bool = True
) -> Notification:
    notif = Notification(student_id=student_id, type=notif_type, message=message, is_read=False)
    db.add(notif)
    await db.commit()
    await db.refresh(notif)

    if send_email:
        user_res = await db.execute(select(RegisteredStudent).where(RegisteredStudent.id == student_id))
        user = user_res.scalar_one_or_none()
        if user and user.email:
            send_smtp_email(
                to_email=user.email,
                subject=f"Digital FTE Notification: {notif_type.replace('_', ' ').title()}",
                content=message,
            )

    return notif


async def check_token_expirations(db: AsyncSession) -> int:
    """Checks for long-lived Instagram tokens expiring within 7 days and alerts the user."""
    threshold = datetime.now(timezone.utc) + timedelta(days=7)
    res = await db.execute(
        select(InstagramAccount).where(
            and_(InstagramAccount.token_expires_at <= threshold, InstagramAccount.token_expires_at > datetime.now(timezone.utc))
        )
    )
    expiring_accounts = res.scalars().all()

    alert_count = 0
    for acc in expiring_accounts:
        days_left = (acc.token_expires_at - datetime.now(timezone.utc)).days
        msg = f"Your connected Instagram account (@{acc.ig_username}) token expires in {days_left} days. Please reconnect your account."
        
        # Check if already notified recently
        existing_res = await db.execute(
            select(Notification).where(
                and_(
                    Notification.student_id == acc.student_id,
                    Notification.type == "token_expiring_warning",
                )
            )
        )
        if not existing_res.scalar_one_or_none():
            await create_notification(db, acc.student_id, "token_expiring_warning", msg, send_email=True)
            alert_count += 1

    return alert_count
