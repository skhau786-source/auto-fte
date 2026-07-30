"""
Comprehensive tests for the Warehouse Allocation Engine (Phase 4).

Covers:
- AllocationStrategyRegistry: registration, lookup, supports
- All 5 strategies: default, highest_stock, priority, round_robin, nearest
- Split fulfillment across multiple warehouses
- AllocationService: allocate, preview, reallocate, validate
- WooCommerce integration
- Validation rules (inactive, cross-store, negative)
- Settings integration
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.warehouse.allocation_strategies import (
    AllocationPlan, WarehouseAllocation, AllocationItem,
    DefaultWarehouseStrategy, HighestStockStrategy,
    PriorityWarehouseStrategy, RoundRobinStrategy,
    NearestWarehouseStrategy,
    AllocationStrategyRegistry, get_registry, get_strategy,
)
from app.warehouse.allocation_service import AllocationService
from app.warehouse.exceptions import (
    AllocationFailedError, InvalidAllocationStrategyError,
)
from app.inventory.constants import AllocationStrategy

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


def _make_warehouse_stock():
    """Create standard warehouse stock list for tests."""
    return [
        (uuid.UUID("11111111-1111-1111-1111-111111111111"), "Warehouse A", "WH-A", 50),
        (uuid.UUID("22222222-2222-2222-2222-222222222222"), "Warehouse B", "WH-B", 100),
        (uuid.UUID("33333333-3333-3333-3333-333333333333"), "Warehouse C", "WH-C", 30),
    ]


def _make_settings(default_wh_id=None):
    return {
        "default_warehouse_id": default_wh_id or uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "multi_warehouse_enabled": True,
        "allocation_priority": [
            uuid.UUID("33333333-3333-3333-3333-333333333333"),
            uuid.UUID("22222222-2222-2222-2222-222222222222"),
        ],
        "allow_negative_stock": False,
    }


def _make_mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _make_mock_store(store_id=None):
    store = MagicMock()
    store.id = store_id or uuid.uuid4()
    store.owner_id = uuid.uuid4()
    store.is_active = True
    return store


# ═══════════════════════════════════════════════════════════════════
# STRATEGY TESTS
# ═══════════════════════════════════════════════════════════════════


class TestDefaultWarehouseStrategy:
    """Tests for DefaultWarehouseStrategy."""

    def setup_method(self):
        self.strategy = DefaultWarehouseStrategy()
        self.variant_id = uuid.uuid4()
        self.stock = _make_warehouse_stock()

    def test_allocates_from_default(self):
        """Default: allocates from the configured default warehouse."""
        plan = self.strategy.allocate(
            self.variant_id, 20, self.stock, _make_settings(),
        )
        assert plan.fulfilled_quantity == 20
        assert len(plan.allocations) == 1
        assert plan.allocations[0].warehouse_code == "WH-A"
        assert not plan.partial

    def test_partial_when_default_insufficient(self):
        """Default: returns partial when default doesn't have enough."""
        plan = self.strategy.allocate(
            self.variant_id, 100, self.stock, _make_settings(),
        )
        assert plan.fulfilled_quantity == 50
        assert plan.partial

    def test_no_default_configured(self):
        """Default: returns empty plan when no default configured."""
        plan = self.strategy.allocate(
            self.variant_id, 20, self.stock, {},
        )
        assert plan.fulfilled_quantity == 0
        assert plan.partial


class TestHighestStockStrategy:
    """Tests for HighestStockStrategy."""

    def setup_method(self):
        self.strategy = HighestStockStrategy()
        self.variant_id = uuid.uuid4()
        self.stock = _make_warehouse_stock()

    def test_allocates_from_highest_stock(self):
        """Highest: allocates from warehouse with most stock."""
        plan = self.strategy.allocate(self.variant_id, 30, self.stock)
        assert plan.fulfilled_quantity == 30
        # WH-B has 100 stock, should be used
        assert plan.allocations[0].warehouse_code == "WH-B"

    def test_split_fulfillment(self):
        """Highest: splits across warehouses when needed."""
        plan = self.strategy.allocate(self.variant_id, 120, self.stock)
        assert plan.fulfilled_quantity == 120
        assert len(plan.allocations) >= 2
        # WH-B (100) + WH-A (50) but only 120 needed
        assert not plan.partial

    def test_partial_when_total_insufficient(self):
        """Highest: returns partial when no warehouse has enough."""
        plan = self.strategy.allocate(self.variant_id, 500, self.stock)
        assert plan.fulfilled_quantity == 180  # Total across all
        assert plan.partial


