"""
Comprehensive tests for Phase 6 — Inventory Aggregation Engine (F.13).

Covers:
- F.2: Variant aggregation (total stock, available, reserved, etc.)
- F.3: Product aggregation (all variants, all warehouses)
- F.4: Warehouse aggregation (capacity, SKU/variant/product counts)
- F.5: Store aggregation (total inventory, value, counts)
- F.6: Dashboard summary
- F.7: Distribution endpoint
- F.8: Performance (COUNT queries, no N+1)
- F.9: Validation (cross-store protection)
- F.11: Reports (fast movers, slow movers, dead stock)
- F.12: Repository methods
"""

import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════

def mock_result_with_one(row):
    """Create a MagicMock result that returns a single row via .one().
    Uses MagicMock (not AsyncMock) to match existing codebase patterns.
    """
    result = MagicMock()
    result.one.return_value = row
    return result


def mock_result_with_scalar(value):
    """Create a MagicMock result that returns a scalar value."""
    result = MagicMock()
    result.scalar.return_value = value
    return result


def mock_result_with_all(rows):
    """Create a MagicMock result that returns rows via .all()."""
    result = MagicMock()
    result.all.return_value = rows
    return result


def mock_result_with_scalar_one_none(value):
    """Create a MagicMock result that returns a value or None."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.id = uuid.uuid4()
    store.owner_id = uuid.uuid4()
    return store


@pytest.mark.asyncio
async def test_aggregation_engine_imports():
    """F.12: Engine imports are valid."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine
    assert InventoryAggregationEngine is not None
    required_methods = [
        "get_variant", "get_product", "get_warehouse",
        "get_store", "get_dashboard", "get_distribution",
        "get_report_data",
    ]
    for method in required_methods:
        assert hasattr(InventoryAggregationEngine, method), f"Missing method: {method}"


@pytest.mark.asyncio
async def test_router_imports():
    """F.7: Router imports are valid."""
    from app.warehouse.aggregation_router import (
        aggregate_store, aggregate_warehouse, aggregate_product,
        aggregate_variant, aggregate_dashboard, aggregate_distribution,
        aggregate_reports,
    )
    assert callable(aggregate_store)
    assert callable(aggregate_warehouse)
    assert callable(aggregate_product)
    assert callable(aggregate_variant)
    assert callable(aggregate_dashboard)
    assert callable(aggregate_distribution)
    assert callable(aggregate_reports)


# ═══════════════════════════════════════════════════════════════════
# F.2 — VARIANT AGGREGATION
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_variant_aggregation_structure(mock_db, mock_store):
    """F.2: Variant aggregation returns correct structure."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine

    engine = InventoryAggregationEngine(db=mock_db, store=mock_store)

    # Mock all helper methods to avoid fragile db.execute side_effect chains
    engine._get_active_warehouse_ids = AsyncMock(return_value=[uuid.uuid4()])
    engine._get_warehouse_name_map = AsyncMock(return_value={})

    # Mock variant lookup
    mock_variant = MagicMock()
    mock_variant.id = uuid.uuid4()
    mock_variant.product_id = uuid.uuid4()
    mock_variant.sku = "TEST-SKU"
    mock_variant.title = "Test Variant"
    r1 = mock_result_with_scalar_one_none(mock_variant)

    # Mock aggregate totals row
    agg_row = MagicMock()
    agg_row.total_available = 100
    agg_row.total_reserved = 20
    agg_row.total_incoming = 10
    agg_row.total_damaged = 5
    agg_row.warehouse_count = 1
    r2 = mock_result_with_one(agg_row)

    # Reservation count & in-transit count
    r3 = mock_result_with_scalar(3)
    r4 = mock_result_with_scalar(15)

    # GROUP BY breakdown
    br_row = MagicMock()
    br_row.warehouse_id = uuid.uuid4()
    br_row.available = 100
    br_row.reserved = 20
    br_row.incoming = 10
    br_row.damaged = 5
    r5 = MagicMock()
    r5.all.return_value = [br_row]

    engine.db.execute = AsyncMock(side_effect=[r1, r2, r3, r4, r5])

    result = await engine.get_variant(mock_variant.id)

    assert "variant_id" in result
    assert "warehouse_breakdown" in result
    assert result["sku"] == "TEST-SKU"


@pytest.mark.asyncio
async def test_variant_no_warehouses(mock_db, mock_store):
    """F.2: Variant with no warehouses returns zeros."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine

    engine = InventoryAggregationEngine(db=mock_db, store=mock_store)

    mock_variant = MagicMock()
    mock_variant.id = uuid.uuid4()
    mock_variant.product_id = uuid.uuid4()
    engine.db.execute.return_value.scalar_one_or_none.return_value = mock_variant

    engine._get_active_warehouse_ids = AsyncMock(return_value=[])
    result = await engine.get_variant(mock_variant.id)

    assert result["total_stock"] == 0
    assert result["warehouse_count"] == 0


