"""
AI Agent Pydantic schemas — request/response models for the API layer.

Follows the project's existing schema conventions (from_attributes=True,
validation on creation, output models for reads).
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.ai.constants import AgentType, AgentStatus, TaskStatus, TaskType


# ═══════════════════════════════════════════════════════════════════
# AGENT SCHEMAS
# ═══════════════════════════════════════════════════════════════════


class AgentCreateRequest(BaseModel):
    """Request to create a new AI agent."""
    name: str = Field(min_length=1, max_length=255, description="Agent display name")
    description: Optional[str] = Field(None, max_length=2000, description="What this agent does")
    agent_type: AgentType = Field(default=AgentType.CUSTOM, description="Agent category")
    config: Optional[dict] = Field(None, description="Agent-specific configuration (model, params, etc.)")
    granted_permissions: Optional[list[str]] = Field(None, description="Permissions this agent may use")
    team_id: Optional[str] = Field(None, description="ID of the team to assign this agent to")


class AgentUpdateRequest(BaseModel):
    """Partial update for an AI agent (PATCH semantics)."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    agent_type: Optional[AgentType] = None
    config: Optional[dict] = None
    granted_permissions: Optional[list[str]] = None


class AgentOut(BaseModel):
    """Agent output model — returned by GET/list endpoints."""
    id: str
    organization_id: str
    team_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    agent_type: str
    status: str
    config: Optional[dict] = None
    granted_permissions: Optional[list[str]] = None
    is_active: bool
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    task_count: int = 0
    active_task_count: int = 0

    class Config:
        from_attributes = True


class AgentListOut(BaseModel):
    """Paginated list of agents."""
    items: list[AgentOut]
    total: int


# ═══════════════════════════════════════════════════════════════════
# TASK SCHEMAS
# ═══════════════════════════════════════════════════════════════════


class TaskSubmitRequest(BaseModel):
    """Request to submit a task to an agent."""
    task_type: TaskType = Field(default=TaskType.CUSTOM, description="Type of task")
    input_data: Optional[dict] = Field(None, description="Input payload for the task")
    requires_human_approval: bool = Field(default=False, description="Require approval before execution")
    metadata_: Optional[dict] = Field(None, alias="metadata", description="Additional metadata")


class TaskOut(BaseModel):
    """Task output model — returned by GET endpoints."""
    id: str
    agent_id: str
    organization_id: str
    task_type: str
    status: str
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    error_message: Optional[str] = None
    requires_human_approval: bool
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    submitted_by: Optional[str] = None
    execution_started_at: Optional[datetime] = None
    execution_completed_at: Optional[datetime] = None
    execution_duration_ms: Optional[int] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_tokens_used: Optional[int] = None
    parent_task_id: Optional[str] = None
    source_agent_id: Optional[str] = None
    target_agent_id: Optional[str] = None
    capability_name: Optional[str] = None
    handoff_depth: int = 0
    metadata_: Optional[dict] = Field(None, alias="metadata")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TaskListOut(BaseModel):
    """Paginated list of tasks."""
    items: list[TaskOut]
    total: int
    pending_approval_count: int = 0


class TaskApprovalRequest(BaseModel):
    """Request to approve or reject a task."""
    reason: Optional[str] = Field(None, max_length=1000, description="Reason for approval/rejection")


# ═══════════════════════════════════════════════════════════════════
# ACTION AUDIT SCHEMA
# ═══════════════════════════════════════════════════════════════════


class AgentActionOut(BaseModel):
    """Agent action audit record output."""
    id: str
    agent_id: Optional[str] = None
    team_id: Optional[str] = None
    task_id: Optional[str] = None
    organization_id: str
    action_type: str
    target_resource: Optional[str] = None
    target_id: Optional[str] = None
    result_status: str
    details: Optional[dict] = None
    performed_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AgentActionListOut(BaseModel):
    """Paginated list of agent actions."""
    items: list[AgentActionOut]
    total: int


# ═══════════════════════════════════════════════════════════════════
# MISC
# ═══════════════════════════════════════════════════════════════════


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str


# ═══════════════════════════════════════════════════════════════════
# CAPABILITY SCHEMAS
# ═══════════════════════════════════════════════════════════════════


class CapabilityOut(BaseModel):
    """Capability descriptor output."""
    name: str
    display_name: str
    description: str
    capability_type: str
    category: str
    requires_approval: bool
    supported_agent_types: list[str]


