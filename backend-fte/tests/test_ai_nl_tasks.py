"""
Tests for Chunk 6 — Natural Language Task Execution.
"""

import uuid
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.ai.models import AIAgent, AIAgentTask, AIAgentAction
from app.ai.constants import AgentType, AgentStatus, TaskStatus, TaskType
from app.organizations.models import OrganizationMember, MembershipRole
from app.ai.service import AIService
from app.ai.exceptions import (
    AgentNotFoundError, AgentInactiveError, MaxConcurrentTasksError, TaskNotFoundError,
)
from app.ai.schemas import NLTaskRequest, NLTaskResponse, NLTaskPlanOut
from app.ai.llm_client import MockLLMClient, reset_llm_client
from app.ai.capabilities.base import capability_registry
from app.ai.runtime.planner import SimplePlanner, set_planner, reset_planner
from app.ai.runtime.models import Plan, PlanAction, ActionStatus, PlanStatus


# ═══════════════════════════════════════════════════════════════════
# FIXTURES & HELPERS
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def org_id():
    return uuid.uuid4()

@pytest.fixture
def user_id():
    return uuid.uuid4()

@pytest.fixture
def other_org_id():
    return uuid.uuid4()

@pytest_asyncio.fixture
async def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


def _ensure_capabilities_registered():
    if not capability_registry.list_all():
        from app.ai.capabilities.inventory_capabilities import register_inventory_capabilities
        from app.ai.capabilities.social_capabilities import register_social_capabilities
        from app.ai.capabilities.sales_capabilities import register_sales_capabilities
        register_inventory_capabilities()
        register_social_capabilities()
        register_sales_capabilities()

_ensure_capabilities_registered()

@pytest.fixture(autouse=True)
def _ensure_caps():
    _ensure_capabilities_registered()

@pytest.fixture(autouse=True)
def _force_simple_planner():
    set_planner(SimplePlanner())
    yield
    reset_planner()

@pytest.fixture(autouse=True)
def _reset_llm():
    reset_llm_client()
    yield
    reset_llm_client()


def _make_agent(org_id, agent_type=AgentType.INVENTORY, status=AgentStatus.ACTIVE, name="Test Agent"):
    return AIAgent(
        id=uuid.uuid4(), organization_id=org_id, name=name,
        agent_type=agent_type, status=status, is_active=True,
    )

def _make_task(agent_id, org_id, status=TaskStatus.PENDING, **kwargs):
    defaults = dict(
        id=uuid.uuid4(), agent_id=agent_id, organization_id=org_id,
        task_type=TaskType.CUSTOM, status=status, requires_human_approval=False,
    )
    defaults.update(kwargs)
    return AIAgentTask(**defaults)

def _make_result(obj):
    r = MagicMock()
    r.scalar_one_or_none.return_value = obj
    return r

def _make_count_result(count=0):
    r = MagicMock()
    r.scalar.return_value = count
    return r


def _nl_task_side_effects(agent):
    """submit_nl_task calls: _get_agent_by_id, _count_active_tasks,
    submit_task calls: _get_agent_by_id, _count_active_tasks."""
    return [
        _make_result(agent), _make_count_result(0),
        _make_result(agent), _make_count_result(0),
    ]

def _nl_task_side_effects_with_runtime(agent):
    """Same as above plus one more _get_agent_by_id for _execute_task_via_runtime."""
    return [
        _make_result(agent), _make_count_result(0),
        _make_result(agent), _make_count_result(0),
        _make_result(agent),
    ]

def _make_runtime_response(status=PlanStatus.COMPLETED, results=None, error=None):
    from app.ai.runtime.models import AgentResponse
    return AgentResponse(
        request_id=str(uuid.uuid4()), plan_id=str(uuid.uuid4()),
        status=status, agent_id=str(uuid.uuid4()),
        results=results or [], error=error,
    )


def _make_mock_runtime(execute_return=None, execute_side_effect=None):
    """Create a mock AgentRuntime with async _validate_plan and execute_request."""
    mock_runtime = MagicMock()
    mock_runtime._validate_plan = AsyncMock()
    if execute_side_effect is not None:
        mock_runtime.execute_request = AsyncMock(side_effect=execute_side_effect)
    else:
        mock_runtime.execute_request = AsyncMock(
            return_value=execute_return or _make_runtime_response()
        )
    return mock_runtime


def _make_plan_with_actions(capability_name="inventory.list_products", input_data=None):
    """Create a Plan with one action for testing execution paths."""
    return Plan(
        plan_id=str(uuid.uuid4()),
        actions=[PlanAction(
            capability_name=capability_name,
            input_data=input_data or {},
            requires_approval=False,
        )],
        metadata={"planner": "llm"},
    )