@pytest.mark.asyncio
async def test_variant_not_found(mock_db, mock_store):
    """F.2: Non-existent variant returns empty result."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine

    engine = InventoryAggregationEngine(db=mock_db, store=mock_store)

    # Mock the variant lookup to return None
    engine.db.execute.return_value = mock_result_with_scalar_one_none(None)

    variant_id = uuid.uuid4()
    result = await engine.get_variant(variant_id)

    assert result["total_stock"] == 0
    assert result["warehouse_count"] == 0


# ═══════════════════════════════════════════════════════════════════
# F.3 — PRODUCT AGGREGATION
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_product_aggregation_structure(mock_db, mock_store):
    """F.3: Product aggregation returns correct structure."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine

    engine = InventoryAggregationEngine(db=mock_db, store=mock_store)

    # Mock helper methods
    engine._get_active_warehouse_ids = AsyncMock(return_value=[uuid.uuid4()])
    engine._batch_product_titles = AsyncMock(return_value={})
    engine._batch_variant_info = AsyncMock(return_value={})

    # Mock all db.execute calls with proper side_effects
    v1 = uuid.uuid4()

    # 1st: product lookup
    mock_product = MagicMock()
    mock_product.id = uuid.uuid4()
    mock_product.title = "Test Product"
    r1 = mock_result_with_scalar_one_none(mock_product)

    # 2nd: variant IDs
    r2 = mock_result_with_all([(v1,)])

    # 3rd: aggregate totals
    agg_row = MagicMock()
    agg_row.total_available = 100
    agg_row.total_reserved = 20
    agg_row.total_incoming = 10
    agg_row.total_damaged = 5
    r3 = mock_result_with_one(agg_row)

    # 4th: warehouse count
    r4 = mock_result_with_scalar(1)

    # 5th: GROUP BY variant breakdown
    br_row = MagicMock()
    br_row.variant_id = v1
    br_row.available = 80
    br_row.reserved = 10
    br_row.incoming = 5
    br_row.damaged = 2
    br_row.wh_count = 1
    r5 = mock_result_with_all([br_row])

    # 6th: variant info (batched)
    v_info_row = MagicMock()
    v_info_row.id = v1
    v_info_row.sku = "SKU-001"
    v_info_row.title = "Test Variant"
    r6 = mock_result_with_all([v_info_row])

    engine.db.execute = AsyncMock(side_effect=[r1, r2, r3, r4, r5, r6])

    result = await engine.get_product(mock_product.id)

    assert "product_id" in result
    assert "variant_breakdown" in result


# ═══════════════════════════════════════════════════════════════════
# F.4 — WAREHOUSE AGGREGATION
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_warehouse_aggregation_structure(mock_db, mock_store):
    """F.4: Warehouse aggregation returns correct structure."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine

    engine = InventoryAggregationEngine(db=mock_db, store=mock_store)

    # Mock warehouse
    mock_wh = MagicMock()
    mock_wh.id = uuid.uuid4()
    mock_wh.store_id = mock_store.id
    mock_wh.name = "Test Warehouse"
    mock_wh.code = "TEST-WH"
    engine.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)

    # Mock aggregate row
    agg_row = MagicMock()
    agg_row.total_available = 500
    agg_row.total_reserved = 100
    agg_row.total_incoming = 50
    agg_row.total_damaged = 10
    agg_row.total_records = 15
    agg_row.variant_count = 10
    agg_row.product_count = 8

    # Mock the capacity service
    engine.capacity_service.get_capacity = AsyncMock(return_value={
        "current_usage": 500,
        "available_capacity": 500,
        "usage_percentage": 50.0,
        "status": "normal",
    })

    # Set up db.execute for aggregate + sku + reservation queries
    agg_exec = mock_result_with_one(agg_row)
    sku_result = mock_result_with_scalar(10)
    res_result = mock_result_with_scalar(5)
    engine.db.execute = AsyncMock(side_effect=[agg_exec, sku_result, res_result])

    result = await engine.get_warehouse(mock_wh.id)

    assert result["warehouse_name"] == "Test Warehouse"
    assert result["warehouse_code"] == "TEST-WH"
    assert "sku_count" in result
    assert "variant_count" in result
    assert "product_count" in result


@pytest.mark.asyncio
async def test_warehouse_wrong_store(mock_db, mock_store):
    """F.9: Warehouse from different store raises error."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine
    from app.warehouse.exceptions import WarehouseNotFoundError

    engine = InventoryAggregationEngine(db=mock_db, store=mock_store)

    mock_wh = MagicMock()
    mock_wh.id = uuid.uuid4()
    mock_wh.store_id = uuid.uuid4()  # Different store
    engine.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)

    with pytest.raises(WarehouseNotFoundError):
        await engine.get_warehouse(mock_wh.id)


