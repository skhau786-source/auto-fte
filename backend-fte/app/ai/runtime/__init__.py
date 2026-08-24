"""
AI Agent Runtime — orchestration layer for agent execution.

Provides the structured pipeline:

    User Request
         ↓
    Agent Runtime
         ↓
    Planner / Decision Provider
         ↓
    Execution Plan (validated)
         ↓
    CapabilityRegistry
         ↓
    CapabilityExecutor
         ↓
    RBAC + Approval Gate
         ↓
    Execution Results
         ↓
    Audit + Events
         ↓
    Agent Response

This module does NOT bypass CapabilityExecutor.
All capability execution goes through the registry → executor path.
"""

from app.ai.runtime.models import (
    Plan,
    PlanAction,
    AgentRequest,
    AgentResponse,
    ActionResult,
    ActionStatus,
)
from app.ai.runtime.planner import (
    BasePlanner,
    SimplePlanner,
    get_planner,
    set_planner,
    reset_planner,
)
from app.ai.runtime.llm_planner import LLMPlanner
from app.ai.runtime.runtime import AgentRuntime

__all__ = [
    "Plan",
    "PlanAction",
    "AgentRequest",
    "AgentResponse",
    "ActionResult",
    "ActionStatus",
    "BasePlanner",
    "SimplePlanner",
    "LLMPlanner",
    "get_planner",
    "set_planner",
    "reset_planner",
    "AgentRuntime",
]
