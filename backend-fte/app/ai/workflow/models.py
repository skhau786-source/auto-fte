"""
Workflow data models — structured representations for workflow definitions,
steps, conditions, and execution results.

These are IN-MEMORY dataclasses (not ORM models). Workflow definitions are
persisted inside AIAgentTask.output_data JSONB, so no database migration is needed.

Security:
- Conditions use a constrained operator set (no eval/exec)
- Step input_data is validated before execution
- All actions must go through CapabilityExecutor
"""

import uuid
import operator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ═══════════════════════════════════════════════════════════════════
# STATUS ENUMS
# ═══════════════════════════════════════════════════════════════════

class WorkflowStatus(str, Enum):
    """Lifecycle status of a workflow execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"       # Blocked on approval
    PARTIALLY_COMPLETED = "partially_completed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """Lifecycle status of a single workflow step."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING_APPROVAL = "pending_approval"


# ═══════════════════════════════════════════════════════════════════
# CONDITION — safe, constrained condition evaluation
# ═══════════════════════════════════════════════════════════════════

# Allowed comparison operators — NO eval/exec, NO arbitrary code
_SAFE_OPERATORS = {
    "eq": operator.eq,
    "ne": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}


@dataclass
class WorkflowCondition:
    """
    A constrained condition that can be evaluated against workflow context.

    Conditions inspect structured results from previous steps.
    They use a fixed set of safe operators — no arbitrary code execution.

    Example:
        WorkflowCondition(
            field="step_1.result.stock",
            operator="lt",
            value=10,
        )
        Evaluates to True if step 1's result.stock < 10

    Security:
    - Only a fixed set of operators is allowed
    - No eval(), exec(), or importlib usage
    - Field paths are dot-separated keys into nested dicts
    - Values must be JSON-serializable primitives
    """
    field: str = ""
    operator: str = "eq"       # eq, ne, gt, gte, lt, lte
    value: Any = None          # JSON-serializable comparison value

    def evaluate(self, context: dict[str, Any]) -> bool:
        """
        Evaluate this condition against the current workflow context.

        The context contains previous step results keyed by step_id.
        Field paths use dot notation to access nested values:
            "step_1.result.stock" → context["step_1"]["result"]["stock"]

        Returns:
            True if the condition is met, False otherwise.

        Raises:
            ValueError: If the operator is unknown or field path is invalid.
        """
        if self.operator not in _SAFE_OPERATORS:
            raise ValueError(
                f"Unknown operator '{self.operator}'. "
                f"Allowed: {', '.join(_SAFE_OPERATORS.keys())}"
            )

        # Resolve field value from context using dot notation
        actual_value = _resolve_field(self.field, context)

        # Compare
        op_func = _SAFE_OPERATORS[self.operator]
        return op_func(actual_value, self.value)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "field": self.field,
            "operator": self.operator,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowCondition":
        """Deserialize from a dict (e.g., from JSONB)."""
        return cls(
            field=data.get("field", ""),
            operator=data.get("operator", "eq"),
            value=data.get("value"),
        )


def _resolve_field(field_path: str, context: dict[str, Any]) -> Any:
    """
    Resolve a dot-separated field path against a nested dict.

    Example: _resolve_field("step_1.result.stock", ctx)
             returns ctx["step_1"]["result"]["stock"]

    Raises:
        KeyError: If any segment of the path is missing.
        TypeError: If an intermediate value is not a dict.
    """
    if not field_path:
        raise ValueError("Empty field path")

    parts = field_path.split(".")
    current = context

    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(f"Field path '{field_path}' not found: '{part}' missing")
            current = current[part]
        else:
            raise TypeError(
                f"Cannot traverse '{part}' in field path '{field_path}': "
                f"intermediate value is {type(current).__name__}, not dict"
            )

    return current


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW STEP
# ═══════════════════════════════════════════════════════════════════

