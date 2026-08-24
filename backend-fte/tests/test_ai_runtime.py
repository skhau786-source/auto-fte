"""
Tests for AI Agent Runtime — Chunk 4 (Agent Runtime / Orchestration Layer).

Coverage:
- Plan and PlanAction models
- AgentRequest / AgentResponse / ActionResult models
- SimplePlanner
- AgentRuntime (request validation, plan creation, plan validation, execution)
- Capability Selection Boundary (CapabilityRegistry → CapabilityExecutor)
- Multi-Step Execution
- Approval Integration
- Audit Integration (via executor)
- Error Handling
- Security (bypass attempts)
"""

import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.ai.runtime.models import (
    Plan, PlanAction, AgentRequest, AgentResponse,
    ActionResult, ActionStatus, PlanStatus,
)
from app.ai.runtime.planner import (
    SimplePlanner, get_planner, set_planner, reset_planner,
)
from app.ai.runtime.runtime import (
    AgentRuntime, RuntimeValidationError, RuntimeExecutionError,
)
from app.ai.capabilities.base import capability_registry
from app.ai.constants import AgentType, AgentStatus


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def org_id():
    return uuid.uuid4()

@pytest.fixture
def user_id():
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
    from app.ai.capabilities.base import capability_registry
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
    """Force SimplePlanner for all runtime tests to avoid real LLM calls."""
    set_planner(SimplePlanner())
    yield
    reset_planner()


# ═══════════════════════════════════════════════════════════════════
# 4A — PLAN AND ACTION MODELS
# ═══════════════════════════════════════════════════════════════════

class TestPlanModels:
    """Tests for Plan, PlanAction, and related data models."""

    def test_plan_action_default_status(self):
        action = PlanAction(capability_name="test.cap")
        assert action.status == ActionStatus.PENDING

    def test_plan_action_mark_running(self):
        action = PlanAction(capability_name="test.cap")
        action.mark_running()
        assert action.status == ActionStatus.RUNNING
        assert action.executed_at is not None

    def test_plan_action_mark_completed(self):
        action = PlanAction(capability_name="test.cap")
        result = {"data": "value"}
        action.mark_completed(result)
        assert action.status == ActionStatus.COMPLETED
        assert action.result == result

    def test_plan_action_mark_failed(self):
        action = PlanAction(capability_name="test.cap")
        action.mark_failed("Something broke")
        assert action.status == ActionStatus.FAILED
        assert action.error == "Something broke"

    def test_plan_action_mark_blocked(self):
        action = PlanAction(capability_name="test.cap")
        action.mark_blocked("Unauthorized")
        assert action.status == ActionStatus.BLOCKED
        assert action.error == "Unauthorized"

    def test_plan_action_mark_pending_approval(self):
        action = PlanAction(capability_name="test.cap", requires_approval=True)
        action.mark_pending_approval()
        assert action.status == ActionStatus.PENDING_APPROVAL

    def test_plan_action_mark_rejected(self):
        action = PlanAction(capability_name="test.cap")
        action.mark_rejected("Not allowed")
        assert action.status == ActionStatus.REJECTED
        assert action.error == "Not allowed"

    def test_plan_default_status(self):
        plan = Plan()
        assert plan.status == PlanStatus.CREATED
        assert plan.action_count == 0

    def test_plan_action_count(self):
        plan = Plan(actions=[
            PlanAction(capability_name="a"),
            PlanAction(capability_name="b"),
            PlanAction(capability_name="c"),
        ])
        assert plan.action_count == 3

    def test_plan_completed_count(self):
        a1 = PlanAction(capability_name="a1")
        a1.mark_completed({})
        a2 = PlanAction(capability_name="a2")
        plan = Plan(actions=[a1, a2])
        assert plan.completed_count == 1

    def test_plan_failed_count(self):
        a1 = PlanAction(capability_name="a1")
        a1.mark_failed("err")
        a2 = PlanAction(capability_name="a2")
        a2.mark_completed({})
        plan = Plan(actions=[a1, a2])
        assert plan.failed_count == 1

    def test_plan_all_completed(self):
        a1 = PlanAction(capability_name="a1")
        a1.mark_completed({})
        a2 = PlanAction(capability_name="a2")
        a2.mark_completed({})
        plan = Plan(actions=[a1, a2])
        assert plan.all_completed is True

    def test_plan_not_all_completed(self):
        a1 = PlanAction(capability_name="a1")
        a1.mark_completed({})
        a2 = PlanAction(capability_name="a2")
        plan = Plan(actions=[a1, a2])
        assert plan.all_completed is False

    def test_plan_any_failed(self):
        a1 = PlanAction(capability_name="a1")
        a1.mark_failed("err")
        plan = Plan(actions=[a1])
        assert plan.any_failed is True

    def test_plan_any_pending_approval(self):
        a1 = PlanAction(capability_name="a1", requires_approval=True)
        a1.mark_pending_approval()
        plan = Plan(actions=[a1])
        assert plan.any_pending_approval is True

    def test_plan_has_approval_required(self):
        a1 = PlanAction(capability_name="a1", requires_approval=True)
        plan = Plan(actions=[a1])
        assert plan.has_approval_required is True


