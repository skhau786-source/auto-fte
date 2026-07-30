"""
Warehouse Allocation Strategies — Phase 4 (D.1, D.4).

Strategy Pattern implementation for warehouse inventory allocation.
Each strategy implements the BaseAllocationStrategy interface.

Strategies:
1. DefaultWarehouseStrategy — Uses configured default warehouse
2. HighestStockStrategy — Picks warehouse with most available stock
3. PriorityWarehouseStrategy — Uses priority-ordered warehouse list
4. RoundRobinStrategy — Balances across warehouses round-robin
5. NearestWarehouseStrategy — Architecture only (distance calc TBD)

New strategies can be added by subclassing BaseAllocationStrategy
without modifying existing code (Open/Closed Principle).
"""

from __future__ import annotations

import uuid
import abc
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.inventory.constants import AllocationStrategy as AllocationStrategyEnum

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════


@dataclass
class AllocationItem:
    """A single item in an allocation request."""
    variant_id: uuid.UUID
    quantity: int


@dataclass
class WarehouseAllocation:
    """A single allocation to a warehouse."""
    warehouse_id: uuid.UUID
    warehouse_name: str
    warehouse_code: str
    variant_id: uuid.UUID
    quantity: int
    available_before: int
    available_after: int


class AllocationPlan:
    """
    Result of an allocation operation.

    Supports split fulfillment — can allocate across multiple warehouses.
    `partial` is auto-computed from fulfilled vs requested quantities.
    """

    def __init__(
        self,
        variant_id: uuid.UUID,
        requested_quantity: int,
        fulfilled_quantity: int = 0,
        allocations: Optional[list[WarehouseAllocation]] = None,
        strategy_name: str = "",
        partial: Optional[bool] = None,
    ):
        self.variant_id = variant_id
        self.requested_quantity = requested_quantity
        self.fulfilled_quantity = fulfilled_quantity
        self.allocations = allocations or []
        self.strategy_name = strategy_name
        # If partial is explicitly set, use it; otherwise auto-compute
        self._partial = partial

    @property
    def partial(self) -> bool:
        return self._partial if self._partial is not None else self.fulfilled_quantity < self.requested_quantity

    @partial.setter
    def partial(self, value: bool):
        self._partial = value

    @property
    def is_fully_fulfilled(self) -> bool:
        return self.fulfilled_quantity >= self.requested_quantity


# ═══════════════════════════════════════════════════════════════════
# Abstract Base Strategy
# ═══════════════════════════════════════════════════════════════════


class BaseAllocationStrategy(abc.ABC):
    """
    Abstract interface for warehouse allocation strategies.

    Each strategy:
    1. Receives a list of (warehouse_id, available_stock) tuples
    2. Applies its algorithm to determine which warehouse(s) to use
    3. Returns an AllocationPlan with the result

    Future strategies implement this interface without changing
    any existing code.
    """

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abc.abstractmethod
    def get_strategy_name(self) -> str:
        """Return the human-readable strategy name."""
        pass

    @abc.abstractmethod
    def allocate(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        warehouse_stock: list[tuple[uuid.UUID, str, str, int]],
        settings: Optional[dict] = None,
        previous_allocations: Optional[dict[uuid.UUID, int]] = None,
    ) -> AllocationPlan:
        """
        Allocate a quantity of a variant across available warehouses.

        Args:
            variant_id: The variant to allocate.
            quantity: The quantity requested.
            warehouse_stock: List of (warehouse_id, name, code, available_stock) tuples.
            settings: Optional dict with allocation settings (e.g., default_wh, priorities).
            previous_allocations: Dict of warehouse_id -> count allocated this session
                                  (for round-robin tracking).

        Returns:
            AllocationPlan with one or more WarehouseAllocation entries.
        """
        pass


# ═══════════════════════════════════════════════════════════════════
# Strategy 1: Default Warehouse
# ═══════════════════════════════════════════════════════════════════


