"""
AI Agent Capability Base Classes and Registry.

Defines the contract that all capabilities must follow, and provides
a central registry for capability discovery and authorization checks.
"""

import abc
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CapabilityType(str, Enum):
    """Whether a capability reads or writes data."""
    READ = "read"
    WRITE = "write"


class CapabilityCategory(str, Enum):
    """Business domain categories."""
    INVENTORY = "inventory"
    SOCIAL = "social"
    SALES = "sales"
    ANALYTICS = "analytics"
    CUSTOM = "custom"


@dataclass
class CapabilityDescriptor:
    """
    Declarative metadata for a capability.

    Every capability must provide this descriptor so the system can:
    - enforce RBAC
    - enforce human approval gates
    - display capabilities in the UI
    - audit capability usage
    """
    name: str
    display_name: str
    description: str
    capability_type: CapabilityType
    category: CapabilityCategory
    requires_approval: bool = False
    supported_agent_types: list[str] = field(default_factory=list)


class BaseCapability(abc.ABC):
    """
    Abstract base class for all agent capabilities.

    Every capability must implement:
    - descriptor: returns metadata
    - execute: runs the capability with given input
    """

    @property
    @abc.abstractmethod
    def descriptor(self) -> CapabilityDescriptor:
        """Return the capability's metadata."""
        ...

    @abc.abstractmethod
    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute the capability.

        Args:
            input_data: The structured input for this capability.
            context: Execution context containing:
                - organization_id: UUID
                - agent_id: UUID
                - task_id: UUID
                - user_id: UUID (if human-initiated)
                - db: AsyncSession

        Returns:
            Structured output dictionary.
        """
        ...

    @property
    def name(self) -> str:
        return self.descriptor.name

    @property
    def requires_approval(self) -> bool:
        return self.descriptor.requires_approval

    @property
    def capability_type(self) -> CapabilityType:
        return self.descriptor.capability_type


class CapabilityRegistry:
    """
    Central registry for all agent capabilities.

    Capabilities are registered at startup and looked up by name
    during task execution.
    """

    def __init__(self):
        self._capabilities: dict[str, BaseCapability] = {}

    def register(self, capability: BaseCapability) -> None:
        """Register a capability."""
        desc = capability.descriptor
        if desc.name in self._capabilities:
            logger.warning("Overwriting capability: %s", desc.name)
        self._capabilities[desc.name] = capability
        logger.debug("Registered capability: %s (%s)", desc.name, desc.capability_type.value)

    def get(self, name: str) -> Optional[BaseCapability]:
        """Get a capability by name."""
        return self._capabilities.get(name)

    def list_all(self) -> list[CapabilityDescriptor]:
        """List all registered capabilities."""
        return [cap.descriptor for cap in self._capabilities.values()]

    def list_for_agent_type(self, agent_type: str) -> list[CapabilityDescriptor]:
        """List capabilities available to a specific agent type."""
        return [
            cap.descriptor
            for cap in self._capabilities.values()
            if not cap.descriptor.supported_agent_types
            or agent_type in cap.descriptor.supported_agent_types
        ]

    def list_by_category(self, category: CapabilityCategory) -> list[CapabilityDescriptor]:
        """List capabilities in a specific category."""
        return [
            cap.descriptor
            for cap in self._capabilities.values()
            if cap.descriptor.category == category
        ]

    def has_capability(self, name: str) -> bool:
        """Check if a capability exists."""
        return name in self._capabilities


# Global registry instance
capability_registry = CapabilityRegistry()