# ═══════════════════════════════════════════════════════════════════
# 4B — AGENT REQUEST / RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════

class TestAgentRequestResponse:
    """Tests for AgentRequest, AgentResponse, and ActionResult models."""

    def test_agent_request_defaults(self):
        req = AgentRequest()
        assert req.request_id
        assert req.agent_id is None
        assert req.instruction == ""
        assert req.is_approved is False

    def test_agent_request_with_data(self):
        req = AgentRequest(
            agent_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            instruction="Check inventory",
        )
        assert req.agent_id is not None
        assert req.instruction == "Check inventory"

    def test_agent_response_defaults(self):
        resp = AgentResponse()
        assert resp.status == PlanStatus.CREATED
        assert resp.results == []
        assert resp.is_success is False

    def test_agent_response_is_success(self):
        resp = AgentResponse(status=PlanStatus.COMPLETED)
        assert resp.is_success is True

    def test_agent_response_is_pending_approval(self):
        resp = AgentResponse(
            status=PlanStatus.BLOCKED,
            results=[ActionResult(status=ActionStatus.PENDING_APPROVAL)],
        )
        assert resp.is_pending_approval is True

    def test_action_result_from_plan_action(self):
        action = PlanAction(
            capability_name="test.cap",
            status=ActionStatus.COMPLETED,
            result={"data": 1},
        )
        result = ActionResult.from_plan_action(action)
        assert result.capability_name == "test.cap"
        assert result.status == ActionStatus.COMPLETED
        assert result.result == {"data": 1}


# ═══════════════════════════════════════════════════════════════════
# 4H — SIMPLE PLANNER
# ═══════════════════════════════════════════════════════════════════

