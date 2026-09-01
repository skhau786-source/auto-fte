"""
AI Agent Service — business logic for agent lifecycle, task management, and execution.

All domain exceptions are raised here (never HTTPException).
The router layer catches and converts them to HTTP responses.

The service NEVER modifies existing inventory/Shopify/WooCommerce data.
Agent tasks interact with those systems through their existing public service APIs.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_

from app.ai.models import AIAgent, AIAgentTask, AIAgentAction
from app.organizations.models import Team
from app.ai.constants import (
    AgentType, AgentStatus, TaskStatus, TaskType,
    MAX_CONCURRENT_TASKS_PER_AGENT,
)  # noqa: E501
from app.ai.exceptions import (
    AgentError,
    AgentNotFoundError,
    AgentInactiveError,
    AgentNameConflictError,
    TaskNotFoundError,
    TaskNotApprovableError,
    MaxConcurrentTasksError,
    TeamAccessDeniedError,
)
from app.ai.events import (
    AgentCreated, AgentUpdated, AgentDeactivated,
    TaskSubmitted, TaskStarted, TaskCompleted, TaskFailed,
    TaskApproved, TaskRejected,
)
from app.ai.metrics import (
    record_task_submitted, record_task_completed, record_task_failed,
    record_task_approved, record_task_rejected,
    record_llm_tokens, record_task_duration,
)  # noqa: F401 — record_task_failed used in _execute_child_task
from app.ai.llm_client import get_llm_client
from app.ai.capabilities.executor import CapabilityExecutor
from app.ai.capabilities.base import capability_registry
from app.events.event_dispatcher import get_dispatcher

logger = logging.getLogger(__name__)


class AIService:
    """
    Orchestrates AI agent operations.

    Usage:
        service = AIService(db=db, organization_id=org.id, user_id=user.id)
        agent = await service.create_agent(data)
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
        self.logger = logging.getLogger(f"{__name__}.AIService")

    # ═══════════════════════════════════════════════════════════════
    # AGENT CRUD
    # ═══════════════════════════════════════════════════════════════

    async def create_agent(
        self,
        name: str,
        agent_type: AgentType = AgentType.CUSTOM,
        description: Optional[str] = None,
        config: Optional[dict] = None,
        granted_permissions: Optional[list[str]] = None,
        team_id: Optional[uuid.UUID] = None,
    ) -> AIAgent:
        """Create a new AI agent in the organization."""
        # Check name uniqueness within org
        existing = await self._get_agent_by_name(name)
        if existing:
            raise AgentNameConflictError(name)

        agent = AIAgent(
            organization_id=self.organization_id,
            name=name,
            description=description,
            agent_type=agent_type,
            status=AgentStatus.INACTIVE,
            config=config,
            granted_permissions=granted_permissions,
            is_active=True,
            created_by=self.user_id,
            team_id=team_id,
        )
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)

        # Log action
        await self._log_action(
            agent_id=agent.id,
            team_id=agent.team_id,
            action_type="agent_created",
            target_resource="agent",
            target_id=str(agent.id),
            details={"name": name, "agent_type": agent_type.value},
        )

        # Dispatch event
        dispatcher = get_dispatcher()
        await dispatcher.dispatch(AgentCreated(
            agent_id=agent.id,
            organization_id=self.organization_id,
            agent_name=name,
            agent_type=agent_type.value,
        ))

        self.logger.info("Agent created: %s (type=%s, org=%s)", name, agent_type.value, self.organization_id)
        return agent

    async def list_agents(self) -> list[AIAgent]:
        """List all agents for the organization."""
        result = await self.db.execute(
            select(AIAgent)
            .where(
                AIAgent.organization_id == self.organization_id,
                AIAgent.is_active == True,  # noqa: E712
            )
            .order_by(AIAgent.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_agent(self, agent_id: uuid.UUID) -> AIAgent:
        """Get a single agent by ID, validating org ownership."""
        agent = await self._get_agent_by_id(agent_id)
        self._ensure_org_owns_agent(agent)
        return agent

    async def update_agent(
        self,
        agent_id: uuid.UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        agent_type: Optional[AgentType] = None,
        config: Optional[dict] = None,
        granted_permissions: Optional[list[str]] = None,
    ) -> AIAgent:
        """Partially update an agent (PATCH semantics)."""
        agent = await self._get_agent_by_id(agent_id)
        self._ensure_org_owns_agent(agent)

        updated_fields = []
        if name is not None:
            # Check uniqueness if name is changing
            if name != agent.name:
                existing = await self._get_agent_by_name(name)
                if existing:
                    raise AgentNameConflictError(name)
            agent.name = name
            updated_fields.append("name")
        if description is not None:
            agent.description = description
            updated_fields.append("description")
        if agent_type is not None:
            agent.agent_type = agent_type
            updated_fields.append("agent_type")
        if config is not None:
            agent.config = config
            updated_fields.append("config")
        if granted_permissions is not None:
            agent.granted_permissions = granted_permissions
            updated_fields.append("granted_permissions")

        if updated_fields:
            await self.db.commit()
            await self.db.refresh(agent)

            # Log action
            await self._log_action(
                agent_id=agent.id,
                team_id=agent.team_id,
                action_type="agent_updated",
                target_resource="agent",
                target_id=str(agent.id),
                details={"updated_fields": updated_fields},
            )

            # Dispatch event
            dispatcher = get_dispatcher()
            await dispatcher.dispatch(AgentUpdated(
                agent_id=agent.id,
                organization_id=self.organization_id,
                updated_fields=updated_fields,
            ))

        return agent

    async def activate_agent(self, agent_id: uuid.UUID) -> AIAgent:
        """Activate an agent."""
        agent = await self._get_agent_by_id(agent_id)
        self._ensure_org_owns_agent(agent)
        agent.status = AgentStatus.ACTIVE
        await self.db.commit()
        await self.db.refresh(agent)
        await self._log_action(
            agent_id=agent.id,
            team_id=agent.team_id,
            action_type="agent_activated",
            target_resource="agent",
            target_id=str(agent.id),
        )
        return agent

    async def deactivate_agent(self, agent_id: uuid.UUID) -> AIAgent:
        """Deactivate an agent (soft disable — does not delete)."""
        agent = await self._get_agent_by_id(agent_id)
        self._ensure_org_owns_agent(agent)
        agent.status = AgentStatus.INACTIVE
        agent.is_active = False
        await self.db.commit()
        await self.db.refresh(agent)

        # Log action
        await self._log_action(
            agent_id=agent.id,
            team_id=agent.team_id,
            action_type="agent_deactivated",
            target_resource="agent",
            target_id=str(agent.id),
        )

        # Dispatch event
        dispatcher = get_dispatcher()
        await dispatcher.dispatch(AgentDeactivated(
            agent_id=agent.id,
            organization_id=self.organization_id,
        ))

        return agent

    # ═══════════════════════════════════════════════════════════════
    # TASK MANAGEMENT
    # ═══════════════════════════════════════════════════════════════

    async def submit_task(
        self,
        agent_id: uuid.UUID,
        task_type: TaskType = TaskType.CUSTOM,
        input_data: Optional[dict] = None,
        requires_human_approval: bool = False,
        metadata: Optional[dict] = None,
        skip_auto_execute: bool = False,
    ) -> AIAgentTask:
        """Submit a task to an agent.

        If input_data contains 'capability_name', the task will be routed
        through the capability execution system when auto-executed.

        Non-approval tasks are auto-executed after submission.
        Approval-gated tasks stay in PENDING_APPROVAL until approved.

        Args:
            skip_auto_execute: If True, create the task but do not auto-execute.
                Used by submit_nl_task() to allow planning/validation before
                execution through the runtime pipeline.
        """
        agent = await self._get_agent_by_id(agent_id)
        self._ensure_org_owns_agent(agent)

        if agent.status != AgentStatus.ACTIVE:
            raise AgentInactiveError(str(agent_id))

        # Check concurrent task limit
        active_count = await self._count_active_tasks(agent_id)
        if active_count >= MAX_CONCURRENT_TASKS_PER_AGENT:
            raise MaxConcurrentTasksError(str(agent_id), MAX_CONCURRENT_TASKS_PER_AGENT)

        # Extract capability_name from input_data if present
        capability_name = (input_data or {}).get("capability_name")
        cleaned_input = {k: v for k, v in (input_data or {}).items() if k != "capability_name"}

        # Determine initial status
        initial_status = (
            TaskStatus.PENDING_APPROVAL if requires_human_approval else TaskStatus.PENDING
        )

        task = AIAgentTask(
            agent_id=agent_id,
            organization_id=self.organization_id,
            task_type=task_type,
            status=initial_status,
            input_data=cleaned_input if cleaned_input else input_data,
            requires_human_approval=requires_human_approval,
            submitted_by=self.user_id,
            metadata_=metadata,
            capability_name=capability_name,
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)

        # Log action
        await self._log_action(
            agent_id=agent_id,
            team_id=agent.team_id,
            task_id=task.id,
            action_type="task_submitted",
            target_resource="task",
            target_id=str(task.id),
            details={
                "task_type": task_type.value,
                "requires_approval": requires_human_approval,
                "status": initial_status.value,
                "capability": capability_name,
            },
        )

        # Metrics
        record_task_submitted(agent.agent_type.value, task_type.value)

        # Dispatch event
        dispatcher = get_dispatcher()
        await dispatcher.dispatch(TaskSubmitted(
            task_id=task.id,
            agent_id=agent_id,
            organization_id=self.organization_id,
            task_type=task_type.value,
            requires_approval=requires_human_approval,
        ))

        self.logger.info(
            "Task submitted: %s to agent %s (type=%s, approval=%s, capability=%s)",
            task.id, agent.name, task_type.value, requires_human_approval, capability_name,
        )

        # Auto-execute non-approval tasks (unless explicitly deferred)
        if not requires_human_approval and not skip_auto_execute:
            await self._execute_task(task)

        return task

    async def submit_nl_task(
        self,
        agent_id: uuid.UUID,
        instruction: str,
        capability_hint: Optional[str] = None,
        input_data: Optional[dict] = None,
        requires_human_approval: bool = False,
        metadata: Optional[dict] = None,
    ) -> AIAgentTask:
        """
        Submit a natural language task for planning and optional execution.

        Flow:
            1. Validate agent
            2. Create persistent AIAgentTask
            3. Run LLMPlanner to produce a validated Plan
            4. Store plan in output_data
            5. Auto-execute non-approval tasks through the runtime
            6. Approval-required tasks stay in PENDING_APPROVAL

        This is the primary integration point for Chunk 6 — connecting
        natural language instructions to the persistent task system.

        Args:
            agent_id: The agent to handle this task.
            instruction: Natural language instruction from the user.
            capability_hint: Optional capability name hint.
            input_data: Optional structured input data.
            requires_human_approval: Force approval requirement.
            metadata: Additional metadata.

        Returns:
            The persisted AIAgentTask with plan and/or execution results.
        """
        agent = await self._get_agent_by_id(agent_id)
        self._ensure_org_owns_agent(agent)

        if agent.status != AgentStatus.ACTIVE:
            raise AgentInactiveError(str(agent_id))

        # Check concurrent task limit
        active_count = await self._count_active_tasks(agent_id)
        if active_count >= MAX_CONCURRENT_TASKS_PER_AGENT:
            raise MaxConcurrentTasksError(str(agent_id), MAX_CONCURRENT_TASKS_PER_AGENT)

        # Build task input_data: preserve the original instruction
        task_input = {
            "instruction": instruction,
        }
        if capability_hint:
            task_input["capability_hint"] = capability_hint
        if input_data:
            task_input["data"] = input_data

        # Merge LLM planner metadata
        task_metadata = dict(metadata or {})
        task_metadata["planner_type"] = "llm"
        task_metadata["instruction"] = instruction

        # Create the task (skip auto-execute — we'll execute through runtime)
        task = await self.submit_task(
            agent_id=agent_id,
            task_type=TaskType.CUSTOM,
            input_data=task_input,
            requires_human_approval=requires_human_approval,
            metadata=task_metadata,
            skip_auto_execute=True,
        )

        # ── Plan through the runtime ──
        try:
            from app.ai.runtime.runtime import AgentRuntime
            from app.ai.runtime.planner import get_planner
            from app.ai.runtime.models import PlanStatus, ActionStatus

            runtime = AgentRuntime(
                db=self.db,
                organization_id=self.organization_id,
                user_id=self.user_id,
            )

            agent_type = (
                agent.agent_type.value
                if hasattr(agent.agent_type, "value")
                else agent.agent_type
            )

            # Create plan through the planner (LLM or SimplePlanner)
            planner = get_planner()
            plan = await planner.create_plan(
                instruction=instruction,
                capability_hint=capability_hint,
                input_data=input_data,
                agent_type=agent_type,
            )

            # Validate plan against capability registry
            await runtime._validate_plan(plan, agent_type)

            # ── Persist the validated plan ──
            plan_data = {
                "plan_id": plan.plan_id,
                "actions": [
                    {
                        "action_id": a.action_id,
                        "capability_name": a.capability_name,
                        "input_data": a.input_data,
                        "requires_approval": a.requires_approval,
                        "status": a.status.value,
                    }
                    for a in plan.actions
                ],
                "metadata": {
                    k: v for k, v in plan.metadata.items()
                    if k not in ("raw_action_count",)
                },
            }
            task.output_data = {"plan": plan_data, "results": []}

            # Update LLM tracking from planner metadata
            task.llm_provider = plan.metadata.get("llm_provider")
            task.llm_model = plan.metadata.get("llm_model")
            task.llm_tokens_used = plan.metadata.get("llm_tokens")

            # ── Determine task status ──
            if not plan.actions:
                # No actions — planner found no matching capabilities
                task.status = TaskStatus.COMPLETED
                task.output_data["message"] = (
                    "No matching capabilities found for this instruction."
                )
            elif plan.has_approval_required and not requires_human_approval:
                # Some actions require approval — gate the entire task
                task.status = TaskStatus.PENDING_APPROVAL
                task.requires_human_approval = True
            else:
                # Non-approval task — auto-execute through runtime
                task.status = TaskStatus.PENDING
                await self.db.commit()
                await self._execute_task(task)
                return task

            await self.db.commit()
            await self.db.refresh(task)

            # Log the planning result
            action_count = len(plan.actions)
            validated_count = len([a for a in plan.actions if a.status != ActionStatus.BLOCKED])
            await self._log_action(
                agent_id=agent_id,
                team_id=agent.team_id,
                task_id=task.id,
                action_type="nl_task_planned",
                target_resource="task",
                target_id=str(task.id),
                details={
                    "instruction": instruction[:200],  # truncate for safety
                    "action_count": action_count,
                    "validated_action_count": validated_count,
                    "status": task.status.value,
                    "has_approval_required": plan.has_approval_required,
                },
            )

            self.logger.info(
                "NL task planned: %s (actions=%d, validated=%d, status=%s)",
                task.id, action_count, validated_count, task.status.value,
            )

        except Exception as exc:
            # Planner failure — persist error state (6E)
            # Sanitize: truncate and avoid storing raw exception details
            # that might contain secrets (API keys, tokens, etc.)
            error_str = str(exc)[:200]
            # Remove anything that looks like a secret
            import re
            sanitized = re.sub(r'(api[_-]?key|token|secret|password)[=:\s]+\S+', r'\1=[REDACTED]', error_str, flags=re.IGNORECASE)
            task.status = TaskStatus.FAILED
            task.error_message = f"Planning failed: {sanitized}"
            await self.db.commit()
            await self.db.refresh(task)

            await self._log_action(
                agent_id=agent_id,
                team_id=agent.team_id,
                task_id=task.id,
                action_type="nl_task_planning_failed",
                target_resource="task",
                target_id=str(task.id),
                details={"error": str(exc)[:500]},
                result_status="failed",
            )

            self.logger.error("NL task planning failed: %s — %s", task.id, exc)

        return task

    async def get_visible_agent_ids(self) -> set[uuid.UUID]:
        """
        Return the set of agent IDs the current user may access.

        Delegates to TeamService for the centralized team-level
        authorization decision. Used for task and workflow filtering.
        """
        if self.user_id is None:
            # Internal execution — return all org agents
            result = await self.db.execute(
                select(AIAgent.id).where(
                    AIAgent.organization_id == self.organization_id,
                    AIAgent.is_active == True,  # noqa: E712
                )
            )
            return set(result.scalars().all())

        from app.ai.team_service import TeamService
        team_svc = TeamService(
            db=self.db,
            organization_id=self.organization_id,
            user_id=self.user_id,
        )
        return await team_svc.get_user_accessible_agent_ids()

    async def get_visible_team_ids(self) -> set[uuid.UUID]:
        """
        Return the set of team IDs the current user may see audit
        actions for.

        Mirrors get_visible_agent_ids(): internal/system execution (no
        user_id) is unrestricted; otherwise delegates to TeamService for
        the same OWNER/ADMIN-sees-all-teams, member-sees-own-team rule
        used everywhere else team visibility is decided. Used by
        get_agent_actions() to scope team-level audit rows (agent_id
        IS NULL, team_id set) alongside the existing agent-based scoping.
        """
        if self.user_id is None:
            result = await self.db.execute(
                select(Team.id).where(Team.organization_id == self.organization_id)
            )
            return set(result.scalars().all())

        from app.ai.team_service import TeamService
        team_svc = TeamService(
            db=self.db,
            organization_id=self.organization_id,
            user_id=self.user_id,
        )
        return await team_svc.get_user_accessible_team_ids()

    async def check_task_access(
        self,
        task: AIAgentTask,
        agent: Optional[AIAgent] = None,
    ) -> None:
        """
        Enforce team-level authorization for a specific task.

        Checks whether the current user can access the task's agent based
        on team membership using TeamService.can_access_agent().

        If unauthorized, raises TaskNotFoundError (NOT TeamAccessDeniedError)
        to prevent information leakage about another team's resources.

        Args:
            task: The task to authorize access for.
            agent: Optional pre-loaded agent. If provided, avoids an extra
                   DB query. If not provided, the agent is fetched.
        """
        if self.user_id is None:
            return  # Internal execution — skip

        # Fetch the agent only if not already provided
        if agent is None:
            agent = await self._get_agent_by_id(task.agent_id)

        from app.ai.team_service import TeamService
        team_svc = TeamService(
            db=self.db,
            organization_id=self.organization_id,
            user_id=self.user_id,
        )
        allowed = await team_svc.can_access_agent(
            agent=agent,
            user_id=self.user_id,
        )
        if not allowed:
            # Raise TaskNotFoundError (404) not TeamAccessDeniedError (403)
            # to prevent leaking information about another team's resources
            raise TaskNotFoundError(str(task.id))

    async def list_tasks(
        self,
        agent_id: Optional[uuid.UUID] = None,
        status: Optional[TaskStatus] = None,
    ) -> list[AIAgentTask]:
        """
        List tasks, optionally filtered by agent and/or status.

        Applies team-level filtering: only tasks belonging to agents
        the current user is authorized to access are returned.
        Teamless agents remain backward-compatible (all org members
        can see their tasks).
        """
        query = select(AIAgentTask).where(
            AIAgentTask.organization_id == self.organization_id,
        )
        if agent_id:
            query = query.where(AIAgentTask.agent_id == agent_id)
        if status:
            query = query.where(AIAgentTask.status == status)
        query = query.order_by(AIAgentTask.created_at.desc())

        result = await self.db.execute(query)
        all_tasks = list(result.scalars().all())

        # Team-level filtering
        if self.user_id is not None:
            visible_agent_ids = await self.get_visible_agent_ids()
            all_tasks = [
                t for t in all_tasks
                if t.agent_id in visible_agent_ids
            ]

        return all_tasks

    async def get_task(self, task_id: uuid.UUID) -> AIAgentTask:
        """
        Get a single task by ID, validating org ownership and team access.

        Team-level authorization: verifies the user is allowed to access
        the task's agent based on team membership. Unauthorized access
        raises TaskNotFoundError (same as org-level) to prevent
        information leakage.
        """
        task = await self._get_task_by_id(task_id)
        self._ensure_org_owns_task(task)
        await self.check_task_access(task)
        return task

    async def approve_task(
        self,
        task_id: uuid.UUID,
        reason: Optional[str] = None,
        skip_team_check: bool = True,
    ) -> AIAgentTask:
        """Approve a task that requires human approval."""
        task = await self._get_task_by_id(task_id)
        self._ensure_org_owns_task(task)

        # Fetch agent once — reused for team check, metrics, and execution
        agent = await self._get_agent_by_id(task.agent_id)

        if not skip_team_check:
            await self.check_task_access(task, agent=agent)

        if task.status != TaskStatus.PENDING_APPROVAL:
            raise TaskNotApprovableError(str(task_id), task.status.value)

        task.status = TaskStatus.PENDING  # Now eligible for execution
        task.approved_by = self.user_id
        task.approved_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(task)

        # Log action
        await self._log_action(
            agent_id=task.agent_id,
            team_id=agent.team_id,
            task_id=task.id,
            action_type="task_approved",
            target_resource="task",
            target_id=str(task.id),
            details={"reason": reason},
            result_status="approved",
        )

        # Metrics
        record_task_approved(agent.agent_type.value, task.task_type.value)

        # Dispatch event
        dispatcher = get_dispatcher()
        await dispatcher.dispatch(TaskApproved(
            task_id=task.id,
            agent_id=task.agent_id,
            organization_id=self.organization_id,
            approved_by=self.user_id,
        ))

        self.logger.info("Task approved: %s by user %s", task.id, self.user_id)

        # Auto-execute now that approval is granted
        await self._execute_task(task)

        return task

    async def reject_task(
        self,
        task_id: uuid.UUID,
        reason: Optional[str] = None,
        skip_team_check: bool = True,
    ) -> AIAgentTask:
        """Reject a task that requires human approval."""
        task = await self._get_task_by_id(task_id)
        self._ensure_org_owns_task(task)

        # Fetch agent once — reused for team check and metrics
        agent = await self._get_agent_by_id(task.agent_id)

        if not skip_team_check:
            await self.check_task_access(task, agent=agent)

        if task.status != TaskStatus.PENDING_APPROVAL:
            raise TaskNotApprovableError(str(task_id), task.status.value)

        task.status = TaskStatus.REJECTED
        task.rejection_reason = reason
        await self.db.commit()
        await self.db.refresh(task)

        # Log action
        await self._log_action(
            agent_id=task.agent_id,
            team_id=agent.team_id,
            task_id=task.id,
            action_type="task_rejected",
            target_resource="task",
            target_id=str(task.id),
            details={"reason": reason},
            result_status="rejected",
        )

        # Metrics
        record_task_rejected(agent.agent_type.value, task.task_type.value)

        # Dispatch event
        dispatcher = get_dispatcher()
        await dispatcher.dispatch(TaskRejected(
            task_id=task.id,
            agent_id=task.agent_id,
            organization_id=self.organization_id,
            rejected_by=self.user_id,
            reason=reason or "",
        ))

        self.logger.info("Task rejected: %s by user %s (reason=%s)", task.id, self.user_id, reason)
        return task

    async def get_agent_actions(
        self,
        agent_id: Optional[uuid.UUID] = None,
        task_id: Optional[uuid.UUID] = None,
    ) -> list[AIAgentAction]:
        """
        Get audit trail for agent actions.

        Applies team-level filtering at the query level (using the
        indexed team_id column, mirroring how agent_id/task_id are
        already filtered in SQL) so a user only ever receives actions
        they're authorized to see — never another team's audit trail.
        Internal/system execution (user_id is None) is unrestricted, same
        as get_visible_agent_ids()/get_visible_team_ids().

        A row is visible if:
        - its agent_id is one the user can access (get_visible_agent_ids), OR
        - its team_id is one the user can access (get_visible_team_ids), OR
        - it has neither an agent nor a team (org-level action) — visible
          to all org members, mirroring the teamless-agent behavior used
          elsewhere in this module.

        team_id is never accepted from the caller/client here — visibility
        is always derived from the authenticated user's own org/team
        membership via TeamService, never trusted from request input.
        """
        query = select(AIAgentAction).where(
            AIAgentAction.organization_id == self.organization_id,
        )
        if agent_id:
            query = query.where(AIAgentAction.agent_id == agent_id)
        if task_id:
            query = query.where(AIAgentAction.task_id == task_id)

        if self.user_id is not None:
            visible_agent_ids = await self.get_visible_agent_ids()
            visible_team_ids = await self.get_visible_team_ids()
            query = query.where(
                or_(
                    AIAgentAction.agent_id.in_(visible_agent_ids),
                    AIAgentAction.team_id.in_(visible_team_ids),
                    and_(
                        AIAgentAction.agent_id.is_(None),
                        AIAgentAction.team_id.is_(None),
                    ),
                )
            )

        query = query.order_by(AIAgentAction.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ═══════════════════════════════════════════════════════════════
    # TASK EXECUTION
    # ═══════════════════════════════════════════════════════════════

    async def _execute_task(self, task: AIAgentTask) -> None:
        """
        Execute a task — orchestrate the full lifecycle.

        If the task has a capability_name, execute through the capability system.
        If the task is LLM-planned (planner_type=llm in metadata), execute
        through the runtime pipeline.
        Otherwise, fall back to the LLM client.

        Lifecycle: PENDING → RUNNING → COMPLETED / FAILED
        """
        # Route LLM-planned tasks to the runtime execution path (6J)
        task_metadata = task.metadata_ or {}
        if task_metadata.get("planner_type") == "llm" and not task.capability_name:
            await self._execute_task_via_runtime(task)
            return

        agent = await self._get_agent_by_id(task.agent_id)
        dispatcher = get_dispatcher()
        start_time = datetime.now(timezone.utc)

        # Mark as running
        task.status = TaskStatus.RUNNING
        task.execution_started_at = start_time
        await self.db.commit()

        # Dispatch start event
        await dispatcher.dispatch(TaskStarted(
            task_id=task.id,
            agent_id=agent.id,
            organization_id=self.organization_id,
        ))

        # Log action
        await self._log_action(
            agent_id=agent.id,
            team_id=agent.team_id,
            task_id=task.id,
            action_type="task_started",
            target_resource="task",
            target_id=str(task.id),
        )

        try:
            # Determine execution path: capability vs LLM
            if task.capability_name:
                result = await self._execute_task_via_capability(task, agent)
            else:
                result = await self._execute_task_via_llm(task, agent)

            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Apply result to task
            task.execution_completed_at = end_time
            task.execution_duration_ms = duration_ms

            if result.get("status") == "success":
                task.status = TaskStatus.COMPLETED
                task.output_data = result
                record_task_completed(agent.agent_type.value, task.task_type.value)
                record_task_duration(agent.agent_type.value, task.task_type.value, duration_ms / 1000)
            elif result.get("status") == "pending_approval":
                task.status = TaskStatus.PENDING_APPROVAL
                task.requires_human_approval = True
                task.output_data = result
            else:
                task.status = TaskStatus.FAILED
                task.error_message = result.get("error", "Unknown error")
                task.output_data = result
                record_task_failed(agent.agent_type.value, task.task_type.value)

            await self.db.commit()

            # Log action
            await self._log_action(
                agent_id=agent.id,
                team_id=agent.team_id,
                task_id=task.id,
                action_type="task_completed" if task.status == TaskStatus.COMPLETED else "task_failed",
                target_resource="task",
                target_id=str(task.id),
                details={"duration_ms": duration_ms, "status": task.status.value},
                result_status=task.status.value,
            )

            # Dispatch completion/failure event
            if task.status == TaskStatus.COMPLETED:
                await dispatcher.dispatch(TaskCompleted(
                    task_id=task.id,
                    agent_id=agent.id,
                    organization_id=self.organization_id,
                    duration_ms=duration_ms,
                    tokens_used=task.llm_tokens_used or 0,
                ))
            elif task.status == TaskStatus.FAILED:
                await dispatcher.dispatch(TaskFailed(
                    task_id=task.id,
                    agent_id=agent.id,
                    organization_id=self.organization_id,
                    error_message=task.error_message or "",
                ))

            self.logger.info(
                "Task %s: %s (status=%s, duration=%dms)",
                "completed" if task.status == TaskStatus.COMPLETED else "failed",
                task.id, task.status.value, duration_ms,
            )

        except Exception as exc:
            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            task.status = TaskStatus.FAILED
            task.error_message = str(exc)
            task.execution_completed_at = end_time
            task.execution_duration_ms = duration_ms
            await self.db.commit()

            record_task_failed(agent.agent_type.value, task.task_type.value)

            await self._log_action(
                agent_id=agent.id,
                team_id=agent.team_id,
                task_id=task.id,
                action_type="task_failed",
                target_resource="task",
                target_id=str(task.id),
                details={"error": str(exc)},
                result_status="failed",
            )

            await dispatcher.dispatch(TaskFailed(
                task_id=task.id,
                agent_id=agent.id,
                organization_id=self.organization_id,
                error_message=str(exc),
            ))

            self.logger.error("Task failed: %s — %s", task.id, exc)

    async def _execute_task_via_capability(self, task: AIAgentTask, agent: AIAgent) -> dict:
        """Execute a task through the capability system."""
        executor = CapabilityExecutor(
            db=self.db,
            organization_id=self.organization_id,
            user_id=self.user_id,
        )
        return await executor.execute_with_approval_check(
            capability_name=task.capability_name,
            input_data=task.input_data or {},
            agent_id=agent.id,
            task_id=task.id,
            agent_type=agent.agent_type.value if hasattr(agent.agent_type, "value") else agent.agent_type,
            is_approved=task.approved_by is not None,
        )

    async def _execute_task_via_llm(self, task: AIAgentTask, agent: AIAgent) -> dict:
        """Execute a task through the LLM client."""
        llm_client = get_llm_client()
        prompt = self._build_prompt(task)
        system_prompt = self._build_system_prompt(agent)

        response = await llm_client.complete(
            prompt=prompt,
            system_prompt=system_prompt,
            model=agent.config.get("model") if agent.config else None,
            max_tokens=agent.config.get("max_tokens", 1024) if agent.config else 1024,
            temperature=agent.config.get("temperature", 0.7) if agent.config else 0.7,
        )

        if response.tokens_used > 0:
            record_llm_tokens(response.provider, response.model, response.tokens_used)

        task.llm_provider = response.provider
        task.llm_model = response.model
        task.llm_tokens_used = response.tokens_used

        return {
            "status": "success",
            "response": response.content,
            "provider": response.provider,
            "model": response.model,
            "tokens_used": response.tokens_used,
        }

    async def _execute_task_via_runtime(self, task: AIAgentTask) -> None:
        """
        Execute an LLM-planned task through the runtime pipeline.

        This is the primary execution path for natural language tasks (Chunk 6).
        The task's validated plan is re-executed through the runtime, which
        routes each action through CapabilityExecutor with RBAC and approval.

        Lifecycle: PENDING → RUNNING → COMPLETED / FAILED / PENDING_APPROVAL

        Result persistence (6O):
        - output_data stores the plan + per-action results
        - error_message stores failure details
        - execution_started_at / execution_completed_at / execution_duration_ms
        - llm_provider / llm_model / llm_tokens_used from planner
        """
        agent = await self._get_agent_by_id(task.agent_id)
        dispatcher = get_dispatcher()
        start_time = datetime.now(timezone.utc)

        # Mark as running
        task.status = TaskStatus.RUNNING
        task.execution_started_at = start_time
        await self.db.commit()

        # Dispatch start event
        await dispatcher.dispatch(TaskStarted(
            task_id=task.id,
            agent_id=agent.id,
            organization_id=self.organization_id,
        ))

        await self._log_action(
            agent_id=agent.id,
            team_id=agent.team_id,
            task_id=task.id,
            action_type="runtime_execution_started",
            target_resource="task",
            target_id=str(task.id),
        )

        try:
            from app.ai.runtime.runtime import AgentRuntime
            from app.ai.runtime.planner import get_planner
            from app.ai.runtime.models import AgentRequest, ActionStatus, PlanStatus

            # Reconstruct the AgentRequest from task data
            task_input = task.input_data or {}
            instruction = task_input.get("instruction", "")
            capability_hint = task_input.get("capability_hint")
            input_data = task_input.get("data") or {}

            # Check if approval was granted
            is_approved = task.approved_by is not None

            request = AgentRequest(
                agent_id=task.agent_id,
                organization_id=self.organization_id,
                user_id=self.user_id,
                instruction=instruction,
                capability_hint=capability_hint,
                input_data=input_data,
                is_approved=is_approved,
            )

            runtime = AgentRuntime(
                db=self.db,
                organization_id=self.organization_id,
                user_id=self.user_id,
            )

            response = await runtime.execute_request(request)

            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # ── Persist results (6O) ──
            task.execution_completed_at = end_time
            task.execution_duration_ms = duration_ms

            action_results = [
                {
                    "action_id": r.action_id,
                    "capability_name": r.capability_name,
                    "status": r.status.value,
                    "result": r.result,
                    "error": r.error,
                    "requires_approval": r.requires_approval,
                }
                for r in response.results
            ]

            # Preserve the plan from output_data
            existing_output = task.output_data or {}
            task.output_data = {
                "plan": existing_output.get("plan"),
                "results": action_results,
                "runtime_status": response.status.value if hasattr(response.status, "value") else response.status,
            }

            # Determine final task status based on runtime results
            if response.status in (PlanStatus.COMPLETED, PlanStatus.PARTIALLY_COMPLETED):
                if response.status == PlanStatus.COMPLETED:
                    task.status = TaskStatus.COMPLETED
                    record_task_completed(
                        agent.agent_type.value, task.task_type.value
                    )
                else:
                    # Partially completed — some actions succeeded, some failed
                    task.status = TaskStatus.FAILED
                    task.error_message = "Partial execution: some actions failed"
                    record_task_failed(
                        agent.agent_type.value, task.task_type.value
                    )
            elif response.is_pending_approval:
                task.status = TaskStatus.PENDING_APPROVAL
                task.requires_human_approval = True
            elif response.status == PlanStatus.FAILED:
                task.status = TaskStatus.FAILED
                task.error_message = response.error or "Execution failed"
                record_task_failed(
                    agent.agent_type.value, task.task_type.value
                )
            else:
                task.status = TaskStatus.COMPLETED
                record_task_completed(
                    agent.agent_type.value, task.task_type.value
                )

            record_task_duration(
                agent.agent_type.value, task.task_type.value, duration_ms / 1000
            )

            await self.db.commit()

            # Log completion
            await self._log_action(
                agent_id=agent.id,
                team_id=agent.team_id,
                task_id=task.id,
                action_type="runtime_execution_completed" if task.status == TaskStatus.COMPLETED else "runtime_execution_failed",
                target_resource="task",
                target_id=str(task.id),
                details={
                    "duration_ms": duration_ms,
                    "status": task.status.value,
                    "action_count": len(action_results),
                    "completed_count": sum(1 for r in action_results if r["status"] == "completed"),
                    "failed_count": sum(1 for r in action_results if r["status"] == "failed"),
                },
                result_status=task.status.value,
            )

            # Dispatch completion/failure events
            if task.status == TaskStatus.COMPLETED:
                await dispatcher.dispatch(TaskCompleted(
                    task_id=task.id,
                    agent_id=agent.id,
                    organization_id=self.organization_id,
                    duration_ms=duration_ms,
                    tokens_used=task.llm_tokens_used or 0,
                ))
            elif task.status == TaskStatus.FAILED:
                await dispatcher.dispatch(TaskFailed(
                    task_id=task.id,
                    agent_id=agent.id,
                    organization_id=self.organization_id,
                    error_message=task.error_message or "",
                ))

            self.logger.info(
                "Runtime task %s: %s (duration=%dms, actions=%d)",
                task.id, task.status.value, duration_ms, len(action_results),
            )

        except Exception as exc:
            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            task.status = TaskStatus.FAILED
            task.error_message = f"Runtime execution failed: {exc}"
            task.execution_completed_at = end_time
            task.execution_duration_ms = duration_ms
            await self.db.commit()

            record_task_failed(agent.agent_type.value, task.task_type.value)

            await self._log_action(
                agent_id=agent.id,
                team_id=agent.team_id,
                task_id=task.id,
                action_type="runtime_execution_failed",
                target_resource="task",
                target_id=str(task.id),
                details={"error": str(exc)[:500]},
                result_status="failed",
            )

            await dispatcher.dispatch(TaskFailed(
                task_id=task.id,
                agent_id=agent.id,
                organization_id=self.organization_id,
                error_message=str(exc),
            ))

            self.logger.error("Runtime task failed: %s — %s", task.id, exc)

    # ═══════════════════════════════════════════════════════════════
    # CAPABILITY EXECUTION
    # ═══════════════════════════════════════════════════════════════

    async def execute_capability(
        self,
        task_id: uuid.UUID,
        capability_name: str,
        input_data: Optional[dict] = None,
        is_approved: bool = False,
    ) -> dict:
        """
        Execute a capability through the secure executor.

        This is the controlled way agents interact with business services.
        Full audit trail and events are recorded.
        """
        task = await self._get_task_by_id(task_id)
        self._ensure_org_owns_task(task)
        agent = await self._get_agent_by_id(task.agent_id)
        await self.check_task_access(task, agent=agent)
        dispatcher = get_dispatcher()

        # Log capability request
        await self._log_action(
            agent_id=agent.id,
            team_id=agent.team_id,
            task_id=task.id,
            action_type="capability_executed",
            target_resource="capability",
            target_id=capability_name,
            details={
                "capability": capability_name,
                "input_keys": list((input_data or {}).keys()),
                "is_approved": is_approved,
            },
        )

        executor = CapabilityExecutor(
            db=self.db,
            organization_id=self.organization_id,
            user_id=self.user_id,
        )

        result = await executor.execute_with_approval_check(
            capability_name=capability_name,
            input_data=input_data or {},
            agent_id=agent.id,
            task_id=task.id,
            agent_type=agent.agent_type.value if hasattr(agent.agent_type, "value") else agent.agent_type,
            is_approved=is_approved,
        )

        # Update task with capability result
        task.capability_name = capability_name
        if result.get("status") == "pending_approval":
            task.status = TaskStatus.PENDING_APPROVAL
            task.requires_human_approval = True
            task.output_data = result
        elif result.get("status") == "success":
            task.status = TaskStatus.COMPLETED
            task.output_data = result
        elif result.get("status") == "error":
            task.status = TaskStatus.FAILED
            task.error_message = result.get("error")
            task.output_data = result

        await self.db.commit()

        # Log completion/failure
        await self._log_action(
            agent_id=agent.id,
            team_id=agent.team_id,
            task_id=task.id,
            action_type="capability_completed" if result.get("status") == "success" else "capability_failed",
            target_resource="capability",
            target_id=capability_name,
            details={"result_status": result.get("status")},
            result_status=result.get("status", "unknown"),
        )

        return result

    # ═══════════════════════════════════════════════════════════════
    # AGENT HANDOFF
    # ═══════════════════════════════════════════════════════════════

    MAX_HANDOFF_DEPTH = 5  # Maximum agent hops to prevent infinite loops

    async def handoff_task(
        self,
        parent_task_id: uuid.UUID,
        target_agent_id: uuid.UUID,
        capability_name: Optional[str] = None,
        input_data: Optional[dict] = None,
        skip_team_check: bool = True,
    ) -> AIAgentTask:
        """
        Hand off work from one agent to another via a child task.

        Creates a new child task assigned to the target agent,
        linked to the parent task for traceability.
        """
        parent_task = await self._get_task_by_id(parent_task_id)
        self._ensure_org_owns_task(parent_task)

        target_agent = await self._get_agent_by_id(target_agent_id)
        self._ensure_org_owns_agent(target_agent)

        if not skip_team_check:
            await self.check_task_access(parent_task)
            await self.check_team_agent_access(target_agent)

        # Check handoff depth limit
        if parent_task.handoff_depth >= self.MAX_HANDOFF_DEPTH:
            raise AgentError(
                message=f"Maximum handoff depth ({self.MAX_HANDOFF_DEPTH}) reached",
                detail={"error_code": "MAX_HANDOFF_DEPTH"},
            )

        if target_agent.status != AgentStatus.ACTIVE:
            raise AgentInactiveError(str(target_agent_id))

        child_task = AIAgentTask(
            agent_id=target_agent_id,
            organization_id=self.organization_id,
            task_type=TaskType.CUSTOM,
            status=TaskStatus.PENDING,
            input_data=input_data or {},
            requires_human_approval=False,
            submitted_by=self.user_id,
            parent_task_id=parent_task.id,
            source_agent_id=parent_task.agent_id,
            target_agent_id=target_agent_id,
            capability_name=capability_name,
            handoff_depth=parent_task.handoff_depth + 1,
        )
        self.db.add(child_task)
        await self.db.commit()
        await self.db.refresh(child_task)

        # Log action
        # team_id intentionally omitted: this event bridges the source
        # agent (parent_task.agent_id, logged as agent_id below) and
        # target_agent, which may belong to different teams. Neither
        # loaded object here is guaranteed to match agent_id's team, and
        # get_agent_actions() already scopes this row correctly via
        # agent_id (get_visible_agent_ids() is team-aware) without it.
        await self._log_action(
            agent_id=parent_task.agent_id,
            task_id=child_task.id,
            action_type="task_handoff",
            target_resource="task",
            target_id=str(child_task.id),
            details={
                "parent_task_id": str(parent_task.id),
                "target_agent_id": str(target_agent_id),
                "capability": capability_name,
                "depth": child_task.handoff_depth,
            },
        )

        self.logger.info(
            "Task handoff: %s → %s (depth=%d)",
            parent_task.id, child_task.id, child_task.handoff_depth,
        )

        # Execute the child task if it has a capability
        if capability_name:
            await self._execute_child_task(child_task, capability_name)

        return child_task

    async def _execute_child_task(self, task: AIAgentTask, capability_name: str) -> None:
        """Execute a child task through its capability with full audit."""
        agent = await self._get_agent_by_id(task.agent_id)
        dispatcher = get_dispatcher()
        start_time = datetime.now(timezone.utc)

        task.status = TaskStatus.RUNNING
        task.execution_started_at = start_time
        await self.db.commit()

        # Dispatch start event
        await dispatcher.dispatch(TaskStarted(
            task_id=task.id,
            agent_id=agent.id,
            organization_id=self.organization_id,
        ))

        await self._log_action(
            agent_id=agent.id,
            team_id=agent.team_id,
            task_id=task.id,
            action_type="child_task_started",
            target_resource="task",
            target_id=str(task.id),
            details={"capability": capability_name, "parent_task_id": str(task.parent_task_id)},
        )

        try:
            executor = CapabilityExecutor(
                db=self.db,
                organization_id=self.organization_id,
                user_id=self.user_id,
            )

            result = await executor.execute(
                capability_name=capability_name,
                input_data=task.input_data or {},
                agent_id=agent.id,
                task_id=task.id,
                agent_type=agent.agent_type.value if hasattr(agent.agent_type, "value") else agent.agent_type,
            )

            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            if result.get("status") == "success":
                task.status = TaskStatus.COMPLETED
                task.output_data = result
                record_task_completed(agent.agent_type.value, task.task_type.value)
            elif result.get("status") == "pending_approval":
                task.status = TaskStatus.PENDING_APPROVAL
                task.requires_human_approval = True
                task.output_data = result
            else:
                task.status = TaskStatus.FAILED
                task.error_message = result.get("error", "Unknown error")
                task.output_data = result
                record_task_failed(agent.agent_type.value, task.task_type.value)

            task.execution_completed_at = end_time
            task.execution_duration_ms = duration_ms
            await self.db.commit()

            # Log and dispatch events
            await self._log_action(
                agent_id=agent.id,
                team_id=agent.team_id,
                task_id=task.id,
                action_type="child_task_completed" if task.status == TaskStatus.COMPLETED else "child_task_failed",
                target_resource="task",
                target_id=str(task.id),
                details={"duration_ms": duration_ms, "capability": capability_name},
                result_status=task.status.value,
            )

            if task.status == TaskStatus.COMPLETED:
                await dispatcher.dispatch(TaskCompleted(
                    task_id=task.id,
                    agent_id=agent.id,
                    organization_id=self.organization_id,
                    duration_ms=duration_ms,
                ))
            elif task.status == TaskStatus.FAILED:
                await dispatcher.dispatch(TaskFailed(
                    task_id=task.id,
                    agent_id=agent.id,
                    organization_id=self.organization_id,
                    error_message=task.error_message or "",
                ))

        except Exception as exc:
            end_time = datetime.now(timezone.utc)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            task.status = TaskStatus.FAILED
            task.error_message = str(exc)
            task.execution_completed_at = end_time
            task.execution_duration_ms = duration_ms
            await self.db.commit()

            record_task_failed(agent.agent_type.value, task.task_type.value)

            await self._log_action(
                agent_id=agent.id,
                team_id=agent.team_id,
                task_id=task.id,
                action_type="child_task_failed",
                target_resource="task",
                target_id=str(task.id),
                details={"error": str(exc)},
                result_status="failed",
            )

            await dispatcher.dispatch(TaskFailed(
                task_id=task.id,
                agent_id=agent.id,
                organization_id=self.organization_id,
                error_message=str(exc),
            ))

    def _build_prompt(self, task: AIAgentTask) -> str:
        """Build an LLM prompt from task input data."""
        input_data = task.input_data or {}
        task_type = task.task_type.value

        # Build a structured prompt based on task type
        prompt_parts = [f"Task Type: {task_type}"]

        if input_data:
            for key, value in input_data.items():
                prompt_parts.append(f"{key}: {value}")

        return "\n".join(prompt_parts)

    def _build_system_prompt(self, agent: AIAgent) -> str:
        """Build a system prompt for the agent based on its type and config."""
        agent_type = agent.agent_type.value
        config = agent.config or {}
        custom_system = config.get("system_prompt", "")

        base_prompts = {
            "inventory": "You are an inventory management AI assistant. Help analyze stock levels, identify low stock items, and suggest reorder quantities. Be concise and data-driven.",
            "social": "You are a social media content AI assistant. Help create engaging posts, captions, and content calendars for e-commerce products. Be creative and brand-aware.",
            "sales": "You are a sales analytics AI assistant. Help analyze sales trends, identify opportunities, and suggest pricing optimizations. Be analytical and actionable.",
            "analytics": "You are a business analytics AI assistant. Help analyze business data, identify trends, and provide actionable insights. Be thorough and evidence-based.",
            "custom": "You are a helpful AI business assistant for an e-commerce platform. Provide clear, actionable responses.",
        }

        base = base_prompts.get(agent_type, base_prompts["custom"])

        if custom_system:
            return f"{base}\n\nAdditional instructions:\n{custom_system}"

        return base

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ═══════════════════════════════════════════════════════════════

    async def _get_agent_by_id(self, agent_id: uuid.UUID) -> AIAgent:
        result = await self.db.execute(
            select(AIAgent).where(AIAgent.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            raise AgentNotFoundError(str(agent_id))
        return agent

    async def _get_agent_by_name(self, name: str) -> Optional[AIAgent]:
        result = await self.db.execute(
            select(AIAgent).where(
                AIAgent.organization_id == self.organization_id,
                AIAgent.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def _get_task_by_id(self, task_id: uuid.UUID) -> AIAgentTask:
        result = await self.db.execute(
            select(AIAgentTask).where(AIAgentTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if task is None:
            raise TaskNotFoundError(str(task_id))
        return task

    async def _count_active_tasks(self, agent_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count(AIAgentTask.id)).where(
                AIAgentTask.agent_id == agent_id,
                AIAgentTask.status.in_([
                    TaskStatus.PENDING,
                    TaskStatus.PENDING_APPROVAL,
                    TaskStatus.RUNNING,
                ]),
            )
        )
        return result.scalar() or 0

    def _ensure_org_owns_agent(self, agent: AIAgent) -> None:
        if str(agent.organization_id) != str(self.organization_id):
            raise AgentNotFoundError(str(agent.id))

    def _ensure_org_owns_task(self, task: AIAgentTask) -> None:
        if str(task.organization_id) != str(self.organization_id):
            raise TaskNotFoundError(str(task.id))

    async def check_team_agent_access(self, agent: AIAgent) -> None:
        """
        Enforce team-level agent authorization.

        Called after org-level ownership is verified. Checks whether the
        current user is authorized to access the agent based on team
        membership. Uses TeamService.can_access_agent() for the
        centralized authorization decision.

        Rules:
        - Org OWNER/ADMIN can access any agent in their org
        - Teamless agents (team_id=None) are accessible to all org members
        - Users must be members of the agent's team to access it
        - Unauthorized access raises TeamAccessDeniedError
        """
        if self.user_id is None:
            return  # No user context — skip team check (internal execution)

        from app.ai.team_service import TeamService
        team_svc = TeamService(
            db=self.db,
            organization_id=self.organization_id,
            user_id=self.user_id,
        )
        allowed = await team_svc.can_access_agent(
            agent=agent,
            user_id=self.user_id,
        )
        if not allowed:
            raise TeamAccessDeniedError(
                agent_id=str(agent.id),
                team_id=str(agent.team_id) if agent.team_id else "none",
            )

    async def _log_action(
        self,
        agent_id: uuid.UUID,
        action_type: str,
        target_resource: Optional[str] = None,
        target_id: Optional[str] = None,
        details: Optional[dict] = None,
        result_status: str = "success",
        task_id: Optional[uuid.UUID] = None,
        team_id: Optional[uuid.UUID] = None,
    ) -> AIAgentAction:
        """
        Create an immutable audit log entry.

        team_id should be the *agent's own* team_id (e.g. agent.team_id),
        passed by the caller from an already-loaded AIAgent — never a
        client-supplied value, and never re-derived here via an extra
        query (this method is called from many hot paths whose tests
        assert exact db.execute() call counts). Omit it only when no
        single team can be attributed to the action; the action then
        remains scoped by agent_id alone in get_agent_actions().
        """
        action = AIAgentAction(
            agent_id=agent_id,
            team_id=team_id,
            task_id=task_id,
            organization_id=self.organization_id,
            action_type=action_type,
            target_resource=target_resource,
            target_id=target_id,
            result_status=result_status,
            details=details,
            performed_by=self.user_id,
        )
        self.db.add(action)
        await self.db.flush()  # Flush but don't commit — let the caller commit
        return action
