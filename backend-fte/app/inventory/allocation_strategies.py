"""
Store-centric Allocation Models.

In the SaaS inventory platform each store is a single inventory location,
so allocation checks whether the store's available stock can fulfill the
requested quantity. The strategy framework is preserved for extensibility
(future locations/connectors) but operates at store level.

Types:
- AllocationItem:      a requested variant + quantity
- AllocationItemResult: fulfillment outcome for a single item
- AllocationPlan:      the full allocation outcome
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AllocationItem:
    """A requested allocation unit: reserve `quantity` of `variant_id`."""

    variant_id: uuid.UUID
    quantity: int


@dataclass
class AllocationItemResult:
    """Fulfillment outcome for a single allocation item."""

    variant_id: uuid.UUID
    requested_quantity: int
    fulfilled_quantity: int = 0
    available_quantity: int = 0
    reservation_id: Optional[uuid.UUID] = None

    @property
    def status(self) -> str:
        """fulfilled | partial | out_of_stock."""
        if self.fulfilled_quantity >= self.requested_quantity:
            return "fulfilled"
        if self.fulfilled_quantity > 0:
            return "partial"
        return "out_of_stock"


@dataclass
class AllocationPlan:
    """Outcome of allocating a set of items at store level."""

    strategy_name: str = "default"
    items: list[AllocationItemResult] = field(default_factory=list)

    @property
    def total_requested(self) -> int:
        return sum(i.requested_quantity for i in self.items)

    @property
    def total_fulfilled(self) -> int:
        return sum(i.fulfilled_quantity for i in self.items)

    @property
    def total_unfulfilled(self) -> int:
        return self.total_requested - self.total_fulfilled

    @property
    def is_fully_fulfilled(self) -> bool:
        return bool(self.items) and self.total_unfulfilled == 0

    @property
    def partial(self) -> bool:
        return 0 < self.total_fulfilled < self.total_requested

    @property
    def status(self) -> str:
        if self.is_fully_fulfilled:
            return "fully_allocated"
        if self.total_fulfilled > 0:
            return "partially_allocated"
        return "out_of_stock"


# Available store-level allocation strategies (for the strategies API)
AVAILABLE_STRATEGIES = [
    {
        "name": "default",
        "description": "Fulfill from the store's available stock (single-location).",
    },
    {
        "name": "manual",
        "description": "Manual allocation — no automatic fulfillment decisions.",
    },
]
