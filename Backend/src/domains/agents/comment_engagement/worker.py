# ═══════════════════════════════════════════════════════════════
# agents / comment_engagement / worker.py
#
# PURPOSE: Event-driven worker — listens for post.published (from
#          Agent 2 / content_scheduling) so it knows which posts to
#          watch, and runs a background poller that checks those
#          posts for new comments via MetaClient every N seconds.
#
#          Also handles comment.received events directly, for when
#          a real Meta webhook is wired in later (Phase 3+).
#
# USED BY: docker-compose, `python -m agents.comment_engagement.worker`
# ═══════════════════════════════════════════════════════════════

import asyncio
import logging

from sqlalchemy import select

from src.sdk.agent_base import BaseAgent
from src.sdk.database import async_session_factory
from src.sdk.events import Event
from src.sdk.logging import setup_logging
from src.sdk.models.social import ScheduledPost, SocialAccount
from src.sdk.crypto import decrypt_token
from src.sdk.config import get_settings as get_fte_settings

from src.domains.agents.comment_engagement.handler import CommentEngagementHandler
from src.domains.agents.comment_engagement.meta_client import MetaClient
from src.domains.agents.comment_engagement.config import get_settings

logger = logging.getLogger(__name__)


class CommentEngagementWorker(BaseAgent):
    """Listens for published posts + polls Meta for new comments on them."""

    def __init__(self):
        super().__init__(agent_name="comment_engagement")
        self.settings = get_settings()
        self._poll_task: asyncio.Task | None = None

    async def on_start(self):
        """Start the background comment-polling loop on agent startup."""
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(f"[comment_engagement] Comment poller started (interval={self.settings.POLL_INTERVAL_SECONDS}s)")

    async def setup_subscriptions(self):
        await self.bus.subscribe("events", self._on_event)
        logger.info("[comment_engagement] Subscribed to events channel")

    async def handle_event(self, event: Event):
        logger.warning(f"Unhandled event type: {event.event_type}")

    async def _on_event(self, data: dict):
        """Route events from the shared 'events' channel."""
        event = Event(**data)

        if event.event_type == "comment.received":
            # Real webhook path (Phase 3+): comment already contains
            # everything needed, no polling required.
            payload = event.payload
            async with async_session_factory() as db:
                handler = CommentEngagementHandler(db)
                try:
                    await handler.process_comment(
                        social_account_id=payload["social_account_id"],
                        platform_post_id=payload.get("platform_post_id", ""),
                        platform_comment_id=payload.get("comment_id", ""),
                        author=payload.get("author", "unknown"),
                        text=payload.get("text", ""),
                    )
                    await db.commit()
                    logger.info("  ✅ Comment processed")
                except Exception as e:
                    await db.rollback()
                    logger.error(f"  ❌ Failed to process comment: {e}")
            return

        if event.event_type == "post.published":
            # Nothing to do immediately — the poll loop below already
            # picks up all published posts each cycle. This branch just
            # confirms the event was received (useful for debugging).
            logger.info(f"  Tracking new published post: {event.payload.get('platform_post_id')}")
            return

    # ─── Background poll loop (mirrors ContentScheduler) ───────

    async def _poll_loop(self):
        while self.running:
            try:
                await self._check_for_new_comments()
            except Exception as e:
                logger.error(f"Comment poll error: {e}")
            await asyncio.sleep(self.settings.POLL_INTERVAL_SECONDS)

    async def _check_for_new_comments(self):
        """Fetch comments for every published post, run each new one
        through the classify → reply/escalate pipeline."""
        async with async_session_factory() as db:
            result = await db.execute(
                select(ScheduledPost)
                .where(ScheduledPost.status == "published")
                .where(ScheduledPost.platform_post_id.isnot(None))
                .limit(50)
            )
            posts = result.scalars().all()
            if not posts:
                return

            for post in posts:
                await self._poll_single_post(db, post)

            await db.commit()

    async def _poll_single_post(self, db, post: ScheduledPost):
        account_result = await db.execute(
            select(SocialAccount).where(SocialAccount.id == post.social_account_id)
        )
        account = account_result.scalar_one_or_none()
        if not account or not account.is_active:
            return

        access_token = ""
        if account.access_token:
            enc_key = get_fte_settings().ENCRYPTION_KEY
            access_token = decrypt_token(account.access_token, enc_key)

        client = MetaClient(access_token)
        try:
            comments = await client.fetch_comments(post.platform_post_id)
        finally:
            await client.close()

        handler = CommentEngagementHandler(db)
        for c in comments:
            try:
                await handler.process_comment(
                    social_account_id=account.id,
                    platform_post_id=post.platform_post_id,
                    platform_comment_id=c["id"],
                    author=c["author"],
                    text=c["text"],
                )
            except Exception as e:
                logger.error(f"Failed to process comment {c.get('id')}: {e}")

    async def shutdown(self):
        if self._poll_task:
            self._poll_task.cancel()
        await super().shutdown()


worker = CommentEngagementWorker()


# ─── Main Entry Point ─────────────────────────────────────────

if __name__ == "__main__":
    setup_logging("comment_engagement")
    asyncio.run(worker.run())
