"""
Agent Runtime data models — structured representations for requests,
responses, plans, and action results.

These models are internal to the runtime layer and do NOT replace
existing API schemas. They provide the structured representation
needed for planning, validation, and multi-step execution.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class ActionStatus(str, Enum):
    """Status of a single action within a plan."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class PlanStatus(str, Enum):
    """Overall status of a plan."""
    CREATED = "created"
    VALIDATING = "validating"
    EXECUTING = "executing"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


@dataclass
class PlanAction:
    """
    A single action within an execution plan.

    Each action maps to one capability invocation with specific input data.
    """
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    capability_name: str = ""
    input_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    status: ActionStatus = ActionStatus.PENDING
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    executed_at: Optional[datetime] = None

    def mark_running(self) -> None:
        self.status = ActionStatus.RUNNING
        self.executed_at = datetime.now(timezone.utc)

    def mark_completed(self, result: dict[str, Any]) -> None:
        self.status = ActionStatus.COMPLETED
        self.result = result

    def mark_failed(self, error: str) -> None:
        self.status = ActionStatus.FAILED
        self.error = error

    def mark_blocked(self, reason: str) -> None:
        self.status = ActionStatus.BLOCKED
        self.error = reason

    def mark_pending_approval(self) -> None:
        self.status = ActionStatus.PENDING_APPROVAL

    def mark_rejected(self, reason: str) -> None:
        self.status = ActionStatus.REJECTED
        self.error = reason


@dataclass
class Plan:
    """
    An execution plan containing one or more validated actions.

    A plan is created by the planner, validated against the capability
    registry, and then executed by the runtime.
    """
    plan_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    actions: list[PlanAction] = field(default_factory=list)
    status: PlanStatus = PlanStatus.CREATED
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def action_count(self) -> int:
        return len(self.actions)

    @property
    def completed_count(self) -> int:
        return sum(1 for a in self.actions if a.status == ActionStatus.COMPLETED)

    @property
    def failed_count(self) -> int:
        return sum(1 for a in self.actions if a.status == ActionStatus.FAILED)

    @property
    def has_approval_required(self) -> bool:
        return any(a.requires_approval for a in self.actions)

    @property
    def all_completed(self) -> bool:
        return all(
            a.status in (ActionStatus.COMPLETED, ActionStatus.SKIPPED)
            for a in self.actions
        )

    @property
    def any_failed(self) -> bool:
        return any(a.status == ActionStatus.FAILED for a in self.actions)

    @property
    def any_pending_approval(self) -> bool:
        return any(a.status == ActionStatus.PENDING_APPROVAL for a in self.actions)


@dataclass
class AgentRequest:
    """
    Structured request to the agent runtime.

    Represents a user's intent to be processed by an agent through
    the planning → validation → execution pipeline.
    """
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: Optional[uuid.UUID] = None
    organization_id: Optional[uuid.UUID] = None
    user_id: Optional[uuid.UUID] = None
    instruction: str = ""
    intent: Optional[str] = None
    session_id: Optional[str] = None
    capability_hint: Optional[str] = None
    input_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    is_approved: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ActionResult:
    """
    Result of executing a single action within a plan.
    """
    action_id: str = ""
    capability_name: str = ""
    status: ActionStatus = ActionStatus.PENDING
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    requires_approval: bool = False
    executed_at: Optional[datetime] = None

    @classmethod
    def from_plan_action(cls, action: PlanAction) -> "ActionResult":
        return cls(
            action_id=action.action_id,
            capability_name=action.capability_name,
            status=action.status,
            result=action.result,
            error=action.error,
            requires_approval=action.requires_approval,
            executed_at=action.executed_at,
        )


@dataclass
class AgentResponse:
    """
    Structured response from the agent runtime.

    Contains the overall execution result plus per-action details.
    """
    request_id: str = ""
    plan_id: str = ""
    status: PlanStatus = PlanStatus.CREATED
    agent_id: Optional[str] = None
    results: list[ActionResult] = field(default_factory=list)
    error: Optional[str] = None
    execution_duration_ms: Optional[int] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    @property
    def is_success(self) -> bool:
        return self.status == PlanStatus.COMPLETED

    @property
    def is_pending_approval(self) -> bool:
        return self.status == PlanStatus.BLOCKED and any(
            r.status == ActionStatus.PENDING_APPROVAL for r in self.results
        )

    @property
    def action_results(self) -> list[ActionResult]:
        return self.results