class TestSimplePlanner:
    """Tests for the SimplePlanner (rule-based planner)."""

    @pytest.mark.asyncio
    async def test_planner_with_valid_capability(self):
        planner = SimplePlanner()
        plan = await planner.create_plan(
            instruction="List products",
            capability_hint="inventory.list_products",
            agent_type="inventory",
        )
        assert len(plan.actions) == 1
        assert plan.actions[0].capability_name == "inventory.list_products"

    @pytest.mark.asyncio
    async def test_planner_with_invalid_capability(self):
        planner = SimplePlanner()
        plan = await planner.create_plan(
            instruction="Do something",
            capability_hint="nonexistent.capability",
            agent_type="inventory",
        )
        assert len(plan.actions) == 0

    @pytest.mark.asyncio
    async def test_planner_with_unauthorized_agent_type(self):
        planner = SimplePlanner()
        plan = await planner.create_plan(
            instruction="Analyze orders",
            capability_hint="sales.analyze_orders",
            agent_type="inventory",  # inventory agents can't use sales capabilities
        )
        assert len(plan.actions) == 0

    @pytest.mark.asyncio
    async def test_planner_without_capability_hint(self):
        planner = SimplePlanner()
        plan = await planner.create_plan(
            instruction="General task",
            agent_type="inventory",
        )
        assert len(plan.actions) == 0

    @pytest.mark.asyncio
    async def test_planner_sets_approval_flag(self):
        planner = SimplePlanner()
        plan = await planner.create_plan(
            instruction="Adjust stock",
            capability_hint="inventory.adjust_stock",
            agent_type="inventory",
        )
        assert len(plan.actions) == 1
        assert plan.actions[0].requires_approval is True

    @pytest.mark.asyncio
    async def test_planner_sets_input_data(self):
        planner = SimplePlanner()
        plan = await planner.create_plan(
            instruction="Get product",
            capability_hint="inventory.get_product",
            input_data={"product_id": str(uuid.uuid4())},
            agent_type="inventory",
        )
        assert len(plan.actions) == 1
        assert "product_id" in plan.actions[0].input_data

    def test_get_planner_returns_simple_planner_by_default(self):
        reset_planner()
        with patch("app.ai.runtime.planner.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.is_configured = False
            mock_get.return_value = mock_client
            planner = get_planner()
        assert isinstance(planner, SimplePlanner)

    def test_set_planner_override(self):
        custom = SimplePlanner()
        set_planner(custom)
        assert get_planner() is custom
        reset_planner()


# ═══════════════════════════════════════════════════════════════════
# 4A + 4D + 4E + 4F — AGENT RUNTIME
# ═══════════════════════════════════════════════════════════════════

class TestAgentRuntime:
    """Tests for the AgentRuntime orchestrator."""

    @pytest.mark.asyncio
    async def test_execute_request_validates_agent_id(self, mock_db, org_id, user_id):
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(organization_id=org_id)  # No agent_id
        response = await runtime.execute_request(request)
        assert response.status == PlanStatus.FAILED
        assert "agent_id" in response.error.lower()

    @pytest.mark.asyncio
    async def test_execute_request_validates_org_id(self, mock_db, org_id, user_id):
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(agent_id=uuid.uuid4())  # No org_id
        response = await runtime.execute_request(request)
        assert response.status == PlanStatus.FAILED

    @pytest.mark.asyncio
    async def test_execute_request_agent_not_found(self, mock_db, org_id, user_id):
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(
            agent_id=uuid.uuid4(),
            organization_id=org_id,
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        response = await runtime.execute_request(request)
        assert response.status == PlanStatus.FAILED
        assert "not found" in response.error.lower()

    @pytest.mark.asyncio
    async def test_execute_request_agent_inactive(self, mock_db, org_id, user_id):
        from app.ai.models import AIAgent
        from app.ai.constants import AgentStatus
        from app.ai.models import AIAgent

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Inactive Agent",
            agent_type=AgentType.CUSTOM,
            status=AgentStatus.INACTIVE,
        )
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(
            agent_id=agent.id,
            organization_id=org_id,
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))
        response = await runtime.execute_request(request)
        assert response.status == PlanStatus.FAILED
        assert "inactive" in response.error.lower()

    @pytest.mark.asyncio
    async def test_execute_request_org_mismatch(self, mock_db, org_id, user_id):
        from app.ai.models import AIAgent
        other_org = uuid.uuid4()
        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=other_org,  # Different org
            name="Other Org Agent",
            agent_type=AgentType.CUSTOM,
            status=AgentStatus.ACTIVE,
        )
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(
            agent_id=agent.id,
            organization_id=org_id,
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))
        response = await runtime.execute_request(request)
        assert response.status == PlanStatus.FAILED

    @pytest.mark.asyncio
    async def test_execute_request_empty_plan(self, mock_db, org_id, user_id):
        """Request with no capability hint produces empty plan (valid)."""
        from app.ai.models import AIAgent

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Test Agent",
            agent_type=AgentType.CUSTOM,
            status=AgentStatus.ACTIVE,
        )
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(
            agent_id=agent.id,
            organization_id=org_id,
            instruction="General instruction",
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))
        response = await runtime.execute_request(request)
        assert response.status == PlanStatus.COMPLETED
        assert len(response.results) == 0

    @pytest.mark.asyncio
    async def test_execute_request_single_capability_success(self, mock_db, org_id, user_id):
        """Single capability execution through the runtime."""
        from app.ai.models import AIAgent

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Inventory Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
        )
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(
            agent_id=agent.id,
            organization_id=org_id,
            instruction="List products",
            capability_hint="inventory.list_products",
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))

        with patch("app.ai.runtime.runtime.capability_registry") as mock_registry:
            cap = MagicMock()
            cap.descriptor.supported_agent_types = ["inventory", "custom"]
            cap.descriptor.requires_approval = False
            mock_registry.get.return_value = cap

            with patch("app.ai.runtime.runtime.CapabilityExecutor") as MockExecutor:
                mock_executor = AsyncMock()
                mock_executor.execute.return_value = {
                    "status": "success",
                    "result": {"accounts": []},
                }
                MockExecutor.return_value = mock_executor

                response = await runtime.execute_request(request)

                assert response.status == PlanStatus.COMPLETED
                assert len(response.results) == 1
                assert response.results[0].status == ActionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_request_approval_required(self, mock_db, org_id, user_id):
        """Approval-required capability blocks execution."""
        from app.ai.models import AIAgent

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Inventory Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
        )
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(
            agent_id=agent.id,
            organization_id=org_id,
            instruction="Adjust stock",
            capability_hint="inventory.adjust_stock",
            input_data={"variant_id": str(uuid.uuid4()), "quantity_change": 10},
            is_approved=False,
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))

        with patch("app.ai.runtime.runtime.capability_registry") as mock_registry:
            cap = MagicMock()
            cap.descriptor.supported_agent_types = ["inventory", "custom"]
            cap.descriptor.requires_approval = True
            mock_registry.get.return_value = cap

            response = await runtime.execute_request(request)

            assert response.status == PlanStatus.BLOCKED
            assert len(response.results) == 1
            assert response.results[0].status == ActionStatus.PENDING_APPROVAL
            assert response.results[0].requires_approval is True

    @pytest.mark.asyncio
    async def test_execute_request_approved_execution(self, mock_db, org_id, user_id):
        """Approved request executes the capability."""
        from app.ai.models import AIAgent

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Inventory Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
        )
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(
            agent_id=agent.id,
            organization_id=org_id,
            instruction="Adjust stock",
            capability_hint="inventory.adjust_stock",
            input_data={"variant_id": str(uuid.uuid4()), "quantity_change": 10},
            is_approved=True,
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))

        with patch("app.ai.runtime.runtime.capability_registry") as mock_registry:
            cap = MagicMock()
            cap.descriptor.supported_agent_types = ["inventory", "custom"]
            cap.descriptor.requires_approval = True
            mock_registry.get.return_value = cap

            with patch("app.ai.runtime.runtime.CapabilityExecutor") as MockExecutor:
                mock_executor = AsyncMock()
                mock_executor.execute.return_value = {
                    "status": "success",
                    "result": {"adjusted": True},
                }
                MockExecutor.return_value = mock_executor

                response = await runtime.execute_request(request)

                assert response.status == PlanStatus.COMPLETED
                assert len(response.results) == 1
                assert response.results[0].status == ActionStatus.COMPLETED
                # Verify executor was called
                mock_executor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_request_capability_failure(self, mock_db, org_id, user_id):
        """Capability execution failure is captured."""
        from app.ai.models import AIAgent

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Inventory Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
        )
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(
            agent_id=agent.id,
            organization_id=org_id,
            instruction="List products",
            capability_hint="inventory.list_products",
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))

        with patch("app.ai.runtime.runtime.capability_registry") as mock_registry:
            cap = MagicMock()
            cap.descriptor.supported_agent_types = ["inventory", "custom"]
            cap.descriptor.requires_approval = False
            mock_registry.get.return_value = cap

            with patch("app.ai.runtime.runtime.CapabilityExecutor") as MockExecutor:
                mock_executor = AsyncMock()
                mock_executor.execute.return_value = {
                    "status": "error",
                    "error": "Database connection failed",
                }
                MockExecutor.return_value = mock_executor

                response = await runtime.execute_request(request)

                assert response.status == PlanStatus.FAILED
                assert len(response.results) == 1
                assert response.results[0].status == ActionStatus.FAILED

    @pytest.mark.asyncio
    async def test_execute_request_capability_not_in_registry(self, mock_db, org_id, user_id):
        """Capability not found in registry produces empty plan (planner handles it)."""
        from app.ai.models import AIAgent

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Agent",
            agent_type=AgentType.CUSTOM,
            status=AgentStatus.ACTIVE,
        )
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(
            agent_id=agent.id,
            organization_id=org_id,
            instruction="Do something",
            capability_hint="fake.capability",
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))

        # The planner checks the real registry and returns empty plan for unknown caps
        response = await runtime.execute_request(request)

        # Empty plan is valid — planner gracefully handles missing capabilities
        assert response.status == PlanStatus.COMPLETED
        assert len(response.results) == 0

    @pytest.mark.asyncio
    async def test_execute_request_agent_type_unauthorized(self, mock_db, org_id, user_id):
        """Agent type not authorized for capability — planner returns empty plan."""
        from app.ai.models import AIAgent

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Social Agent",
            agent_type=AgentType.SOCIAL,
            status=AgentStatus.ACTIVE,
        )
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(
            agent_id=agent.id,
            organization_id=org_id,
            instruction="Analyze orders",
            capability_hint="sales.analyze_orders",
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))

        # The planner checks agent type authorization and returns empty plan
        response = await runtime.execute_request(request)

        # Empty plan is valid — planner gracefully handles unauthorized access
        assert response.status == PlanStatus.COMPLETED
        assert len(response.results) == 0