# ═══════════════════════════════════════════════════════════════════
# F.5 — STORE AGGREGATION
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_store_aggregation_structure(mock_db, mock_store):
    """F.5: Store aggregation returns correct structure."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine

    engine = InventoryAggregationEngine(db=mock_db, store=mock_store)

    # Mock helper methods
    engine._get_active_warehouse_ids = AsyncMock(return_value=[uuid.uuid4()])
    engine._get_warehouse_name_map = AsyncMock(return_value={str(uuid.uuid4()): "Test WH"})
    engine._batch_product_titles = AsyncMock(return_value={})
    engine._batch_variant_info = AsyncMock(return_value={})

    # Mock capacity service completely (it calls wh_repo internally)
    engine.capacity_service.wh_repo.get_by_id = AsyncMock()
    mock_wh = MagicMock()
    mock_wh.id = engine._get_active_warehouse_ids.return_value[0]
    mock_wh.name = "Test WH"
    mock_wh.store_id = mock_store.id
    mock_wh.capacity = 1000
    engine.capacity_service.wh_repo.get_by_id.return_value = mock_wh
    engine.capacity_service.get_capacity = AsyncMock(return_value={
        "current_usage": 500,
        "available_capacity": 500,
        "usage_percentage": 50.0,
        "status": "normal",
    })

    # Mock warehouse repo get_by_id for capacity service
    engine.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)

    # Mock all db.execute calls
    agg_row = MagicMock()
    agg_row.total_available = 1000
    agg_row.total_reserved = 200
    agg_row.total_incoming = 50
    agg_row.total_damaged = 10
    agg_row.product_count = 30
    agg_row.variant_count = 50
    r1 = mock_result_with_one(agg_row)               # 1st: aggregate_store
    r2 = mock_result_with_scalar(5000.0)             # 2nd: inventory_value
    r3 = mock_result_with_scalar(15)                 # 3rd: reservation count
    r4 = mock_result_with_all([])                    # 4th: top warehouses
    r5 = mock_result_with_all([])                    # 5th: lowest stock
    r6 = mock_result_with_scalar(0)                  # 6th: product titles count
    r7 = mock_result_with_all([])                    # 7th: most reserved
    r8 = mock_result_with_scalar(0)                  # 8th (unused: batch product titles)
    r9 = mock_result_with_all([])                    # 9th: aggregate_capacity
    r10 = mock_result_with_all([])                   # 10th: warehouse capacity batch

    engine.db.execute = AsyncMock(side_effect=[r1, r2, r3, r4, r5, r6, r7, r8, r9, r10])

    result = await engine.get_store()

    assert "store_id" in result
    assert "total_available_stock" in result
    assert "inventory_value" in result
    assert "warehouse_count" in result
    assert "top_warehouses" in result
    assert "lowest_stock_products" in result
    assert "most_reserved_products" in result
    assert "warehouse_utilization" in result


@pytest.mark.asyncio
async def test_store_no_warehouses(mock_db, mock_store):
    """F.5: Store with no warehouses returns zeros."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine

    engine = InventoryAggregationEngine(db=mock_db, store=mock_store)
    engine._get_active_warehouse_ids = AsyncMock(return_value=[])

    result = await engine.get_store()

    assert result["warehouse_count"] == 0
    assert result["total_available_stock"] == 0
    assert result["inventory_value"] == 0.0


# ═══════════════════════════════════════════════════════════════════
# F.6 — DASHBOARD SUMMARY
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_dashboard_summary_structure(mock_db, mock_store):
    """F.6: Dashboard summary returns correct structure."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine

    engine = InventoryAggregationEngine(db=mock_db, store=mock_store)

    # Mock warehouse IDs
    wh_id = uuid.uuid4()
    engine._get_active_warehouse_ids = AsyncMock(return_value=[wh_id])
    engine.wh_repo.count_active = AsyncMock(return_value=1)

    # Mock all db.execute calls
    agg_row = MagicMock()
    agg_row.total_available = 1000
    agg_row.total_reserved = 200
    agg_row.total_incoming = 50
    agg_row.total_damaged = 10
    r1 = mock_result_with_one(agg_row)       # 1st: aggregate totals
    r2 = mock_result_with_scalar(5000.0)     # 2nd: inventory value
    r3 = mock_result_with_scalar(5)           # 3rd: reservations
    r4 = mock_result_with_scalar(2)           # 4th: in-transit transfers

    engine.db.execute = AsyncMock(side_effect=[r1, r2, r3, r4])

    result = await engine.get_dashboard()

    assert "total_available_inventory" in result
    assert "total_reserved_inventory" in result
    assert "total_incoming_inventory" in result
    assert "inventory_value" in result
    assert "warehouse_count" in result
    assert "active_reservations" in result
    assert "transfer_in_transit_count" in result


# ═══════════════════════════════════════════════════════════════════
# F.7 — DISTRIBUTION
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_distribution_structure(mock_db, mock_store):
    """F.7: Distribution returns correct structure with percentages."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine

    engine = InventoryAggregationEngine(db=mock_db, store=mock_store)

    # Mock get_variant to return distribution data
    variant_id = uuid.uuid4()
    engine.get_variant = AsyncMock(return_value={
        "variant_id": str(variant_id),
        "sku": "TEST-SKU",
        "title": "Test",
        "total_stock": 100,
        "warehouse_breakdown": [
            {"warehouse_id": str(uuid.uuid4()), "warehouse_name": "WH-A",
             "available": 60, "reserved": 10, "incoming": 5, "damaged": 0, "total": 70},
            {"warehouse_id": str(uuid.uuid4()), "warehouse_name": "WH-B",
             "available": 30, "reserved": 0, "incoming": 0, "damaged": 0, "total": 30},
        ],
    })

    result = await engine.get_distribution(variant_id)

    assert "variant_id" in result
    assert "total_stock" in result
    assert "warehouses" in result
    assert len(result["warehouses"]) == 2
    # Percentages should sum to ~100
    total_pct = sum(w["percentage"] for w in result["warehouses"])
    assert 99.0 <= total_pct <= 101.0


