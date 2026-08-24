"""
AI Agent Workflow Engine — multi-step business workflow orchestration.

Provides reusable, auditable workflow execution built on top of the
existing agent/capability/task infrastructure.

Architecture:

    Workflow Request / Trigger
              ↓
    WorkflowDefinition
              ↓
    WorkflowEngine.execute()
              ↓
    Step 1 → CapabilityRegistry → CapabilityExecutor → Result
              ↓
    Condition Evaluation (safe, constrained)
              ↓
    Step 2 → CapabilityRegistry → CapabilityExecutor → Result
              ↓
    ...
              ↓
    Workflow Result (persistent, auditable)

Every executable action MUST pass through:
    CapabilityRegistry → CapabilityExecutor → RBAC → Approval → Capability

CRITICAL SECURITY:
- No eval() / exec()
- No arbitrary Python execution
- No capability registry bypass
- No RBAC bypass
- No approval bypass
- All workflow input is untrusted
"""

from app.ai.workflow.models import (
    WorkflowStatus,
    StepStatus,
    WorkflowCondition,
    WorkflowStep,
    WorkflowDefinition,
    WorkflowStepResult,
    WorkflowResult,
)
from app.ai.workflow.engine import WorkflowEngine

__all__ = [
    "WorkflowStatus",
    "StepStatus",
    "WorkflowCondition",
    "WorkflowStep",
    "WorkflowDefinition",
    "WorkflowStepResult",
    "WorkflowResult",
    "WorkflowEngine",
]
