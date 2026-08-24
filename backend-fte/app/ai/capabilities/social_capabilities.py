"""
Social Capabilities — interface layer for social media operations.

⚠️  PRODUCTION INTEGRATION NOT PRESENT

No real social media integration (Instagram, Facebook, etc.) exists
in the codebase. These capabilities provide the clean interface required
for future integration and Mock implementations for tests/development.

When a real social integration is added:
1. Replace MockSocialProvider with RealSocialProvider
2. The capability interface remains the same
3. No changes needed in the agent layer
"""

import uuid
import logging
from typing import Any

from app.ai.capabilities.base import (
    BaseCapability,
    CapabilityDescriptor,
    CapabilityType,
    CapabilityCategory,
    capability_registry,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Mock Social Provider
# ═══════════════════════════════════════════════════════════════════


class MockSocialProvider:
    """
    Mock social media provider for development and testing.

    Returns realistic-looking data without making real API calls.
    """

    async def list_accounts(self, organization_id: str) -> list[dict]:
        """List connected social accounts."""
        # No real accounts — return empty
        return []

    async def create_post_draft(
        self,
        organization_id: str,
        content: str,
        platforms: list[str],
        media_urls: list[str] | None = None,
        scheduled_at: str | None = None,
    ) -> dict:
        """Create a post draft (does NOT publish)."""
        return {
            "id": str(uuid.uuid4()),
            "content": content,
            "platforms": platforms,
            "media_urls": media_urls or [],
            "scheduled_at": scheduled_at,
            "status": "draft",
            "organization_id": organization_id,
        }

    async def list_posts(
        self,
        organization_id: str,
        status: str | None = None,
    ) -> list[dict]:
        """List posts for the organization."""
        return []


# Global mock provider
_social_provider = MockSocialProvider()


def get_social_provider():
    """Get the social media provider (mock or real)."""
    return _social_provider


# ═══════════════════════════════════════════════════════════════════
# Social Capabilities
# ═══════════════════════════════════════════════════════════════════


class SocialListAccountsCapability(BaseCapability):
    """List connected social media accounts."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="social.list_accounts",
            display_name="List Social Accounts",
            description="List connected social media accounts (Instagram, Facebook, etc.).",
            capability_type=CapabilityType.READ,
            category=CapabilityCategory.SOCIAL,
            requires_approval=False,
            supported_agent_types=["social", "analytics", "custom"],
        )

    async def execute(self, input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        provider = get_social_provider()
        accounts = await provider.list_accounts(str(context["organization_id"]))
        return {"accounts": accounts, "total": len(accounts)}


class SocialCreatePostDraftCapability(BaseCapability):
    """Create a social media post draft (does NOT publish)."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="social.create_post_draft",
            display_name="Create Post Draft",
            description="Draft a social media post for review. Does NOT publish — requires separate approval.",
            capability_type=CapabilityType.WRITE,
            category=CapabilityCategory.SOCIAL,
            requires_approval=False,  # Drafts are safe
            supported_agent_types=["social", "custom"],
        )

    async def execute(self, input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        provider = get_social_provider()
        draft = await provider.create_post_draft(
            organization_id=str(context["organization_id"]),
            content=input_data.get("content", ""),
            platforms=input_data.get("platforms", []),
            media_urls=input_data.get("media_urls"),
            scheduled_at=input_data.get("scheduled_at"),
        )
        return {"draft": draft, "message": "Post draft created (not published)"}


class SocialPublishPostCapability(BaseCapability):
    """Publish a social media post. REQUIRES human approval."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="social.publish_post",
            display_name="Publish Post",
            description="Publish a social media post to connected platforms. Requires human approval.",
            capability_type=CapabilityType.WRITE,
            category=CapabilityCategory.SOCIAL,
            requires_approval=True,
            supported_agent_types=["social"],
        )

    async def execute(self, input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        # In production, this would call the real social provider's publish API
        # For now, return a clear indication that this is a mock
        return {
            "error": "Social publishing not available — no social media provider configured",
            "status": "not_configured",
            "required": "Real social media integration (Instagram/Facebook API credentials)",
        }


class SocialListPostsCapability(BaseCapability):
    """List social media posts."""

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="social.list_posts",
            display_name="List Posts",
            description="List social media posts and their statuses.",
            capability_type=CapabilityType.READ,
            category=CapabilityCategory.SOCIAL,
            requires_approval=False,
            supported_agent_types=["social", "analytics", "custom"],
        )

    async def execute(self, input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        provider = get_social_provider()
        posts = await provider.list_posts(
            organization_id=str(context["organization_id"]),
            status=input_data.get("status"),
        )
        return {"posts": posts, "total": len(posts)}


# ═══════════════════════════════════════════════════════════════════
# Registration
# ═══════════════════════════════════════════════════════════════════


def register_social_capabilities() -> None:
    """Register all social capabilities with the global registry."""
    capabilities = [
        SocialListAccountsCapability(),
        SocialCreatePostDraftCapability(),
        SocialPublishPostCapability(),
        SocialListPostsCapability(),
    ]
    for cap in capabilities:
        capability_registry.register(cap)