# ═══════════════════════════════════════════════════════════════════
# 6A — TASK CREATION FROM NATURAL LANGUAGE
# ═══════════════════════════════════════════════════════════════════

class TestNLTaskCreation:

    @pytest.mark.asyncio
    async def test_submit_nl_task_creates_task(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task = await service.submit_nl_task(agent_id=agent.id, instruction="List all products")
        assert task.agent_id == agent.id
        assert task.organization_id == org_id
        assert task.input_data["instruction"] == "List all products"
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_nl_task_belongs_to_correct_organization(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task = await service.submit_nl_task(agent_id=agent.id, instruction="Check inventory")
        assert str(task.organization_id) == str(org_id)

    @pytest.mark.asyncio
    async def test_nl_task_belongs_to_correct_user(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task = await service.submit_nl_task(agent_id=agent.id, instruction="Analyze sales")
        assert str(task.submitted_by) == str(user_id)

    @pytest.mark.asyncio
    async def test_nl_task_correct_agent_associated(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, name="Inventory Bot")
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task = await service.submit_nl_task(agent_id=agent.id, instruction="Get low stock items")
        assert str(task.agent_id) == str(agent.id)

    @pytest.mark.asyncio
    async def test_nl_task_instruction_persisted(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task = await service.submit_nl_task(agent_id=agent.id, instruction="Show me top selling products")
        assert task.input_data["instruction"] == "Show me top selling products"

    @pytest.mark.asyncio
    async def test_nl_task_inactive_agent_fails(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, status=AgentStatus.INACTIVE)
        mock_db.execute.return_value = _make_result(agent)
        with pytest.raises(AgentInactiveError):
            await service.submit_nl_task(agent_id=agent.id, instruction="Do something")

    @pytest.mark.asyncio
    async def test_nl_task_concurrent_limit(self, mock_db, org_id, user_id):
        from app.ai.constants import MAX_CONCURRENT_TASKS_PER_AGENT
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = [
            _make_result(agent),
            _make_count_result(MAX_CONCURRENT_TASKS_PER_AGENT),
        ]
        with pytest.raises(MaxConcurrentTasksError):
            await service.submit_nl_task(agent_id=agent.id, instruction="Do something")


# ═══════════════════════════════════════════════════════════════════
# 6B — PLAN → TASK CONVERSION
# ═══════════════════════════════════════════════════════════════════

class TestPlanToTaskConversion:

    @pytest.mark.asyncio
    async def test_plan_persisted_in_output_data(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task = await service.submit_nl_task(agent_id=agent.id, instruction="List all products")
        output = task.output_data or {}
        assert "plan" in output
        plan = output["plan"]
        assert "plan_id" in plan
        assert "actions" in plan
        assert isinstance(plan["actions"], list)

    @pytest.mark.asyncio
    async def test_plan_has_planner_metadata(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        output = task.output_data or {}
        plan = output.get("plan", {})
        metadata = plan.get("metadata", {})
        assert metadata.get("planner") in ("llm", "rule_based", None)

    @pytest.mark.asyncio
    async def test_raw_llm_output_never_executed(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        output = task.output_data or {}
        assert "plan" in output
        plan_str = json.dumps(output.get("plan", {}))
        assert "```" not in plan_str


# ═══════════════════════════════════════════════════════════════════
# 6C — TASK PERSISTENCE
# ═══════════════════════════════════════════════════════════════════

class TestTaskPersistence:

    @pytest.mark.asyncio
    async def test_task_metadata_contains_planner_type(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task = await service.submit_nl_task(agent_id=agent.id, instruction="Check stock levels")
        assert task.metadata_ is not None
        assert task.metadata_.get("planner_type") == "llm"

    @pytest.mark.asyncio
    async def test_task_instruction_in_metadata(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task = await service.submit_nl_task(agent_id=agent.id, instruction="Show me revenue data")
        assert task.metadata_.get("instruction") == "Show me revenue data"

    @pytest.mark.asyncio
    async def test_task_type_is_custom(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task = await service.submit_nl_task(agent_id=agent.id, instruction="Analyze trends")
        assert task.task_type == TaskType.CUSTOM

    @pytest.mark.asyncio
    async def test_task_input_data_structure(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task = await service.submit_nl_task(
            agent_id=agent.id, instruction="Get product details",
            input_data={"product_id": "123"},
        )
        assert task.input_data["instruction"] == "Get product details"
        assert task.input_data["data"]["product_id"] == "123"

    @pytest.mark.asyncio
    async def test_task_with_capability_hint(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task = await service.submit_nl_task(
            agent_id=agent.id, instruction="List products",
            capability_hint="inventory.list_products",
        )
        assert task.input_data.get("capability_hint") == "inventory.list_products"


# ═══════════════════════════════════════════════════════════════════
# 6D — TASK LIFECYCLE
# ═══════════════════════════════════════════════════════════════════

class TestTaskLifecycle:

    @pytest.mark.asyncio
    async def test_no_action_plan_completes(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task = await service.submit_nl_task(
            agent_id=agent.id, instruction="Do something unrelated to any capability",
        )
        assert task.status == TaskStatus.COMPLETED
        assert task.output_data is not None

    @pytest.mark.asyncio
    async def test_task_status_persisted_on_planning_failure(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        with patch("app.ai.runtime.planner.get_planner") as mock_factory:
            mock_planner = MagicMock()
            mock_planner.create_plan = AsyncMock(side_effect=Exception("Planner crashed"))
            mock_factory.return_value = mock_planner
            task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        assert task.status == TaskStatus.FAILED
        assert "Planning failed" in (task.error_message or "")

    @pytest.mark.asyncio
    async def test_task_status_updated_on_execution_success(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects_with_runtime(agent)
        mock_planner = MagicMock()
        mock_planner.create_plan = AsyncMock(return_value=_make_plan_with_actions())
        set_planner(mock_planner)
        with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            from app.ai.runtime.models import AgentResponse, ActionResult
            mock_runtime.execute_request = AsyncMock(return_value=AgentResponse(
                request_id=str(uuid.uuid4()), plan_id=str(uuid.uuid4()),
                status=PlanStatus.COMPLETED, agent_id=str(agent.id),
                results=[ActionResult(
                    action_id=str(uuid.uuid4()), capability_name="inventory.list_products",
                    status=ActionStatus.COMPLETED, result={"products": []},
                )],
            ))
            mock_runtime._validate_plan = AsyncMock()
            MockRuntime.return_value = mock_runtime
            task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        assert task.status == TaskStatus.COMPLETED
        output = task.output_data or {}
        assert "results" in output
        assert len(output["results"]) > 0

    @pytest.mark.asyncio
    async def test_task_status_updated_on_execution_failure(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects_with_runtime(agent)
        mock_planner = MagicMock()
        mock_planner.create_plan = AsyncMock(return_value=_make_plan_with_actions())
        set_planner(mock_planner)
        with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            mock_runtime.execute_request = AsyncMock(return_value=_make_runtime_response(
                status=PlanStatus.FAILED, error="Capability execution failed",
            ))
            mock_runtime._validate_plan = AsyncMock()
            MockRuntime.return_value = mock_runtime
            task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        assert task.status == TaskStatus.FAILED
        assert task.error_message is not None

    @pytest.mark.asyncio
    async def test_task_execution_timestamps(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects_with_runtime(agent)
        mock_planner = MagicMock()
        mock_planner.create_plan = AsyncMock(return_value=_make_plan_with_actions())
        set_planner(mock_planner)
        with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            mock_runtime.execute_request = AsyncMock(return_value=_make_runtime_response())
            mock_runtime._validate_plan = AsyncMock()
            MockRuntime.return_value = mock_runtime
            task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        assert task.execution_started_at is not None
        assert task.execution_completed_at is not None
        assert task.execution_duration_ms is not None
        assert task.execution_duration_ms >= 0


# ═══════════════════════════════════════════════════════════════════
# 6E — PLANNING FAILURE
# ═══════════════════════════════════════════════════════════════════

class TestPlanningFailure:

    @pytest.mark.asyncio
    async def test_planner_exception_creates_failed_task(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        with patch("app.ai.runtime.planner.get_planner") as mock_factory:
            mock_planner = MagicMock()
            mock_planner.create_plan = AsyncMock(side_effect=RuntimeError("LLM timeout"))
            mock_factory.return_value = mock_planner
            task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        assert task.status == TaskStatus.FAILED
        assert "Planning failed" in (task.error_message or "")
        assert "LLM timeout" in (task.error_message or "")

    @pytest.mark.asyncio
    async def test_planning_failure_does_not_execute(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        with patch("app.ai.runtime.planner.get_planner") as mock_factory:
            mock_planner = MagicMock()
            mock_planner.create_plan = AsyncMock(side_effect=Exception("fail"))
            mock_factory.return_value = mock_planner
            with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
                mock_runtime = MagicMock()
                mock_runtime.execute_request = AsyncMock()
                mock_runtime._validate_plan = AsyncMock()
                MockRuntime.return_value = mock_runtime
                task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        # Runtime was constructed (for validate_plan) but execute_request was not called
        mock_runtime.execute_request.assert_not_called()
        assert task.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_planning_failure_does_not_store_secrets(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        with patch("app.ai.runtime.planner.get_planner") as mock_factory:
            mock_planner = MagicMock()
            mock_planner.create_plan = AsyncMock(
                side_effect=Exception("Error with api_key=sk-abc123")
            )
            mock_factory.return_value = mock_planner
            task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        assert "sk-abc123" not in (task.error_message or "")

    @pytest.mark.asyncio
    async def test_planning_failure_audit_logged(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        with patch("app.ai.runtime.planner.get_planner") as mock_factory:
            mock_planner = MagicMock()
            mock_planner.create_plan = AsyncMock(side_effect=Exception("fail"))
            mock_factory.return_value = mock_planner
            task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        add_calls = mock_db.add.call_args_list
        assert len(add_calls) >= 1


# ═══════════════════════════════════════════════════════════════════
# 6F — EXECUTION FAILURE
# ═══════════════════════════════════════════════════════════════════

class TestExecutionFailure:

    @pytest.mark.asyncio
    async def test_execution_exception_sets_task_failed(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects_with_runtime(agent)
        mock_planner = MagicMock()
        mock_planner.create_plan = AsyncMock(return_value=_make_plan_with_actions())
        set_planner(mock_planner)
        with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            mock_runtime.execute_request = AsyncMock(side_effect=Exception("Runtime crash"))
            mock_runtime._validate_plan = AsyncMock()
            MockRuntime.return_value = mock_runtime
            task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        assert task.status == TaskStatus.FAILED
        assert "Runtime execution failed" in (task.error_message or "")

    @pytest.mark.asyncio
    async def test_execution_failure_preserves_plan(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects_with_runtime(agent)
        mock_planner = MagicMock()
        mock_planner.create_plan = AsyncMock(return_value=_make_plan_with_actions())
        set_planner(mock_planner)
        with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            mock_runtime.execute_request = AsyncMock(side_effect=Exception("fail"))
            mock_runtime._validate_plan = AsyncMock()
            MockRuntime.return_value = mock_runtime
            task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        output = task.output_data or {}
        assert "plan" in output

    @pytest.mark.asyncio
    async def test_partial_failure_preserves_completed_actions(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects_with_runtime(agent)
        from app.ai.runtime.models import ActionResult
        mock_planner = MagicMock()
        mock_planner.create_plan = AsyncMock(return_value=_make_plan_with_actions())
        set_planner(mock_planner)
        with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            mock_runtime.execute_request = AsyncMock(return_value=_make_runtime_response(
                status=PlanStatus.PARTIALLY_COMPLETED,
                results=[
                    ActionResult(action_id=str(uuid.uuid4()), capability_name="inventory.list_products",
                                 status=ActionStatus.COMPLETED, result={"products": []}),
                    ActionResult(action_id=str(uuid.uuid4()), capability_name="inventory.adjust_stock",
                                 status=ActionStatus.FAILED, error="Adjustment failed"),
                ],
            ))
            mock_runtime._validate_plan = AsyncMock()
            MockRuntime.return_value = mock_runtime
            task = await service.submit_nl_task(agent_id=agent.id, instruction="List products and adjust stock")
        assert task.status == TaskStatus.FAILED
        output = task.output_data or {}
        results = output.get("results", [])
        assert len(results) == 2
        completed = [r for r in results if r["status"] == "completed"]
        failed = [r for r in results if r["status"] == "failed"]
        assert len(completed) == 1
        assert len(failed) == 1


# ═══════════════════════════════════════════════════════════════════
# 6G — APPROVAL WORKFLOW
# ═══════════════════════════════════════════════════════════════════

class TestApprovalWorkflow:

    @pytest.mark.asyncio
    async def test_approval_required_task_blocks_execution(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        async def create_plan_with_approval(**kwargs):
            return Plan(
                plan_id=str(uuid.uuid4()),
                actions=[PlanAction(
                    capability_name="inventory.adjust_stock",
                    input_data={"variant_id": str(uuid.uuid4()), "quantity_change": 10},
                    requires_approval=True,
                )],
                metadata={"planner": "llm"},
            )
        mock_planner = MagicMock()
        mock_planner.create_plan = AsyncMock(side_effect=create_plan_with_approval)
        set_planner(mock_planner)
        with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            mock_runtime.execute_request = AsyncMock()
            mock_runtime._validate_plan = AsyncMock()
            MockRuntime.return_value = mock_runtime
            task = await service.submit_nl_task(
                agent_id=agent.id, instruction="Adjust stock by 10 units",
            )
        assert task.status == TaskStatus.PENDING_APPROVAL
        assert task.requires_human_approval is True
        mock_runtime.execute_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_approval_required_action_not_executed(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        async def create_plan_approval(**kwargs):
            return Plan(
                plan_id=str(uuid.uuid4()),
                actions=[PlanAction(
                    capability_name="inventory.adjust_stock",
                    input_data={"variant_id": str(uuid.uuid4()), "quantity_change": 10},
                    requires_approval=True,
                )],
                metadata={"planner": "llm"},
            )
        mock_planner = MagicMock()
        mock_planner.create_plan = AsyncMock(side_effect=create_plan_approval)
        set_planner(mock_planner)
        with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            mock_runtime.execute_request = AsyncMock()
            mock_runtime._validate_plan = AsyncMock()
            MockRuntime.return_value = mock_runtime
            task = await service.submit_nl_task(
                agent_id=agent.id, instruction="Adjust stock",
            )
        mock_runtime.execute_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_approved_task_executes(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        task = _make_task(
            agent_id=agent.id, org_id=org_id,
            status=TaskStatus.PENDING_APPROVAL,
            requires_human_approval=True,
            input_data={"instruction": "Adjust stock"},
            metadata_={"planner_type": "llm", "instruction": "Adjust stock"},
            output_data={"plan": {"plan_id": "test", "actions": []}, "results": []},
        )
        task.approved_by = user_id
        task.approved_at = datetime.now(timezone.utc)
        # approve_task: get_task, get_agent (metrics), then _execute_task routes to runtime
        # _execute_task_via_runtime: _get_agent_by_id
        mock_db.execute.side_effect = [
            _make_result(task),   # approve_task: get_task
            _make_result(agent),  # approve_task: get agent for metrics
            _make_result(agent),  # _execute_task_via_runtime: _get_agent_by_id
        ]
        with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            mock_runtime.execute_request = AsyncMock(return_value=_make_runtime_response())
            mock_runtime._validate_plan = AsyncMock()
            MockRuntime.return_value = mock_runtime
            result = await service.approve_task(task.id, reason="Looks good")
        # After approval, task should have been executed through the runtime
        assert result.status == TaskStatus.COMPLETED
        mock_runtime.execute_request.assert_called_once()


# ═══════════════════════════════════════════════════════════════════
# 6H — RBAC / TENANT ISOLATION
# ═══════════════════════════════════════════════════════════════════

class TestRBACAndTenantIsolation:

    @pytest.mark.asyncio
    async def test_cross_org_task_access_rejected(self, mock_db, org_id, other_org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        task = _make_task(agent_id=uuid.uuid4(), org_id=other_org_id)
        mock_db.execute.return_value = _make_result(task)
        with pytest.raises(TaskNotFoundError):
            await service.get_task(task.id)

    @pytest.mark.asyncio
    async def test_cross_org_agent_access_rejected(self, mock_db, org_id, other_org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(other_org_id)
        mock_db.execute.return_value = _make_result(agent)
        with pytest.raises(AgentNotFoundError):
            await service.get_agent(agent.id)

    @pytest.mark.asyncio
    async def test_task_execution_respects_org_boundary(self, mock_db, org_id, other_org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        task = _make_task(agent_id=uuid.uuid4(), org_id=other_org_id)
        mock_db.execute.return_value = _make_result(task)
        with pytest.raises(TaskNotFoundError):
            await service.get_task(task.id)


# ═══════════════════════════════════════════════════════════════════
# 6I — TASK EXECUTION VIA RUNTIME
# ═══════════════════════════════════════════════════════════════════

class TestTaskExecutionViaRuntime:

    @pytest.mark.asyncio
    async def test_llm_task_routed_to_runtime(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        task = _make_task(
            agent_id=agent.id, org_id=org_id,
            metadata_={"planner_type": "llm", "instruction": "List products"},
            input_data={"instruction": "List products"},
        )
        mock_db.execute.side_effect = [_make_result(agent)]
        with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            mock_runtime.execute_request = AsyncMock(return_value=_make_runtime_response())
            mock_runtime._validate_plan = AsyncMock()
            MockRuntime.return_value = mock_runtime
            await service._execute_task(task)
        MockRuntime.assert_called_once()
        mock_runtime.execute_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_runtime_uses_capability_executor(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        task = _make_task(
            agent_id=agent.id, org_id=org_id,
            metadata_={"planner_type": "llm"},
            input_data={"instruction": "List products"},
        )
        mock_db.execute.side_effect = [_make_result(agent)]
        with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            from app.ai.runtime.models import ActionResult
            mock_runtime.execute_request = AsyncMock(return_value=_make_runtime_response(
                results=[ActionResult(
                    action_id=str(uuid.uuid4()), capability_name="inventory.list_products",
                    status=ActionStatus.COMPLETED, result={"products": []},
                )],
            ))
            mock_runtime._validate_plan = AsyncMock()
            MockRuntime.return_value = mock_runtime
            await service._execute_task(task)
        assert mock_runtime.execute_request.called


# ═══════════════════════════════════════════════════════════════════
# 6J — RUNTIME INTEGRATION
# ═══════════════════════════════════════════════════════════════════

class TestRuntimeIntegration:

    @pytest.mark.asyncio
    async def test_existing_runtime_endpoint_not_broken(self):
        from app.ai.schemas import RuntimeExecuteRequest
        req = RuntimeExecuteRequest(instruction="Test instruction")
        assert req.instruction == "Test instruction"

    @pytest.mark.asyncio
    async def test_existing_task_endpoint_not_broken(self):
        from app.ai.schemas import TaskSubmitRequest
        req = TaskSubmitRequest(task_type="custom", input_data={"key": "value"})
        assert req.task_type == "custom"

    @pytest.mark.asyncio
    async def test_submit_task_skip_auto_execute_default_false(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = [
            _make_result(agent), _make_count_result(0), _make_result(agent),
        ]
        with patch("app.ai.service.get_llm_client") as mock_llm:
            mock_client = MockLLMClient(response="Done")
            mock_llm.return_value = mock_client
            task = await service.submit_task(
                agent_id=agent.id, task_type=TaskType.CUSTOM,
                input_data={"prompt": "test"},
            )
        assert task.status == TaskStatus.COMPLETED


# ═══════════════════════════════════════════════════════════════════
# 6K — NATURAL LANGUAGE TASK API SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class TestNLTaskSchemas:

    def test_nl_task_request_minimal(self):
        req = NLTaskRequest(instruction="List products")
        assert req.instruction == "List products"
        assert req.capability_hint is None
        assert req.requires_human_approval is False

    def test_nl_task_request_with_hint(self):
        req = NLTaskRequest(instruction="Show low stock", capability_hint="inventory.get_low_stock")
        assert req.capability_hint == "inventory.get_low_stock"

    def test_nl_task_request_empty_instruction_fails(self):
        with pytest.raises(Exception):
            NLTaskRequest(instruction="")

    def test_nl_task_request_long_instruction_fails(self):
        with pytest.raises(Exception):
            NLTaskRequest(instruction="x" * 5001)

    def test_nl_task_response_structure(self):
        from app.ai.schemas import TaskOut
        task_out = TaskOut(
            id=str(uuid.uuid4()), agent_id=str(uuid.uuid4()),
            organization_id=str(uuid.uuid4()), task_type="custom",
            status="completed", requires_human_approval=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        resp = NLTaskResponse(task=task_out, planner_type="llm", message="Test")
        assert resp.planner_type == "llm"
        assert resp.task.status == "completed"
        assert resp.plan is None
        assert resp.action_results == []


# ═══════════════════════════════════════════════════════════════════
# 6L — BACKWARD COMPATIBILITY
# ═══════════════════════════════════════════════════════════════════

class TestBackwardCompatibility:

    @pytest.mark.asyncio
    async def test_submit_task_existing_callers_work(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = [
            _make_result(agent), _make_count_result(0), _make_result(agent),
        ]
        with patch("app.ai.service.get_llm_client") as mock_llm:
            mock_llm.return_value = MockLLMClient(response="Done")
            task = await service.submit_task(
                agent_id=agent.id, task_type=TaskType.INVENTORY_CHECK,
                input_data={"prompt": "Check stock"},
            )
        assert task.status == TaskStatus.COMPLETED
        assert task.task_type == TaskType.INVENTORY_CHECK

    @pytest.mark.asyncio
    async def test_approval_task_still_works(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = [_make_result(agent), _make_count_result(0)]
        task = await service.submit_task(
            agent_id=agent.id, task_type=TaskType.CUSTOM,
            requires_human_approval=True,
        )
        assert task.status == TaskStatus.PENDING_APPROVAL

    @pytest.mark.asyncio
    async def test_handoff_still_works(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        parent_task = _make_task(
            agent_id=uuid.uuid4(), org_id=org_id,
            status=TaskStatus.COMPLETED, handoff_depth=0,
        )
        target_agent = _make_agent(org_id, name="Social Agent", agent_type=AgentType.SOCIAL)
        mock_db.execute.side_effect = [_make_result(parent_task), _make_result(target_agent)]
        child_task = await service.handoff_task(
            parent_task_id=parent_task.id, target_agent_id=target_agent.id,
            input_data={"content": "Low stock alert"},
        )
        assert child_task.parent_task_id == parent_task.id
        assert child_task.handoff_depth == 1

    @pytest.mark.asyncio
    async def test_existing_task_list_still_works(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        tasks = await service.list_tasks()
        assert tasks == []


# ═══════════════════════════════════════════════════════════════════
# 6M — IDEMPOTENCY
# ═══════════════════════════════════════════════════════════════════

class TestIdempotency:

    @pytest.mark.asyncio
    async def test_same_instruction_creates_separate_tasks(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task1 = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task2 = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        # Both should be separate task objects
        assert task1 is not task2

    @pytest.mark.asyncio
    async def test_completed_task_not_re_executed(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        task = _make_task(agent_id=agent.id, org_id=org_id, status=TaskStatus.COMPLETED)
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.VIEWER, is_active=True,
        )
        mock_db.execute.side_effect = [
            _make_result(task),      # _get_task_by_id
            _make_result(agent),     # check_task_access → _get_agent_by_id
            _make_result(org_member),# can_access_agent → _get_org_member (VIEWER → not OWNER)
            _make_result(None),      # can_access_agent → _get_team_member (teamless agent → None)
        ]
        retrieved = await service.get_task(task.id)
        assert retrieved.status == TaskStatus.COMPLETED


# ═══════════════════════════════════════════════════════════════════
# 6N — RETRY SAFETY
# ═══════════════════════════════════════════════════════════════════

class TestRetrySafety:

    @pytest.mark.asyncio
    async def test_failed_task_state_preserved(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        task = _make_task(
            agent_id=agent.id, org_id=org_id, status=TaskStatus.FAILED,
            error_message="Original failure",
        )
        org_member = OrganizationMember(
            id=uuid.uuid4(), organization_id=org_id,
            user_id=user_id, role=MembershipRole.VIEWER, is_active=True,
        )
        mock_db.execute.side_effect = [
            _make_result(task),      # _get_task_by_id
            _make_result(agent),     # check_task_access → _get_agent_by_id
            _make_result(org_member),# can_access_agent → _get_org_member (VIEWER → not OWNER)
            _make_result(None),      # can_access_agent → _get_team_member (teamless agent → None)
        ]
        retrieved = await service.get_task(task.id)
        assert retrieved.status == TaskStatus.FAILED
        assert retrieved.error_message == "Original failure"


# ═══════════════════════════════════════════════════════════════════
# 6O — RESULT PERSISTENCE
# ═══════════════════════════════════════════════════════════════════

class TestResultPersistence:

    @pytest.mark.asyncio
    async def test_successful_result_persisted(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects_with_runtime(agent)
        from app.ai.runtime.models import ActionResult
        mock_planner = MagicMock()
        mock_planner.create_plan = AsyncMock(return_value=_make_plan_with_actions())
        set_planner(mock_planner)
        with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            mock_runtime.execute_request = AsyncMock(return_value=_make_runtime_response(
                results=[ActionResult(
                    action_id=str(uuid.uuid4()), capability_name="inventory.list_products",
                    status=ActionStatus.COMPLETED,
                    result={"products": [{"id": "1", "title": "Widget"}]},
                )],
            ))
            mock_runtime._validate_plan = AsyncMock()
            MockRuntime.return_value = mock_runtime
            task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        output = task.output_data or {}
        results = output.get("results", [])
        assert len(results) == 1
        assert results[0]["status"] == "completed"
        assert results[0]["result"]["products"][0]["title"] == "Widget"

    @pytest.mark.asyncio
    async def test_task_has_completion_status(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects_with_runtime(agent)
        mock_planner = MagicMock()
        mock_planner.create_plan = AsyncMock(return_value=_make_plan_with_actions())
        set_planner(mock_planner)
        with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            mock_runtime.execute_request = AsyncMock(return_value=_make_runtime_response())
            mock_runtime._validate_plan = AsyncMock()
            MockRuntime.return_value = mock_runtime
            task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        assert task.status == TaskStatus.COMPLETED
        assert task.execution_completed_at is not None
        assert task.execution_duration_ms is not None

    @pytest.mark.asyncio
    async def test_error_message_persisted_on_failure(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects_with_runtime(agent)
        mock_planner = MagicMock()
        mock_planner.create_plan = AsyncMock(return_value=_make_plan_with_actions())
        set_planner(mock_planner)
        with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            mock_runtime.execute_request = AsyncMock(return_value=_make_runtime_response(
                status=PlanStatus.FAILED, error="Capability 'inventory.nonexistent' not found",
            ))
            mock_runtime._validate_plan = AsyncMock()
            MockRuntime.return_value = mock_runtime
            task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        assert task.status == TaskStatus.FAILED
        assert "Capability" in (task.error_message or "")


# ═══════════════════════════════════════════════════════════════════
# 6P — OBSERVABILITY
# ═══════════════════════════════════════════════════════════════════

class TestObservability:

    @pytest.mark.asyncio
    async def test_planning_audit_logged(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        add_calls = mock_db.add.call_args_list
        assert len(add_calls) >= 1

    @pytest.mark.asyncio
    async def test_execution_duration_recorded(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id, agent_type=AgentType.INVENTORY)
        mock_db.execute.side_effect = _nl_task_side_effects_with_runtime(agent)
        mock_planner = MagicMock()
        mock_planner.create_plan = AsyncMock(return_value=_make_plan_with_actions())
        set_planner(mock_planner)
        with patch("app.ai.runtime.runtime.AgentRuntime") as MockRuntime:
            mock_runtime = MagicMock()
            mock_runtime.execute_request = AsyncMock(return_value=_make_runtime_response())
            mock_runtime._validate_plan = AsyncMock()
            MockRuntime.return_value = mock_runtime
            task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        assert task.execution_duration_ms is not None
        assert task.execution_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_no_secrets_in_audit(self, mock_db, org_id, user_id):
        service = AIService(db=mock_db, organization_id=org_id, user_id=user_id)
        agent = _make_agent(org_id)
        mock_db.execute.side_effect = _nl_task_side_effects(agent)
        with patch("app.ai.runtime.planner.get_planner") as mock_factory:
            mock_planner = MagicMock()
            mock_planner.create_plan = AsyncMock(
                side_effect=Exception("Error: api_key=sk-secret123 in config")
            )
            mock_factory.return_value = mock_planner
            task = await service.submit_nl_task(agent_id=agent.id, instruction="List products")
        assert "sk-secret123" not in (task.error_message or "")


# ═══════════════════════════════════════════════════════════════════
# REGRESSION
# ═══════════════════════════════════════════════════════════════════

class TestPhase4Regression:

    def test_constants_unchanged(self):
        from app.ai.constants import TaskStatus, TaskType, AgentType, AgentStatus
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.PENDING_APPROVAL.value == "pending_approval"

    def test_models_unchanged(self):
        from app.ai.models import AIAgent, AIAgentTask, AIAgentAction
        task = AIAgentTask()
        assert hasattr(task, "id")
        assert hasattr(task, "agent_id")
        assert hasattr(task, "organization_id")
        assert hasattr(task, "status")
        assert hasattr(task, "input_data")
        assert hasattr(task, "output_data")
        assert hasattr(task, "error_message")
        assert hasattr(task, "metadata_")
        assert hasattr(task, "capability_name")

    def test_schemas_unchanged(self):
        from app.ai.schemas import AgentCreateRequest, TaskSubmitRequest, RuntimeExecuteRequest
        req = AgentCreateRequest(name="Test")
        assert req.name == "Test"
        task_req = TaskSubmitRequest(task_type="custom")
        assert task_req.task_type == "custom"
        runtime_req = RuntimeExecuteRequest(instruction="Test")
        assert runtime_req.instruction == "Test"

    def test_new_schemas_coexist(self):
        from app.ai.schemas import NLTaskRequest, NLTaskResponse, RuntimeExecuteRequest, TaskSubmitRequest
        assert NLTaskRequest is not None
        assert NLTaskResponse is not None
        assert RuntimeExecuteRequest is not None
        assert TaskSubmitRequest is not None

    def test_runtime_models_unchanged(self):
        from app.ai.runtime.models import Plan, PlanAction, AgentRequest, AgentResponse
        plan = Plan()
        assert plan.status.value == "created"
        action = PlanAction(capability_name="test")
        assert action.status.value == "pending"