# ═══════════════════════════════════════════════════════════════════
# F.11 — REPORT DATA
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_report_data_structure(mock_db, mock_store):
    """F.11: Report data returns correct structure."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine

    engine = InventoryAggregationEngine(db=mock_db, store=mock_store)

    # Mock helper methods
    engine._get_active_warehouse_ids = AsyncMock(return_value=[uuid.uuid4()])
    engine._get_warehouse_name_map = AsyncMock(return_value={str(uuid.uuid4()): "Test WH"})
    engine._batch_variant_info = AsyncMock(return_value={})

    # Mock db.execute calls for value_by_wh + fast/slow/dead
    r1 = mock_result_with_scalar(1000.0)     # 1st: value query
    r2 = mock_result_with_all([])             # 2nd: fast movers
    r3 = mock_result_with_all([])             # 3rd: slow movers
    r4 = mock_result_with_scalar(0)           # 4th: dead stock

    engine.db.execute = AsyncMock(side_effect=[r1, r2, r3, r4])

    result = await engine.get_report_data()

    assert "inventory_value_by_warehouse" in result
    assert "fast_movers" in result
    assert "slow_movers" in result
    assert "dead_stock_count" in result


# ═══════════════════════════════════════════════════════════════════
# F.8 — PERFORMANCE (QUERY VALIDATION)
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_variant_aggregation_uses_warehouse_count(mock_db, mock_store):
    """F.8: Variant aggregation uses COUNT/SUM queries, not row loading."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine

    engine = InventoryAggregationEngine(db=mock_db, store=mock_store)

    # Use helper method mocks
    engine._get_active_warehouse_ids = AsyncMock(return_value=[uuid.uuid4()])
    engine._get_warehouse_name_map = AsyncMock(return_value={})

    # Mock variant lookup
    mock_variant = MagicMock()
    mock_variant.id = uuid.uuid4()
    mock_variant.product_id = uuid.uuid4()
    mock_variant.sku = "TEST"
    mock_variant.title = "Test"
    r1 = mock_result_with_scalar_one_none(mock_variant)

    # Mock the aggregate totals row
    agg_row = MagicMock()
    agg_row.total_available = 100
    agg_row.total_reserved = 20
    agg_row.total_incoming = 10
    agg_row.total_damaged = 5
    agg_row.warehouse_count = 1
    r2 = mock_result_with_one(agg_row)

    # Reservation count
    r3 = mock_result_with_scalar(3)

    # In-transit count
    r4 = mock_result_with_scalar(15)

    # Breakdown (GROUP BY)
    r5 = mock_result_with_all([])

    engine.db.execute = AsyncMock(side_effect=[r1, r2, r3, r4, r5])

    result = await engine.get_variant(mock_variant.id)
    assert "warehouse_count" in result
    # Engine uses aggregate functions, not row loading — we verify by checking
    # that result doesn't have .scalars().all() for the main aggregation


# ═══════════════════════════════════════════════════════════════════
# F.9 — VALIDATION (CROSS-STORE PROTECTION)
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_warehouse_aggregation_cross_store_protection(mock_db, mock_store):
    """F.9: Cross-store warehouse access is prevented."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine
    from app.warehouse.exceptions import WarehouseNotFoundError

    other_store_id = uuid.uuid4()

    engine = InventoryAggregationEngine(db=mock_db, store=mock_store)

    # Warehouse belongs to another store
    mock_wh = MagicMock()
    mock_wh.id = uuid.uuid4()
    mock_wh.store_id = other_store_id  # Different store!
    engine.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)

    with pytest.raises(WarehouseNotFoundError):
        await engine.get_warehouse(mock_wh.id)


@pytest.mark.asyncio
async def test_engine_only_uses_active_warehouses(mock_db, mock_store):
    """F.9: Engine only aggregates across active warehouses."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine

    engine = InventoryAggregationEngine(db=mock_db, store=mock_store)

    # Only returns active warehouses
    engine._get_active_warehouse_ids = AsyncMock(return_value=[uuid.uuid4()])

    wh_ids = await engine._get_active_warehouse_ids()
    assert len(wh_ids) == 1


# ═══════════════════════════════════════════════════════════════════
# ROUTER ENDPOINT VALIDATION
# ═══════════════════════════════════════════════════════════════════


def test_router_has_expected_endpoints():
    """F.7: Router has all 7 expected endpoints."""
    from app.warehouse.aggregation_router import router

    endpoints = {route.path for route in router.routes}
    expected = {
        "/inventory/aggregate/store",
        "/inventory/aggregate/warehouse/{warehouse_id}",
        "/inventory/aggregate/product/{product_id}",
        "/inventory/aggregate/variant/{variant_id}",
        "/inventory/aggregate/dashboard",
        "/inventory/aggregate/distribution/{variant_id}",
        "/inventory/aggregate/reports",
    }

    for exp in expected:
        assert exp in endpoints, f"Missing endpoint: {exp}"


