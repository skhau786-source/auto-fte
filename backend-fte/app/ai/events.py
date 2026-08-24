"""
AI Agent domain events — extend the existing EventDispatcher with agent-specific events.

Events:
- AgentCreated
- AgentUpdated
- AgentDeactivated
- TaskSubmitted
- TaskStarted
- TaskCompleted
- TaskFailed
- TaskApproved
- TaskRejected
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class AgentCreated:
    """Fired when a new agent is created."""
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    agent_name: str = ""
    agent_type: str = ""
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class AgentUpdated:
    """Fired when an agent is updated."""
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    updated_fields: list[str] = field(default_factory=list)
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class AgentDeactivated:
    """Fired when an agent is deactivated."""
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class TaskSubmitted:
    """Fired when a task is submitted to an agent."""
    task_id: uuid.UUID = field(default_factory=uuid.uuid4)
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    task_type: str = ""
    requires_approval: bool = False
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class TaskStarted:
    """Fired when a task begins execution."""
    task_id: uuid.UUID = field(default_factory=uuid.uuid4)
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class TaskCompleted:
    """Fired when a task completes successfully."""
    task_id: uuid.UUID = field(default_factory=uuid.uuid4)
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    duration_ms: int = 0
    tokens_used: int = 0
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class TaskFailed:
    """Fired when a task fails."""
    task_id: uuid.UUID = field(default_factory=uuid.uuid4)
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    error_message: str = ""
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class TaskApproved:
    """Fired when a task is approved by a human."""
    task_id: uuid.UUID = field(default_factory=uuid.uuid4)
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    approved_by: uuid.UUID = field(default_factory=uuid.uuid4)
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class TaskRejected:
    """Fired when a task is rejected by a human."""
    task_id: uuid.UUID = field(default_factory=uuid.uuid4)
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    rejected_by: uuid.UUID = field(default_factory=uuid.uuid4)
    reason: str = ""
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW EVENTS
# ═══════════════════════════════════════════════════════════════════


@dataclass
class WorkflowCreated:
    """Fired when a workflow is created/defined."""
    workflow_id: str = ""
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = ""
    step_count: int = 0
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class WorkflowStarted:
    """Fired when a workflow begins execution."""
    workflow_id: str = ""
    task_id: uuid.UUID = field(default_factory=uuid.uuid4)
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class WorkflowCompleted:
    """Fired when a workflow completes successfully."""
    workflow_id: str = ""
    task_id: uuid.UUID = field(default_factory=uuid.uuid4)
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    duration_ms: int = 0
    steps_completed: int = 0
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class WorkflowFailed:
    """Fired when a workflow execution fails."""
    workflow_id: str = ""
    task_id: uuid.UUID = field(default_factory=uuid.uuid4)
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    error_message: str = ""
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class WorkflowStepCompleted:
    """Fired when a single workflow step completes."""
    workflow_id: str = ""
    step_id: str = ""
    capability_name: str = ""
    status: str = ""
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    duration_ms: int = 0
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════════
# TEAM EVENTS
# ═══════════════════════════════════════════════════════════════════


@dataclass
class TeamCreated:
    """Fired when a team is created."""
    team_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = ""
    created_by: uuid.UUID = field(default_factory=uuid.uuid4)
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class TeamUpdated:
    """Fired when a team is updated."""
    team_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    updated_fields: list[str] = field(default_factory=list)
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class TeamDeactivated:
    """Fired when a team is deactivated."""
    team_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class TeamMemberAdded:
    """Fired when a user is added to a team."""
    team_id: uuid.UUID = field(default_factory=uuid.uuid4)
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    role: str = "member"
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class TeamMemberRemoved:
    """Fired when a user is removed from a team."""
    team_id: uuid.UUID = field(default_factory=uuid.uuid4)
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class TeamAgentAssigned:
    """Fired when an agent is assigned to a team."""
    team_id: uuid.UUID = field(default_factory=uuid.uuid4)
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())


@dataclass
class TeamAgentRemoved:
    """Fired when an agent is removed from a team."""
    team_id: uuid.UUID = field(default_factory=uuid.uuid4)
    agent_id: uuid.UUID = field(default_factory=uuid.uuid4)
    organization_id: uuid.UUID = field(default_factory=uuid.uuid4)
    event_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id:
            self.event_id = str(uuid.uuid4())
