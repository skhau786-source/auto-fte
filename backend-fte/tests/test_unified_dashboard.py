"""
Comprehensive tests for Phase 7 — Unified Dashboard.

Covers:
- Schema validation
- Service orchestration
- Router registration
- Import validation
- Error resilience (each phase section fails independently)
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ═══════════════════════════════════════════════════════════════════
# SCHEMA IMPORT & STRUCTURE TESTS
# ═══════════════════════════════════════════════════════════════════


def test_unified_schema_imports():
    """Unified dashboard schema imports correctly."""
    from app.dashboard.unified_schema import (
        UnifiedDashboardResponse,
        InventorySummaryWidget,
        ReservationSummaryWidget,
        AllocationSummaryWidget,
        OrderIntegrationSummaryWidget,
        AggregationSummaryWidget,
    )
    assert UnifiedDashboardResponse is not None
    assert InventorySummaryWidget is not None
    assert ReservationSummaryWidget is not None
    assert AllocationSummaryWidget is not None
    assert OrderIntegrationSummaryWidget is not None
    assert AggregationSummaryWidget is not None


def test_unified_dashboard_response_has_all_sections():
    """UnifiedDashboardResponse contains all phase sections (store-centric)."""
    from app.dashboard.unified_schema import UnifiedDashboardResponse

    resp = UnifiedDashboardResponse(store_id=str(uuid.uuid4()))

    assert hasattr(resp, "store_id")
    assert hasattr(resp, "generated_at")
    assert hasattr(resp, "inventory")
    assert hasattr(resp, "reservation")
    assert hasattr(resp, "allocation")
    assert hasattr(resp, "order_integration")
    assert hasattr(resp, "aggregation")

    # All sections should have default factory values (not None)
    assert resp.inventory.total_products == 0
    assert resp.reservation.active_reservations == 0
    assert resp.allocation.allocation_strategy == "default"
    assert resp.order_integration.orders_waiting_allocation == 0
    assert resp.aggregation.total_available_inventory == 0


def test_inventory_summary_widget_fields():
    """Phase 1 widget has all required fields."""
    from app.dashboard.unified_schema import InventorySummaryWidget
    fields = {"total_products", "total_variants", "total_inventory_units",
              "total_inventory_value", "low_stock_count", "out_of_stock_count",
              "category_count"}
    widget = InventorySummaryWidget()
    for field in fields:
        assert hasattr(widget, field)


def test_reservation_summary_widget_fields():
    """Phase 3 widget has all required fields."""
    from app.dashboard.unified_schema import ReservationSummaryWidget
    fields = {"active_reservations", "reserved_stock_units", "expired_today",
              "reservation_success_rate", "reservations_by_source"}
    widget = ReservationSummaryWidget()
    for field in fields:
        assert hasattr(widget, field)


def test_allocation_summary_widget_fields():
    """Phase 4 widget has all required fields (store-centric)."""
    from app.dashboard.unified_schema import AllocationSummaryWidget
    fields = {"allocation_strategy", "total_allocated_units",
              "active_reservations", "orders_allocated",
              "allocation_success_rate"}
    widget = AllocationSummaryWidget()
    for field in fields:
        assert hasattr(widget, field)


def test_order_integration_summary_widget_fields():
    """Phase 5 widget has all required fields."""
    from app.dashboard.unified_schema import OrderIntegrationSummaryWidget
    fields = {"orders_waiting_allocation", "reserved_orders",
              "partially_fulfilled_orders", "committed_orders",
              "released_reservations", "allocation_success_rate",
              "reservation_success_rate"}
    widget = OrderIntegrationSummaryWidget()
    for field in fields:
        assert hasattr(widget, field)


def test_aggregation_summary_widget_fields():
    """Phase 6 widget has all required fields (store-centric)."""
    from app.dashboard.unified_schema import AggregationSummaryWidget
    fields = {"total_available_inventory", "total_reserved_inventory",
              "inventory_value", "low_stock_variants",
              "out_of_stock_variants", "active_reservations_count"}
    widget = AggregationSummaryWidget()
    for field in fields:
        assert hasattr(widget, field)


# ═══════════════════════════════════════════════════════════════════
# ROUTER IMPORT & REGISTRATION TESTS
# ═══════════════════════════════════════════════════════════════════


def test_router_imports():
    """Unified dashboard router imports correctly."""
    from app.dashboard.unified_router import router, get_unified_dashboard

    assert router is not None
    assert callable(get_unified_dashboard)


def test_router_has_unified_endpoint():
    """Router exposes GET /dashboard/unified."""
    from app.dashboard.unified_router import router

    paths = [route.path for route in router.routes]
    assert "/dashboard/unified" in paths


def test_router_registered_in_main():
    """Router is registered in the main FastAPI app.

    Traverses nested _IncludedRouter objects introduced by Starlette 0.40+.
    """
    from app.main import app

    found = False
    for route in app.routes:
        # Direct APIRoute objects
        if hasattr(route, 'path') and 'unified' in str(route.path):
            found = True
            break
        # _IncludedRouter objects — drill into original_router.routes
        inner = getattr(route, 'original_router', None)
        if inner is not None:
            for sub in getattr(inner, 'routes', []):
                if hasattr(sub, 'path') and 'unified' in str(sub.path):
                    found = True
                    break
        if found:
            break
    assert found, (
        f"No unified dashboard route found among {len(app.routes)} routes"
    )


# ═══════════════════════════════════════════════════════════════════
# SERVICE TESTS
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.id = uuid.uuid4()
    store.owner_id = uuid.uuid4()
    return store


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


@pytest.mark.asyncio
async def test_service_returns_unified_response(mock_db, mock_store, mock_user):
    """UnifiedDashboardService returns a properly structured response."""
    from app.dashboard.unified_service import UnifiedDashboardService

    service = UnifiedDashboardService(
        db=mock_db,
        store=mock_store,
        user_id=mock_user.id,
    )

    # Mock all internal methods
    service._get_inventory_summary = AsyncMock()
    service._get_reservation_summary = AsyncMock()
    service._get_allocation_summary = AsyncMock()
    service._get_order_integration_summary = AsyncMock()
    service._get_aggregation_summary = AsyncMock()

    result = await service.get_dashboard()

    assert result.store_id == str(mock_store.id)
    assert result.inventory is not None
    assert result.reservation is not None
    assert result.allocation is not None
    assert result.order_integration is not None
    assert result.aggregation is not None


@pytest.mark.asyncio
async def test_phase_failure_does_not_affect_others(mock_db, mock_store):
    """Each phase section failing doesn't crash the full dashboard."""
    from app.dashboard.unified_service import UnifiedDashboardService

    service = UnifiedDashboardService(db=mock_db, store=mock_store)

    # Mock Phases 3-6 to return valid data
    from app.dashboard.unified_schema import (
        ReservationSummaryWidget,
        AllocationSummaryWidget, OrderIntegrationSummaryWidget,
        AggregationSummaryWidget,
    )
    service._get_reservation_summary = AsyncMock(return_value=ReservationSummaryWidget(
        active_reservations=5,
    ))
    service._get_allocation_summary = AsyncMock(return_value=AllocationSummaryWidget(
        allocation_strategy="default",
    ))
    service._get_order_integration_summary = AsyncMock(return_value=OrderIntegrationSummaryWidget(
        committed_orders=10,
    ))
    service._get_aggregation_summary = AsyncMock(return_value=AggregationSummaryWidget(
        total_available_inventory=1000,
    ))

    # Mock Phase 1 to raise (has internal try/except, needs patch to force failure)
    with patch.object(service, '_get_inventory_summary',
                      side_effect=Exception("Inventory failed")):
        result = await service.get_dashboard()

    # Phase 1 failed - should have default zeros
    assert result.inventory.total_products == 0

    # Phases 3-6 should still have their values
    assert result.reservation.active_reservations == 5
    assert result.allocation.allocation_strategy == "default"
    assert result.order_integration.committed_orders == 10
    assert result.aggregation.total_available_inventory == 1000