# ═══════════════════════════════════════════════════════════════════
# 4E — MULTI-STEP EXECUTION
# ═══════════════════════════════════════════════════════════════════

class TestMultiStepExecution:
    """Tests for multi-action plan execution."""

    @pytest.mark.asyncio
    async def test_multi_step_plan_execution(self, mock_db, org_id, user_id):
        """Multiple actions execute sequentially."""
        from app.ai.models import AIAgent
        from app.ai.runtime.planner import BasePlanner

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
        )

        # Create a custom planner that returns a multi-action plan
        class MultiActionPlanner(BasePlanner):
            async def create_plan(self, instruction, capability_hint=None,
                                  input_data=None, agent_type=None):
                return Plan(actions=[
                    PlanAction(
                        capability_name="social.list_accounts",
                        input_data={},
                        requires_approval=False,
                    ),
                    PlanAction(
                        capability_name="sales.analyze_orders",
                        input_data={},
                        requires_approval=False,
                    ),
                ])

        set_planner(MultiActionPlanner())
        try:
            runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
            request = AgentRequest(
                agent_id=agent.id,
                organization_id=org_id,
                instruction="Multi-step task",
            )
            mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))

            with patch("app.ai.runtime.runtime.capability_registry") as mock_registry:
                def get_cap(name):
                    cap = MagicMock()
                    cap.descriptor.supported_agent_types = ["inventory", "social", "sales", "custom"]
                    cap.descriptor.requires_approval = False
                    return cap
                mock_registry.get.side_effect = get_cap

                with patch("app.ai.runtime.runtime.CapabilityExecutor") as MockExecutor:
                    mock_executor = AsyncMock()
                    mock_executor.execute.return_value = {
                        "status": "success",
                        "result": {"ok": True},
                    }
                    MockExecutor.return_value = mock_executor

                    response = await runtime.execute_request(request)

                    assert response.status == PlanStatus.COMPLETED
                    assert len(response.results) == 2
                    assert all(r.status == ActionStatus.COMPLETED for r in response.results)
                    # Executor called twice (once per action)
                    assert mock_executor.execute.call_count == 2
        finally:
            reset_planner()

    @pytest.mark.asyncio
    async def test_multi_step_partial_failure(self, mock_db, org_id, user_id):
        """Second action failure doesn't prevent first from completing."""
        from app.ai.models import AIAgent
        from app.ai.runtime.planner import BasePlanner

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
        )

        class TwoStepPlanner(BasePlanner):
            async def create_plan(self, instruction, capability_hint=None,
                                  input_data=None, agent_type=None):
                return Plan(actions=[
                    PlanAction(capability_name="social.list_accounts", input_data={}),
                    PlanAction(capability_name="social.list_accounts", input_data={}),
                ])

        set_planner(TwoStepPlanner())
        try:
            runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
            request = AgentRequest(
                agent_id=agent.id,
                organization_id=org_id,
                instruction="Two step",
            )
            mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))

            with patch("app.ai.runtime.runtime.capability_registry") as mock_registry:
                cap = MagicMock()
                cap.descriptor.supported_agent_types = ["inventory", "social", "custom"]
                cap.descriptor.requires_approval = False
                mock_registry.get.return_value = cap

                with patch("app.ai.runtime.runtime.CapabilityExecutor") as MockExecutor:
                    mock_executor = AsyncMock()
                    # First succeeds, second fails
                    mock_executor.execute.side_effect = [
                        {"status": "success", "result": {}},
                        {"status": "error", "error": "DB error"},
                    ]
                    MockExecutor.return_value = mock_executor

                    response = await runtime.execute_request(request)

                    assert response.status == PlanStatus.PARTIALLY_COMPLETED
                    assert len(response.results) == 2
                    assert response.results[0].status == ActionStatus.COMPLETED
                    assert response.results[1].status == ActionStatus.FAILED
        finally:
            reset_planner()

    @pytest.mark.asyncio
    async def test_multi_step_mixed_approval(self, mock_db, org_id, user_id):
        """Actions with mixed approval requirements handled correctly."""
        from app.ai.models import AIAgent
        from app.ai.runtime.planner import BasePlanner

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
        )

        class MixedPlanner(BasePlanner):
            async def create_plan(self, instruction, capability_hint=None,
                                  input_data=None, agent_type=None):
                return Plan(actions=[
                    PlanAction(capability_name="social.list_accounts", requires_approval=False),
                    PlanAction(capability_name="inventory.adjust_stock", requires_approval=True),
                ])

        set_planner(MixedPlanner())
        try:
            runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
            request = AgentRequest(
                agent_id=agent.id,
                organization_id=org_id,
                instruction="Mixed",
                is_approved=False,
            )
            mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))

            with patch("app.ai.runtime.runtime.capability_registry") as mock_registry:
                def get_cap(name):
                    cap = MagicMock()
                    cap.descriptor.supported_agent_types = ["inventory", "social", "custom"]
                    cap.descriptor.requires_approval = (name == "inventory.adjust_stock")
                    return cap
                mock_registry.get.side_effect = get_cap

                with patch("app.ai.runtime.runtime.CapabilityExecutor") as MockExecutor:
                    mock_executor = AsyncMock()
                    mock_executor.execute.return_value = {
                        "status": "success",
                        "result": {},
                    }
                    MockExecutor.return_value = mock_executor

                    response = await runtime.execute_request(request)

                    # First action completes, second is blocked (approval required)
                    assert response.status == PlanStatus.BLOCKED
                    assert response.results[0].status == ActionStatus.COMPLETED
                    assert response.results[1].status == ActionStatus.PENDING_APPROVAL
        finally:
            reset_planner()