class CapabilityListOut(BaseModel):
    """List of capabilities."""
    items: list[CapabilityOut]
    total: int


# ═══════════════════════════════════════════════════════════════════
# HANDOFF SCHEMAS
# ═══════════════════════════════════════════════════════════════════


class HandoffRequest(BaseModel):
    """Request to hand off a task to another agent."""
    target_agent_id: str = Field(description="ID of the agent to hand off to")
    capability_name: Optional[str] = Field(None, description="Capability for the target agent to execute")
    input_data: Optional[dict] = Field(None, description="Input data for the child task")


# ═══════════════════════════════════════════════════════════════════
# AGENT RUNTIME SCHEMAS
# ═══════════════════════════════════════════════════════════════════


class RuntimeExecuteRequest(BaseModel):
    """Request to execute an agent through the runtime pipeline."""
    instruction: str = Field(description="Natural language instruction for the agent")
    capability_hint: Optional[str] = Field(None, description="Optional capability name to execute")
    input_data: Optional[dict] = Field(None, description="Structured input data")
    session_id: Optional[str] = Field(None, description="Optional conversation/session ID")
    is_approved: bool = Field(default=False, description="Whether human approval has been granted")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class ActionResultOut(BaseModel):
    """Result of a single action within a plan."""
    action_id: str
    capability_name: str
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None
    requires_approval: bool = False
    executed_at: Optional[datetime] = None


class RuntimeExecuteResponse(BaseModel):
    """Response from the agent runtime pipeline."""
    request_id: str
    plan_id: str
    status: str
    agent_id: Optional[str] = None
    results: list[ActionResultOut] = []
    error: Optional[str] = None
    execution_duration_ms: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    @property
    def is_success(self) -> bool:
        return self.status == "completed"

    @property
    def is_pending_approval(self) -> bool:
        return self.status == "blocked" and any(
            r.status == "pending_approval" for r in self.results
        )


# ═══════════════════════════════════════════════════════════════════
# NATURAL LANGUAGE TASK SCHEMAS (Chunk 6)
# ═══════════════════════════════════════════════════════════════════


class NLTaskRequest(BaseModel):
    """Request to create and execute a natural language AI task.

    The instruction is processed through the LLMPlanner to produce
    a validated execution plan, which is then persisted as an
    AIAgentTask and executed through the runtime pipeline.
    """
    instruction: str = Field(
        min_length=1,
        max_length=5000,
        description="Natural language instruction for the agent",
    )
    capability_hint: Optional[str] = Field(
        None,
        description="Optional capability name hint to guide planning",
    )
    input_data: Optional[dict] = Field(
        None,
        description="Structured input data to include in the plan",
    )
    requires_human_approval: bool = Field(
        default=False,
        description="Force human approval before execution",
    )
    metadata: Optional[dict] = Field(
        None,
        description="Additional metadata to attach to the task",
    )


class NLTaskPlanActionOut(BaseModel):
    """A single action within a persisted NL task plan."""
    action_id: str
    capability_name: str
    input_data: dict = Field(default_factory=dict)
    requires_approval: bool = False
    status: str


class NLTaskPlanOut(BaseModel):
    """The validated plan persisted within a NL task."""
    plan_id: str
    actions: list[NLTaskPlanActionOut] = Field(default_factory=list)
    metadata: Optional[dict] = None


class NLTaskResponse(BaseModel):
    """Response from creating/executing a natural language AI task.

    Wraps the standard TaskOut with additional plan details.
    The task's output_data contains the plan and per-action results.
    """
    task: TaskOut
    plan: Optional[NLTaskPlanOut] = None
    action_results: list[ActionResultOut] = Field(default_factory=list)
    planner_type: str = "llm"
    message: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW SCHEMAS (Phase 4 — Advanced Automation Workflows)
# ═══════════════════════════════════════════════════════════════════


class WorkflowConditionRequest(BaseModel):
    """A condition for a workflow step."""
    field: str = Field(description="Dot-separated field path to evaluate (e.g., 'step_1.result.stock')")
    operator: str = Field(
        default="eq",
        description="Comparison operator: eq, ne, gt, gte, lt, lte",
    )
    value: Any = Field(description="Value to compare against")


