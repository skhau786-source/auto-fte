"""
Multi-Tenant Models — Organizations, Teams, Members, Roles, Permissions.

Supports:
- Organizations (top-level tenant)
- Teams (sub-groups within an organization)
- Organization Members (users with roles)
- Roles (customizable permission sets)
- Permissions (granular action-based controls)
- Tenant Isolation (every query scoped to organization)
"""

import uuid
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Boolean, DateTime, ForeignKey, Enum, func, Text,
    Integer, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MembershipRole(str, enum.Enum):
    """Built-in roles for organization membership."""
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Permission(str, enum.Enum):
    """Granular permissions for the RBAC system."""
    # Inventory
    INVENTORY_READ = "inventory:read"
    INVENTORY_WRITE = "inventory:write"
    INVENTORY_ADJUST = "inventory:adjust"
    INVENTORY_BULK = "inventory:bulk"

    # Products
    PRODUCT_READ = "product:read"
    PRODUCT_CREATE = "product:create"
    PRODUCT_UPDATE = "product:update"
    PRODUCT_DELETE = "product:delete"

    # Dashboard
    DASHBOARD_VIEW = "dashboard:view"

    # Exports
    EXPORT_CREATE = "export:create"
    EXPORT_DOWNLOAD = "export:download"

    # Admin
    ADMIN_SYNC_RETRY = "admin:sync:retry"
    ADMIN_INVENTORY_REBUILD = "admin:inventory:rebuild"
    ADMIN_WEBHOOKS = "admin:webhooks"
    ADMIN_CACHE_FLUSH = "admin:cache:flush"
    ADMIN_QUEUE_VIEW = "admin:queue:view"
    ADMIN_STATS = "admin:stats"

    # Settings
    SETTINGS_READ = "settings:read"
    SETTINGS_WRITE = "settings:write"
    SETTINGS_BILLING = "settings:billing"

    # Audit
    AUDIT_READ = "audit:read"
    AUDIT_EXPORT = "audit:export"

    # Users & Teams
    USERS_INVITE = "users:invite"
    USERS_MANAGE = "users:manage"
    TEAMS_MANAGE = "teams:manage"

    # AI Agents
    AGENT_MANAGE = "agent:manage"
    AGENT_EXECUTE = "agent:execute"
    AGENT_APPROVE = "agent:approve"


# ═══════════════════════════════════════════════════════════════════
# DEFAULT ROLE PERMISSIONS
# ═══════════════════════════════════════════════════════════════════

DEFAULT_ROLE_PERMISSIONS: dict[str, list[str]] = {
    MembershipRole.OWNER.value: [p.value for p in Permission],
    MembershipRole.ADMIN.value: [p.value for p in Permission],
    MembershipRole.MANAGER.value: [
        Permission.INVENTORY_READ.value,
        Permission.INVENTORY_WRITE.value,
        Permission.INVENTORY_ADJUST.value,
        Permission.INVENTORY_BULK.value,
        Permission.PRODUCT_READ.value,
        Permission.PRODUCT_CREATE.value,
        Permission.PRODUCT_UPDATE.value,
        Permission.PRODUCT_DELETE.value,
        Permission.DASHBOARD_VIEW.value,
        Permission.EXPORT_CREATE.value,
        Permission.EXPORT_DOWNLOAD.value,
        Permission.ADMIN_QUEUE_VIEW.value,
        Permission.ADMIN_STATS.value,
        Permission.SETTINGS_READ.value,
        Permission.AUDIT_READ.value,
        Permission.AUDIT_EXPORT.value,
        Permission.USERS_INVITE.value,
        Permission.AGENT_MANAGE.value,
        Permission.AGENT_EXECUTE.value,
        Permission.AGENT_APPROVE.value,
    ],
    MembershipRole.OPERATOR.value: [
        Permission.INVENTORY_READ.value,
        Permission.INVENTORY_WRITE.value,
        Permission.INVENTORY_ADJUST.value,
        Permission.PRODUCT_READ.value,
        Permission.PRODUCT_CREATE.value,
        Permission.PRODUCT_UPDATE.value,
        Permission.DASHBOARD_VIEW.value,
        Permission.EXPORT_CREATE.value,
        Permission.EXPORT_DOWNLOAD.value,
        Permission.ADMIN_QUEUE_VIEW.value,
        Permission.ADMIN_STATS.value,
        Permission.AGENT_EXECUTE.value,
    ],
    MembershipRole.VIEWER.value: [
        Permission.INVENTORY_READ.value,
        Permission.PRODUCT_READ.value,
        Permission.DASHBOARD_VIEW.value,
        Permission.AUDIT_READ.value,
    ],
}


def get_default_permissions(role: MembershipRole) -> list[str]:
    """Get the default permissions for a built-in role."""
    return DEFAULT_ROLE_PERMISSIONS.get(role.value, [])


# ═══════════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════════


class Organization(Base):
    """Top-level tenant. Everything is scoped to an organization."""
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Subscription info (linked to billing)
    subscription_plan: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    subscription_status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Feature flags (based on plan)
    features: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    members: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    teams: Mapped[list["Team"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    # Note: Subscription relationship is defined in subscriptions.models
    # Stores are linked via the organization's subscription settings


class Team(Base):
    """A sub-group within an organization (e.g., 'Operations Team', 'QA')."""
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="teams")
    members: Mapped[list["OrganizationMember"]] = relationship(back_populates="team")


class OrganizationMember(Base):
    """Maps a user to an organization with a specific role and optional team."""
    __tablename__ = "organization_members"

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
    )

    role: Mapped[MembershipRole] = mapped_column(
        Enum(MembershipRole, name="membership_role_enum", values_callable=lambda e: [m.value for m in e]),
        default=MembershipRole.VIEWER,
        nullable=False,
    )

    # Custom permissions override (JSON list of permission strings)
    custom_permissions: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    invited_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="members")
    user: Mapped["RegisteredStudent"] = relationship()
    team: Mapped[Optional["Team"]] = relationship(back_populates="members")

    def get_permissions(self) -> list[str]:
        """Get effective permissions for this member."""
        if self.custom_permissions:
            return self.custom_permissions
        return get_default_permissions(self.role)
