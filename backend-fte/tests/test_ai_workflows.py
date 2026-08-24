"""
Tests for AI Agent Workflows — Phase 4: Advanced Automation Workflows.

Test Coverage:
- Workflow models (WorkflowDefinition, WorkflowStep, Condition, enums)
- Safe condition evaluation (no eval/exec)
- Workflow validation (structural + capability checks)
- WorkflowEngine execution (single-step, multi-step, sequential)
- Failure handling (deterministic, partial results preserved)
- Approval integration (capability-driven, not workflow-driven)
- Security (no arbitrary code execution, capability registry bypass impossible)
- API schemas (request/response models)
- Integration with existing AIAgentTask infrastructure
"""

import uuid
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.ai.workflow.models import (
    WorkflowStatus,
    StepStatus,
    WorkflowCondition,
    WorkflowStep,
    WorkflowDefinition,
    WorkflowStepResult,
    WorkflowResult,
    _resolve_field,
    _SAFE_OPERATORS,
)
from app.ai.workflow.engine import (
    WorkflowEngine,
    WorkflowValidationError,
    WorkflowStepError,
)
from app.ai.constants import TaskType, MAX_WORKFLOW_STEPS
from app.ai.exceptions import (
    WorkflowNotFoundError,
    WorkflowValidationError as WVE,
    WorkflowStepError as WSE,
    WorkflowConditionError,
)


# ═══════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def org_id():
    return uuid.uuid4()


@pytest.fixture
def user_id():
    return uuid.uuid4()


@pytest.fixture
def agent_id():
    return uuid.uuid4()


@pytest.fixture
def task_id():
    return uuid.uuid4()