@pytest.mark.asyncio
async def test_all_phases_fail_gracefully(mock_db, mock_store):
    """When all phases fail, dashboard returns empty defaults."""
    from app.dashboard.unified_service import UnifiedDashboardService

    service = UnifiedDashboardService(db=mock_db, store=mock_store)

    # Make the whole _build_all raise
    with patch.object(service, '_build_all', side_effect=Exception("Total failure")):
        result = await service.get_dashboard()

        assert result.store_id == str(mock_store.id)
        assert result.inventory.total_products == 0
        assert result.reservation.active_reservations == 0


# ═══════════════════════════════════════════════════════════════════
# PHASE 1 — INVENTORY SUMMARY SERVICE
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_inventory_summary_calls_dashboard_service(mock_db, mock_store):
    """_get_inventory_summary delegates to DashboardService."""
    from app.dashboard.unified_service import UnifiedDashboardService

    service = UnifiedDashboardService(db=mock_db, store=mock_store)

    # Patch DashboardService.get_dashboard
    from app.dashboard.dashboard_schema import (
        DashboardResponse, DashboardSummary, TodayTransactionSummary,
        SyncHealthSummary, WebhookHealthSummary,
    )

    mock_response = DashboardResponse(
        inventory_summary=DashboardSummary(
            total_products=50,
            total_variants=120,
            total_inventory_units=10000,
            low_stock_count=5,
            out_of_stock_count=3,
            category_count=8,
        ),
        today_transactions=TodayTransactionSummary(total=10),
        sync_health=SyncHealthSummary(),
        webhook_health=WebhookHealthSummary(),
        store_id=mock_store.id,
        store_domain="test.myshopify.com",
    )

    with patch(
        'app.dashboard.dashboard_service.DashboardService.get_dashboard',
        new_callable=AsyncMock, return_value=mock_response,
    ):
        result = await service._get_inventory_summary()

        assert result.total_products == 50
        assert result.total_variants == 120
        assert result.total_inventory_units == 10000
        assert result.low_stock_count == 5
        assert result.out_of_stock_count == 3
        assert result.category_count == 8


# ═══════════════════════════════════════════════════════════════════
# REGRESSION TESTS
# ═══════════════════════════════════════════════════════════════════


def test_existing_dashboard_imports_unaffected():
    """Existing dashboard imports still work after the store-centric pivot."""
    from app.dashboard.dashboard_service import DashboardService
    from app.dashboard.dashboard_schema import (
        DashboardResponse, DashboardSummary,
    )
    from app.inventory.aggregation_engine import InventoryAggregationEngine
    from app.inventory.reservation_service import ReservationService
    from app.inventory.allocation_service import AllocationService

    assert DashboardService is not None
    assert DashboardResponse is not None
    assert DashboardSummary is not None
    assert InventoryAggregationEngine is not None
    assert ReservationService is not None
    assert AllocationService is not None


def test_no_duplicate_routes_all():
    """Verify no duplicate route paths across all dashboard routers."""
    from app.dashboard.unified_router import router as unified_router
    from app.dashboard.dashboard import router as dashboard_router

    all_paths = []
    for r in [dashboard_router, unified_router]:
        all_paths.extend([route.path for route in r.routes])

    # Check for duplicates
    duplicates = {p for p in all_paths if all_paths.count(p) > 1}
    assert not duplicates, f"Duplicate routes found: {duplicates}"