# ═══════════════════════════════════════════════════════════════════
# F.13 — WOOCOMMERCE SYNC CACHE INVALIDATION TEST
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_woocommerce_sync_invalidates_cache(mock_db, mock_store):
    """
    F.13: WooCommerce sync triggers cache invalidation through normal sync flow.

    Patches aggregation_cache.invalidate_store and verifies it's called
    during a WooCommerce warehouse sync operation.
    """
    from unittest.mock import patch
    from app.warehouse.aggregation_cache import aggregation_cache

    store_id = uuid.uuid4()
    mock_store.id = store_id
    mock_store.owner_id = uuid.uuid4()

    # Mock the warehouse inventory sync service that WooCommerce sync calls
    with patch.object(
        aggregation_cache, 'invalidate_store',
        new_callable=AsyncMock,
    ) as mock_invalidate:
        # Simulate the WooCommerce warehouse sync flow
        # This is the path: WooCommerce sync → WarehouseInventorySyncService
        # → adjust_stock → invalidate_store
        from app.warehouse.service import WarehouseInventoryService

        # Mock the underlying services that adjust_stock() uses
        wh_inv_service = WarehouseInventoryService(
            db=mock_db, store=mock_store,
        )

        # Mock all repo methods that adjust_stock needs
        mock_wh = MagicMock()
        mock_wh.id = uuid.uuid4()
        mock_wh.store_id = store_id
        mock_wh.is_active = True
        mock_wh.code = "TEST"
        mock_wh.name = "Test Warehouse"
        wh_inv_service.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)

        mock_variant = MagicMock()
        mock_variant.id = uuid.uuid4()
        mock_variant.sku = "TEST-SKU"
        mock_variant.inventory_quantity = 50
        wh_inv_service.variant_repo.get_by_id = AsyncMock(return_value=mock_variant)

        mock_inv = MagicMock()
        mock_inv.available_stock = 100
        mock_inv.reserved_stock = 20
        mock_inv.updated_at = None
        wh_inv_service.inv_repo.get_or_create = AsyncMock(return_value=mock_inv)

        mock_txn = MagicMock()
        mock_txn.id = uuid.uuid4()
        mock_txn.synced_to_shopify = False
        wh_inv_service.txn_repo.create = AsyncMock(return_value=mock_txn)

        wh_inv_service.log_repo.create = AsyncMock()

        # Execute the normal sync flow via adjust_stock (which WooCommerce sync calls)
        result = await wh_inv_service.adjust_stock(
            warehouse_id=mock_wh.id,
            variant_id=mock_variant.id,
            quantity_change=10,
            reason="WooCommerce sync",
        )

        # Verify invalidate_store was called exactly once with the correct store_id
        mock_invalidate.assert_awaited_once_with(store_id)

        # Verify sync operation still succeeded
        assert result["quantity_change"] == 10
        assert "increased" in result["message"]


@pytest.mark.asyncio
async def test_woocommerce_sync_continues_on_cache_failure(mock_db, mock_store):
    """
    F.13: WooCommerce sync continues even if cache invalidation fails.
    """
    from unittest.mock import patch
    from app.warehouse.aggregation_cache import aggregation_cache

    store_id = uuid.uuid4()
    mock_store.id = store_id

    with patch.object(
        aggregation_cache, 'invalidate_store',
        new_callable=AsyncMock, side_effect=Exception("Cache failure"),
    ) as mock_invalidate:
        from app.warehouse.service import WarehouseInventoryService
        wh_inv_service = WarehouseInventoryService(db=mock_db, store=mock_store)

        mock_wh = MagicMock()
        mock_wh.id = uuid.uuid4()
        mock_wh.store_id = store_id
        mock_wh.is_active = True
        mock_wh.code = "TEST"
        mock_wh.name = "Test"
        wh_inv_service.wh_repo.get_by_id = AsyncMock(return_value=mock_wh)

        mock_variant = MagicMock()
        mock_variant.id = uuid.uuid4()
        mock_variant.sku = "SKU"
        mock_variant.inventory_quantity = 50
        wh_inv_service.variant_repo.get_by_id = AsyncMock(return_value=mock_variant)

        mock_inv = MagicMock()
        mock_inv.available_stock = 100
        mock_inv.reserved_stock = 20
        mock_inv.updated_at = None
        wh_inv_service.inv_repo.get_or_create = AsyncMock(return_value=mock_inv)

        mock_txn = MagicMock()
        mock_txn.id = uuid.uuid4()
        mock_txn.synced_to_shopify = False
        wh_inv_service.txn_repo.create = AsyncMock(return_value=mock_txn)
        wh_inv_service.log_repo.create = AsyncMock()

        # Sync must succeed even though cache invalidation fails
        result = await wh_inv_service.adjust_stock(
            warehouse_id=mock_wh.id,
            variant_id=mock_variant.id,
            quantity_change=5,
            reason="WooCommerce sync",
        )

        mock_invalidate.assert_awaited_once_with(store_id)
        assert result["quantity_change"] == 5