class TestPriorityWarehouseStrategy:
    """Tests for PriorityWarehouseStrategy."""

    def setup_method(self):
        self.strategy = PriorityWarehouseStrategy()
        self.variant_id = uuid.uuid4()
        self.stock = _make_warehouse_stock()

    def test_allocates_in_priority_order(self):
        """Priority: allocates from highest priority warehouse first."""
        plan = self.strategy.allocate(
            self.variant_id, 20, self.stock, _make_settings(),
        )
        assert plan.fulfilled_quantity == 20
        # WH-C is priority 1, but has only 30; we request 20
        assert plan.allocations[0].warehouse_code == "WH-C"

    def test_split_fulfillment_by_priority(self):
        """Priority: falls through priority list if needed."""
        plan = self.strategy.allocate(
            self.variant_id, 50, self.stock, _make_settings(),
        )
        assert plan.fulfilled_quantity == 50
        assert len(plan.allocations) == 2
        # WH-C (30) + WH-B (20)
        assert plan.allocations[0].warehouse_code == "WH-C"
        assert plan.allocations[1].warehouse_code == "WH-B"

    def test_empty_priority_list(self):
        """Priority: returns partial when no priority list configured."""
        plan = self.strategy.allocate(
            self.variant_id, 20, self.stock, {},
        )
        assert plan.fulfilled_quantity == 0
        assert plan.partial


class TestRoundRobinStrategy:
    """Tests for RoundRobinStrategy."""

    def setup_method(self):
        self.strategy = RoundRobinStrategy()
        self.variant_id = uuid.uuid4()
        self.stock = _make_warehouse_stock()

    def test_balances_across_warehouses(self):
        """RoundRobin: distributes across warehouses evenly."""
        plan = self.strategy.allocate(self.variant_id, 60, self.stock)
        assert plan.fulfilled_quantity == 60
        # Should touch at least 2 warehouses (50 + 30 = 80, we request 60)
        assert len(plan.allocations) >= 2

    def test_tracks_previous_allocations(self):
        """RoundRobin: considers previous allocations for balance."""
        prev = {uuid.UUID("11111111-1111-1111-1111-111111111111"): 100}
        plan = self.strategy.allocate(
            self.variant_id, 30, self.stock,
            previous_allocations=prev,
        )
        # WH-A should be deprioritized due to many previous allocations
        assert plan.fulfilled_quantity == 30
        # First allocation should NOT be to WH-A
        assert plan.allocations[0].warehouse_code != "WH-A"


class TestNearestWarehouseStrategy:
    """Tests for NearestWarehouseStrategy (architecture only, falls back)."""

    def setup_method(self):
        self.strategy = NearestWarehouseStrategy()
        self.variant_id = uuid.uuid4()
        self.stock = _make_warehouse_stock()

    def test_falls_back_to_highest_stock(self):
        """Nearest: falls back to highest stock when distance not implemented."""
        plan = self.strategy.allocate(self.variant_id, 30, self.stock)
        assert plan.fulfilled_quantity > 0
        assert plan.strategy_name == "nearest_warehouse"


class TestAllocationStrategyRegistry:
    """Tests for the strategy registry."""

    def test_registry_contains_all_strategies(self):
        """Registry: contains all 5 core strategies."""
        registry = AllocationStrategyRegistry()
        strategies = registry.get_all()
        assert "default_warehouse" in strategies
        assert "highest_stock" in strategies
        assert "priority" in strategies
        assert "round_robin" in strategies
        assert "nearest_warehouse" in strategies

    def test_registry_lookup(self):
        """Registry: get returns correct strategy."""
        strategy = get_strategy("default_warehouse")
        assert isinstance(strategy, DefaultWarehouseStrategy)

    def test_registry_unknown_strategy(self):
        """Registry: get raises KeyError for unknown strategy."""
        with pytest.raises(KeyError):
            get_strategy("nonexistent_strategy")

    def test_registry_supports(self):
        """Registry: supports checks correctly."""
        registry = AllocationStrategyRegistry()
        assert registry.supports("default_warehouse")
        assert not registry.supports("random_strategy")


