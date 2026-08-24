"""
Workflow Execution Engine — orchestrates multi-step business workflows.

Architecture:

    WorkflowEngine.execute(workflow, context)
              ↓
    For each step:
        1. Validate step (capability exists)
        2. Evaluate condition (if present)
        3. Execute through CapabilityExecutor (never bypassed)
        4. Collect result
        5. Build context for next step
              ↓
    WorkflowResult (structured, persistent, auditable)

CRITICAL SECURITY INVARIANTS:
- Every action goes through CapabilityRegistry → CapabilityExecutor
- No direct function calls to business services
- No eval() / exec() / arbitrary code execution
- RBAC enforced by CapabilityExecutor
- Approval enforced by CapabilityExecutor (not workflow definition)
- All input_data is validated before execution
- Workflow input is untrusted
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.workflow.models import (
    WorkflowDefinition,
    WorkflowStep,
    WorkflowCondition,
    WorkflowStepResult,
    WorkflowResult,
    WorkflowStatus,
    StepStatus,
)
from app.ai.capabilities.base import capability_registry
from app.ai.capabilities.executor import CapabilityExecutor
from app.ai.exceptions import AgentError

logger = logging.getLogger(__name__)


class WorkflowValidationError(AgentError):
    """Raised when a workflow definition is invalid."""
    def __init__(self, message: str, detail: Optional[dict] = None):
        super().__init__(
            message=message,
            detail=detail or {"error_code": "WORKFLOW_VALIDATION_FAILED"},
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


class WorkflowEngine:
    """
    Orchestrates multi-step workflow execution.

    Usage:
        engine = WorkflowEngine(db=db, organization_id=org_id, user_id=user_id)
        result = await engine.execute(workflow, agent_id=agent_id, task_id=task_id)

    The engine:
    - Validates the workflow definition
    - Executes steps sequentially
    - Evaluates conditions safely
    - Routes every action through CapabilityExecutor
    - Collects structured results
    - Preserves partial results on failure
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
        self.logger = logging.getLogger(f"{__name__}.WorkflowEngine")

    # ═══════════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════════

    async def execute(
        self,
        workflow: WorkflowDefinition,
        agent_id: uuid.UUID,
        task_id: Optional[uuid.UUID] = None,
        agent_type: str = "custom",
        context: Optional[dict[str, Any]] = None,
    ) -> WorkflowResult:
        """
        Execute a complete workflow.

        Args:
            workflow: The validated workflow definition.
            agent_id: ID of the agent executing the workflow.
            task_id: Optional task ID for audit trail linkage.
            agent_type: Type of the agent (for capability authorization).
            context: Optional initial context (merged with step results).

        Returns:
            WorkflowResult with per-step results and overall status.
        """
        start_time = datetime.now(timezone.utc)
        result = WorkflowResult(
            workflow_id=workflow.workflow_id,
            status=WorkflowStatus.RUNNING,
            started_at=start_time,
        )

        # Build execution context: initial context + accumulated step results
        exec_context: dict[str, Any] = dict(context or {})

        try:
            # Validate workflow first
            await self._validate_workflow(workflow, agent_type)

            # Execute steps sequentially
            for step in workflow.steps:
                step_result = await self._execute_step(
                    step=step,
                    agent_id=agent_id,
                    task_id=task_id,
                    agent_type=agent_type,
                    exec_context=exec_context,
                )
                result.step_results.append(step_result)

                # Store step result in context for condition evaluation
                exec_context[step.step_id] = {
                    "status": step_result.status.value,
                    "result": step_result.result,
                    "error": step_result.error,
                }

                # Handle step outcomes
                if step_result.status == StepStatus.FAILED:
                    # Step failed — workflow fails
                    result.status = WorkflowStatus.FAILED
                    result.error = f"Step '{step.step_id}' failed: {step_result.error}"
                    break

                elif step_result.status == StepStatus.PENDING_APPROVAL:
                    # Step requires approval — workflow blocks
                    result.status = WorkflowStatus.BLOCKED
                    result.error = f"Step '{step.step_id}' requires human approval"
                    break

            # Determine final status if not already set
            if result.status == WorkflowStatus.RUNNING:
                completed = sum(
                    1 for sr in result.step_results
                    if sr.status == StepStatus.COMPLETED
                )
                skipped = sum(
                    1 for sr in result.step_results
                    if sr.status == StepStatus.SKIPPED
                )
                total_executed = len(workflow.steps)
                completed_or_skipped = completed + skipped

                if completed_or_skipped == total_executed:
                    result.status = WorkflowStatus.COMPLETED
                else:
                    result.status = WorkflowStatus.PARTIALLY_COMPLETED

        except WorkflowValidationError as exc:
            result.status = WorkflowStatus.FAILED
            result.error = exc.message
            self.logger.error("Workflow validation failed: %s", exc.message)

        except Exception as exc:
            result.status = WorkflowStatus.FAILED
            result.error = f"Workflow execution error: {exc}"
            self.logger.error("Workflow execution failed: %s", exc)

        end_time = datetime.now(timezone.utc)
        result.completed_at = end_time
        result.duration_ms = int((end_time - start_time).total_seconds() * 1000)

        self.logger.info(
            "Workflow %s: %s (steps=%d, completed=%d, duration=%dms)",
            workflow.workflow_id,
            result.status.value,
            len(workflow.steps),
            result.completed_count,
            result.duration_ms,
        )

        return result

    async def validate_workflow(
        self,
        workflow: WorkflowDefinition,
        agent_type: str = "custom",
    ) -> list[str]:
        """
        Validate a workflow definition without executing it.

        Returns a list of validation error messages.
        Empty list means valid.
        """
        errors = list(workflow.validate())  # Basic structural validation

        # Validate capabilities exist
        for i, step in enumerate(workflow.steps):
            if step.capability_name:
                cap = capability_registry.get(step.capability_name)
                if cap is None:
                    errors.append(
                        f"Step {i} ('{step.step_id}'): "
                        f"capability '{step.capability_name}' not found in registry"
                    )
                else:
                    # Check agent type authorization
                    desc = cap.descriptor
                    if (
                        desc.supported_agent_types
                        and agent_type not in desc.supported_agent_types
                    ):
                        errors.append(
                            f"Step {i} ('{step.step_id}'): "
                            f"agent type '{agent_type}' not authorized for "
                            f"capability '{step.capability_name}'"
                        )

            # Validate condition if present
            if step.condition:
                if step.condition.operator not in ("eq", "ne", "gt", "gte", "lt", "lte"):
                    errors.append(
                        f"Step {i} ('{step.step_id}'): "
                        f"unknown condition operator '{step.condition.operator}'"
                    )

        return errors

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL — STEP EXECUTION
    # ═══════════════════════════════════════════════════════════════

    async def _validate_workflow(
        self,
        workflow: WorkflowDefinition,
        agent_type: str,
    ) -> None:
        """Validate a workflow, raising if invalid."""
        errors = await self.validate_workflow(workflow, agent_type)
        if errors:
            raise WorkflowValidationError(
                f"Workflow validation failed with {len(errors)} error(s)",
                detail={
                    "errors": errors,
                    "workflow_id": workflow.workflow_id,
                },
            )

    async def _execute_step(
        self,
        step: WorkflowStep,
        agent_id: uuid.UUID,
        task_id: Optional[uuid.UUID],
        agent_type: str,
        exec_context: dict[str, Any],
    ) -> WorkflowStepResult:
        """
        Execute a single workflow step.

        Flow:
        1. Evaluate condition (if present)
        2. Validate capability exists
        3. Execute through CapabilityExecutor (NEVER bypassed)
        4. Return structured result
        """
        step_result = WorkflowStepResult(
            step_id=step.step_id,
            capability_name=step.capability_name,
            started_at=datetime.now(timezone.utc),
        )

        try:
            # 1. Evaluate condition (if present)
            if step.condition is not None:
                try:
                    condition_met = step.condition.evaluate(exec_context)
                except (KeyError, TypeError, ValueError) as exc:
                    step_result.status = StepStatus.SKIPPED
                    step_result.error = f"Condition evaluation failed: {exc}"
                    step_result.completed_at = datetime.now(timezone.utc)
                    self.logger.info(
                        "Step %s: condition not met or invalid (%s)", step.step_id, exc
                    )
                    return step_result

                if not condition_met:
                    step_result.status = StepStatus.SKIPPED
                    step_result.error = "Condition not met"
                    step_result.completed_at = datetime.now(timezone.utc)
                    self.logger.info("Step %s: skipped (condition not met)", step.step_id)
                    return step_result

            # 2. Validate capability exists
            cap = capability_registry.get(step.capability_name)
            if cap is None:
                step_result.status = StepStatus.FAILED
                step_result.error = (
                    f"Capability '{step.capability_name}' not found in registry"
                )
                step_result.completed_at = datetime.now(timezone.utc)
                self.logger.error(
                    "Step %s: capability '%s' not found",
                    step.step_id, step.capability_name,
                )
                return step_result

            # 3. Check approval requirement from capability (NOT from workflow)
            if cap.requires_approval:
                # Check if this step was previously approved
                # (approval is tracked at the task level in the existing system)
                # For workflow execution, we surface the approval requirement
                step_result.status = StepStatus.PENDING_APPROVAL
                step_result.requires_approval = True
                step_result.completed_at = datetime.now(timezone.utc)
                self.logger.info(
                    "Step %s: requires approval (capability '%s')",
                    step.step_id, step.capability_name,
                )
                return step_result

            # 4. Execute through CapabilityExecutor (NEVER bypassed)
            step_result.status = StepStatus.RUNNING
            executor = CapabilityExecutor(
                db=self.db,
                organization_id=self.organization_id,
                user_id=self.user_id,
            )

            exec_result = await executor.execute(
                capability_name=step.capability_name,
                input_data=step.input_data,
                agent_id=agent_id,
                task_id=task_id,
                agent_type=agent_type,
            )

            end_time = datetime.now(timezone.utc)
            step_result.completed_at = end_time
            step_result.duration_ms = int(
                (end_time - step_result.started_at).total_seconds() * 1000
            )

            if exec_result.get("status") == "success":
                step_result.status = StepStatus.COMPLETED
                step_result.result = exec_result.get("result", {})
                self.logger.info(
                    "Step %s: completed (capability=%s)",
                    step.step_id, step.capability_name,
                )
            else:
                step_result.status = StepStatus.FAILED
                step_result.error = exec_result.get("error", "Unknown execution error")
                self.logger.warning(
                    "Step %s: failed (capability=%s, error=%s)",
                    step.step_id, step.capability_name, step_result.error,
                )

        except Exception as exc:
            end_time = datetime.now(timezone.utc)
            step_result.status = StepStatus.FAILED
            step_result.error = str(exc)
            step_result.completed_at = end_time
            if step_result.started_at:
                step_result.duration_ms = int(
                    (end_time - step_result.started_at).total_seconds() * 1000
                )
            self.logger.error(
                "Step %s: exception (%s)", step.step_id, exc
            )

        return step_result
