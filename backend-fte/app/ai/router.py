"""
AI Agent Router — exposes agent management and task execution endpoints.

Endpoints:
POST   /ai/agents              — Create an agent
GET    /ai/agents              — List agents
GET    /ai/agents/{id}         — Get agent details
PATCH  /ai/agents/{id}         — Update agent
DELETE /ai/agents/{id}         — Deactivate agent

POST   /ai/agents/{id}/tasks   — Submit a task
GET    /ai/agents/{id}/tasks   — List tasks for agent

GET    /ai/tasks/{id}          — Get task details
POST   /ai/tasks/{id}/approve  — Approve a task
POST   /ai/tasks/{id}/reject   — Reject a task

GET    /ai/actions             — List agent audit actions

POST   /ai/tasks/{id}/execute  — Execute a capability
POST   /ai/tasks/{id}/handoff  — Hand off to another agent
GET    /ai/capabilities        — List available capabilities

POST   /ai/runtime/execute     — Execute agent through runtime pipeline
POST   /ai/tasks/nl            — Create natural language task

POST   /ai/workflows           — Create and execute a workflow
POST   /ai/workflows/validate  — Validate a workflow definition
GET    /ai/workflows           — List workflows
GET    /ai/workflows/{id}      — Get workflow details

POST   /ai/teams               — Create a team
GET    /ai/teams               — List teams
GET    /ai/teams/{id}          — Get team details
PATCH  /ai/teams/{id}          — Update team
DELETE /ai/teams/{id}          — Deactivate team
POST   /ai/teams/{id}/members  — Add member to team
DELETE /ai/teams/{id}/members/{user_id} — Remove member
GET    /ai/teams/{id}/members  — List team members
POST   /ai/teams/{id}/agents   — Assign agent to team
DELETE /ai/teams/{id}/agents/{agent_id} — Remove agent
GET    /ai/teams/{id}/agents   — List team agents
"""

import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import RegisteredStudent
from app.organizations.models import Organization
from app.ai.dependencies import require_agent_manage, require_agent_execute, require_agent_approve
from app.ai.schemas import (
    AgentCreateRequest, AgentUpdateRequest, AgentOut, AgentListOut,
    TaskSubmitRequest, TaskOut, TaskListOut, TaskApprovalRequest,
    AgentActionOut, AgentActionListOut, MessageResponse,
)
from app.ai.service import AIService
from app.ai.exceptions import (
    AgentError, AgentNotFoundError, AgentInactiveError,
    AgentNameConflictError, TaskNotFoundError, TaskNotApprovableError,
    TaskNotExecutableError, MaxConcurrentTasksError,
    TeamAccessDeniedError,
)
from app.ai.constants import TaskStatus
from app.ai.capabilities.base import capability_registry, CapabilityCategory
from app.ai.schemas import CapabilityOut, CapabilityListOut, HandoffRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Agents"])


# ═══════════════════════════════════════════════════════════════════
# Error mapping
# ═══════════════════════════════════════════════════════════════════

_EXCEPTION_TO_STATUS = {
    AgentNotFoundError: status.HTTP_404_NOT_FOUND,
    AgentInactiveError: status.HTTP_400_BAD_REQUEST,
    AgentNameConflictError: status.HTTP_409_CONFLICT,
    TaskNotFoundError: status.HTTP_404_NOT_FOUND,
    TaskNotApprovableError: status.HTTP_400_BAD_REQUEST,
    TaskNotExecutableError: status.HTTP_400_BAD_REQUEST,
    MaxConcurrentTasksError: status.HTTP_429_TOO_MANY_REQUESTS,
    TeamAccessDeniedError: status.HTTP_403_FORBIDDEN,
}


def _handle_error(exc: AgentError) -> None:
    """Convert a domain exception to the appropriate HTTP response."""
    status_code = _EXCEPTION_TO_STATUS.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    raise HTTPException(
        status_code=status_code,
        detail={
            "message": exc.message,
            **exc.detail,
        },
    )


# ═══════════════════════════════════════════════════════════════════
# Helper to build agent output with counts
# ═══════════════════════════════════════════════════════════════════