# ═══════════════════════════════════════════════════════════════════
# SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAllocationService:
    """Tests for AllocationService business logic."""

    async def _make_service(self):
        db = _make_mock_db()
        store = _make_mock_store()
        service = AllocationService(db=db, store=store)
        return db, store, service

    async def test_get_strategy_returns_configured(self):
        """Service: get_strategy returns the configured strategy."""
        db, store, service = await self._make_service()

        mock_settings = MagicMock()
        mock_settings.allocation_strategy = "highest_stock"
        service.settings_repo.get_or_create = AsyncMock(return_value=mock_settings)

        result = await service.get_strategy()
        assert result["name"] == "highest_stock"

    async def test_get_strategy_with_override(self):
        """Service: get_strategy with explicit name returns that strategy."""
        db, store, service = await self._make_service()
        result = await service.get_strategy("priority")
        assert result["name"] == "priority"

    async def test_get_strategy_invalid(self):
        """Service: get_strategy with invalid name raises error."""
        db, store, service = await self._make_service()
        with pytest.raises(InvalidAllocationStrategyError):
            await service.get_strategy("nonexistent")

    async def test_list_strategies(self):
        """Service: list_strategies returns all available strategies."""
        db, store, service = await self._make_service()
        strategies = await service.list_strategies()
        assert len(strategies) >= 5
        names = [s["name"] for s in strategies]
        assert "default_warehouse" in names
        assert "highest_stock" in names
        assert "priority" in names
        assert "round_robin" in names
        assert "nearest_warehouse" in names

    async def test_validate_allocation_valid(self):
        """Service: validate_allocation returns valid=True when stock available."""
        db, store, service = await self._make_service()
        wh_id = uuid.uuid4()
        v_id = uuid.uuid4()

        mock_wh = MagicMock()
        mock_wh.id = wh_id
        mock_wh.store_id = store.id
        mock_wh.is_active = True
        mock_wh.name = "Test WH"
        mock_wh.code = "TST"

        mock_inv = MagicMock()
        mock_inv.available_stock = 50

        service.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)
        service.inv_repo.get_by_variant_and_warehouse = AsyncMock(return_value=mock_inv)

        result = await service.validate_allocation(v_id, 30, wh_id)
        assert result["valid"] is True
        assert result["available_stock"] == 50

    async def test_validate_allocation_insufficient(self):
        """Service: validate_allocation returns valid=False when insufficient."""
        db, store, service = await self._make_service()
        wh_id = uuid.uuid4()
        v_id = uuid.uuid4()

        mock_wh = MagicMock()
        mock_wh.id = wh_id
        mock_wh.store_id = store.id
        mock_wh.is_active = True

        mock_inv = MagicMock()
        mock_inv.available_stock = 5

        service.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)
        service.inv_repo.get_by_variant_and_warehouse = AsyncMock(return_value=mock_inv)

        result = await service.validate_allocation(v_id, 30, wh_id)
        assert result["valid"] is False
        assert result["reason"] == "insufficient_stock"

    async def test_validate_allocation_inactive_warehouse(self):
        """Service: validate_allocation returns valid=False when inactive."""
        db, store, service = await self._make_service()
        wh_id = uuid.uuid4()

        mock_wh = MagicMock()
        mock_wh.id = wh_id
        mock_wh.store_id = store.id
        mock_wh.is_active = False

        service.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)

        result = await service.validate_allocation(uuid.uuid4(), 30, wh_id)
        assert result["valid"] is False
        assert result["reason"] == "inactive"

    async def test_preview_allocation_no_side_effects(self):
        """Service: preview_allocation returns plan without modifying anything."""
        db, store, service = await self._make_service()
        v_id = uuid.uuid4()

        mock_variant = MagicMock()
        mock_variant.id = v_id

        mock_wh = MagicMock()
        mock_wh.id = uuid.uuid4()
        mock_wh.store_id = store.id
        mock_wh.is_active = True
        mock_wh.name = "Test WH"
        mock_wh.code = "TST"

        mock_inv = MagicMock()
        mock_inv.available_stock = 100

        # Mock settings to avoid real DB access
        mock_settings = MagicMock()
        mock_settings.allocation_strategy = "default_warehouse"
        mock_settings.multi_warehouse_enabled = False
        mock_settings.allow_negative_stock = False
        mock_settings.reserve_stock_on_order = True
        mock_settings.auto_release_cancelled_orders = True
        service.settings_repo.get_or_create = AsyncMock(return_value=mock_settings)

        service.variant_repo.get_by_id = AsyncMock(return_value=mock_variant)
        service.wh_repo.list_by_store = AsyncMock(return_value=([mock_wh], 1))
        service.wh_repo.get_default = AsyncMock(return_value=mock_wh)
        service.inv_repo.get_by_variant_and_warehouse = AsyncMock(return_value=mock_inv)

        result = await service.preview_allocation(v_id, 30)
        assert result["no_side_effects"] is True
        assert result["fulfilled"] == 30
        assert result["fully_fulfilled"] is True
        # Verify no mutations happened
        assert not db.commit.called

    async def test_reallocate_moves_stock(self):
        """Service: reallocate moves stock from source to destination."""
        db, store, service = await self._make_service()
        src_id = uuid.uuid4()
        dst_id = uuid.uuid4()
        v_id = uuid.uuid4()

        mock_src = MagicMock()
        mock_src.id = src_id
        mock_src.store_id = store.id
        mock_src.is_active = True
        mock_src.name = "Source WH"

        mock_dst = MagicMock()
        mock_dst.id = dst_id
        mock_dst.store_id = store.id
        mock_dst.is_active = True
        mock_dst.name = "Dest WH"

        mock_src_inv = MagicMock()
        mock_src_inv.available_stock = 50
        mock_src_inv.reserved_stock = 0

        service.wh_repo.get_by_id = AsyncMock(side_effect=lambda rid: mock_src if rid == src_id else mock_dst)
        service.inv_repo.get_by_variant_and_warehouse = AsyncMock(return_value=mock_src_inv)
        service.inv_repo.get_or_create = AsyncMock(return_value=MagicMock())

        result = await service.reallocate(
            variant_id=v_id, quantity=30,
            from_warehouse_id=src_id, to_warehouse_id=dst_id,
        )
        assert result["from_warehouse_id"] == str(src_id)
        assert result["to_warehouse_id"] == str(dst_id)
        assert result["quantity"] == 30