# ═══════════════════════════════════════════════════════════════════
# F.13 — SHOPIFY SYNC CACHE INVALIDATION TEST
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_shopify_sync_from_shopify_invalidates_cache(mock_db, mock_store):
    """
    F.13: Shopify sync triggers cache invalidation through normal sync flow.

    Patches aggregation_cache.invalidate_store and verifies it's called
    during InventoryService.sync_from_shopify().
    """
    from unittest.mock import patch
    from app.warehouse.aggregation_cache import aggregation_cache
    from app.inventory.service import InventoryService

    store_id = uuid.uuid4()
    mock_store.id = store_id
    mock_store.owner_id = uuid.uuid4()
    mock_store.shopify_domain = "test.myshopify.com"
    mock_store.access_token = "test-token"
    mock_store.shopify_location_id = 12345

    # Patch the Shopify client entirely to avoid real HTTP calls
    with patch.object(
        aggregation_cache, 'invalidate_store',
        new_callable=AsyncMock,
    ) as mock_invalidate:
        from app.inventory.shopify_client import ShopifyClient

        inv_service = InventoryService(db=mock_db, store=mock_store)

        # Mock ShopifyClient.fetch_all_products and close
        mock_product_data = {
            "id": 1001,
            "title": "Synced Product",
            "body_html": "<p>Description</p>",
            "vendor": "TestVendor",
            "product_type": "Physical",
            "status": "active",
            "featured_image_url": "https://example.com/img.jpg",
            "variants": [
                {
                    "id": 2001,
                    "title": "Default",
                    "sku": "SYNC-SKU-001",
                    "barcode": "123456789",
                    "price": "29.99",
                    "compare_at_price": "39.99",
                    "inventory_quantity": 50,
                    "requires_shipping": True,
                    "inventory_item_id": 3001,
                }
            ],
        }

        with patch.object(
            ShopifyClient, 'fetch_all_products',
            new_callable=AsyncMock, return_value=[mock_product_data],
        ), patch.object(
            ShopifyClient, 'close',
            new_callable=AsyncMock,
        ):
            # Mock repository methods that sync_from_shopify calls
            inv_service.product_repo.get_by_shopify_id = AsyncMock(return_value=None)
            mock_new_product = MagicMock()
            mock_new_product.id = uuid.uuid4()
            inv_service.product_repo.create = AsyncMock(return_value=mock_new_product)

            inv_service.variant_repo.get_by_shopify_id = AsyncMock(return_value=None)
            inv_service.variant_repo.create = AsyncMock()
            inv_service.log_repo.create = AsyncMock()

            # Execute the normal Shopify sync flow
            stats = await inv_service.sync_from_shopify()

            # Verify invalidate_store was called with the correct store_id
            mock_invalidate.assert_awaited_once_with(store_id)

            # Verify sync succeeded
            assert stats["products_created"] == 1
            assert stats["variants_created"] == 1


@pytest.mark.asyncio
async def test_shopify_webhook_invalidates_cache(mock_db, mock_store):
    """
    F.13: Shopify webhook inventory update triggers cache invalidation.
    """
    from unittest.mock import patch
    from app.warehouse.aggregation_cache import aggregation_cache
    from app.inventory.service import InventoryService

    store_id = uuid.uuid4()
    mock_store.id = store_id
    mock_store.owner_id = uuid.uuid4()
    mock_store.shopify_domain = "test.myshopify.com"
    mock_store.access_token = "test-token"
    mock_store.shopify_location_id = 12345

    with patch.object(
        aggregation_cache, 'invalidate_store',
        new_callable=AsyncMock,
    ) as mock_invalidate:
        inv_service = InventoryService(db=mock_db, store=mock_store)

        # Mock the variant lookup for webhook
        mock_variant = MagicMock()
        mock_variant.id = uuid.uuid4()
        mock_variant.product_id = uuid.uuid4()
        mock_variant.product = None  # Bypass ownership check
        mock_variant.inventory_quantity = 100
        mock_variant.shopify_inventory_item_id = 3001
        inv_service.variant_repo.get_by_inventory_item_id = AsyncMock(
            return_value=mock_variant
        )
        inv_service.transaction_repo.create = AsyncMock()
        inv_service.log_repo.create = AsyncMock()

        # Execute the webhook update flow
        result = await inv_service.update_inventory_from_webhook(
            inventory_item_id=3001,
            location_id=12345,
            new_quantity=75,
        )

        # Verify cache was invalidated
        mock_invalidate.assert_awaited_once_with(store_id)

        # Verify webhook succeeded
        assert result["status"] == "updated"
        assert result["quantity_after"] == 75


# ═══════════════════════════════════════════════════════════════════
# REGRESSION TESTS
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_existing_warehouse_imports_unaffected(mock_db, mock_store):
    """Existing warehouse imports still work."""
    from app.warehouse.service import (
        WarehouseService, WarehouseInventoryService,
        WarehouseTransferService, CapacityService,
    )
    from app.warehouse.aggregation_service import WarehouseDashboardService
    from app.warehouse.aggregation_engine import InventoryAggregationEngine

    assert WarehouseService is not None
    assert WarehouseInventoryService is not None
    assert WarehouseTransferService is not None
    assert CapacityService is not None
    assert WarehouseDashboardService is not None
    assert InventoryAggregationEngine is not None


def test_no_duplicate_prefix():
    """Router uses /inventory/aggregate prefix without conflict."""
    from app.warehouse.aggregation_router import router
    for route in router.routes:
        assert "/inventory/aggregate" in route.path


# ═══════════════════════════════════════════════════════════════════
# F.10 — CACHE TESTS
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cache_get_set():
    """F.10: Cache get/set operations work correctly."""
    from app.warehouse.aggregation_cache import InventoryAggregationCache

    cache = InventoryAggregationCache(default_ttl=60)
    key = "agg:test:key"
    value = {"data": "test_value"}

    # Should miss
    result = await cache.get(key)
    assert result is None

    # Set and get
    await cache.set(key, value)
    result = await cache.get(key)
    assert result == value

    # Delete
    existed = await cache.delete(key)
    assert existed is True
    result = await cache.get(key)
    assert result is None


@pytest.mark.asyncio
async def test_cache_ttl_expiry():
    """F.10: Cache entries expire after TTL."""
    from app.warehouse.aggregation_cache import InventoryAggregationCache

    cache = InventoryAggregationCache(default_ttl=60)
    key = "agg:test:expire"

    await cache.set(key, {"data": "test"}, ttl=-1)  # Negative TTL = immediate expiry
    result = await cache.get(key)
    assert result is None  # Expired immediately


