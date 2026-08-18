"""
Email bhejne ka service (stdlib smtplib - koi extra package nahi).

SMTP set nahi hai to email nahi jata, sirf log hota hai - isse development
me app crash nahi hota.
"""
import logging
import smtplib
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, html_body: str) -> None:
    if not settings.SMTP_HOST:
        logger.warning(
            "SMTP not configured - email send nahi hua. to=%s subject=%s",
            to_email,
            subject,
        )
        return

    msg = MIMEText(html_body, "html")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM or settings.SMTP_USER
    msg["To"] = to_email

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        logger.exception("Email send fail hone par: %s", e)