class DefaultWarehouseStrategy(BaseAllocationStrategy):
    """
    Allocates using the store's configured default warehouse.

    If the default warehouse doesn't have enough stock:
    - Returns a partial allocation with what's available
    - Does NOT fall through to other warehouses (single-warehouse strategy)
    """

    def get_strategy_name(self) -> str:
        return "default_warehouse"

    def allocate(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        warehouse_stock: list[tuple[uuid.UUID, str, str, int]],
        settings: Optional[dict] = None,
        previous_allocations: Optional[dict[uuid.UUID, int]] = None,
    ) -> AllocationPlan:
        default_wh_id = settings.get("default_warehouse_id") if settings else None

        plan = AllocationPlan(
            variant_id=variant_id,
            requested_quantity=quantity,
            fulfilled_quantity=0,
            strategy_name=self.get_strategy_name(),
        )

        if not default_wh_id:
            self.logger.warning(
                "No default warehouse configured for variant %s", variant_id,
            )
            plan.partial = True
            return plan

        # Find the default warehouse in the stock list
        for wh_id, wh_name, wh_code, available in warehouse_stock:
            if wh_id == default_wh_id:
                alloc_qty = min(quantity, available)
                if alloc_qty > 0:
                    plan.allocations.append(WarehouseAllocation(
                        warehouse_id=wh_id,
                        warehouse_name=wh_name,
                        warehouse_code=wh_code,
                        variant_id=variant_id,
                        quantity=alloc_qty,
                        available_before=available,
                        available_after=available - alloc_qty,
                    ))
                    plan.fulfilled_quantity = alloc_qty
                    plan.partial = alloc_qty < quantity
                break

        if plan.fulfilled_quantity == 0:
            self.logger.warning(
                "Default warehouse not found in active warehouses for variant %s",
                variant_id,
            )
            plan.partial = True

        return plan


# ═══════════════════════════════════════════════════════════════════
# Strategy 2: Highest Stock
# ═══════════════════════════════════════════════════════════════════


class HighestStockStrategy(BaseAllocationStrategy):
    """
    Allocates from the warehouse with the greatest available stock.

    Supports split fulfillment:
    - Takes as much as needed from the highest-stock warehouse
    - Falls through to the next highest if more is needed
    """

    def get_strategy_name(self) -> str:
        return "highest_stock"

    def allocate(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        warehouse_stock: list[tuple[uuid.UUID, str, str, int]],
        settings: Optional[dict] = None,
        previous_allocations: Optional[dict[uuid.UUID, int]] = None,
    ) -> AllocationPlan:
        # Sort by available_stock descending
        sorted_stock = sorted(warehouse_stock, key=lambda x: x[3], reverse=True)

        plan = AllocationPlan(
            variant_id=variant_id,
            requested_quantity=quantity,
            fulfilled_quantity=0,
            strategy_name=self.get_strategy_name(),
        )

        remaining = quantity
        for wh_id, wh_name, wh_code, available in sorted_stock:
            if remaining <= 0:
                break
            if available <= 0:
                continue

            take = min(remaining, available)
            plan.allocations.append(WarehouseAllocation(
                warehouse_id=wh_id,
                warehouse_name=wh_name,
                warehouse_code=wh_code,
                variant_id=variant_id,
                quantity=take,
                available_before=available,
                available_after=available - take,
            ))
            plan.fulfilled_quantity += take
            remaining -= take

        plan.partial = remaining > 0
        return plan


# ═══════════════════════════════════════════════════════════════════
# Strategy 3: Priority Warehouse
# ═══════════════════════════════════════════════════════════════════


