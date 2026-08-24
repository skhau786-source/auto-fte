"""
Agent Planner / Decision Provider — abstraction layer for agent planning.

The planner takes a user request and produces an execution Plan
containing one or more validated PlanActions.

This abstraction is intentionally LLM-independent. A planner can be:
- A rule-based planner (SimplePlanner) for deterministic flows
- An LLM-powered planner for natural language → plan conversion
- A hybrid planner that combines rules with LLM decisions

The runtime does not care which implementation is used — it only
requires a BasePlanner that produces valid Plans.
"""

import abc
import logging
import uuid
from typing import Any, Optional

from app.ai.runtime.models import Plan, PlanAction
from app.ai.capabilities.base import capability_registry
from app.ai.llm_client import get_llm_client

logger = logging.getLogger(__name__)


class BasePlanner(abc.ABC):
    """
    Abstract base class for agent planners.

    Every planner must accept an AgentRequest and produce a Plan
    with validated actions.
    """

    @abc.abstractmethod
    async def create_plan(
        self,
        instruction: str,
        capability_hint: Optional[str] = None,
        input_data: Optional[dict[str, Any]] = None,
        agent_type: Optional[str] = None,
    ) -> Plan:
        """
        Create an execution plan from a user instruction.

        Args:
            instruction: The user's natural language instruction.
            capability_hint: Optional capability name if the user specified one.
            input_data: Optional structured input data.
            agent_type: The agent type for capability authorization.

        Returns:
            A Plan containing one or more PlanActions.
        """
        ...


class SimplePlanner(BasePlanner):
    """
    Simple rule-based planner for deterministic capability selection.

    When a capability_hint is provided, creates a single-action plan
    for that capability. Otherwise, returns an empty plan (the runtime
    can fall back to LLM-based planning).
    """

    @property
    def planner_type(self) -> str:
        return "rule_based"

    async def create_plan(
        self,
        instruction: str,
        capability_hint: Optional[str] = None,
        input_data: Optional[dict[str, Any]] = None,
        agent_type: Optional[str] = None,
    ) -> Plan:
        plan = Plan()

        if capability_hint:
            # Validate the capability exists
            cap = capability_registry.get(capability_hint)
            if cap is None:
                logger.warning(
                    "Planner: capability '%s' not found in registry", capability_hint
                )
                return plan

            # Check agent type authorization
            desc = cap.descriptor
            if (
                desc.supported_agent_types
                and agent_type
                and agent_type not in desc.supported_agent_types
            ):
                logger.warning(
                    "Planner: agent type '%s' not authorized for '%s'",
                    agent_type, capability_hint,
                )
                return plan

            action = PlanAction(
                capability_name=capability_hint,
                input_data=input_data or {},
                requires_approval=desc.requires_approval,
                metadata={"source": "simple_planner", "instruction": instruction},
            )
            plan.actions.append(action)

        return plan


# ═══════════════════════════════════════════════════════════════════
# Planner singleton
# ═══════════════════════════════════════════════════════════════════

_planner_instance: Optional[BasePlanner] = None


def get_planner() -> BasePlanner:
    """
    Get the configured planner.

    Selection priority:
    1. Explicitly set planner (via set_planner)
    2. LLMPlanner if LLM client is configured
    3. SimplePlanner (deterministic fallback)
    """
    global _planner_instance
    if _planner_instance is not None:
        return _planner_instance

    # Auto-select: try LLMPlanner first, fall back to SimplePlanner
    try:
        from app.ai.runtime.llm_planner import LLMPlanner
        client = get_llm_client()
        if client.is_configured:
            _planner_instance = LLMPlanner()
            logger.info("Planner auto-selected: LLMPlanner (provider=%s)", client.provider_name)
            return _planner_instance
    except Exception:
        pass

    _planner_instance = SimplePlanner()
    logger.info("Planner auto-selected: SimplePlanner (no LLM configured)")
    return _planner_instance


def set_planner(planner: BasePlanner) -> None:
    """Override the planner (for testing or custom implementations)."""
    global _planner_instance
    _planner_instance = planner


def reset_planner() -> None:
    """Reset to default (auto-selection on next get)."""
    global _planner_instance
    _planner_instance = None
