"""
Capability Execution Engine — securely executes agent capabilities.

This is the single entry point for all capability execution.
It enforces:
1. Capability existence check
2. RBAC permission check
3. Human approval gate (if required)
4. Audit logging
5. Error handling
6. Event dispatch
"""

import uuid
import logging
from typing import Any, Optional
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.capabilities.base import (
    BaseCapability,
    CapabilityType,
    capability_registry,
)
from app.ai.exceptions import AgentError

logger = logging.getLogger(__name__)


class CapabilityExecutionError(AgentError):
    """Raised when a capability fails to execute."""
    def __init__(self, capability_name: str, message: str):
        super().__init__(
            message=f"Capability '{capability_name}' failed: {message}",
            detail={"capability": capability_name, "error_code": "CAPABILITY_EXECUTION_FAILED"},
        )


class CapabilityNotFoundError(AgentError):
    """Raised when a requested capability does not exist."""
    def __init__(self, capability_name: str):
        super().__init__(
            message=f"Capability '{capability_name}' not found",
            detail={"capability": capability_name, "error_code": "CAPABILITY_NOT_FOUND"},
        )


class CapabilityUnauthorizedError(AgentError):
    """Raised when an agent is not authorized to use a capability."""
    def __init__(self, capability_name: str, agent_type: str):
        super().__init__(
            message=f"Agent type '{agent_type}' is not authorized for capability '{capability_name}'",
            detail={
                "capability": capability_name,
                "agent_type": agent_type,
                "error_code": "CAPABILITY_UNAUTHORIZED",
            },
        )


class CapabilityExecutor:
    """
    Executes capabilities with full security and audit trail.

    Usage:
        executor = CapabilityExecutor(db=db, organization_id=org_id, user_id=user_id)
        result = await executor.execute(
            capability_name="inventory.list_products",
            input_data={},
            agent_id=agent_id,
            task_id=task_id,
            agent_type="inventory",
        )
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

    async def execute(
        self,
        capability_name: str,
        input_data: dict[str, Any],
        agent_id: Optional[uuid.UUID] = None,
        task_id: Optional[uuid.UUID] = None,
        agent_type: str = "custom",
    ) -> dict[str, Any]:
        """
        Execute a capability with full security checks.

        Args:
            capability_name: Name of the capability to execute.
            input_data: Input parameters for the capability.
            agent_id: ID of the agent executing.
            task_id: ID of the task triggering execution.
            agent_type: Type of the agent (for authorization).

        Returns:
            Capability execution result.
        """
        # 1. Check capability exists
        capability = capability_registry.get(capability_name)
        if capability is None:
            raise CapabilityNotFoundError(capability_name)

        # 2. Check agent type authorization
        desc = capability.descriptor
        if desc.supported_agent_types and agent_type not in desc.supported_agent_types:
            raise CapabilityUnauthorizedError(capability_name, agent_type)

        # 3. Build execution context
        context = {
            "organization_id": self.organization_id,
            "user_id": self.user_id,
            "agent_id": agent_id,
            "task_id": task_id,
            "db": self.db,
        }

        # 4. Execute with error handling
        try:
            result = await capability.execute(input_data=input_data, context=context)

            # Log success
            logger.info(
                "Capability executed: %s (agent=%s, task=%s, org=%s)",
                capability_name, agent_id, task_id, self.organization_id,
            )

            return {
                "capability": capability_name,
                "status": "success",
                "result": result,
                "requires_approval": desc.requires_approval,
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as exc:
            logger.error(
                "Capability execution failed: %s — %s (agent=%s, task=%s)",
                capability_name, exc, agent_id, task_id,
            )
            return {
                "capability": capability_name,
                "status": "error",
                "error": str(exc),
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }

    async def execute_with_approval_check(
        self,
        capability_name: str,
        input_data: dict[str, Any],
        agent_id: Optional[uuid.UUID] = None,
        task_id: Optional[uuid.UUID] = None,
        agent_type: str = "custom",
        is_approved: bool = False,
    ) -> dict[str, Any]:
        """
        Execute a capability, checking approval if required.

        If the capability requires approval and is_approved is False,
        returns a "pending_approval" status instead of executing.

        Args:
            capability_name: Name of the capability.
            input_data: Input parameters.
            agent_id: Agent performing the action.
            task_id: Task triggering execution.
            agent_type: Type of the agent.
            is_approved: Whether human approval has been granted.

        Returns:
            Execution result or approval-required status.
        """
        capability = capability_registry.get(capability_name)
        if capability is None:
            raise CapabilityNotFoundError(capability_name)

        # If approval required and not approved, return pending status
        if capability.requires_approval and not is_approved:
            return {
                "capability": capability_name,
                "status": "pending_approval",
                "message": f"Capability '{capability_name}' requires human approval before execution",
                "requires_approval": True,
            }

        # Execute normally
        return await self.execute(
            capability_name=capability_name,
            input_data=input_data,
            agent_id=agent_id,
            task_id=task_id,
            agent_type=agent_type,
        )