# ═══════════════════════════════════════════════════════════════════
# 4L — SECURITY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestRuntimeSecurity:
    """Tests for security requirements — bypass attempts."""

    @pytest.mark.asyncio
    async def test_cannot_bypass_registry(self, mock_db, org_id, user_id):
        """Runtime cannot execute capabilities not in the registry.

        The planner returns an empty plan for unknown capabilities,
        so the runtime never attempts to execute them.
        """
        from app.ai.models import AIAgent

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Agent",
            agent_type=AgentType.CUSTOM,
            status=AgentStatus.ACTIVE,
        )
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(
            agent_id=agent.id,
            organization_id=org_id,
            instruction="Hack",
            capability_hint="os.system",  # Attempt to bypass
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))

        response = await runtime.execute_request(request)

        # Planner returns empty plan for unknown capabilities — no execution occurs
        assert response.status == PlanStatus.COMPLETED
        assert len(response.results) == 0
        # Verify no capability was executed
        assert not any(r.status == ActionStatus.COMPLETED for r in response.results)

    @pytest.mark.asyncio
    async def test_cannot_bypass_executor(self, mock_db, org_id, user_id):
        """Runtime always uses CapabilityExecutor — never calls capability directly."""
        from app.ai.models import AIAgent

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
        )
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(
            agent_id=agent.id,
            organization_id=org_id,
            instruction="Execute",
            capability_hint="inventory.list_products",
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))

        with patch("app.ai.runtime.runtime.capability_registry") as mock_registry:
            cap = MagicMock()
            cap.descriptor.supported_agent_types = ["inventory", "custom"]
            cap.descriptor.requires_approval = False
            mock_registry.get.return_value = cap

            with patch("app.ai.runtime.runtime.CapabilityExecutor") as MockExecutor:
                mock_executor = AsyncMock()
                mock_executor.execute.return_value = {"status": "success", "result": {}}
                MockExecutor.return_value = mock_executor

                response = await runtime.execute_request(request)

                # Verify CapabilityExecutor was used
                MockExecutor.assert_called_once()
                mock_executor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_approval_cannot_be_bypassed(self, mock_db, org_id, user_id):
        """Approval-required capabilities cannot be executed without approval."""
        from app.ai.models import AIAgent

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Agent",
            agent_type=AgentType.INVENTORY,
            status=AgentStatus.ACTIVE,
        )
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(
            agent_id=agent.id,
            organization_id=org_id,
            instruction="Delete everything",
            capability_hint="inventory.adjust_stock",
            input_data={"variant_id": str(uuid.uuid4()), "quantity_change": -1000},
            is_approved=False,
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))

        with patch("app.ai.runtime.runtime.capability_registry") as mock_registry:
            cap = MagicMock()
            cap.descriptor.supported_agent_types = ["inventory", "custom"]
            cap.descriptor.requires_approval = True
            mock_registry.get.return_value = cap

            response = await runtime.execute_request(request)

            # Must NOT be completed — approval required
            assert response.status != PlanStatus.COMPLETED
            assert response.results[0].status == ActionStatus.PENDING_APPROVAL

    @pytest.mark.asyncio
    async def test_org_isolation_enforced(self, mock_db, org_id, user_id):
        """Cross-organization access is blocked."""
        from app.ai.models import AIAgent

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),  # Different org
            name="Other Agent",
            agent_type=AgentType.CUSTOM,
            status=AgentStatus.ACTIVE,
        )
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(
            agent_id=agent.id,
            organization_id=org_id,
            instruction="Hack",
        )
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent))

        response = await runtime.execute_request(request)

        assert response.status == PlanStatus.FAILED


