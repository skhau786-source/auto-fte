"""AI Agent domain exceptions — raised by the service layer."""

from typing import Optional


class AgentError(Exception):
    """Base exception for all agent-related errors."""

    def __init__(self, message: str, detail: Optional[dict] = None):
        self.message = message
        self.detail = detail or {}
        super().__init__(self.message)


class AgentNotFoundError(AgentError):
    """Raised when an agent is not found or not accessible."""

    def __init__(self, agent_id: str):
        super().__init__(
            message=f"Agent '{agent_id}' not found",
            detail={"agent_id": agent_id, "error_code": "AGENT_NOT_FOUND"},
        )


class AgentInactiveError(AgentError):
    """Raised when attempting to submit a task to an inactive agent."""

    def __init__(self, agent_id: str):
        super().__init__(
            message=f"Agent '{agent_id}' is inactive and cannot accept tasks",
            detail={"agent_id": agent_id, "error_code": "AGENT_INACTIVE"},
        )


class AgentNameConflictError(AgentError):
    """Raised when an agent with the same name already exists in the organization."""

    def __init__(self, name: str):
        super().__init__(
            message=f"An agent named '{name}' already exists in this organization",
            detail={"name": name, "error_code": "AGENT_NAME_CONFLICT"},
        )


class TaskNotFoundError(AgentError):
    """Raised when a task is not found or not accessible."""

    def __init__(self, task_id: str):
        super().__init__(
            message=f"Task '{task_id}' not found",
            detail={"task_id": task_id, "error_code": "TASK_NOT_FOUND"},
        )


class TaskNotApprovableError(AgentError):
    """Raised when attempting to approve/reject a task that is not in pending_approval state."""

    def __init__(self, task_id: str, current_status: str):
        super().__init__(
            message=f"Task '{task_id}' cannot be approved/rejected (current status: {current_status})",
            detail={
                "task_id": task_id,
                "current_status": current_status,
                "error_code": "TASK_NOT_APPROVABLE",
            },
        )


class TaskNotExecutableError(AgentError):
    """Raised when attempting to execute a task that requires approval."""

    def __init__(self, task_id: str):
        super().__init__(
            message=f"Task '{task_id}' requires human approval before execution",
            detail={"task_id": task_id, "error_code": "TASK_REQUIRES_APPROVAL"},
        )


class LLMProviderError(AgentError):
    """Raised when the LLM provider fails."""

    def __init__(self, provider: str, message: str):
        super().__init__(
            message=f"LLM provider '{provider}' error: {message}",
            detail={"provider": provider, "error_code": "LLM_PROVIDER_ERROR"},
        )


class LLMNotConfiguredError(AgentError):
    """Raised when no LLM provider is configured."""

    def __init__(self):
        super().__init__(
            message="No LLM provider configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable.",
            detail={"error_code": "LLM_NOT_CONFIGURED"},
        )


class MaxConcurrentTasksError(AgentError):
    """Raised when an agent has reached its maximum concurrent task limit."""

    def __init__(self, agent_id: str, limit: int):
        super().__init__(
            message=f"Agent '{agent_id}' has reached the maximum concurrent task limit ({limit})",
            detail={"agent_id": agent_id, "limit": limit, "error_code": "MAX_CONCURRENT_TASKS"},
        )


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════


class WorkflowNotFoundError(AgentError):
    """Raised when a workflow is not found or not accessible."""

    def __init__(self, workflow_id: str):
        super().__init__(
            message=f"Workflow '{workflow_id}' not found",
            detail={"workflow_id": workflow_id, "error_code": "WORKFLOW_NOT_FOUND"},
        )


class WorkflowValidationError(AgentError):
    """Raised when a workflow definition is invalid."""

    def __init__(self, errors: list[str], workflow_id: str = ""):
        super().__init__(
            message=f"Workflow validation failed: {'; '.join(errors[:3])}",
            detail={
                "errors": errors,
                "workflow_id": workflow_id,
                "error_code": "WORKFLOW_VALIDATION_FAILED",
            },
        )


class WorkflowStepError(AgentError):
    """Raised when a workflow step fails."""

    def __init__(self, step_id: str, message: str):
        super().__init__(
            message=f"Workflow step '{step_id}' failed: {message}",
            detail={
                "step_id": step_id,
                "error_code": "WORKFLOW_STEP_FAILED",
            },
        )


class WorkflowConditionError(AgentError):
    """Raised when a workflow condition is invalid."""

    def __init__(self, step_id: str, message: str):
        super().__init__(
            message=f"Workflow condition error in step '{step_id}': {message}",
            detail={
                "step_id": step_id,
                "error_code": "WORKFLOW_CONDITION_ERROR",
            },
        )


# ═══════════════════════════════════════════════════════════════════
# TEAM EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════


class TeamNotFoundError(AgentError):
    """Raised when a team is not found or not accessible."""

    def __init__(self, team_id: str):
        super().__init__(
            message=f"Team '{team_id}' not found",
            detail={"team_id": team_id, "error_code": "TEAM_NOT_FOUND"},
        )


class TeamNameConflictError(AgentError):
    """Raised when a team with the same name already exists in the organization."""

    def __init__(self, name: str):
        super().__init__(
            message=f"A team named '{name}' already exists in this organization",
            detail={"name": name, "error_code": "TEAM_NAME_CONFLICT"},
        )


class TeamMemberNotFoundError(AgentError):
    """Raised when a user is not a member of the team."""

    def __init__(self, team_id: str, user_id: str):
        super().__init__(
            message=f"User '{user_id}' is not a member of team '{team_id}'",
            detail={"team_id": team_id, "user_id": user_id, "error_code": "TEAM_MEMBER_NOT_FOUND"},
        )


class TeamMemberAlreadyExistsError(AgentError):
    """Raised when trying to add a user who is already a member of the team."""

    def __init__(self, team_id: str, user_id: str):
        super().__init__(
            message=f"User '{user_id}' is already a member of team '{team_id}'",
            detail={"team_id": team_id, "user_id": user_id, "error_code": "TEAM_MEMBER_ALREADY_EXISTS"},
        )


class TeamAgentNotFoundError(AgentError):
    """Raised when an agent is not associated with the team."""

    def __init__(self, team_id: str, agent_id: str):
        super().__init__(
            message=f"Agent '{agent_id}' is not associated with team '{team_id}'",
            detail={"team_id": team_id, "agent_id": agent_id, "error_code": "TEAM_AGENT_NOT_FOUND"},
        )


class TeamAgentAlreadyExistsError(AgentError):
    """Raised when trying to assign an agent that is already on the team."""

    def __init__(self, team_id: str, agent_id: str):
        super().__init__(
            message=f"Agent '{agent_id}' is already associated with team '{team_id}'",
            detail={"team_id": team_id, "agent_id": agent_id, "error_code": "TEAM_AGENT_ALREADY_EXISTS"},
        )


class CrossTenantTeamError(AgentError):
    """Raised when trying to associate entities from different organizations."""

    def __init__(self, detail_msg: str = "Cross-organization team operation is not allowed"):
        super().__init__(
            message=detail_msg,
            detail={"error_code": "CROSS_TENANT_TEAM_ERROR"},
        )


class TeamAccessDeniedError(AgentError):
    """Raised when a user lacks team-level authorization to access an agent."""

    def __init__(self, agent_id: str, team_id: str):
        super().__init__(
            message=f"Access denied: you are not authorized to access agent '{agent_id}'",
            detail={
                "agent_id": agent_id,
                "team_id": team_id,
                "error_code": "TEAM_ACCESS_DENIED",
            },
        )