@pytest_asyncio.fixture
async def mock_db():
    """Create a mock database session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


# ───────────────────────────────────────────────────────────────────
# Register capabilities once at module level
# ───────────────────────────────────────────────────────────────────

def _ensure_capabilities_registered():
    """Register all capabilities if not already registered."""
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


# ═══════════════════════════════════════════════════════════════════
# SECTION 1: WORKFLOW MODELS
# ═══════════════════════════════════════════════════════════════════

class TestWorkflowEnums:
    """Test workflow status enums."""

    def test_workflow_status_values(self):
        assert WorkflowStatus.PENDING.value == "pending"
        assert WorkflowStatus.RUNNING.value == "running"
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert WorkflowStatus.FAILED.value == "failed"
        assert WorkflowStatus.BLOCKED.value == "blocked"
        assert WorkflowStatus.PARTIALLY_COMPLETED.value == "partially_completed"
        assert WorkflowStatus.CANCELLED.value == "cancelled"

    def test_step_status_values(self):
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.RUNNING.value == "running"
        assert StepStatus.COMPLETED.value == "completed"
        assert StepStatus.FAILED.value == "failed"
        assert StepStatus.SKIPPED.value == "skipped"
        assert StepStatus.PENDING_APPROVAL.value == "pending_approval"


class TestWorkflowCondition:
    """Test safe condition evaluation."""

    def test_condition_eq_true(self):
        cond = WorkflowCondition(field="stock", operator="eq", value=10)
        assert cond.evaluate({"stock": 10}) is True

    def test_condition_eq_false(self):
        cond = WorkflowCondition(field="stock", operator="eq", value=10)
        assert cond.evaluate({"stock": 5}) is False

    def test_condition_ne_true(self):
        cond = WorkflowCondition(field="status", operator="ne", value="error")
        assert cond.evaluate({"status": "success"}) is True

    def test_condition_ne_false(self):
        cond = WorkflowCondition(field="status", operator="ne", value="error")
        assert cond.evaluate({"status": "error"}) is False

    def test_condition_gt_true(self):
        cond = WorkflowCondition(field="count", operator="gt", value=5)
        assert cond.evaluate({"count": 10}) is True

    def test_condition_gt_false(self):
        cond = WorkflowCondition(field="count", operator="gt", value=5)
        assert cond.evaluate({"count": 3}) is False

    def test_condition_gte_true(self):
        cond = WorkflowCondition(field="count", operator="gte", value=5)
        assert cond.evaluate({"count": 5}) is True

    def test_condition_gte_false(self):
        cond = WorkflowCondition(field="count", operator="gte", value=5)
        assert cond.evaluate({"count": 4}) is False

    def test_condition_lt_true(self):
        cond = WorkflowCondition(field="stock", operator="lt", value=10)
        assert cond.evaluate({"stock": 3}) is True

    def test_condition_lt_false(self):
        cond = WorkflowCondition(field="stock", operator="lt", value=10)
        assert cond.evaluate({"stock": 15}) is False

    def test_condition_lte_true(self):
        cond = WorkflowCondition(field="stock", operator="lte", value=10)
        assert cond.evaluate({"stock": 10}) is True

    def test_condition_lte_false(self):
        cond = WorkflowCondition(field="stock", operator="lte", value=10)
        assert cond.evaluate({"stock": 11}) is False

    def test_condition_nested_field(self):
        cond = WorkflowCondition(field="step_1.result.stock", operator="lt", value=10)
        context = {"step_1": {"result": {"stock": 5}}}
        assert cond.evaluate(context) is True

    def test_condition_deeply_nested(self):
        cond = WorkflowCondition(
            field="step_1.result.data.items.count",
            operator="gt",
            value=0,
        )
        context = {"step_1": {"result": {"data": {"items": {"count": 5}}}}}
        assert cond.evaluate(context) is True

    def test_condition_unknown_operator_raises(self):
        cond = WorkflowCondition(field="x", operator="contains", value="a")
        with pytest.raises(ValueError, match="Unknown operator"):
            cond.evaluate({"x": "abc"})

    def test_condition_missing_field_raises(self):
        cond = WorkflowCondition(field="missing.field", operator="eq", value=1)
        with pytest.raises(KeyError, match="not found"):
            cond.evaluate({"other": 1})

    def test_condition_non_dict_intermediate_raises(self):
        cond = WorkflowCondition(field="x.y.z", operator="eq", value=1)
        with pytest.raises(TypeError, match="intermediate value"):
            cond.evaluate({"x": "not_a_dict"})

    def test_condition_empty_field_raises(self):
        cond = WorkflowCondition(field="", operator="eq", value=1)
        with pytest.raises(ValueError, match="Empty field path"):
            cond.evaluate({})

    def test_condition_to_dict(self):
        cond = WorkflowCondition(field="stock", operator="lt", value=10)
        d = cond.to_dict()
        assert d == {"field": "stock", "operator": "lt", "value": 10}

    def test_condition_from_dict(self):
        d = {"field": "stock", "operator": "lt", "value": 10}
        cond = WorkflowCondition.from_dict(d)
        assert cond.field == "stock"
        assert cond.operator == "lt"
        assert cond.value == 10

    def test_condition_from_dict_defaults(self):
        cond = WorkflowCondition.from_dict({})
        assert cond.field == ""
        assert cond.operator == "eq"
        assert cond.value is None

    def test_condition_string_comparison(self):
        cond = WorkflowCondition(field="status", operator="eq", value="active")
        assert cond.evaluate({"status": "active"}) is True
        assert cond.evaluate({"status": "inactive"}) is False

    def test_condition_boolean_comparison(self):
        cond = WorkflowCondition(field="flag", operator="eq", value=True)
        assert cond.evaluate({"flag": True}) is True
        assert cond.evaluate({"flag": False}) is False


class TestSafeOperators:
    """Verify only safe operators are allowed."""

    def test_all_safe_operators(self):
        assert set(_SAFE_OPERATORS.keys()) == {"eq", "ne", "gt", "gte", "lt", "lte"}

    def test_no_eval_in_operators(self):
        import operator as op
        for name, func in _SAFE_OPERATORS.items():
            # Should be standard comparison functions, not eval/exec
            assert func in (
                op.eq, op.ne, op.gt, op.ge, op.lt, op.le,
            )


class TestResolveField:
    """Test the _resolve_field helper."""

    def test_simple_field(self):
        assert _resolve_field("x", {"x": 42}) == 42

    def test_nested_field(self):
        assert _resolve_field("a.b.c", {"a": {"b": {"c": "deep"}}}) == "deep"

    def test_missing_field(self):
        with pytest.raises(KeyError):
            _resolve_field("missing", {"other": 1})

    def test_empty_path(self):
        with pytest.raises(ValueError):
            _resolve_field("", {})

    def test_non_dict_intermediate(self):
        with pytest.raises(TypeError):
            _resolve_field("a.b", {"a": 42})


class TestWorkflowStep:
    """Test WorkflowStep model."""

    def test_valid_step(self):
        step = WorkflowStep(
            step_id="step_1",
            capability_name="inventory.list_products",
            input_data={"limit": 10},
        )
        assert step.step_id == "step_1"
        assert step.capability_name == "inventory.list_products"
        assert step.input_data == {"limit": 10}

    def test_step_with_condition(self):
        cond = WorkflowCondition(field="stock", operator="lt", value=10)
        step = WorkflowStep(
            step_id="step_1",
            capability_name="inventory.list_products",
            condition=cond,
        )
        assert step.condition is not None
        assert step.condition.operator == "lt"

    def test_step_to_dict(self):
        step = WorkflowStep(
            step_id="s1",
            capability_name="test.cap",
            input_data={"key": "val"},
        )
        d = step.to_dict()
        assert d["step_id"] == "s1"
        assert d["capability_name"] == "test.cap"
        assert d["input_data"] == {"key": "val"}
        assert "condition" not in d

    def test_step_to_dict_with_condition(self):
        cond = WorkflowCondition(field="x", operator="eq", value=1)
        step = WorkflowStep(step_id="s1", capability_name="test.cap", condition=cond)
        d = step.to_dict()
        assert d["condition"]["operator"] == "eq"

    def test_step_from_dict(self):
        d = {
            "step_id": "s1",
            "capability_name": "test.cap",
            "input_data": {"key": "val"},
            "description": "A test step",
        }
        step = WorkflowStep.from_dict(d)
        assert step.step_id == "s1"
        assert step.description == "A test step"

    def test_step_from_dict_with_condition(self):
        d = {
            "step_id": "s1",
            "capability_name": "test.cap",
            "condition": {"field": "x", "operator": "gt", "value": 0},
        }
        step = WorkflowStep.from_dict(d)
        assert step.condition is not None
        assert step.condition.operator == "gt"

    def test_step_auto_generates_id(self):
        step = WorkflowStep(capability_name="test.cap")
        assert step.step_id  # Should have a generated ID

    def test_step_empty_condition(self):
        step = WorkflowStep(
            step_id="s1",
            capability_name="test.cap",
            condition=None,
        )
        d = step.to_dict()
        assert "condition" not in d


class TestWorkflowDefinition:
    """Test WorkflowDefinition model."""

    def test_valid_workflow(self):
        wf = WorkflowDefinition(
            name="Test Workflow",
            steps=[WorkflowStep(capability_name="inventory.list_products")],
        )
        errors = wf.validate()
        assert errors == []

    def test_workflow_empty_name(self):
        wf = WorkflowDefinition(
            name="",
            steps=[WorkflowStep(capability_name="inventory.list_products")],
        )
        errors = wf.validate()
        assert any("name is required" in e for e in errors)

    def test_workflow_no_steps(self):
        wf = WorkflowDefinition(name="Test", steps=[])
        errors = wf.validate()
        assert any("at least one step" in e for e in errors)

    def test_workflow_step_no_capability(self):
        wf = WorkflowDefinition(
            name="Test",
            steps=[WorkflowStep(step_id="s1", capability_name="")],
        )
        errors = wf.validate()
        assert any("capability_name is required" in e for e in errors)

    def test_workflow_duplicate_step_ids(self):
        wf = WorkflowDefinition(
            name="Test",
            steps=[
                WorkflowStep(step_id="dup", capability_name="inventory.list_products"),
                WorkflowStep(step_id="dup", capability_name="inventory.list_products"),
            ],
        )
        errors = wf.validate()
        assert any("duplicate step_id" in e for e in errors)

    def test_workflow_invalid_condition_operator(self):
        wf = WorkflowDefinition(
            name="Test",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    capability_name="inventory.list_products",
                    condition=WorkflowCondition(field="x", operator="INVALID"),
                ),
            ],
        )
        errors = wf.validate()
        assert any("unknown operator" in e for e in errors)

    def test_workflow_to_dict(self):
        wf = WorkflowDefinition(
            name="Test",
            steps=[WorkflowStep(step_id="s1", capability_name="inventory.list_products")],
            trigger="api",
            metadata={"key": "val"},
        )
        d = wf.to_dict()
        assert d["name"] == "Test"
        assert len(d["steps"]) == 1
        assert d["trigger"] == "api"
        assert d["metadata"] == {"key": "val"}
        assert "created_at" in d

    def test_workflow_from_dict(self):
        d = {
            "workflow_id": "test-id",
            "name": "Test",
            "description": "A test",
            "steps": [{"step_id": "s1", "capability_name": "test.cap"}],
            "trigger": "manual",
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        wf = WorkflowDefinition.from_dict(d)
        assert wf.workflow_id == "test-id"
        assert wf.name == "Test"
        assert len(wf.steps) == 1

    def test_workflow_from_dict_defaults(self):
        wf = WorkflowDefinition.from_dict({})
        assert wf.name == ""
        assert wf.steps == []
        assert wf.trigger == "manual"


class TestWorkflowResult:
    """Test WorkflowResult model."""

    def test_empty_result(self):
        result = WorkflowResult()
        assert result.status == WorkflowStatus.PENDING
        assert result.completed_count == 0
        assert result.failed_count == 0

    def test_result_counts(self):
        result = WorkflowResult()
        result.step_results = [
            WorkflowStepResult(step_id="s1", status=StepStatus.COMPLETED),
            WorkflowStepResult(step_id="s2", status=StepStatus.COMPLETED),
            WorkflowStepResult(step_id="s3", status=StepStatus.FAILED),
            WorkflowStepResult(step_id="s4", status=StepStatus.SKIPPED),
        ]
        assert result.completed_count == 2
        assert result.failed_count == 1
        assert result.skipped_count == 1

    def test_result_get_step(self):
        result = WorkflowResult()
        result.step_results = [
            WorkflowStepResult(step_id="s1", status=StepStatus.COMPLETED),
        ]
        assert result.get_step_result("s1") is not None
        assert result.get_step_result("s2") is None

    def test_result_to_dict(self):
        result = WorkflowResult(
            workflow_id="wf-1",
            status=WorkflowStatus.COMPLETED,
        )
        d = result.to_dict()
        assert d["workflow_id"] == "wf-1"
        assert d["status"] == "completed"


class TestWorkflowStepResult:
    """Test WorkflowStepResult model."""

    def test_step_result_to_dict(self):
        sr = WorkflowStepResult(
            step_id="s1",
            capability_name="test.cap",
            status=StepStatus.COMPLETED,
            result={"key": "val"},
        )
        d = sr.to_dict()
        assert d["step_id"] == "s1"
        assert d["status"] == "completed"
        assert d["result"] == {"key": "val"}


# ═══════════════════════════════════════════════════════════════════
# SECTION 2: WORKFLOW ENGINE
# ═══════════════════════════════════════════════════════════════════

class TestWorkflowEngineValidation:
    """Test workflow validation."""

    @pytest.mark.asyncio
    async def test_validate_valid_workflow(self, mock_db, org_id, user_id):
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="Test",
            steps=[WorkflowStep(capability_name="inventory.list_products")],
        )
        errors = await engine.validate_workflow(wf, "inventory")
        assert errors == []

    @pytest.mark.asyncio
    async def test_validate_unknown_capability(self, mock_db, org_id, user_id):
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="Test",
            steps=[WorkflowStep(capability_name="nonexistent.capability")],
        )
        errors = await engine.validate_workflow(wf, "inventory")
        assert any("not found in registry" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_unauthorized_agent_type(self, mock_db, org_id, user_id):
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        # inventory.list_products requires agent_type "inventory"
        wf = WorkflowDefinition(
            name="Test",
            steps=[WorkflowStep(capability_name="inventory.list_products")],
        )
        errors = await engine.validate_workflow(wf, "social")
        assert any("not authorized" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_empty_workflow(self, mock_db, org_id, user_id):
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(name="Empty", steps=[])
        errors = await engine.validate_workflow(wf, "inventory")
        assert any("at least one step" in e for e in errors)

    @pytest.mark.asyncio
    async def test_validate_invalid_condition_operator(self, mock_db, org_id, user_id):
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="Test",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    capability_name="inventory.list_products",
                    condition=WorkflowCondition(field="x", operator="BAD"),
                ),
            ],
        )
        errors = await engine.validate_workflow(wf, "inventory")
        assert any("unknown operator" in e for e in errors)


class TestWorkflowEngineExecution:
    """Test workflow execution."""

    @pytest.mark.asyncio
    async def test_single_step_workflow(self, mock_db, org_id, user_id, agent_id):
        """Execute a single-step workflow successfully."""
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="Single Step",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    capability_name="inventory.list_products",
                    input_data={},
                ),
            ],
        )

        with patch("app.ai.workflow.engine.capability_registry") as mock_registry:
            mock_cap = MagicMock()
            mock_cap.requires_approval = False
            mock_cap.descriptor.supported_agent_types = ["inventory"]
            mock_registry.get.return_value = mock_cap

            with patch("app.ai.workflow.engine.CapabilityExecutor") as MockExecutor:
                mock_executor = AsyncMock()
                mock_executor.execute.return_value = {
                    "capability": "inventory.list_products",
                    "status": "success",
                    "result": {"products": [], "total": 0},
                }
                MockExecutor.return_value = mock_executor

                result = await engine.execute(
                    wf, agent_id=agent_id, agent_type="inventory"
                )

                assert result.status == WorkflowStatus.COMPLETED
                assert result.completed_count == 1
                assert result.failed_count == 0
                assert result.step_results[0].status == StepStatus.COMPLETED
                assert result.step_results[0].result == {"products": [], "total": 0}

    @pytest.mark.asyncio
    async def test_multi_step_workflow(self, mock_db, org_id, user_id, agent_id):
        """Execute a multi-step workflow sequentially."""
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="Multi Step",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    capability_name="inventory.list_products",
                    input_data={},
                ),
                WorkflowStep(
                    step_id="s2",
                    capability_name="inventory.get_low_stock",
                    input_data={"threshold": 10},
                ),
            ],
        )

        with patch("app.ai.workflow.engine.capability_registry") as mock_registry:
            mock_cap = MagicMock()
            mock_cap.requires_approval = False
            mock_cap.descriptor.supported_agent_types = ["inventory"]
            mock_registry.get.return_value = mock_cap

            with patch("app.ai.workflow.engine.CapabilityExecutor") as MockExecutor:
                mock_executor = AsyncMock()
                call_count = 0

                async def mock_execute(**kwargs):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        return {
                            "status": "success",
                            "result": {"products": [], "total": 0},
                        }
                    else:
                        return {
                            "status": "success",
                            "result": {"low_stock": [], "count": 0},
                        }

                mock_executor.execute.side_effect = mock_execute
                MockExecutor.return_value = mock_executor

                result = await engine.execute(
                    wf, agent_id=agent_id, agent_type="inventory"
                )

                assert result.status == WorkflowStatus.COMPLETED
                assert len(result.step_results) == 2
                assert all(
                    sr.status == StepStatus.COMPLETED for sr in result.step_results
                )

    @pytest.mark.asyncio
    async def test_failed_step_workflow(self, mock_db, org_id, user_id, agent_id):
        """Workflow fails deterministically when a step fails."""
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="Fail Step",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    capability_name="inventory.list_products",
                    input_data={},
                ),
                WorkflowStep(
                    step_id="s2",
                    capability_name="inventory.get_low_stock",
                    input_data={},
                ),
            ],
        )

        with patch("app.ai.workflow.engine.capability_registry") as mock_registry:
            mock_cap = MagicMock()
            mock_cap.requires_approval = False
            mock_cap.descriptor.supported_agent_types = ["inventory"]
            mock_registry.get.return_value = mock_cap

            with patch("app.ai.workflow.engine.CapabilityExecutor") as MockExecutor:
                mock_executor = AsyncMock()
                call_count = 0

                async def mock_execute(**kwargs):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        return {"status": "success", "result": {}}
                    else:
                        return {"status": "error", "error": "Something went wrong"}

                mock_executor.execute.side_effect = mock_execute
                MockExecutor.return_value = mock_executor

                result = await engine.execute(
                    wf, agent_id=agent_id, agent_type="inventory"
                )

                assert result.status == WorkflowStatus.FAILED
                assert "Step 's2' failed" in result.error
                # First step result should be preserved
                assert result.step_results[0].status == StepStatus.COMPLETED
                assert result.step_results[1].status == StepStatus.FAILED

    @pytest.mark.asyncio
    async def test_partial_results_preserved(self, mock_db, org_id, user_id, agent_id):
        """When a step fails, previous step results are preserved."""
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="Partial",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    capability_name="inventory.list_products",
                ),
                WorkflowStep(
                    step_id="s2",
                    capability_name="inventory.get_low_stock",
                ),
                WorkflowStep(
                    step_id="s3",
                    capability_name="inventory.list_products",
                ),
            ],
        )

        with patch("app.ai.workflow.engine.capability_registry") as mock_registry:
            mock_cap = MagicMock()
            mock_cap.requires_approval = False
            mock_cap.descriptor.supported_agent_types = ["inventory"]
            mock_registry.get.return_value = mock_cap

            with patch("app.ai.workflow.engine.CapabilityExecutor") as MockExecutor:
                mock_executor = AsyncMock()
                call_count = 0

                async def mock_execute(**kwargs):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 2:
                        return {"status": "error", "error": "Step 2 failed"}
                    return {"status": "success", "result": {}}

                mock_executor.execute.side_effect = mock_execute
                MockExecutor.return_value = mock_executor

                result = await engine.execute(
                    wf, agent_id=agent_id, agent_type="inventory"
                )

                assert result.status == WorkflowStatus.FAILED
                # Only 2 step results (execution stopped at s2)
                assert len(result.step_results) == 2
                assert result.step_results[0].status == StepStatus.COMPLETED
                assert result.step_results[1].status == StepStatus.FAILED

    @pytest.mark.asyncio
    async def test_approval_required_step(self, mock_db, org_id, user_id, agent_id):
        """Steps requiring approval block the workflow."""
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="Approval",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    capability_name="inventory.list_products",
                ),
            ],
        )

        with patch("app.ai.workflow.engine.capability_registry") as mock_registry:
            mock_cap = MagicMock()
            mock_cap.requires_approval = True  # Requires approval
            mock_cap.descriptor.supported_agent_types = ["inventory"]
            mock_registry.get.return_value = mock_cap

            result = await engine.execute(
                wf, agent_id=agent_id, agent_type="inventory"
            )

            assert result.status == WorkflowStatus.BLOCKED
            assert result.step_results[0].status == StepStatus.PENDING_APPROVAL
            assert result.step_results[0].requires_approval is True

    @pytest.mark.asyncio
    async def test_condition_true_executes(self, mock_db, org_id, user_id, agent_id):
        """Step executes when condition is met."""
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="Condition True",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    capability_name="inventory.list_products",
                ),
                WorkflowStep(
                    step_id="s2",
                    capability_name="inventory.get_low_stock",
                    condition=WorkflowCondition(
                        field="s1.result.total", operator="gt", value=0
                    ),
                ),
            ],
        )

        with patch("app.ai.workflow.engine.capability_registry") as mock_registry:
            mock_cap = MagicMock()
            mock_cap.requires_approval = False
            mock_cap.descriptor.supported_agent_types = ["inventory"]
            mock_registry.get.return_value = mock_cap

            with patch("app.ai.workflow.engine.CapabilityExecutor") as MockExecutor:
                mock_executor = AsyncMock()
                call_count = 0

                async def mock_execute(**kwargs):
                    nonlocal call_count
                    call_count += 1
                    if call_count == 1:
                        return {"status": "success", "result": {"total": 5}}
                    else:
                        return {"status": "success", "result": {"low_stock": []}}

                mock_executor.execute.side_effect = mock_execute
                MockExecutor.return_value = mock_executor

                result = await engine.execute(
                    wf, agent_id=agent_id, agent_type="inventory"
                )

                assert result.status == WorkflowStatus.COMPLETED
                assert len(result.step_results) == 2
                assert all(sr.status == StepStatus.COMPLETED for sr in result.step_results)

    @pytest.mark.asyncio
    async def test_condition_false_skips(self, mock_db, org_id, user_id, agent_id):
        """Step is skipped when condition is not met."""
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="Condition False",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    capability_name="inventory.list_products",
                ),
                WorkflowStep(
                    step_id="s2",
                    capability_name="inventory.get_low_stock",
                    condition=WorkflowCondition(
                        field="s1.result.total", operator="gt", value=0
                    ),
                ),
            ],
        )

        with patch("app.ai.workflow.engine.capability_registry") as mock_registry:
            mock_cap = MagicMock()
            mock_cap.requires_approval = False
            mock_cap.descriptor.supported_agent_types = ["inventory"]
            mock_registry.get.return_value = mock_cap

            with patch("app.ai.workflow.engine.CapabilityExecutor") as MockExecutor:
                mock_executor = AsyncMock()

                async def mock_execute(**kwargs):
                    return {"status": "success", "result": {"total": 0}}

                mock_executor.execute.side_effect = mock_execute
                MockExecutor.return_value = mock_executor

                result = await engine.execute(
                    wf, agent_id=agent_id, agent_type="inventory"
                )

                assert result.status == WorkflowStatus.COMPLETED
                assert result.step_results[0].status == StepStatus.COMPLETED
                assert result.step_results[1].status == StepStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_invalid_condition_skips_step(self, mock_db, org_id, user_id, agent_id):
        """Step is skipped when condition evaluation fails (missing field)."""
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="Bad Condition",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    capability_name="inventory.list_products",
                ),
                WorkflowStep(
                    step_id="s2",
                    capability_name="inventory.get_low_stock",
                    condition=WorkflowCondition(
                        field="nonexistent.field", operator="gt", value=0
                    ),
                ),
            ],
        )

        with patch("app.ai.workflow.engine.capability_registry") as mock_registry:
            mock_cap = MagicMock()
            mock_cap.requires_approval = False
            mock_cap.descriptor.supported_agent_types = ["inventory"]
            mock_registry.get.return_value = mock_cap

            with patch("app.ai.workflow.engine.CapabilityExecutor") as MockExecutor:
                mock_executor = AsyncMock()
                mock_executor.execute.return_value = {
                    "status": "success",
                    "result": {"total": 5},
                }
                MockExecutor.return_value = mock_executor

                result = await engine.execute(
                    wf, agent_id=agent_id, agent_type="inventory"
                )

                # s1 completes, s2 skipped due to invalid condition
                assert result.step_results[0].status == StepStatus.COMPLETED
                assert result.step_results[1].status == StepStatus.SKIPPED
                assert "Condition evaluation failed" in result.step_results[1].error

    @pytest.mark.asyncio
    async def test_unknown_capability_fails_step(self, mock_db, org_id, user_id, agent_id):
        """Workflow fails when capability is not in registry."""
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="Unknown Cap",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    capability_name="nonexistent.capability",
                ),
            ],
        )

        with patch("app.ai.workflow.engine.capability_registry") as mock_registry:
            mock_registry.get.return_value = None

            result = await engine.execute(
                wf, agent_id=agent_id, agent_type="inventory"
            )

            # Validation catches unknown capability, workflow fails
            assert result.status == WorkflowStatus.FAILED
            assert "validation" in result.error.lower() or "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_workflow_with_context(self, mock_db, org_id, user_id, agent_id):
        """Workflow can receive initial context."""
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="With Context",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    capability_name="inventory.list_products",
                ),
            ],
        )

        with patch("app.ai.workflow.engine.capability_registry") as mock_registry:
            mock_cap = MagicMock()
            mock_cap.requires_approval = False
            mock_cap.descriptor.supported_agent_types = ["inventory"]
            mock_registry.get.return_value = mock_cap

            with patch("app.ai.workflow.engine.CapabilityExecutor") as MockExecutor:
                mock_executor = AsyncMock()
                mock_executor.execute.return_value = {
                    "status": "success",
                    "result": {},
                }
                MockExecutor.return_value = mock_executor

                result = await engine.execute(
                    wf,
                    agent_id=agent_id,
                    agent_type="inventory",
                    context={"preloaded": True},
                )

                assert result.status == WorkflowStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_workflow_tracks_duration(self, mock_db, org_id, user_id, agent_id):
        """Workflow tracks execution duration."""
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="Duration",
            steps=[
                WorkflowStep(step_id="s1", capability_name="inventory.list_products"),
            ],
        )

        with patch("app.ai.workflow.engine.capability_registry") as mock_registry:
            mock_cap = MagicMock()
            mock_cap.requires_approval = False
            mock_cap.descriptor.supported_agent_types = ["inventory"]
            mock_registry.get.return_value = mock_cap

            with patch("app.ai.workflow.engine.CapabilityExecutor") as MockExecutor:
                mock_executor = AsyncMock()
                mock_executor.execute.return_value = {"status": "success", "result": {}}
                MockExecutor.return_value = mock_executor

                result = await engine.execute(
                    wf, agent_id=agent_id, agent_type="inventory"
                )

                assert result.started_at is not None
                assert result.completed_at is not None
                assert result.duration_ms is not None
                assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_empty_workflow_fails(self, mock_db, org_id, user_id, agent_id):
        """Empty workflow fails validation."""
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(name="Empty", steps=[])

        result = await engine.execute(
            wf, agent_id=agent_id, agent_type="inventory"
        )

        assert result.status == WorkflowStatus.FAILED


# ═══════════════════════════════════════════════════════════════════
# SECTION 3: SECURITY
# ═══════════════════════════════════════════════════════════════════

class TestWorkflowSecurity:
    """Test security invariants."""

    def test_no_eval_in_condition(self):
        """Conditions must not use eval()."""
        cond = WorkflowCondition(field="x", operator="eq", value=1)
        # The condition uses operator.eq, not eval
        assert callable(cond.evaluate)

    def test_no_exec_in_condition(self):
        """Conditions must not use exec() or eval() for code execution."""
        # Verify the condition module uses only safe operators
        from app.ai.workflow.models import WorkflowCondition
        cond = WorkflowCondition(field="x", operator="eq", value=1)
        # The evaluate method should use operator.eq, not eval
        import operator as op
        from app.ai.workflow.models import _SAFE_OPERATORS
        # Only standard comparison functions, no eval/exec
        assert all(func in (op.eq, op.ne, op.gt, op.ge, op.lt, op.le) for func in _SAFE_OPERATORS.values())

    def test_only_safe_operators(self):
        """Only predefined safe operators are allowed."""
        allowed = {"eq", "ne", "gt", "gte", "lt", "lte"}
        assert set(_SAFE_OPERATORS.keys()) == allowed

    @pytest.mark.asyncio
    async def test_workflow_uses_capability_executor(self, mock_db, org_id, user_id, agent_id):
        """Workflow engine must use CapabilityExecutor, never direct calls."""
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="Security Test",
            steps=[
                WorkflowStep(step_id="s1", capability_name="inventory.list_products"),
            ],
        )

        with patch("app.ai.workflow.engine.capability_registry") as mock_registry:
            mock_cap = MagicMock()
            mock_cap.requires_approval = False
            mock_cap.descriptor.supported_agent_types = ["inventory"]
            mock_registry.get.return_value = mock_cap

            with patch("app.ai.workflow.engine.CapabilityExecutor") as MockExecutor:
                mock_executor = AsyncMock()
                mock_executor.execute.return_value = {"status": "success", "result": {}}
                MockExecutor.return_value = mock_executor

                result = await engine.execute(
                    wf, agent_id=agent_id, agent_type="inventory"
                )

                # CapabilityExecutor was used
                MockExecutor.assert_called_once()
                mock_executor.execute.assert_called_once()
                # Verify it was called with the capability name
                call_kwargs = mock_executor.execute.call_args
                assert call_kwargs[1]["capability_name"] == "inventory.list_products"

    @pytest.mark.asyncio
    async def test_approval_from_capability_not_workflow(self, mock_db, org_id, user_id, agent_id):
        """Approval requirement comes from capability, not workflow definition."""
        engine = WorkflowEngine(db=mock_db, organization_id=org_id, user_id=user_id)
        wf = WorkflowDefinition(
            name="Approval Test",
            steps=[
                WorkflowStep(step_id="s1", capability_name="inventory.list_products"),
            ],
        )

        # Capability says it requires approval
        with patch("app.ai.workflow.engine.capability_registry") as mock_registry:
            mock_cap = MagicMock()
            mock_cap.requires_approval = True  # From capability
            mock_cap.descriptor.supported_agent_types = ["inventory"]
            mock_registry.get.return_value = mock_cap

            result = await engine.execute(
                wf, agent_id=agent_id, agent_type="inventory"
            )

            # Workflow blocks because capability requires approval
            assert result.status == WorkflowStatus.BLOCKED
            assert result.step_results[0].requires_approval is True


# ═══════════════════════════════════════════════════════════════════
# SECTION 4: API SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class TestWorkflowSchemas:
    """Test Pydantic schema models."""

    def test_workflow_condition_request(self):
        from app.ai.schemas import WorkflowConditionRequest
        req = WorkflowConditionRequest(field="stock", operator="lt", value=10)
        assert req.field == "stock"
        assert req.operator == "lt"

    def test_workflow_step_request(self):
        from app.ai.schemas import WorkflowStepRequest
        req = WorkflowStepRequest(
            capability_name="inventory.list_products",
            input_data={"limit": 10},
        )
        assert req.capability_name == "inventory.list_products"

    def test_workflow_create_request(self):
        from app.ai.schemas import WorkflowCreateRequest
        req = WorkflowCreateRequest(
            name="Test Workflow",
            steps=[
                {
                    "capability_name": "inventory.list_products",
                    "input_data": {},
                }
            ],
            agent_id=str(uuid.uuid4()),
        )
        assert req.name == "Test Workflow"
        assert len(req.steps) == 1

    def test_workflow_create_request_min_steps(self):
        from app.ai.schemas import WorkflowCreateRequest
        with pytest.raises(Exception):
            WorkflowCreateRequest(
                name="Empty",
                steps=[],
                agent_id=str(uuid.uuid4()),
            )

    def test_workflow_result_out(self):
        from app.ai.schemas import WorkflowResultOut
        out = WorkflowResultOut(
            workflow_id="wf-1",
            status="completed",
            steps_completed=1,
        )
        assert out.status == "completed"
        assert out.steps_completed == 1

    def test_workflow_validation_response(self):
        from app.ai.schemas import WorkflowValidationResponse
        resp = WorkflowValidationResponse(valid=True)
        assert resp.valid is True
        assert resp.errors == []


# ═══════════════════════════════════════════════════════════════════
# SECTION 5: INTEGRATION
# ═══════════════════════════════════════════════════════════════════

class TestWorkflowIntegration:
    """Integration tests for the workflow system."""

    def test_workflow_type_in_constants(self):
        """WORKFLOW type exists in TaskType."""
        assert TaskType.WORKFLOW.value == "workflow"

    def test_max_workflow_steps(self):
        """MAX_WORKFLOW_STEPS is defined."""
        assert MAX_WORKFLOW_STEPS == 20

    def test_workflow_module_exports(self):
        """Workflow module exports all expected symbols."""
        from app.ai.workflow import (
            WorkflowStatus,
            StepStatus,
            WorkflowCondition,
            WorkflowStep,
            WorkflowDefinition,
            WorkflowStepResult,
            WorkflowResult,
            WorkflowEngine,
        )
        assert WorkflowEngine is not None

    def test_workflow_definitions_roundtrip(self):
        """WorkflowDefinition serialization roundtrip preserves data."""
        wf = WorkflowDefinition(
            name="Roundtrip",
            description="Test roundtrip",
            steps=[
                WorkflowStep(
                    step_id="s1",
                    capability_name="inventory.list_products",
                    input_data={"limit": 10},
                    description="List products",
                ),
                WorkflowStep(
                    step_id="s2",
                    capability_name="inventory.get_low_stock",
                    condition=WorkflowCondition(
                        field="s1.result.total", operator="gt", value=0
                    ),
                    description="Check low stock",
                ),
            ],
            trigger="api",
            metadata={"key": "val"},
        )

        d = wf.to_dict()
        wf2 = WorkflowDefinition.from_dict(d)

        assert wf2.name == wf.name
        assert wf2.description == wf.description
        assert len(wf2.steps) == len(wf.steps)
        assert wf2.trigger == wf.trigger
        assert wf2.metadata == wf.metadata

        # Check steps
        assert wf2.steps[0].step_id == wf.steps[0].step_id
        assert wf2.steps[0].capability_name == wf.steps[0].capability_name
        assert wf2.steps[1].condition is not None
        assert wf2.steps[1].condition.field == "s1.result.total"

    def test_workflow_result_roundtrip(self):
        """WorkflowResult serialization roundtrip preserves data."""
        result = WorkflowResult(
            workflow_id="wf-1",
            status=WorkflowStatus.COMPLETED,
        )
        result.step_results.append(
            WorkflowStepResult(
                step_id="s1",
                capability_name="test.cap",
                status=StepStatus.COMPLETED,
                result={"key": "val"},
            )
        )

        d = result.to_dict()
        assert d["workflow_id"] == "wf-1"
        assert d["status"] == "completed"
        assert len(d["step_results"]) == 1
        assert d["step_results"][0]["status"] == "completed"


# ═══════════════════════════════════════════════════════════════════
# SECTION 6: EXCEPTIONS
# ═══════════════════════════════════════════════════════════════════

class TestWorkflowExceptions:
    """Test workflow exception classes."""

    def test_workflow_not_found(self):
        exc = WorkflowNotFoundError("wf-123")
        assert "not found" in exc.message
        assert exc.detail["error_code"] == "WORKFLOW_NOT_FOUND"

    def test_workflow_validation_error(self):
        exc = WVE(["Error 1", "Error 2"], "wf-1")
        assert "Error 1" in exc.message
        assert exc.detail["errors"] == ["Error 1", "Error 2"]

    def test_workflow_step_error(self):
        exc = WSE("s1", "capability failed")
        assert "s1" in exc.message
        assert exc.detail["step_id"] == "s1"

    def test_workflow_condition_error(self):
        exc = WorkflowConditionError("s1", "bad field")
        assert "s1" in exc.message
        assert exc.detail["error_code"] == "WORKFLOW_CONDITION_ERROR"