class PriorityWarehouseStrategy(BaseAllocationStrategy):
    """
    Allocates from warehouses in a configured priority order.

    Settings:
    - allocation_priority: list of warehouse IDs in priority order

    Supports split fulfillment across priority warehouses.
    """

    def get_strategy_name(self) -> str:
        return "priority"

    def allocate(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        warehouse_stock: list[tuple[uuid.UUID, str, str, int]],
        settings: Optional[dict] = None,
        previous_allocations: Optional[dict[uuid.UUID, int]] = None,
    ) -> AllocationPlan:
        priority_list = (
            settings.get("allocation_priority", []) if settings else []
        )

        plan = AllocationPlan(
            variant_id=variant_id,
            requested_quantity=quantity,
            fulfilled_quantity=0,
            strategy_name=self.get_strategy_name(),
        )

        if not priority_list:
            self.logger.warning(
                "No priority list configured for variant %s, falling back to default",
                variant_id,
            )
            plan.partial = True
            return plan

        # Build a lookup for warehouse stock
        stock_by_id = {wh_id: (name, code, avail) for wh_id, name, code, avail in warehouse_stock}

        remaining = quantity
        for wh_id in priority_list:
            if remaining <= 0:
                break
            if wh_id not in stock_by_id:
                continue

            wh_name, wh_code, available = stock_by_id[wh_id]
            if available <= 0:
                continue

            take = min(remaining, available)
            plan.allocations.append(WarehouseAllocation(
                warehouse_id=wh_id,
                warehouse_name=wh_name,
                warehouse_code=wh_code,
                variant_id=variant_id,
                quantity=take,
                available_before=available,
                available_after=available - take,
            ))
            plan.fulfilled_quantity += take
            remaining -= take

        plan.partial = remaining > 0
        return plan


# ═══════════════════════════════════════════════════════════════════
# Strategy 4: Round Robin
# ═══════════════════════════════════════════════════════════════════


class RoundRobinStrategy(BaseAllocationStrategy):
    """
    Distributes allocation evenly across available warehouses.

    Tracks previous allocations per session to ensure balanced distribution.
    Each call allocates to the warehouse with the fewest allocations so far.

    Supports split fulfillment across all warehouses with stock.
    """

    def get_strategy_name(self) -> str:
        return "round_robin"

    def allocate(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        warehouse_stock: list[tuple[uuid.UUID, str, str, int]],
        settings: Optional[dict] = None,
        previous_allocations: Optional[dict[uuid.UUID, int]] = None,
    ) -> AllocationPlan:
        prev = previous_allocations or {}

        # Filter to warehouses with stock
        active = [(wh_id, name, code, avail) for wh_id, name, code, avail in warehouse_stock if avail > 0]

        plan = AllocationPlan(
            variant_id=variant_id,
            requested_quantity=quantity,
            fulfilled_quantity=0,
            strategy_name=self.get_strategy_name(),
        )

        if not active:
            plan.partial = True
            return plan

        remaining = quantity
        while remaining > 0:
            # Find the warehouse with the fewest previous allocations
            active.sort(key=lambda x: prev.get(x[0], 0))
            wh_id, wh_name, wh_code, available = active[0]

            if available <= 0:
                # This warehouse is exhausted; skip to next
                # Recalculate available from what we've already allocated
                allocated_so_far = sum(
                    a.quantity for a in plan.allocations if a.warehouse_id == wh_id
                )
                still_available = available - allocated_so_far
                if still_available <= 0:
                    active.pop(0)
                    if not active:
                        break
                    continue

                # Recalculate with actual remaining
                still_available = available - allocated_so_far
                take = min(remaining, still_available)
            else:
                take = min(remaining, available)

            plan.allocations.append(WarehouseAllocation(
                warehouse_id=wh_id,
                warehouse_name=wh_name,
                warehouse_code=wh_code,
                variant_id=variant_id,
                quantity=take,
                available_before=available,
                available_after=available - take,
            ))
            plan.fulfilled_quantity += take
            remaining -= take
            prev[wh_id] = prev.get(wh_id, 0) + take

        plan.partial = remaining > 0
        return plan


# ═══════════════════════════════════════════════════════════════════
# Strategy 5: Nearest Warehouse (Architecture Only)
# ═══════════════════════════════════════════════════════════════════