@dataclass
class WorkflowStep:
    """
    A single step within a workflow.

    Each step maps to exactly one capability invocation. The workflow
    engine validates that the capability exists before execution.

    Fields:
        step_id: Unique identifier for this step within the workflow.
        capability_name: Must be a registered capability (validated by engine).
        input_data: Input payload passed to the capability.
        condition: Optional condition — if not met, step is skipped.
        description: Human-readable step description.
    """
    step_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    capability_name: str = ""
    input_data: dict[str, Any] = field(default_factory=dict)
    condition: Optional[WorkflowCondition] = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        result = {
            "step_id": self.step_id,
            "capability_name": self.capability_name,
            "input_data": self.input_data,
            "description": self.description,
        }
        if self.condition is not None:
            result["condition"] = self.condition.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowStep":
        """Deserialize from a dict."""
        condition = None
        if "condition" in data and data["condition"] is not None:
            condition = WorkflowCondition.from_dict(data["condition"])

        return cls(
            step_id=data.get("step_id", str(uuid.uuid4())[:8]),
            capability_name=data.get("capability_name", ""),
            input_data=data.get("input_data", {}),
            condition=condition,
            description=data.get("description", ""),
        )


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW DEFINITION
# ═══════════════════════════════════════════════════════════════════

@dataclass
class WorkflowDefinition:
    """
    A complete workflow definition.

    Contains the workflow metadata and ordered list of steps.
    The engine executes steps sequentially, evaluating conditions
    and routing through CapabilityExecutor.

    Fields:
        workflow_id: Unique workflow identifier.
        name: Human-readable workflow name.
        description: What this workflow does.
        steps: Ordered list of workflow steps.
        trigger: What triggers this workflow (e.g., "manual", "api", "schedule").
        metadata: Additional metadata (not used for execution logic).
    """
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    trigger: str = "manual"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def validate(self) -> list[str]:
        """
        Validate the workflow definition.

        Returns a list of validation error messages.
        An empty list means the workflow is valid.
        """
        errors = []

        if not self.name:
            errors.append("Workflow name is required")

        if not self.steps:
            errors.append("Workflow must have at least one step")

        step_ids = set()
        for i, step in enumerate(self.steps):
            if not step.capability_name:
                errors.append(f"Step {i}: capability_name is required")

            if step.step_id in step_ids:
                errors.append(f"Step {i}: duplicate step_id '{step.step_id}'")
            step_ids.add(step.step_id)

            if step.condition:
                if step.condition.operator not in _SAFE_OPERATORS:
                    errors.append(
                        f"Step {i}: unknown operator '{step.condition.operator}'"
                    )

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict for persistence."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "trigger": self.trigger,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowDefinition":
        """Deserialize from a dict (e.g., from task output_data JSONB)."""
        steps = [WorkflowStep.from_dict(s) for s in data.get("steps", [])]
        created_at_str = data.get("created_at")
        created_at = (
            datetime.fromisoformat(created_at_str)
            if created_at_str
            else datetime.now(timezone.utc)
        )

        return cls(
            workflow_id=data.get("workflow_id", str(uuid.uuid4())),
            name=data.get("name", ""),
            description=data.get("description", ""),
            steps=steps,
            trigger=data.get("trigger", "manual"),
            metadata=data.get("metadata", {}),
            created_at=created_at,
        )


# ═══════════════════════════════════════════════════════════════════
# WORKFLOW EXECUTION RESULTS
# ═══════════════════════════════════════════════════════════════════

@dataclass
class WorkflowStepResult:
    """
    Result of executing a single workflow step.
    """
    step_id: str = ""
    capability_name: str = ""
    status: StepStatus = StepStatus.PENDING
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    requires_approval: bool = False
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "step_id": self.step_id,
            "capability_name": self.capability_name,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "requires_approval": self.requires_approval,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
        }


@dataclass
class WorkflowResult:
    """
    Complete result of a workflow execution.

    Contains overall status plus per-step results. This is what gets
    persisted in AIAgentTask.output_data.
    """
    workflow_id: str = ""
    status: WorkflowStatus = WorkflowStatus.PENDING
    step_results: list[WorkflowStepResult] = field(default_factory=list)
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.step_results if s.status == StepStatus.COMPLETED)

    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.step_results if s.status == StepStatus.FAILED)

    @property
    def skipped_count(self) -> int:
        return sum(1 for s in self.step_results if s.status == StepStatus.SKIPPED)

    @property
    def pending_approval_count(self) -> int:
        return sum(1 for s in self.step_results if s.status == StepStatus.PENDING_APPROVAL)

    def get_step_result(self, step_id: str) -> Optional[WorkflowStepResult]:
        """Get the result for a specific step by ID."""
        for sr in self.step_results:
            if sr.step_id == step_id:
                return sr
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict for persistence."""
        return {
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "step_results": [sr.to_dict() for sr in self.step_results],
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_ms": self.duration_ms,
        }
