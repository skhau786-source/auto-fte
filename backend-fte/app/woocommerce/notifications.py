"""
Email Notification Service for WooCommerce Alerts.

Sends email notifications for critical WooCommerce events:
- Low stock alerts
- Sync failure alerts
- API failure alerts
- Store disconnection alerts

Uses SMTP for email delivery. Falls back to logging when email is not configured.
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.woocommerce.models import WooCommerceAlert, WooCommerceSetting, WooCommerceStore

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Handles email notifications for WooCommerce alerts."""

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        from_email: Optional[str] = None,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port or 587
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email or "alerts@digital-fte.com"

    async def send_alert_email(
        self,
        db: AsyncSession,
        alert_id,
    ) -> bool:
        """
        Send an email notification for a specific alert.

        Checks store settings to determine if email alerts are enabled
        and if there's a configured alert email address.

        Args:
            db: Database session
            alert_id: Alert UUID

        Returns:
            True if email was sent, False if skipped or failed
        """
        result = await db.execute(
            select(WooCommerceAlert).where(WooCommerceAlert.id == alert_id)
        )
        alert = result.scalar_one_or_none()
        if not alert:
            logger.warning("Alert %s not found, cannot send email", alert_id)
            return False

        # Check if email already sent
        if alert.email_sent:
            return True

        # Get store settings
        settings_result = await db.execute(
            select(WooCommerceSetting).where(WooCommerceSetting.store_id == alert.store_id)
        )
        settings = settings_result.scalar_one_or_none()

        if not settings or not settings.email_alerts or not settings.alert_email:
            logger.info(
                "Email alerts not configured for store %s (alert %s)",
                alert.store_id, alert_id,
            )
            return False

        # Get store name
        store_result = await db.execute(
            select(WooCommerceStore).where(WooCommerceStore.id == alert.store_id)
        )
        store = store_result.scalar_one_or_none()
        store_name = store.store_name if store else "Unknown Store"

        # Build email
        to_email = settings.alert_email
        subject = f"[Digital FTE] {alert.severity.upper()}: {alert.title} - {store_name}"

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f5f3ff;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; 
                        padding: 30px; border: 1px solid #e0e0e0;">
                <div style="text-align: center; margin-bottom: 20px;">
                    <h1 style="color: #7c3aed; font-size: 24px; margin: 0;">Digital FTE</h1>
                    <p style="color: #666; font-size: 14px;">WooCommerce Alert Notification</p>
                </div>
                <div style="background: {'#fef2f2' if alert.severity.name == 'CRITICAL' else '#fffbeb' if alert.severity.name == 'WARNING' else '#eff6ff'}; 
                            border-radius: 8px; padding: 15px; margin-bottom: 20px;
                            border-left: 4px solid {'#ef4444' if alert.severity.name == 'CRITICAL' else '#f59e0b' if alert.severity.name == 'WARNING' else '#3b82f6'};">
                    <h2 style="margin: 0 0 8px 0; font-size: 18px; color: #333;">{alert.title}</h2>
                    <p style="margin: 0; color: #555; font-size: 14px;">{alert.message}</p>
                </div>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                    <tr>
                        <td style="padding: 8px; color: #666; font-size: 13px; border-bottom: 1px solid #eee;">Alert Type</td>
                        <td style="padding: 8px; color: #333; font-size: 13px; border-bottom: 1px solid #eee; font-weight: bold;">{alert.alert_type.value}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; color: #666; font-size: 13px; border-bottom: 1px solid #eee;">Severity</td>
                        <td style="padding: 8px; color: #333; font-size: 13px; border-bottom: 1px solid #eee; font-weight: bold;">{alert.severity.value}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; color: #666; font-size: 13px; border-bottom: 1px solid #eee;">Store</td>
                        <td style="padding: 8px; color: #333; font-size: 13px; border-bottom: 1px solid #eee; font-weight: bold;">{store_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; color: #666; font-size: 13px;">Time</td>
                        <td style="padding: 8px; color: #333; font-size: 13px; font-weight: bold;">{alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</td>
                    </tr>
                </table>
                <div style="text-align: center; margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee;">
                    <p style="color: #999; font-size: 12px;">
                        This is an automated alert from Digital FTE WooCommerce Inventory Sync Agent.<br>
                        To change alert preferences, update your store settings in the Digital FTE dashboard.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        return await self._send_email(to_email, subject, html_body, alert)

    async def _send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        alert,
    ) -> bool:
        """
        Send an email via SMTP or log it if SMTP is not configured.

        Args:
            to_email: Recipient email address
            subject: Email subject line
            html_body: HTML email body
            alert: Alert object (to update email_sent flag)

        Returns:
            True if sent successfully
        """
        # If SMTP is not configured, log the notification
        if not self.smtp_host:
            logger.info(
                "EMAIL NOTIFICATION (SMTP not configured):\nTo: %s\nSubject: %s\nBody: %s",
                to_email, subject, alert.message,
            )
            alert.email_sent = True
            alert.email_sent_at = datetime.now(timezone.utc)
            return True

        # Send via SMTP
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email

            part = MIMEText(html_body, "html")
            msg.attach(part)

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            alert.email_sent = True
            alert.email_sent_at = datetime.now(timezone.utc)
            logger.info("Alert email sent to %s for alert %s", to_email, alert.id)
            return True

        except Exception as exc:
            logger.error("Failed to send alert email to %s: %s", to_email, exc)
            return False


async def send_alert_notification(
    db: AsyncSession,
    alert_id,
    notifier: EmailNotifier | None = None,
) -> bool:
    """
    Send an alert notification and persist the email_sent flag.

    This is the main entry point for sending alert notifications.
    It ensures the email_sent flag is committed to the database.

    Args:
        db: Database session
        alert_id: Alert UUID
        notifier: Optional EmailNotifier instance. If None, creates a default one.

    Returns:
        True if email was sent successfully
    """
    if notifier is None:
        notifier = EmailNotifier()

    sent = await notifier.send_alert_email(db, alert_id)

    if sent:
        # Persist the email_sent flag to the database
        await db.commit()
        logger.info("Alert notification persisted: alert_id=%s, sent=%s", alert_id, sent)

    return sent
