"""
Agent Runtime — the orchestration layer that connects user requests
to the existing capability execution infrastructure.

Architecture:

    AgentRequest
         ↓
    AgentRuntime.execute_request()
         ↓
    AgentValidation (agent exists, active, org-owned)
         ↓
    Planner.create_plan()         ← abstraction boundary
         ↓
    Plan Validation               ← registry checks
         ↓
    Sequential Action Execution   ← CapabilityExecutor
         ↓
    Results Collection
         ↓
    AgentResponse

CRITICAL: The runtime NEVER bypasses CapabilityExecutor.
All capability execution goes through:
    Runtime → CapabilityRegistry → CapabilityExecutor → Capability
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.runtime.models import (
    Plan, PlanAction, AgentRequest, AgentResponse,
    ActionResult, ActionStatus, PlanStatus,
)
from app.ai.runtime.planner import get_planner
from app.ai.capabilities.base import capability_registry
from app.ai.capabilities.executor import CapabilityExecutor
from app.ai.exceptions import AgentError
from app.events.event_dispatcher import get_dispatcher
from app.ai.events import TaskStarted, TaskCompleted, TaskFailed

logger = logging.getLogger(__name__)


class RuntimeValidationError(AgentError):
    """Raised when plan validation fails."""
    def __init__(self, message: str, detail: Optional[dict] = None):
        super().__init__(message=message, detail=detail or {"error_code": "RUNTIME_VALIDATION_FAILED"})


class RuntimeExecutionError(AgentError):
    """Raised when the runtime encounters an execution error."""
    def __init__(self, message: str, detail: Optional[dict] = None):
        super().__init__(message=message, detail=detail or {"error_code": "RUNTIME_EXECUTION_FAILED"})


class AgentRuntime:
    """
    Agent Runtime — orchestrates agent request processing.

    Usage:
        runtime = AgentRuntime(db=db, organization_id=org_id, user_id=user_id)
        response = await runtime.execute_request(request)
    """

    def __init__(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ):
        self.db = db
        self.organization_id = organization_id
        self.user_id = user_id
        self.logger = logging.getLogger(f"{__name__}.AgentRuntime")

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════════

    async def execute_request(self, request: AgentRequest) -> AgentResponse:
        """
        Process an agent request through the full pipeline.

        1. Validate the request
        2. Create a plan via the planner
        3. Validate the plan against capabilities
        4. Execute actions sequentially
        5. Collect and return results
        """
        start_time = datetime.now(timezone.utc)
        response = AgentResponse(
            request_id=request.request_id,
            created_at=start_time,
        )

        try:
            # Step 1: Validate the request
            agent = await self._validate_request(request)
            response.agent_id = str(agent.id)
            agent_type = (
                agent.agent_type.value
                if hasattr(agent.agent_type, "value")
                else agent.agent_type
            )

            # Step 2: Create a plan via the planner
            planner = get_planner()
            plan = await planner.create_plan(
                instruction=request.instruction,
                capability_hint=request.capability_hint,
                input_data=request.input_data,
                agent_type=agent_type,
            )
            response.plan_id = plan.plan_id

            # Step 3: Validate the plan
            await self._validate_plan(plan, agent_type)

            # Step 4: Execute actions sequentially
            plan.status = PlanStatus.EXECUTING
            await self._execute_plan(plan, agent, request)

            # Step 5: Collect results
            response.results = [
                ActionResult.from_plan_action(action)
                for action in plan.actions
            ]

            # Determine final status
            if plan.all_completed:
                plan.status = PlanStatus.COMPLETED
            elif plan.any_pending_approval:
                plan.status = PlanStatus.BLOCKED
            elif plan.any_failed:
                plan.status = (
                    PlanStatus.PARTIALLY_COMPLETED
                    if plan.completed_count > 0
                    else PlanStatus.FAILED
                )
            else:
                plan.status = PlanStatus.COMPLETED

            response.status = plan.status

        except AgentError as exc:
            response.status = PlanStatus.FAILED
            response.error = exc.message
            self.logger.error("Runtime request failed: %s", exc.message)

        except Exception as exc:
            response.status = PlanStatus.FAILED
            response.error = str(exc)
            self.logger.error("Runtime request failed with unexpected error: %s", exc)

        end_time = datetime.now(timezone.utc)
        response.completed_at = end_time
        response.execution_duration_ms = int(
            (end_time - start_time).total_seconds() * 1000
        )

        return response

    # ═══════════════════════════════════════════════════════════════
    # PLAN EXECUTION (4E — Multi-Step)
    # ═══════════════════════════════════════════════════════════════

    async def _execute_plan(
        self,
        plan: Plan,
        agent: Any,
        request: AgentRequest,
    ) -> None:
        """
        Execute all actions in a plan sequentially.

        Each action goes through:
            CapabilityRegistry → CapabilityExecutor → Result

        For approval-required actions that aren't yet approved,
        the action is marked PENDING_APPROVAL and execution continues
        (remaining actions may still execute).
        """
        agent_type = (
            agent.agent_type.value
            if hasattr(agent.agent_type, "value")
            else agent.agent_type
        )

        for action in plan.actions:
            try:
                await self._execute_action(action, agent, agent_type, request)
            except Exception as exc:
                action.mark_failed(str(exc))
                self.logger.error(
                    "Action %s failed: %s", action.action_id, exc
                )

    async def _execute_action(
        self,
        action: PlanAction,
        agent: Any,
        agent_type: str,
        request: AgentRequest,
    ) -> None:
        """Execute a single action through the capability executor."""
        action.mark_running()

        # Check if capability exists in registry (4D — Capability Selection Boundary)
        cap = capability_registry.get(action.capability_name)
        if cap is None:
            action.mark_blocked(f"Capability '{action.capability_name}' not found in registry")
            return

        # Handle approval-required actions (4F — Approval Integration)
        if action.requires_approval and not request.is_approved:
            action.mark_pending_approval()
            return

        # Execute through the EXISTING CapabilityExecutor (4D — never bypass)
        executor = CapabilityExecutor(
            db=self.db,
            organization_id=self.organization_id,
            user_id=self.user_id,
        )

        result = await executor.execute(
            capability_name=action.capability_name,
            input_data=action.input_data,
            agent_id=agent.id,
            task_id=None,  # Runtime may not have a task yet
            agent_type=agent_type,
        )

        if result.get("status") == "success":
            action.mark_completed(result)
        elif result.get("status") == "pending_approval":
            action.mark_pending_approval()
        else:
            action.mark_failed(result.get("error", "Unknown execution error"))

    # ═══════════════════════════════════════════════════════════════
    # VALIDATION
    # ═══════════════════════════════════════════════════════════════

    async def _validate_request(self, request: AgentRequest) -> Any:
        """Validate an incoming agent request."""
        if not request.agent_id:
            raise RuntimeValidationError(
                "agent_id is required",
                detail={"error_code": "MISSING_AGENT_ID"},
            )

        if not request.organization_id:
            raise RuntimeValidationError(
                "organization_id is required",
                detail={"error_code": "MISSING_ORGANIZATION_ID"},
            )

        if str(request.organization_id) != str(self.organization_id):
            raise RuntimeValidationError(
                "organization_id does not match runtime context",
                detail={"error_code": "ORG_MISMATCH"},
            )

        # Load agent from database
        from sqlalchemy import select
        from app.ai.models import AIAgent
        from app.ai.constants import AgentStatus

        result = await self.db.execute(
            select(AIAgent).where(AIAgent.id == request.agent_id)
        )
        agent = result.scalar_one_or_none()

        if agent is None:
            raise RuntimeValidationError(
                f"Agent '{request.agent_id}' not found",
                detail={"error_code": "AGENT_NOT_FOUND"},
            )

        # Org ownership check
        if str(agent.organization_id) != str(self.organization_id):
            raise RuntimeValidationError(
                "Agent does not belong to this organization",
                detail={"error_code": "AGENT_ORG_MISMATCH"},
            )

        # Agent must be active
        if agent.status != AgentStatus.ACTIVE:
            raise RuntimeValidationError(
                f"Agent is {agent.status.value}, must be active",
                detail={"error_code": "AGENT_INACTIVE"},
            )

        return agent

    async def _validate_plan(self, plan: Plan, agent_type: str) -> None:
        """
        Validate a plan against the capability registry.

        Checks:
        - Referenced capabilities exist
        - Agent type is authorized for each capability
        - Action structure is valid
        """
        if not plan.actions:
            # Empty plan is valid (e.g., planner found no matching capabilities)
            return

        for action in plan.actions:
            # Check capability exists
            cap = capability_registry.get(action.capability_name)
            if cap is None:
                action.mark_blocked(
                    f"Capability '{action.capability_name}' not found in registry"
                )
                continue

            # Check agent type authorization
            desc = cap.descriptor
            if (
                desc.supported_agent_types
                and agent_type not in desc.supported_agent_types
            ):
                action.mark_blocked(
                    f"Agent type '{agent_type}' not authorized for "
                    f"capability '{action.capability_name}'"
                )
                continue

            # Validate input structure
            if not isinstance(action.input_data, dict):
                action.mark_blocked("input_data must be a dictionary")
                continue

            # Update requires_approval from actual capability descriptor
            action.requires_approval = desc.requires_approval