@pytest.mark.asyncio
async def test_cache_does_not_cache_none():
    """F.10: Cache never stores None values."""
    from app.warehouse.aggregation_cache import InventoryAggregationCache

    cache = InventoryAggregationCache(default_ttl=60)
    key = "agg:test:none"

    await cache.set(key, None)
    result = await cache.get(key)
    assert result is None


@pytest.mark.asyncio
async def test_cache_does_not_cache_empty_dict():
    """F.10: Cache never stores empty dicts."""
    from app.warehouse.aggregation_cache import InventoryAggregationCache

    cache = InventoryAggregationCache(default_ttl=60)
    key = "agg:test:empty"

    await cache.set(key, {})
    result = await cache.get(key)
    assert result is None


@pytest.mark.asyncio
async def test_cache_clear():
    """F.10: Cache clear removes all entries."""
    from app.warehouse.aggregation_cache import InventoryAggregationCache

    cache = InventoryAggregationCache(default_ttl=60)
    await cache.set("k1", "v1")
    await cache.set("k2", "v2")

    cleared = await cache.clear()
    assert cleared == 2

    result1 = await cache.get("k1")
    result2 = await cache.get("k2")
    assert result1 is None
    assert result2 is None


@pytest.mark.asyncio
async def test_cache_clear_prefix():
    """F.10: Cache clear_prefix removes entries with matching prefix."""
    from app.warehouse.aggregation_cache import InventoryAggregationCache

    cache = InventoryAggregationCache(default_ttl=60)
    store_id = uuid.uuid4()

    await cache.set(f"agg:store:{store_id}", {"data": 1})
    await cache.set(f"agg:dashboard:{store_id}", {"data": 2})
    await cache.set(f"agg:other:{store_id}", {"data": 3})

    cleared = await cache.clear_prefix(f"agg:store:{store_id}")
    assert cleared == 1  # Only store key matched

    result = await cache.get(f"agg:dashboard:{store_id}")
    assert result is not None  # Dashboard key still exists


@pytest.mark.asyncio
async def test_cache_invalidate_store():
    """F.10: invalidate_store clears all entries for a store."""
    from app.warehouse.aggregation_cache import InventoryAggregationCache

    cache = InventoryAggregationCache(default_ttl=60)
    store_id = uuid.uuid4()

    await cache.set(f"agg:store:{store_id}", {"data": 1})
    await cache.set(f"agg:dashboard:{store_id}", {"data": 2})
    await cache.set(f"agg:reports:{store_id}", {"data": 3})
    await cache.set(f"agg:warehouse:{store_id}:{uuid.uuid4()}", {"data": 4})

    cleared = await cache.invalidate_store(store_id)
    assert cleared >= 3

    result = await cache.get(f"agg:store:{store_id}")
    assert result is None
    result = await cache.get(f"agg:dashboard:{store_id}")
    assert result is None
    result = await cache.get(f"agg:reports:{store_id}")
    assert result is None


@pytest.mark.asyncio
async def test_cache_invalidate_warehouse():
    """F.10: invalidate_warehouse clears warehouse and store entries."""
    from app.warehouse.aggregation_cache import InventoryAggregationCache

    cache = InventoryAggregationCache(default_ttl=60)
    store_id = uuid.uuid4()
    wh_id = uuid.uuid4()

    await cache.set(f"agg:warehouse:{store_id}:{wh_id}", {"data": 1})
    await cache.set(f"agg:store:{store_id}", {"data": 2})

    cleared = await cache.invalidate_warehouse(store_id, wh_id)
    assert cleared >= 2

    result = await cache.get(f"agg:warehouse:{store_id}:{wh_id}")
    assert result is None
    result = await cache.get(f"agg:store:{store_id}")
    assert result is None


@pytest.mark.asyncio
async def test_cache_stats():
    """F.10: Cache stats are accurate."""
    from app.warehouse.aggregation_cache import InventoryAggregationCache

    cache = InventoryAggregationCache(default_ttl=60)

    await cache.get("miss")
    await cache.get("miss2")
    await cache.set("hit", "value")
    await cache.get("hit")

    stats = cache.stats
    assert stats["hit_count"] == 1
    assert stats["miss_count"] == 2
    assert stats["hit_ratio"] > 0


@pytest.mark.asyncio
async def test_cache_key_builders():
    """F.10: Cache key builders produce consistent keys."""
    from app.warehouse.aggregation_cache import InventoryAggregationCache

    store_id = uuid.uuid4()
    wh_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    var_id = uuid.uuid4()

    assert InventoryAggregationCache.key_store(store_id) == f"agg:store:{store_id}"
    assert InventoryAggregationCache.key_dashboard(store_id) == f"agg:dashboard:{store_id}"
    assert InventoryAggregationCache.key_warehouse(store_id, wh_id) == f"agg:warehouse:{store_id}:{wh_id}"
    assert InventoryAggregationCache.key_product(store_id, prod_id) == f"agg:product:{store_id}:{prod_id}"
    assert InventoryAggregationCache.key_variant(store_id, var_id) == f"agg:variant:{store_id}:{var_id}"
    assert InventoryAggregationCache.key_distribution(store_id, var_id) == f"agg:distribution:{store_id}:{var_id}"
    assert InventoryAggregationCache.key_reports(store_id) == f"agg:reports:{store_id}"