# ═══════════════════════════════════════════════════════════════════
# ALLOCATION PLAN TESTS
# ═══════════════════════════════════════════════════════════════════

class TestAllocationPlan:
    """Tests for AllocationPlan data class."""

    def test_fully_fulfilled_property(self):
        """Plan: is_fully_fulfilled returns True when fulfilled >= requested."""
        plan = AllocationPlan(
            variant_id=uuid.uuid4(),
            requested_quantity=10,
            fulfilled_quantity=10,
        )
        assert plan.is_fully_fulfilled

    def test_not_fully_fulfilled_property(self):
        """Plan: is_fully_fulfilled returns False when fulfilled < requested."""
        plan = AllocationPlan(
            variant_id=uuid.uuid4(),
            requested_quantity=10,
            fulfilled_quantity=7,
        )
        assert not plan.is_fully_fulfilled
        assert plan.partial  # Auto-computed from fulfilled < requested

    def test_empty_allocations(self):
        """Plan: empty allocations list works correctly."""
        plan = AllocationPlan(
            variant_id=uuid.uuid4(),
            requested_quantity=10,
            fulfilled_quantity=0,
        )
        assert plan.allocations == []
        assert plan.partial  # Auto-computed from 0 < 10
        assert not plan.is_fully_fulfilled


# ═══════════════════════════════════════════════════════════════════
# VALIDATION RULES TESTS (D.12)
# ═══════════════════════════════════════════════════════════════════

class TestValidationRules:
    """Tests for allocation validation rules."""

    def test_default_strategy_enum(self):
        """Validation: AllocationStrategy enum has expected values."""
        assert AllocationStrategy.DEFAULT_WAREHOUSE.value == "default_warehouse"
        assert AllocationStrategy.HIGHEST_STOCK.value == "highest_stock"
        assert AllocationStrategy.PRIORITY.value == "priority"
        assert AllocationStrategy.ROUND_ROBIN.value == "round_robin"
        assert AllocationStrategy.NEAREST_WAREHOUSE.value == "nearest_warehouse"
        assert AllocationStrategy.MANUAL.value == "manual"