# ═══════════════════════════════════════════════════════════════════
# 4J — ERROR HANDLING
# ═══════════════════════════════════════════════════════════════════

class TestRuntimeErrorHandling:
    """Tests for structured error handling."""

    def test_validation_error_has_error_code(self):
        exc = RuntimeValidationError("test error")
        assert "error_code" in exc.detail

    def test_execution_error_has_error_code(self):
        exc = RuntimeExecutionError("test error")
        assert "error_code" in exc.detail

    def test_agent_error_hierarchy(self):
        assert issubclass(RuntimeValidationError, Exception)
        assert issubclass(RuntimeExecutionError, Exception)

    @pytest.mark.asyncio
    async def test_unexpected_error_captured(self, mock_db, org_id, user_id):
        """Unexpected errors are captured, not raised."""
        from app.ai.models import AIAgent

        agent = AIAgent(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Agent",
            agent_type=AgentType.CUSTOM,
            status=AgentStatus.ACTIVE,
        )
        runtime = AgentRuntime(db=mock_db, organization_id=org_id, user_id=user_id)
        request = AgentRequest(
            agent_id=agent.id,
            organization_id=org_id,
            instruction="Test",
            capability_hint="social.list_accounts",
        )

        # Make DB execute raise an unexpected error after the agent lookup
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=agent))
            raise RuntimeError("Unexpected DB error")

        mock_db.execute.side_effect = side_effect

        response = await runtime.execute_request(request)
        # Should not raise — error is captured in response
        assert response.status in (PlanStatus.FAILED, PlanStatus.COMPLETED)