class WorkflowStepRequest(BaseModel):
    """A single step in a workflow definition."""
    step_id: Optional[str] = Field(None, description="Unique step identifier (auto-generated if not provided)")
    capability_name: str = Field(description="Name of the capability to execute")
    input_data: dict = Field(default_factory=dict, description="Input data for the capability")
    condition: Optional[WorkflowConditionRequest] = Field(None, description="Optional condition to evaluate before execution")
    description: Optional[str] = Field(None, description="Human-readable step description")


class WorkflowCreateRequest(BaseModel):
    """Request to create and optionally execute a workflow."""
    name: str = Field(min_length=1, max_length=255, description="Workflow name")
    description: Optional[str] = Field(None, max_length=2000, description="What this workflow does")
    steps: list[WorkflowStepRequest] = Field(
        min_length=1,
        max_length=20,
        description="Ordered list of workflow steps",
    )
    trigger: str = Field(default="manual", description="Trigger type: manual, api, schedule")
    agent_id: str = Field(description="ID of the agent to execute this workflow")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class WorkflowStepConditionOut(BaseModel):
    """Condition output for a workflow step."""
    field: str
    operator: str
    value: Any


class WorkflowStepOut(BaseModel):
    """Workflow step output model."""
    step_id: str
    capability_name: str
    input_data: dict = Field(default_factory=dict)
    condition: Optional[WorkflowStepConditionOut] = None
    description: Optional[str] = None


class WorkflowDefinitionOut(BaseModel):
    """Workflow definition output model."""
    workflow_id: str
    name: str
    description: Optional[str] = None
    steps: list[WorkflowStepOut]
    trigger: str = "manual"
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class WorkflowStepResultOut(BaseModel):
    """Result of a single workflow step execution."""
    step_id: str
    capability_name: str
    status: str
    result: Optional[dict] = None
    error: Optional[str] = None
    requires_approval: bool = False
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None


class WorkflowResultOut(BaseModel):
    """Complete workflow execution result."""
    workflow_id: str
    status: str
    step_results: list[WorkflowStepResultOut] = Field(default_factory=list)
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    steps_completed: int = 0
    steps_failed: int = 0
    steps_skipped: int = 0
    steps_pending_approval: int = 0


class WorkflowExecuteResponse(BaseModel):
    """Response from workflow creation and execution."""
    task: TaskOut
    workflow: WorkflowDefinitionOut
    result: Optional[WorkflowResultOut] = None
    message: Optional[str] = None


class WorkflowListOut(BaseModel):
    """List of workflows."""
    items: list[WorkflowDefinitionOut]
    total: int


class WorkflowValidationResponse(BaseModel):
    """Response from workflow validation."""
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# TEAM SCHEMAS (Phase 4 — 4.6A Team & Agent Collaboration)
# ═══════════════════════════════════════════════════════════════════


class TeamCreateRequest(BaseModel):
    """Request to create a new team."""
    name: str = Field(min_length=1, max_length=255, description="Team name")
    description: Optional[str] = Field(None, max_length=2000, description="Team description")


class TeamUpdateRequest(BaseModel):
    """Partial update for a team (PATCH semantics)."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)


class TeamOut(BaseModel):
    """Team output model — returned by GET endpoints."""
    id: str
    organization_id: str
    name: str
    description: Optional[str] = None
    member_count: int = 0
    agent_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class TeamListOut(BaseModel):
    """Paginated list of teams."""
    items: list[TeamOut]
    total: int


class TeamMemberAddRequest(BaseModel):
    """Request to add a user to a team."""
    user_id: str = Field(description="ID of the user to add")
    role: Optional[str] = Field(None, description="Optional role override for this team membership")


class TeamMemberOut(BaseModel):
    """Team member output model."""
    user_id: str
    username: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str
    is_active: bool
    joined_at: datetime


class TeamMemberListOut(BaseModel):
    """List of team members."""
    items: list[TeamMemberOut]
    total: int


class TeamAgentAssignRequest(BaseModel):
    """Request to assign an agent to a team."""
    agent_id: str = Field(description="ID of the agent to assign")


class TeamAgentOut(BaseModel):
    """Team agent output model."""
    id: str
    name: str
    agent_type: str
    status: str
    team_id: Optional[str] = None
    created_at: datetime


class TeamAgentListOut(BaseModel):
    """List of agents in a team."""
    items: list[TeamAgentOut]
    total: int