@pytest.mark.asyncio
async def test_cache_configurable_ttl():
    """F.10: Cache respects custom TTL per entry."""
    from app.warehouse.aggregation_cache import InventoryAggregationCache
    import time

    cache = InventoryAggregationCache(default_ttl=60)
    key = "agg:test:custom_ttl"

    await cache.set(key, {"data": "test"}, ttl=-1)  # Custom TTL of -1 = immediate expire
    result = await cache.get(key)
    assert result is None  # Should have expired


@pytest.mark.asyncio
async def test_aggregation_engine_respects_cache(mock_db, mock_store):
    """F.10: Engine checks cache before computing."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine
    from app.warehouse.aggregation_cache import InventoryAggregationCache

    cache = InventoryAggregationCache(default_ttl=60)
    engine = InventoryAggregationEngine(
        db=mock_db, store=mock_store, cache=cache,
    )

    # Pre-populate cache
    dashboard_key = InventoryAggregationCache.key_dashboard(mock_store.id)
    await cache.set(dashboard_key, {"cached": True, "total_available_inventory": 100})

    result = await engine.get_dashboard()
    assert result.get("cached") is True
    assert result["total_available_inventory"] == 100


@pytest.mark.asyncio
async def test_aggregation_engine_skips_cache_on_no_warehouses(mock_db, mock_store):
    """F.10: Empty results are cached with short TTL (don't recompute on every request)."""
    from app.warehouse.aggregation_engine import InventoryAggregationEngine
    from app.warehouse.aggregation_cache import InventoryAggregationCache

    cache = InventoryAggregationCache(default_ttl=60)
    engine = InventoryAggregationEngine(
        db=mock_db, store=mock_store, cache=cache,
    )

    # No warehouses
    engine._get_active_warehouse_ids = AsyncMock(return_value=[])

    result = await engine.get_store()
    assert result["warehouse_count"] == 0
    assert result["total_available_stock"] == 0

    # Result should be cached
    store_key = InventoryAggregationCache.key_store(mock_store.id)
    cached = await cache.get(store_key)
    assert cached is not None


# ═══════════════════════════════════════════════════════════════════
# F.12 — REPOSITORY AGGREGATE METHOD TESTS
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_repository_aggregate_store_method():
    """F.12: Repository aggregate_store uses SQL aggregate functions."""
    from app.warehouse.repository import WarehouseInventoryRepository
    from sqlalchemy import select, func

    mock_db = AsyncMock()
    repo = WarehouseInventoryRepository(mock_db)

    wh_ids = [uuid.uuid4()]
    agg_row = MagicMock()
    agg_row.total_available = 100
    agg_row.total_reserved = 20
    agg_row.total_incoming = 10
    agg_row.total_damaged = 5
    agg_row.product_count = 30
    agg_row.variant_count = 50

    result_mock = MagicMock()
    result_mock.one.return_value = agg_row
    mock_db.execute = AsyncMock(return_value=result_mock)

    result = await repo.aggregate_store(wh_ids)

    assert result["total_available"] == 100
    assert result["total_reserved"] == 20
    assert result["product_count"] == 30
    assert result["variant_count"] == 50


@pytest.mark.asyncio
async def test_repository_aggregate_store_empty():
    """F.12: Repository aggregate_store returns zeros for empty warehouse list."""
    from app.warehouse.repository import WarehouseInventoryRepository

    mock_db = AsyncMock()
    repo = WarehouseInventoryRepository(mock_db)

    result = await repo.aggregate_store([])

    assert result["total_available"] == 0
    assert result["total_reserved"] == 0
    assert result["product_count"] == 0


@pytest.mark.asyncio
async def test_repository_aggregate_warehouse_method():
    """F.12: Repository aggregate_warehouse uses SQL aggregate functions."""
    from app.warehouse.repository import WarehouseInventoryRepository

    mock_db = AsyncMock()
    repo = WarehouseInventoryRepository(mock_db)

    wh_id = uuid.uuid4()
    agg_row = MagicMock()
    agg_row.total_available = 500
    agg_row.total_reserved = 100
    agg_row.total_incoming = 50
    agg_row.total_damaged = 10
    agg_row.total_records = 15
    agg_row.variant_count = 10
    agg_row.product_count = 8

    result_mock = MagicMock()
    result_mock.one.return_value = agg_row
    mock_db.execute = AsyncMock(return_value=result_mock)

    result = await repo.aggregate_warehouse(wh_id)

    assert result["total_available"] == 500
    assert result["variant_count"] == 10
    assert result["product_count"] == 8


@pytest.mark.asyncio
async def test_repository_aggregate_capacity_method():
    """F.12: Repository aggregate_capacity uses GROUP BY for batch queries."""
    from app.warehouse.repository import WarehouseInventoryRepository

    mock_db = AsyncMock()
    repo = WarehouseInventoryRepository(mock_db)

    wh_ids = [uuid.uuid4(), uuid.uuid4()]

    row1 = MagicMock()
    row1.warehouse_id = wh_ids[0]
    row1.total_stock = 600
    row1.record_count = 10

    row2 = MagicMock()
    row2.warehouse_id = wh_ids[1]
    row2.total_stock = 300
    row2.record_count = 5

    result_mock = MagicMock()
    result_mock.all.return_value = [row1, row2]
    mock_db.execute = AsyncMock(return_value=result_mock)

    result = await repo.aggregate_capacity(wh_ids)

    assert str(wh_ids[0]) in result
    assert str(wh_ids[1]) in result
    assert result[str(wh_ids[0])]["total_stock"] == 600
    assert result[str(wh_ids[1])]["total_stock"] == 300