class NearestWarehouseStrategy(BaseAllocationStrategy):
    """
    Allocates from the nearest warehouse based on geographic proximity.

    ARCHITECTURE ONLY — distance calculation is not yet implemented.
    Falls through to the default warehouse strategy.

    TODO: Implement distance calculation using warehouse lat/long.
    TODO: Integrate with a geocoding/maps service.
    """

    def get_strategy_name(self) -> str:
        return "nearest_warehouse"

    def allocate(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        warehouse_stock: list[tuple[uuid.UUID, str, str, int]],
        settings: Optional[dict] = None,
        previous_allocations: Optional[dict[uuid.UUID, int]] = None,
    ) -> AllocationPlan:
        # Nearest distance calculation not yet implemented.
        # Falls back to highest-stock strategy as a reasonable default.
        self.logger.info(
            "NearestWarehouseStrategy not fully implemented — "
            "falling back to highest_stock for variant %s",
            variant_id,
        )
        fallback = HighestStockStrategy()
        plan = fallback.allocate(
            variant_id, quantity, warehouse_stock, settings, previous_allocations,
        )
        plan.strategy_name = self.get_strategy_name()
        return plan


# ═══════════════════════════════════════════════════════════════════
# Strategy Registry
# ═══════════════════════════════════════════════════════════════════


class AllocationStrategyRegistry:
    """
    Registry of all available allocation strategies.

    Strategies are auto-registered by name for lookup.
    New strategies register themselves here to be discoverable
    by the AllocationService.
    """

    def __init__(self):
        self._strategies: dict[str, BaseAllocationStrategy] = {}
        self._register_core_strategies()

    def _register_core_strategies(self):
        """Register the built-in strategies."""
        self.register(DefaultWarehouseStrategy())
        self.register(HighestStockStrategy())
        self.register(PriorityWarehouseStrategy())
        self.register(RoundRobinStrategy())
        self.register(NearestWarehouseStrategy())
        self.register(ManualSelectionStrategy())

    def register(self, strategy: BaseAllocationStrategy):
        """Register a strategy by name."""
        self._strategies[strategy.get_strategy_name()] = strategy

    def get(self, name: str) -> BaseAllocationStrategy:
        """Look up a strategy by name. Raises KeyError if not found."""
        if name not in self._strategies:
            raise KeyError(f"Unknown allocation strategy: '{name}'")
        return self._strategies[name]

    def get_all(self) -> dict[str, str]:
        """Return all registered strategies as name -> class name."""
        return {
            name: type(strategy).__name__
            for name, strategy in self._strategies.items()
        }

    def supports(self, name: str) -> bool:
        """Check if a strategy is registered."""
        return name in self._strategies


# ═══════════════════════════════════════════════════════════════════
# Strategy 6: Manual Selection (No-op)
# ═══════════════════════════════════════════════════════════════════


class ManualSelectionStrategy(BaseAllocationStrategy):
    """
    Manual selection — no automatic allocation.

    Returns an empty allocation plan. The caller must explicitly
    specify which warehouse(s) to use. Useful for systems where
    a human operator makes the allocation decision.
    """

    def get_strategy_name(self) -> str:
        return "manual"

    def allocate(
        self,
        variant_id: uuid.UUID,
        quantity: int,
        warehouse_stock: list[tuple[uuid.UUID, str, str, int]],
        settings: Optional[dict] = None,
        previous_allocations: Optional[dict[uuid.UUID, int]] = None,
    ) -> AllocationPlan:
        self.logger.info(
            "Manual selection strategy — no automatic allocation for variant %s",
            variant_id,
        )
        return AllocationPlan(
            variant_id=variant_id,
            requested_quantity=quantity,
            fulfilled_quantity=0,
            strategy_name=self.get_strategy_name(),
            partial=True,
        )


# Singleton registry
_registry: Optional[AllocationStrategyRegistry] = None


def get_registry() -> AllocationStrategyRegistry:
    """Get or create the singleton strategy registry."""
    global _registry
    if _registry is None:
        _registry = AllocationStrategyRegistry()
    return _registry


def get_strategy(name: str) -> BaseAllocationStrategy:
    """Convenience function to get a strategy by name."""
    return get_registry().get(name)
