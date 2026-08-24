"""
AI Agent models — SQLAlchemy ORM definitions.

Tables:
- ai_agents: Agent definitions (per-organization)
- ai_agent_tasks: Task submissions and lifecycle tracking
- ai_agent_actions: Immutable audit trail for all agent actions

All tables are organization-scoped for tenant isolation.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Boolean, DateTime, ForeignKey, Enum, func, Text, Integer,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.ai.constants import (
    AgentType, AgentStatus, TaskStatus, TaskType,
)


class AIAgent(Base):
    """
    An AI agent instance owned by an organization.

    Each agent has a type (inventory, social, sales, etc.), a status
    (active/inactive), and optional configuration stored as JSONB.
    """
    __tablename__ = "ai_agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    agent_type: Mapped[AgentType] = mapped_column(
        Enum(AgentType, name="ai_agent_type_enum"),
        nullable=False,
        default=AgentType.CUSTOM,
    )

    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, name="ai_agent_status_enum"),
        nullable=False,
        default=AgentStatus.INACTIVE,
    )

    # Agent-specific configuration (LLM model, parameters, etc.)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Capabilities this agent has been granted (list of permission strings)
    granted_permissions: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    tasks: Mapped[list["AIAgentTask"]] = relationship(
        "AIAgentTask",
        back_populates="agent",
        cascade="all, delete-orphan",
        foreign_keys="[AIAgentTask.agent_id]",
    )
    actions: Mapped[list["AIAgentAction"]] = relationship(
        "AIAgentAction",
        back_populates="agent",
        cascade="all, delete-orphan",
        foreign_keys="[AIAgentAction.agent_id]",
    )


class AIAgentTask(Base):
    """
    A task submitted to an AI agent.

    Lifecycle: PENDING → RUNNING → COMPLETED / FAILED
    With approval: PENDING → PENDING_APPROVAL → (approved) → RUNNING → COMPLETED / FAILED
                                             → (rejected) → REJECTED
    """
    __tablename__ = "ai_agent_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task_type: Mapped[TaskType] = mapped_column(
        Enum(TaskType, name="ai_task_type_enum"),
        nullable=False,
        default=TaskType.CUSTOM,
    )

    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="ai_task_status_enum"),
        nullable=False,
        default=TaskStatus.PENDING,
    )

    # Input/output data
    input_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Human approval
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Who submitted
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Execution tracking
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # LLM usage tracking
    llm_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    llm_tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Task handoff / collaboration
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_agent_tasks.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    source_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    capability_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    handoff_depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Metadata
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent: Mapped["AIAgent"] = relationship(
        "AIAgent", back_populates="tasks", foreign_keys="[AIAgentTask.agent_id]"
    )
    actions: Mapped[list["AIAgentAction"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class AIAgentAction(Base):
    """
    Immutable audit trail for every agent action.

    Records what the agent did, to what resource, and the outcome.
    Never updated after creation.
    """
    __tablename__ = "ai_agent_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_agent_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    action_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_resource: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    result_status: Mapped[str] = mapped_column(String(50), nullable=False, default="success")
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Who triggered (user or agent itself)
    performed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registered_students.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    agent: Mapped["AIAgent"] = relationship(
        "AIAgent", back_populates="actions", foreign_keys="[AIAgentAction.agent_id]"
    )
    task: Mapped["AIAgentTask | None"] = relationship(back_populates="actions")