def _agent_to_out(agent) -> AgentOut:
    """Convert an AIAgent model to output schema."""
    return AgentOut(
        id=str(agent.id),
        organization_id=str(agent.organization_id),
        team_id=str(agent.team_id) if agent.team_id else None,
        name=agent.name,
        description=agent.description,
        agent_type=agent.agent_type.value if hasattr(agent.agent_type, "value") else agent.agent_type,
        status=agent.status.value if hasattr(agent.status, "value") else agent.status,
        config=agent.config,
        granted_permissions=agent.granted_permissions,
        is_active=agent.is_active,
        created_by=str(agent.created_by) if agent.created_by else None,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


def _task_to_out(task) -> TaskOut:
    """Convert an AIAgentTask model to output schema."""
    return TaskOut(
        id=str(task.id),
        agent_id=str(task.agent_id),
        organization_id=str(task.organization_id),
        task_type=task.task_type.value if hasattr(task.task_type, "value") else task.task_type,
        status=task.status.value if hasattr(task.status, "value") else task.status,
        input_data=task.input_data,
        output_data=task.output_data,
        error_message=task.error_message,
        requires_human_approval=task.requires_human_approval,
        approved_by=str(task.approved_by) if task.approved_by else None,
        approved_at=task.approved_at,
        rejection_reason=task.rejection_reason,
        submitted_by=str(task.submitted_by) if task.submitted_by else None,
        execution_started_at=task.execution_started_at,
        execution_completed_at=task.execution_completed_at,
        execution_duration_ms=task.execution_duration_ms,
        llm_provider=task.llm_provider,
        llm_model=task.llm_model,
        llm_tokens_used=task.llm_tokens_used,
        parent_task_id=str(task.parent_task_id) if task.parent_task_id else None,
        source_agent_id=str(task.source_agent_id) if task.source_agent_id else None,
        target_agent_id=str(task.target_agent_id) if task.target_agent_id else None,
        capability_name=task.capability_name,
        handoff_depth=task.handoff_depth or 0,
        metadata_=task.metadata_,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


# ═══════════════════════════════════════════════════════════════════
# AGENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/agents",
    status_code=status.HTTP_201_CREATED,
    summary="Create an AI agent",
)
async def create_agent(
    payload: AgentCreateRequest,
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new AI agent in the current organization."""
    try:
        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        team_uuid = uuid.UUID(payload.team_id) if payload.team_id else None
        agent = await service.create_agent(
            name=payload.name,
            agent_type=payload.agent_type,
            description=payload.description,
            config=payload.config,
            granted_permissions=payload.granted_permissions,
            team_id=team_uuid,
        )
        return _agent_to_out(agent)
    except AgentError as exc:
        _handle_error(exc)


@router.get(
    "/agents",
    response_model=AgentListOut,
    summary="List AI agents",
)
async def list_agents(
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all AI agents in the current organization."""
    service = AIService(db=db, organization_id=org.id, user_id=user.id)
    agents = await service.list_agents()
    return AgentListOut(
        items=[_agent_to_out(a) for a in agents],
        total=len(agents),
    )


@router.get(
    "/agents/{agent_id}",
    summary="Get AI agent details",
)
async def get_agent(
    agent_id: uuid.UUID,
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single AI agent by ID."""
    try:
        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        agent = await service.get_agent(agent_id)
        await service.check_team_agent_access(agent)
        return _agent_to_out(agent)
    except AgentError as exc:
        _handle_error(exc)


@router.patch(
    "/agents/{agent_id}",
    summary="Update AI agent",
)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdateRequest,
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Partially update an AI agent."""
    try:
        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        agent = await service.get_agent(agent_id)
        await service.check_team_agent_access(agent)
        updated = await service.update_agent(
            agent_id=agent_id,
            name=payload.name,
            description=payload.description,
            agent_type=payload.agent_type,
            config=payload.config,
            granted_permissions=payload.granted_permissions,
        )
        return _agent_to_out(updated)
    except AgentError as exc:
        _handle_error(exc)


@router.delete(
    "/agents/{agent_id}",
    summary="Deactivate AI agent",
)
async def deactivate_agent(
    agent_id: uuid.UUID,
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate (soft-disable) an AI agent."""
    try:
        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        agent = await service.get_agent(agent_id)
        await service.check_team_agent_access(agent)
        await service.deactivate_agent(agent_id)
        return MessageResponse(message="Agent deactivated successfully")
    except AgentError as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# TASK ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.post(
    "/agents/{agent_id}/tasks",
    status_code=status.HTTP_201_CREATED,
    summary="Submit a task to an agent",
)
async def submit_task(
    agent_id: uuid.UUID,
    payload: TaskSubmitRequest,
    org: Organization = Depends(require_agent_execute),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a new task to an AI agent."""
    try:
        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        agent = await service.get_agent(agent_id)
        await service.check_team_agent_access(agent)
        task = await service.submit_task(
            agent_id=agent_id,
            task_type=payload.task_type,
            input_data=payload.input_data,
            requires_human_approval=payload.requires_human_approval,
            metadata=payload.metadata_,
        )
        return _task_to_out(task)
    except AgentError as exc:
        _handle_error(exc)


@router.get(
    "/agents/{agent_id}/tasks",
    response_model=TaskListOut,
    summary="List tasks for an agent",
)
async def list_agent_tasks(
    agent_id: uuid.UUID,
    task_status: str = Query(None, alias="status", description="Filter by task status"),
    org: Organization = Depends(require_agent_execute),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all tasks for a specific agent."""
    try:
        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        status_filter = None
        if task_status:
            try:
                status_filter = TaskStatus(task_status)
            except ValueError:
                pass

        # Verify agent exists, is accessible, AND passes team authorization
        agent_obj = await service.get_agent(agent_id)
        await service.check_team_agent_access(agent_obj)

        tasks = await service.list_tasks(agent_id=agent_id, status=status_filter)
        pending_approval = sum(
            1 for t in tasks if t.status == TaskStatus.PENDING_APPROVAL
        )
        return TaskListOut(
            items=[_task_to_out(t) for t in tasks],
            total=len(tasks),
            pending_approval_count=pending_approval,
        )
    except AgentError as exc:
        _handle_error(exc)


@router.get(
    "/tasks/{task_id}",
    summary="Get task details",
)
async def get_task(
    task_id: uuid.UUID,
    org: Organization = Depends(require_agent_execute),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single task by ID."""
    try:
        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        task = await service.get_task(task_id)
        return _task_to_out(task)
    except AgentError as exc:
        _handle_error(exc)


@router.post(
    "/tasks/{task_id}/approve",
    summary="Approve a task",
)
async def approve_task(
    task_id: uuid.UUID,
    payload: TaskApprovalRequest = TaskApprovalRequest(),
    org: Organization = Depends(require_agent_approve),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a task that requires human approval."""
    try:
        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        task = await service.approve_task(task_id=task_id, reason=payload.reason, skip_team_check=False)
        return _task_to_out(task)
    except AgentError as exc:
        _handle_error(exc)


@router.post(
    "/tasks/{task_id}/reject",
    summary="Reject a task",
)
async def reject_task(
    task_id: uuid.UUID,
    payload: TaskApprovalRequest = TaskApprovalRequest(),
    org: Organization = Depends(require_agent_approve),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject a task that requires human approval."""
    try:
        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        task = await service.reject_task(task_id=task_id, reason=payload.reason, skip_team_check=False)
        return _task_to_out(task)
    except AgentError as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# CAPABILITY ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/capabilities",
    response_model=CapabilityListOut,
    summary="List available capabilities",
)
async def list_capabilities(
    category: str = Query(None, description="Filter by category: inventory, social, sales"),
    agent_type: str = Query(None, description="Filter by agent type"),
    org: Organization = Depends(require_agent_manage),
):
    """List all registered capabilities, optionally filtered by category or agent type."""
    if agent_type:
        caps = capability_registry.list_for_agent_type(agent_type)
    elif category:
        try:
            cat = CapabilityCategory(category)
            caps = capability_registry.list_by_category(cat)
        except ValueError:
            caps = capability_registry.list_all()
    else:
        caps = capability_registry.list_all()

    return CapabilityListOut(
        items=[
            CapabilityOut(
                name=c.name,
                display_name=c.display_name,
                description=c.description,
                capability_type=c.capability_type.value,
                category=c.category.value,
                requires_approval=c.requires_approval,
                supported_agent_types=c.supported_agent_types,
            )
            for c in caps
        ],
        total=len(caps),
    )


@router.post(
    "/tasks/{task_id}/execute",
    summary="Execute a capability through a task",
)
async def execute_capability(
    task_id: uuid.UUID,
    capability_name: str = Query(..., description="Capability to execute"),
    org: Organization = Depends(require_agent_execute),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute a capability through an existing task."""
    try:
        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        task = await service.get_task(task_id)
        result = await service.execute_capability(
            task_id=task_id,
            capability_name=capability_name,
            input_data=task.input_data,
        )
        return result
    except AgentError as exc:
        _handle_error(exc)


@router.post(
    "/tasks/{task_id}/handoff",
    status_code=status.HTTP_201_CREATED,
    summary="Hand off task to another agent",
)
async def handoff_task(
    task_id: uuid.UUID,
    payload: HandoffRequest,
    org: Organization = Depends(require_agent_execute),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hand off work from the current task to a target agent."""
    try:
        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        child_task = await service.handoff_task(
            parent_task_id=task_id,
            target_agent_id=uuid.UUID(payload.target_agent_id),
            capability_name=payload.capability_name,
            input_data=payload.input_data,
            skip_team_check=False,
        )
        return _task_to_out(child_task)
    except AgentError as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# AUDIT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/actions",
    response_model=AgentActionListOut,
    summary="List agent audit actions",
)
async def list_actions(
    agent_id: uuid.UUID = Query(None, description="Filter by agent"),
    task_id: uuid.UUID = Query(None, description="Filter by task"),
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List audit trail actions for agents and teams.

    Team-scoped: results are always filtered to the requesting user's
    own authorized scope (their team, or all teams for org OWNER/ADMIN)
    by AIService.get_agent_actions() — there is no client-supplied
    team_id filter here, so a user can never request another team's
    audit trail by passing one in.
    """
    service = AIService(db=db, organization_id=org.id, user_id=user.id)
    actions = await service.get_agent_actions(agent_id=agent_id, task_id=task_id)
    return AgentActionListOut(
        items=[
            AgentActionOut(
                id=str(a.id),
                agent_id=str(a.agent_id) if a.agent_id else None,
                team_id=str(a.team_id) if a.team_id else None,
                task_id=str(a.task_id) if a.task_id else None,
                organization_id=str(a.organization_id),
                action_type=a.action_type,
                target_resource=a.target_resource,
                target_id=a.target_id,
                result_status=a.result_status,
                details=a.details,
                performed_by=str(a.performed_by) if a.performed_by else None,
                created_at=a.created_at,
            )
            for a in actions
        ],
        total=len(actions),
    )


# ═══════════════════════════════════════════════════════════════════
# AGENT RUNTIME ENDPOINT
# ═══════════════════════════════════════════════════════════════════

from app.ai.schemas import RuntimeExecuteRequest, RuntimeExecuteResponse, ActionResultOut
from app.ai.runtime.runtime import AgentRuntime, RuntimeValidationError
from app.ai.runtime.models import AgentRequest, PlanStatus


@router.post(
    "/runtime/execute",
    response_model=RuntimeExecuteResponse,
    summary="Execute an agent through the runtime pipeline",
)
async def runtime_execute(
    agent_id: uuid.UUID,
    payload: RuntimeExecuteRequest,
    org: Organization = Depends(require_agent_execute),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute an agent through the full runtime pipeline:

    AgentRequest → Planner → Plan → Validation → CapabilityExecutor → Response

    This endpoint:
    - Validates the agent exists and is active
    - Creates an execution plan via the planner
    - Validates capabilities against the registry
    - Executes actions through CapabilityExecutor (never bypassed)
    - Respects approval gates for destructive capabilities
    - Returns structured results with audit information
    """
    try:
        # Team-level authorization check before runtime execution
        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        agent = await service.get_agent(agent_id)
        await service.check_team_agent_access(agent)

        request = AgentRequest(
            agent_id=agent_id,
            organization_id=org.id,
            user_id=user.id,
            instruction=payload.instruction,
            capability_hint=payload.capability_hint,
            input_data=payload.input_data or {},
            session_id=payload.session_id,
            is_approved=payload.is_approved,
            metadata=payload.metadata or {},
        )

        runtime = AgentRuntime(
            db=db,
            organization_id=org.id,
            user_id=user.id,
        )

        response = await runtime.execute_request(request)

        return RuntimeExecuteResponse(
            request_id=response.request_id,
            plan_id=response.plan_id,
            status=response.status.value,
            agent_id=response.agent_id,
            results=[
                ActionResultOut(
                    action_id=r.action_id,
                    capability_name=r.capability_name,
                    status=r.status.value,
                    result=r.result,
                    error=r.error,
                    requires_approval=r.requires_approval,
                    executed_at=r.executed_at,
                )
                for r in response.results
            ],
            error=response.error,
            execution_duration_ms=response.execution_duration_ms,
            created_at=response.created_at,
            completed_at=response.completed_at,
        )
    except RuntimeValidationError as exc:
        _handle_error(exc)
    except AgentError as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# NATURAL LANGUAGE TASK ENDPOINT (Chunk 6)
# ═══════════════════════════════════════════════════════════════════

from app.ai.schemas import NLTaskRequest, NLTaskResponse, NLTaskPlanOut, NLTaskPlanActionOut


@router.post(
    "/tasks/nl",
    status_code=status.HTTP_201_CREATED,
    response_model=NLTaskResponse,
    summary="Create and execute a natural language AI task",
)
async def create_nl_task(
    agent_id: uuid.UUID,
    payload: NLTaskRequest,
    org: Organization = Depends(require_agent_execute),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a persistent AI task from a natural language instruction.

    Flow:
        1. Validate agent exists and is active
        2. Create persistent AIAgentTask
        3. LLMPlanner produces a validated execution Plan
        4. Plan is persisted in output_data
        5. Non-approval tasks auto-execute through the runtime
        6. Approval-required tasks stay in PENDING_APPROVAL

    This is the primary integration point for natural language
    → persistent task execution (Chunk 6).

    Backward compatibility:
    - POST /ai/agents/{id}/tasks remains unchanged
    - POST /ai/runtime/execute remains unchanged (stateless)
    - This endpoint is additive
    """
    try:
        service = AIService(db=db, organization_id=org.id, user_id=user.id)

        # Team-level authorization check
        agent_obj = await service.get_agent(agent_id)
        await service.check_team_agent_access(agent_obj)

        task = await service.submit_nl_task(
            agent_id=agent_id,
            instruction=payload.instruction,
            capability_hint=payload.capability_hint,
            input_data=payload.input_data,
            requires_human_approval=payload.requires_human_approval,
            metadata=payload.metadata,
        )

        # Build response with plan and action results
        task_out = _task_to_out(task)

        plan_out = None
        action_results = []
        message = None

        output_data = task.output_data or {}
        plan_data = output_data.get("plan")
        results_data = output_data.get("results", [])
        message = output_data.get("message")

        if plan_data:
            plan_out = NLTaskPlanOut(
                plan_id=plan_data.get("plan_id", ""),
                actions=[
                    NLTaskPlanActionOut(
                        action_id=a.get("action_id", ""),
                        capability_name=a.get("capability_name", ""),
                        input_data=a.get("input_data", {}),
                        requires_approval=a.get("requires_approval", False),
                        status=a.get("status", "pending"),
                    )
                    for a in plan_data.get("actions", [])
                ],
                metadata=plan_data.get("metadata"),
            )

        action_results = [
            ActionResultOut(
                action_id=r.get("action_id", ""),
                capability_name=r.get("capability_name", ""),
                status=r.get("status", "pending"),
                result=r.get("result"),
                error=r.get("error"),
                requires_approval=r.get("requires_approval", False),
            )
            for r in results_data
        ]

        return NLTaskResponse(
            task=task_out,
            plan=plan_out,
            action_results=action_results,
            planner_type="llm",
            message=message,
        )
    except AgentError as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW ENDPOINTS (Phase 4 — Advanced Automation Workflows)
# ═══════════════════════════════════════════════════════════════════

from app.ai.schemas import (
    WorkflowCreateRequest, WorkflowDefinitionOut, WorkflowStepOut,
    WorkflowStepConditionOut, WorkflowResultOut, WorkflowStepResultOut,
    WorkflowExecuteResponse, WorkflowListOut, WorkflowValidationResponse,
)
from app.ai.workflow.models import (
    WorkflowDefinition, WorkflowStep, WorkflowCondition,
    WorkflowStatus, StepStatus,
)
from app.ai.workflow.engine import WorkflowEngine
from app.ai.exceptions import WorkflowNotFoundError, WorkflowValidationError as WVE
from app.ai.constants import TaskType, MAX_WORKFLOW_STEPS


def _workflow_def_to_out(wf: WorkflowDefinition) -> WorkflowDefinitionOut:
    """Convert a WorkflowDefinition to API output schema."""
    steps_out = []
    for s in wf.steps:
        cond = None
        if s.condition:
            cond = WorkflowStepConditionOut(
                field=s.condition.field,
                operator=s.condition.operator,
                value=s.condition.value,
            )
        steps_out.append(WorkflowStepOut(
            step_id=s.step_id,
            capability_name=s.capability_name,
            input_data=s.input_data,
            condition=cond,
            description=s.description or None,
        ))
    return WorkflowDefinitionOut(
        workflow_id=wf.workflow_id,
        name=wf.name,
        description=wf.description or None,
        steps=steps_out,
        trigger=wf.trigger,
        metadata=wf.metadata,
        created_at=wf.created_at,
    )


def _workflow_result_to_out(result) -> WorkflowResultOut:
    """Convert a WorkflowResult to API output schema."""
    step_results_out = []
    for sr in result.step_results:
        step_results_out.append(WorkflowStepResultOut(
            step_id=sr.step_id,
            capability_name=sr.capability_name,
            status=sr.status.value,
            result=sr.result,
            error=sr.error,
            requires_approval=sr.requires_approval,
            started_at=sr.started_at,
            completed_at=sr.completed_at,
            duration_ms=sr.duration_ms,
        ))
    return WorkflowResultOut(
        workflow_id=result.workflow_id,
        status=result.status.value,
        step_results=step_results_out,
        error=result.error,
        started_at=result.started_at,
        completed_at=result.completed_at,
        duration_ms=result.duration_ms,
        steps_completed=result.completed_count,
        steps_failed=result.failed_count,
        steps_skipped=result.skipped_count,
        steps_pending_approval=result.pending_approval_count,
    )


@router.post(
    "/workflows",
    status_code=status.HTTP_201_CREATED,
    response_model=WorkflowExecuteResponse,
    summary="Create and execute a workflow",
)
async def create_and_execute_workflow(
    payload: WorkflowCreateRequest,
    org: Organization = Depends(require_agent_execute),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a workflow definition and execute it through the workflow engine.

    Flow:
        1. Build WorkflowDefinition from request
        2. Validate workflow (structural + capability checks)
        3. Create persistent AIAgentTask (type=WORKFLOW)
        4. Execute workflow through WorkflowEngine
        5. Persist results in task output_data
        6. Return task + workflow + result

    All actions go through CapabilityRegistry → CapabilityExecutor.
    RBAC and approval are enforced by CapabilityExecutor.
    """
    try:
        # 1. Build workflow definition
        steps = []
        for s_req in payload.steps:
            condition = None
            if s_req.condition:
                condition = WorkflowCondition(
                    field=s_req.condition.field,
                    operator=s_req.condition.operator,
                    value=s_req.condition.value,
                )
            steps.append(WorkflowStep(
                step_id=s_req.step_id or str(uuid.uuid4())[:8],
                capability_name=s_req.capability_name,
                input_data=s_req.input_data,
                condition=condition,
                description=s_req.description or "",
            ))

        workflow = WorkflowDefinition(
            name=payload.name,
            description=payload.description or "",
            steps=steps,
            trigger=payload.trigger,
            metadata=payload.metadata or {},
        )

        # 2. Validate
        engine = WorkflowEngine(db=db, organization_id=org.id, user_id=user.id)
        agent_id_uuid = uuid.UUID(payload.agent_id)

        # Get agent to determine agent_type
        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        agent = await service.get_agent(agent_id_uuid)
        await service.check_team_agent_access(agent)
        agent_type = (
            agent.agent_type.value
            if hasattr(agent.agent_type, "value")
            else agent.agent_type
        )

        errors = await engine.validate_workflow(workflow, agent_type)
        if errors:
            raise WVE(errors, workflow.workflow_id)

        # 3. Create persistent task
        workflow_meta = {
            "planner_type": "workflow",
            "workflow_definition": workflow.to_dict(),
        }
        if payload.metadata:
            workflow_meta.update(payload.metadata)

        task = await service.submit_task(
            agent_id=agent_id_uuid,
            task_type=TaskType.WORKFLOW,
            input_data={"workflow": workflow.to_dict()},
            requires_human_approval=False,
            metadata=workflow_meta,
            skip_auto_execute=True,
        )

        # 4. Execute workflow
        result = await engine.execute(
            workflow=workflow,
            agent_id=agent_id_uuid,
            task_id=task.id,
            agent_type=agent_type,
        )

        # 5. Persist results in task
        task.output_data = {
            "workflow": workflow.to_dict(),
            "result": result.to_dict(),
        }

        if result.status == WorkflowStatus.COMPLETED:
            task.status = TaskStatus.COMPLETED
            message = f"Workflow '{workflow.name}' completed successfully"
        elif result.status == WorkflowStatus.BLOCKED:
            task.status = TaskStatus.PENDING_APPROVAL
            task.requires_human_approval = True
            message = f"Workflow '{workflow.name}' blocked: requires approval"
        elif result.status == WorkflowStatus.FAILED:
            task.status = TaskStatus.FAILED
            task.error_message = result.error
            message = f"Workflow '{workflow.name}' failed: {result.error}"
        else:
            task.status = TaskStatus.COMPLETED
            message = f"Workflow '{workflow.name}' finished with status: {result.status.value}"

        await db.commit()
        await db.refresh(task)

        # 6. Return response
        return WorkflowExecuteResponse(
            task=_task_to_out(task),
            workflow=_workflow_def_to_out(workflow),
            result=_workflow_result_to_out(result),
            message=message,
        )
    except AgentError as exc:
        _handle_error(exc)


@router.post(
    "/workflows/validate",
    response_model=WorkflowValidationResponse,
    summary="Validate a workflow definition",
)
async def validate_workflow_endpoint(
    payload: WorkflowCreateRequest,
    org: Organization = Depends(require_agent_execute),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Validate a workflow definition without executing it.

    Checks:
    - Structural validity (name, steps, conditions)
    - All capabilities exist in the registry
    - Agent type authorization for each capability
    """
    try:
        steps = []
        for s_req in payload.steps:
            condition = None
            if s_req.condition:
                condition = WorkflowCondition(
                    field=s_req.condition.field,
                    operator=s_req.condition.operator,
                    value=s_req.condition.value,
                )
            steps.append(WorkflowStep(
                step_id=s_req.step_id or str(uuid.uuid4())[:8],
                capability_name=s_req.capability_name,
                input_data=s_req.input_data,
                condition=condition,
                description=s_req.description or "",
            ))

        workflow = WorkflowDefinition(
            name=payload.name,
            description=payload.description or "",
            steps=steps,
            trigger=payload.trigger,
            metadata=payload.metadata or {},
        )

        engine = WorkflowEngine(db=db, organization_id=org.id, user_id=user.id)
        agent_id_uuid = uuid.UUID(payload.agent_id)

        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        agent = await service.get_agent(agent_id_uuid)
        agent_type = (
            agent.agent_type.value
            if hasattr(agent.agent_type, "value")
            else agent.agent_type
        )

        errors = await engine.validate_workflow(workflow, agent_type)

        return WorkflowValidationResponse(
            valid=len(errors) == 0,
            errors=errors,
        )
    except AgentError as exc:
        _handle_error(exc)


@router.get(
    "/workflows",
    response_model=WorkflowListOut,
    summary="List workflows for an agent",
)
async def list_workflows(
    agent_id: uuid.UUID = Query(None, description="Filter by agent ID"),
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List workflow tasks for the organization.

    Applies team-level filtering: only workflows belonging to agents
    the current user is authorized to access are returned.
    Workflows are persisted as AIAgentTask records with task_type=WORKFLOW.
    """
    try:
        service = AIService(db=db, organization_id=org.id, user_id=user.id)

        # If filtering by a specific agent, check team access first
        if agent_id is not None:
            agent_obj = await service.get_agent(agent_id)
            await service.check_team_agent_access(agent_obj)

        tasks = await service.list_tasks(agent_id=agent_id)

        workflows = []
        for task in tasks:
            if task.task_type == TaskType.WORKFLOW and task.metadata_:
                wf_data = (task.metadata_ or {}).get("workflow_definition")
                if wf_data:
                    try:
                        wf = WorkflowDefinition.from_dict(wf_data)
                        workflows.append(_workflow_def_to_out(wf))
                    except Exception:
                        pass  # Skip malformed workflow definitions

        return WorkflowListOut(
            items=workflows,
            total=len(workflows),
        )
    except AgentError as exc:
        _handle_error(exc)


@router.get(
    "/workflows/{workflow_id}",
    summary="Get workflow details",
)
async def get_workflow(
    workflow_id: str,
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a single workflow by its workflow_id.

    Applies team-level authorization: the user must be authorized to
    access the workflow's associated agent. Unauthorized access returns
    404 (same as not-found) to prevent information leakage.
    """
    try:
        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        tasks = await service.list_tasks()

        for task in tasks:
            if task.task_type == TaskType.WORKFLOW and task.metadata_:
                wf_data = (task.metadata_ or {}).get("workflow_definition")
                if wf_data and wf_data.get("workflow_id") == workflow_id:
                    # Team-level access check: verify user can access this task's agent
                    await service.check_task_access(task)

                    wf = WorkflowDefinition.from_dict(wf_data)

                    # Build result if available
                    result_out = None
                    output_data = task.output_data or {}
                    result_data = output_data.get("result")
                    if result_data:
                        # Reconstruct minimal result for output
                        from app.ai.workflow.models import WorkflowResult, WorkflowStepResult
                        wf_result = WorkflowResult(
                            workflow_id=result_data.get("workflow_id", workflow_id),
                            status=WorkflowStatus(result_data.get("status", "pending")),
                            error=result_data.get("error"),
                        )
                        for sr_data in result_data.get("step_results", []):
                            wf_result.step_results.append(WorkflowStepResult(
                                step_id=sr_data.get("step_id", ""),
                                capability_name=sr_data.get("capability_name", ""),
                                status=StepStatus(sr_data.get("status", "pending")),
                                result=sr_data.get("result"),
                                error=sr_data.get("error"),
                                requires_approval=sr_data.get("requires_approval", False),
                            ))
                        result_out = _workflow_result_to_out(wf_result)

                    return {
                        "workflow": _workflow_def_to_out(wf).model_dump(),
                        "result": result_out.model_dump() if result_out else None,
                        "task": _task_to_out(task).model_dump(),
                    }

        raise WorkflowNotFoundError(workflow_id)
    except WorkflowNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": f"Workflow '{workflow_id}' not found", "error_code": "WORKFLOW_NOT_FOUND"},
        )
    except AgentError as exc:
        _handle_error(exc)


# ═══════════════════════════════════════════════════════════════════
# TEAM MANAGEMENT ENDPOINTS (Phase 4 — 4.6A)
# ═══════════════════════════════════════════════════════════════════

from app.ai.schemas import (
    TeamCreateRequest, TeamUpdateRequest, TeamOut, TeamListOut,
    TeamMemberAddRequest, TeamMemberOut, TeamMemberListOut,
    TeamAgentAssignRequest, TeamAgentOut, TeamAgentListOut,
)
from app.ai.team_service import TeamService
from app.ai.exceptions import (
    TeamNotFoundError, TeamNameConflictError,
    TeamMemberNotFoundError, TeamMemberAlreadyExistsError,
    TeamAgentNotFoundError, TeamAgentAlreadyExistsError,
)


async def _get_team_service(
    org: Organization = Depends(require_agent_manage),
    user: RegisteredStudent = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TeamService:
    """Create a TeamService with the current org and user context."""
    return TeamService(db=db, organization_id=org.id, user_id=user.id)


# ── Team CRUD ──

@router.post(
    "/teams",
    status_code=status.HTTP_201_CREATED,
    response_model=TeamOut,
    summary="Create a team",
)
async def create_team(
    payload: TeamCreateRequest,
    service: TeamService = Depends(_get_team_service),
):
    """Create a new team in the current organization."""
    try:
        team = await service.create_team(
            name=payload.name,
            description=payload.description,
        )
        return TeamOut(
            id=str(team.id),
            organization_id=str(team.organization_id),
            name=team.name,
            description=team.description,
            member_count=0,
            agent_count=0,
            created_at=team.created_at,
        )
    except AgentError as exc:
        _handle_error(exc)


@router.get(
    "/teams",
    response_model=TeamListOut,
    summary="List teams",
)
async def list_teams(
    service: TeamService = Depends(_get_team_service),
):
    """List all teams in the current organization."""
    teams = await service.list_teams()
    return TeamListOut(
        items=[
            TeamOut(
                id=str(t.id),
                organization_id=str(t.organization_id),
                name=t.name,
                description=t.description,
                member_count=getattr(t, '_member_count', 0),
                agent_count=getattr(t, '_agent_count', 0),
                created_at=t.created_at,
            )
            for t in teams
        ],
        total=len(teams),
    )


@router.get(
    "/teams/{team_id}",
    response_model=TeamOut,
    summary="Get team details",
)
async def get_team(
    team_id: uuid.UUID,
    service: TeamService = Depends(_get_team_service),
):
    """Get a single team by ID."""
    try:
        team = await service.get_team(team_id)
        return TeamOut(
            id=str(team.id),
            organization_id=str(team.organization_id),
            name=team.name,
            description=team.description,
            member_count=await service._count_team_members(team.id),
            agent_count=await service._count_team_agents(team.id),
            created_at=team.created_at,
        )
    except AgentError as exc:
        _handle_error(exc)


@router.patch(
    "/teams/{team_id}",
    response_model=TeamOut,
    summary="Update team",
)
async def update_team(
    team_id: uuid.UUID,
    payload: TeamUpdateRequest,
    service: TeamService = Depends(_get_team_service),
):
    """Partially update a team (PATCH semantics)."""
    try:
        team = await service.update_team(
            team_id=team_id,
            name=payload.name,
            description=payload.description,
        )
        return TeamOut(
            id=str(team.id),
            organization_id=str(team.organization_id),
            name=team.name,
            description=team.description,
            member_count=await service._count_team_members(team.id),
            agent_count=await service._count_team_agents(team.id),
            created_at=team.created_at,
        )
    except AgentError as exc:
        _handle_error(exc)


@router.delete(
    "/teams/{team_id}",
    summary="Deactivate team",
)
async def deactivate_team(
    team_id: uuid.UUID,
    service: TeamService = Depends(_get_team_service),
):
    """Deactivate a team (removes all members and agents)."""
    try:
        await service.deactivate_team(team_id)
        return MessageResponse(message="Team deactivated successfully")
    except AgentError as exc:
        _handle_error(exc)


# ── Team Membership ──

@router.post(
    "/teams/{team_id}/members",
    status_code=status.HTTP_201_CREATED,
    response_model=TeamMemberOut,
    summary="Add member to team",
)
async def add_team_member(
    team_id: uuid.UUID,
    payload: TeamMemberAddRequest,
    service: TeamService = Depends(_get_team_service),
):
    """Add a user to a team."""
    try:
        user_uuid = uuid.UUID(payload.user_id)
        member = await service.add_member(
            team_id=team_id,
            user_id=user_uuid,
            role=payload.role,
        )
        return TeamMemberOut(
            user_id=str(member.user_id),
            role=member.role.value,
            is_active=member.is_active,
            joined_at=member.created_at,
        )
    except AgentError as exc:
        _handle_error(exc)


@router.delete(
    "/teams/{team_id}/members/{user_id}",
    summary="Remove member from team",
)
async def remove_team_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    service: TeamService = Depends(_get_team_service),
):
    """Remove a user from a team."""
    try:
        await service.remove_member(team_id=team_id, user_id=user_id)
        return MessageResponse(message="Member removed from team")
    except AgentError as exc:
        _handle_error(exc)


@router.get(
    "/teams/{team_id}/members",
    response_model=TeamMemberListOut,
    summary="List team members",
)
async def list_team_members(
    team_id: uuid.UUID,
    service: TeamService = Depends(_get_team_service),
):
    """List all members of a team."""
    try:
        members = await service.list_members(team_id)
        return TeamMemberListOut(
            items=[
                TeamMemberOut(
                    user_id=m["user_id"],
                    username=m.get("username"),
                    email=m.get("email"),
                    full_name=m.get("full_name"),
                    role=m["role"],
                    is_active=m["is_active"],
                    joined_at=m["joined_at"],
                )
                for m in members
            ],
            total=len(members),
        )
    except AgentError as exc:
        _handle_error(exc)


# ── Agent-Team Association ──

@router.post(
    "/teams/{team_id}/agents",
    status_code=status.HTTP_201_CREATED,
    response_model=TeamAgentOut,
    summary="Assign agent to team",
)
async def assign_agent_to_team(
    team_id: uuid.UUID,
    payload: TeamAgentAssignRequest,
    service: TeamService = Depends(_get_team_service),
):
    """Assign an agent to a team."""
    try:
        agent_uuid = uuid.UUID(payload.agent_id)
        agent = await service.assign_agent(
            team_id=team_id,
            agent_id=agent_uuid,
        )
        return TeamAgentOut(
            id=str(agent.id),
            name=agent.name,
            agent_type=agent.agent_type.value if hasattr(agent.agent_type, 'value') else agent.agent_type,
            status=agent.status.value if hasattr(agent.status, 'value') else agent.status,
            team_id=str(agent.team_id) if agent.team_id else None,
            created_at=agent.created_at,
        )
    except AgentError as exc:
        _handle_error(exc)


@router.delete(
    "/teams/{team_id}/agents/{agent_id}",
    summary="Remove agent from team",
)
async def remove_agent_from_team(
    team_id: uuid.UUID,
    agent_id: uuid.UUID,
    service: TeamService = Depends(_get_team_service),
):
    """Remove an agent from a team."""
    try:
        await service.unassign_agent(team_id=team_id, agent_id=agent_id)
        return MessageResponse(message="Agent removed from team")
    except AgentError as exc:
        _handle_error(exc)


@router.get(
    "/teams/{team_id}/agents",
    response_model=TeamAgentListOut,
    summary="List agents in team",
)
async def list_team_agents(
    team_id: uuid.UUID,
    service: TeamService = Depends(_get_team_service),
):
    """List all agents assigned to a team."""
    try:
        agents = await service.list_team_agents(team_id)
        return TeamAgentListOut(
            items=[
                TeamAgentOut(
                    id=str(a.id),
                    name=a.name,
                    agent_type=a.agent_type.value if hasattr(a.agent_type, 'value') else a.agent_type,
                    status=a.status.value if hasattr(a.status, 'value') else a.status,
                    team_id=str(a.team_id) if a.team_id else None,
                    created_at=a.created_at,
                )
                for a in agents
            ],
            total=len(agents),
        )
    except AgentError as exc:
        _handle_error(exc)
