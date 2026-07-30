"""
Alert Notification System — abstract notifier pattern.

Provides a common interface for sending alerts through multiple channels:
- Email
- Slack Webhook
- Future SMS (interface ready)

Usage:
    notifier = AlertNotifier()
    notifier.add_channel(EmailNotifier(sender="alerts@example.com"))
    notifier.add_channel(SlackNotifier(webhook_url=settings.SLACK_WEBHOOK_URL))
    await notifier.send_alert(Alert("Low stock", level="warning"))
"""

import abc
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Alert Data Structures
# ═══════════════════════════════════════════════════════════════════


@dataclass
class Alert:
    """A single alert event that can be routed to one or more channels."""
    title: str
    message: str
    level: str = "info"  # info, warning, error, critical
    source: str = "inventory"  # inventory, shopify, webhook, system
    store_domain: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ═══════════════════════════════════════════════════════════════════
# Notifier Abstraction
# ═══════════════════════════════════════════════════════════════════


class BaseNotifier(abc.ABC):
    """Abstract base class for all notification channels."""

    @abc.abstractmethod
    async def send(self, alert: Alert) -> bool:
        """Send an alert through this channel. Returns True on success."""
        ...

    @property
    @abc.abstractmethod
    def channel_name(self) -> str:
        """Human-readable name for this channel."""
        ...


class AlertNotifier:
    """Composite notifier that sends alerts through all registered channels."""

    def __init__(self):
        self._channels: list[BaseNotifier] = []

    def add_channel(self, channel: BaseNotifier) -> None:
        """Register a notification channel."""
        self._channels.append(channel)

    async def send_alert(self, alert: Alert) -> dict[str, bool]:
        """
        Send an alert through all registered channels.

        Returns:
            Dict mapping channel_name -> success (True/False).
        """
        results = {}
        for channel in self._channels:
            try:
                success = await channel.send(alert)
                results[channel.channel_name] = success
                if not success:
                    logger.warning(
                        "Alert channel %s failed to send alert: %s",
                        channel.channel_name,
                        alert.title,
                    )
            except Exception as exc:
                logger.exception(
                    "Alert channel %s raised exception: %s",
                    channel.channel_name,
                    exc,
                )
                results[channel.channel_name] = False
        return results


# ═══════════════════════════════════════════════════════════════════
# Email Notifier
# ═══════════════════════════════════════════════════════════════════


class EmailNotifier(BaseNotifier):
    """
    Email alert channel.

    Sends alerts via SMTP. Configure with environment variables:
        ALERT_EMAIL_SENDER
        ALERT_EMAIL_RECIPIENTS (comma-separated)
        ALERT_EMAIL_SMTP_HOST
        ALERT_EMAIL_SMTP_PORT
        ALERT_EMAIL_SMTP_USERNAME
        ALERT_EMAIL_SMTP_PASSWORD
        ALERT_EMAIL_USE_TLS (default: True)
    """

    def __init__(
        self,
        sender: str,
        recipients: list[str],
        smtp_host: str = "localhost",
        smtp_port: int = 587,
        username: Optional[str] = None,
        password: Optional[str] = None,
        use_tls: bool = True,
    ):
        self.sender = sender
        self.recipients = recipients
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.use_tls = use_tls

    @property
    def channel_name(self) -> str:
        return "email"

    async def send(self, alert: Alert) -> bool:
        """
        Send an alert email.

        Uses aiosmtplib if available, otherwise falls back to synchronous smtplib
        (run in a thread executor to avoid blocking the event loop).
        """
        subject = f"[{alert.level.upper()}] {alert.title} — {alert.source}"
        body = self._format_email_body(alert)

        try:
            import aiosmtplib
            from email.mime.text import MIMEText

            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = self.sender
            msg["To"] = ", ".join(self.recipients)

            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.username,
                password=self.password,
                use_tls=self.use_tls,
                timeout=10,
            )
            return True

        except ImportError:
            # Fallback to synchronous smtplib (run in thread to avoid blocking)
            import smtplib
            from email.mime.text import MIMEText
            import asyncio

            def _send_sync():
                msg = MIMEText(body, "plain", "utf-8")
                msg["Subject"] = subject
                msg["From"] = self.sender
                msg["To"] = ", ".join(self.recipients)

                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                    if self.use_tls:
                        server.starttls()
                    if self.username and self.password:
                        server.login(self.username, self.password)
                    server.send_message(msg)
                return True

            return await asyncio.to_thread(_send_sync)

        except Exception as exc:
            logger.error("Email notifier failed: %s", exc)
            return False

    def _format_email_body(self, alert: Alert) -> str:
        """Build a plain-text email body from an alert."""
        lines = [
            f"Alert: {alert.title}",
            f"Level: {alert.level.upper()}",
            f"Source: {alert.source}",
            f"Time: {alert.timestamp.isoformat()}",
            "",
            alert.message,
        ]
        if alert.store_domain:
            lines.insert(3, f"Store: {alert.store_domain}")
        if alert.metadata:
            lines.append("")
            lines.append("Metadata:")
            for key, value in alert.metadata.items():
                lines.append(f"  {key}: {value}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Slack Notifier
# ═══════════════════════════════════════════════════════════════════


class SlackNotifier(BaseNotifier):
    """
    Slack alert channel.

    Sends alerts to a Slack channel via Incoming Webhook.
    Configure with environment variable: SLACK_WEBHOOK_URL
    """

    def __init__(self, webhook_url: str, channel: Optional[str] = None):
        self.webhook_url = webhook_url
        self.channel = channel

    @property
    def channel_name(self) -> str:
        return "slack"

    async def send(self, alert: Alert) -> bool:
        """Send a Slack message with the alert details."""
        import httpx

        # Determine Slack color based on level
        color = {
            "info": "#3498db",
            "warning": "#f39c12",
            "error": "#e74c3c",
            "critical": "#c0392b",
        }.get(alert.level, "#95a5a6")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"[{alert.level.upper()}] {alert.title}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Source:* {alert.source}"},
                    {"type": "mrkdwn", "text": f"*Level:* {alert.level}"},
                ],
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": alert.message}},
        ]

        if alert.metadata:
            meta_text = "\n".join(
                f"• *{k}:* {v}" for k, v in alert.metadata.items()
            )
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Details:*\n{meta_text}"},
            })

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"🕐 {alert.timestamp.isoformat()}",
                }
            ],
        })

        payload = {
            "attachments": [
                {
                    "color": color,
                    "blocks": blocks,
                }
            ]
        }

        if self.channel:
            payload["channel"] = self.channel

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(self.webhook_url, json=payload)
                response.raise_for_status()
            return True
        except Exception as exc:
            logger.error("Slack notifier failed: %s", exc)
            return False


# ═══════════════════════════════════════════════════════════════════
# SMS Notifier (Future / Stub)
# ═══════════════════════════════════════════════════════════════════


class SMSNotifier(BaseNotifier):
    """
    SMS alert channel — interface ready for production integration.

    To implement:
    1. Choose a provider (Twilio, AWS SNS, Vonage)
    2. Install the provider's SDK
    3. Fill in the send() method
    """

    def __init__(self, provider: str = "twilio", **kwargs):
        self.provider = provider
        self.config = kwargs

    @property
    def channel_name(self) -> str:
        return f"sms_{self.provider}"

    async def send(self, alert: Alert) -> bool:
        """Send an SMS alert. Not implemented — ready for integration."""
        logger.info(
            "SMS notifier is not yet integrated. Would send alert: %s (%s)",
            alert.title,
            alert.level,
        )
        # TODO: Implement SMS sending via Twilio or similar
        return False
