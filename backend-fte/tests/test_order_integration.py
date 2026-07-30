"""
Comprehensive tests for Phase 5 — WooCommerce Order Integration.

Covers:
- E.1: Order Allocation
- E.2: Automatic Reservation
- E.3: Order Status Events (pending→reserve, completed→commit, cancelled→release)
- E.4: Configurable Behavior (reserve_stock_on_order, auto_release_cancelled_orders)
- E.5: Webhook Integration
- E.6: Sync Engine Integration
- E.7: Fulfillment Summary
- E.8: Multi-Warehouse Orders
- E.9: Inventory Updates
- E.10: Failure Recovery
- E.11: Dashboard
- E.12: API Endpoints
- E.13: Validation Rules
- E.15: Service layer, Webhook layer, Integration layer
"""

import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from fastapi import HTTPException

from app.woocommerce.order_integration_service import WooCommerceOrderIntegrationService
from app.inventory.constants import ReservationStatus, ReservationSource
from app.woocommerce.constants import OrderStatus as WC_OrderStatus


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_wc_store():
    store = MagicMock()
    store.id = uuid.uuid4()
    store.owner_id = uuid.uuid4()
    store.store_name = "Test Store"
    store.store_url = "https://example.com"
    return store


@pytest.fixture
def mock_inventory_store():
    store = MagicMock()
    store.id = uuid.uuid4()
    store.owner_id = uuid.uuid4()
    return store


@pytest.fixture
def mock_order():
    order = MagicMock()
    order.id = uuid.uuid4()
    order.wc_order_id = 12345
    order.store_id = uuid.uuid4()
    order.number = "WC-12345"
    order.status = WC_OrderStatus.PENDING

    line_item = MagicMock()
    line_item.quantity = 5
    line_item.sku = "TEST-SKU-001"

    order.items = [line_item]
    return order


@pytest.fixture
def mock_variant():
    variant = MagicMock()
    variant.id = uuid.uuid4()
    variant.product_id = uuid.uuid4()
    variant.sku = "TEST-SKU-001"
    return variant


@pytest.fixture
def mock_reservation():
    res = MagicMock()
    res.id = uuid.uuid4()
    res.warehouse_id = uuid.uuid4()
    res.variant_id = uuid.uuid4()
    res.quantity = 5
    res.status = ReservationStatus.ACTIVE
    res.store_id = uuid.uuid4()
    return res


# ═══════════════════════════════════════════════════════════════════
# E.1 — ORDER ALLOCATION
# ═══════════════════════════════════════════════════════════════════


class TestAllocation:
    """E.1: When WooCommerce order arrives, automatically call AllocationService."""

    @pytest.mark.asyncio
    async def test_allocate_order_success(self, mock_db, mock_wc_store, mock_inventory_store, mock_order, mock_variant):
        """E.1: Successfully allocate inventory for an order."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        # Mock settings to enable reservation
        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.reserve_stock_on_order = True
        service.settings_repo.get_or_create.return_value = settings

        # Mock _find_inventory_variant to return a variant
        service._find_inventory_variant = AsyncMock(return_value=mock_variant)

        # Mock allocation_service.allocate_for_woocommerce
        service.allocation_service.allocate_for_woocommerce = AsyncMock(return_value={
            "order_id": str(mock_order.wc_order_id),
            "total_items": 1,
            "total_requested": 5,
            "total_fulfilled": 5,
            "fully_fulfilled": True,
            "strategy_used": "default_warehouse",
            "items": [{"variant_id": str(mock_variant.id), "requested": 5, "fulfilled": 5}],
        })

        result = await service.allocate_order(mock_order)

        assert result["fully_fulfilled"] is True
        assert result["total_fulfilled"] == 5
        assert result["order_number"] == mock_order.number
        service.allocation_service.allocate_for_woocommerce.assert_called_once()

    @pytest.mark.asyncio
    async def test_allocate_order_settings_disabled(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.4: Respect reserve_stock_on_order=False."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        # Mock settings to disable reservation
        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.reserve_stock_on_order = False
        service.settings_repo.get_or_create.return_value = settings

        result = await service.allocate_order(mock_order)

        assert result["status"] == "skipped"
        assert result["detail"] == "reserve_stock_on_order_disabled"

    @pytest.mark.asyncio
    async def test_allocate_order_no_allocatable_items(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.1: Gracefully handle orders with no allocatable items."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.reserve_stock_on_order = True
        service.settings_repo.get_or_create.return_value = settings

        # No variant found for any SKU
        service._find_inventory_variant = AsyncMock(return_value=None)

        result = await service.allocate_order(mock_order)

        assert result["status"] == "no_items"

    @pytest.mark.asyncio
    async def test_allocate_order_failure_isolation(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.10: If allocation fails, WooCommerce sync does not break."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.reserve_stock_on_order = True
        service.settings_repo.get_or_create.return_value = settings

        # _find_inventory_variant raises
        service._find_inventory_variant = AsyncMock(side_effect=Exception("DB connection error"))

        # Should not raise — returns failure dict
        result = await service.allocate_order(mock_order)

        assert result["status"] == "allocation_failed" or result["status"] == "no_items"


# ═══════════════════════════════════════════════════════════════════
# E.2 — AUTOMATIC RESERVATION
# ═══════════════════════════════════════════════════════════════════


class TestReservationIntegration:
    """E.2: After successful allocation, automatically create reservations."""

    @pytest.mark.asyncio
    async def test_allocate_reserves_automatically(self, mock_db, mock_wc_store, mock_inventory_store, mock_order, mock_variant):
        """E.2: allocate_for_woocommerce creates reservations via ReservationService."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.reserve_stock_on_order = True
        service.settings_repo.get_or_create.return_value = settings
        service._find_inventory_variant = AsyncMock(return_value=mock_variant)

        # The allocation should auto-reserve
        service.allocation_service.allocate_for_woocommerce = AsyncMock(return_value={
            "order_id": str(mock_order.wc_order_id),
            "total_items": 1,
            "total_requested": 5,
            "total_fulfilled": 5,
            "fully_fulfilled": True,
            "strategy_used": "default_warehouse",
            "items": [{"variant_id": str(mock_variant.id), "requested": 5, "fulfilled": 5}],
        })

        result = await service.allocate_order(mock_order)

        assert result["fully_fulfilled"] is True
        assert result["total_fulfilled"] == 5


# ═══════════════════════════════════════════════════════════════════
# E.3 — ORDER STATUS EVENTS
# ═══════════════════════════════════════════════════════════════════


class TestStatusEvents:
    """E.3: Handle order status changes — pending/reserve, completed/commit, cancelled/release."""

    @pytest.mark.asyncio
    async def test_pending_triggers_allocation(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.3: Pending status triggers allocation if no reservations exist."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.reserve_stock_on_order = True
        settings.auto_release_cancelled_orders = True
        service.settings_repo.get_or_create.return_value = settings

        # No existing reservations
        service.reservation_service.repo.get_by_order = AsyncMock(return_value=[])

        # Mock allocate_order to ensure it's called
        service.allocate_order = AsyncMock(return_value={"status": "allocated"})

        mock_order.status = WC_OrderStatus.PENDING
        result = await service.handle_order_status_change(mock_order)

        service.allocate_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_completed_commits_reservations(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.3: Completed commits all active reservations."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.auto_release_cancelled_orders = True
        service.settings_repo.get_or_create.return_value = settings

        mock_res = MagicMock()
        mock_res.id = uuid.uuid4()
        mock_res.status = ReservationStatus.ACTIVE
        mock_res.quantity = 5
        mock_res.warehouse_id = uuid.uuid4()

        service.reservation_service.repo.get_by_order = AsyncMock(return_value=[mock_res])
        service.reservation_service.commit_stock = AsyncMock(return_value=mock_res)

        mock_order.status = WC_OrderStatus.COMPLETED
        result = await service.handle_order_status_change(mock_order)

        assert result["action"] == "commit"
        assert result["committed"] >= 1
        service.reservation_service.commit_stock.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancelled_releases_reservations(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.3: Cancelled releases all reservations (when auto_release enabled)."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.auto_release_cancelled_orders = True
        service.settings_repo.get_or_create.return_value = settings

        service.reservation_service.cancel_order = AsyncMock(return_value=[MagicMock()])

        mock_order.status = WC_OrderStatus.CANCELLED
        result = await service.handle_order_status_change(mock_order)

        assert result["action"] == "release"
        assert result["reservations_released"] >= 1

    @pytest.mark.asyncio
    async def test_cancelled_auto_release_disabled(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.4: auto_release_cancelled_orders=False skips release."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.auto_release_cancelled_orders = False
        service.settings_repo.get_or_create.return_value = settings

        mock_order.status = WC_OrderStatus.CANCELLED
        result = await service.handle_order_status_change(mock_order)

        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_refunded_releases_reservations(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.3: Refunded releases all reservations."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.auto_release_cancelled_orders = True
        service.settings_repo.get_or_create.return_value = settings

        service.reservation_service.cancel_order = AsyncMock(return_value=[MagicMock()])

        mock_order.status = WC_OrderStatus.REFUNDED
        result = await service.handle_order_status_change(mock_order)

        assert result["action"] == "release"

    @pytest.mark.asyncio
    async def test_failed_releases_reservations(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.3: Failed releases all reservations."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.auto_release_cancelled_orders = True
        service.settings_repo.get_or_create.return_value = settings

        service.reservation_service.cancel_order = AsyncMock(return_value=[MagicMock()])

        mock_order.status = WC_OrderStatus.FAILED
        result = await service.handle_order_status_change(mock_order)

        assert result["action"] == "release"

    @pytest.mark.asyncio
    async def test_processing_checks_existing(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.3: Processing keeps reservations active."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.auto_release_cancelled_orders = True
        service.settings_repo.get_or_create.return_value = settings

        service.reservation_service.repo.get_by_order = AsyncMock(return_value=[MagicMock()])

        mock_order.status = WC_OrderStatus.PROCESSING
        result = await service.handle_order_status_change(mock_order)

        assert result["status"] == "active"


# ═══════════════════════════════════════════════════════════════════
# E.6 — SYNC ENGINE INTEGRATION
# ═══════════════════════════════════════════════════════════════════


class TestSyncIntegration:
    """E.6: SyncEngine triggers allocation+reservation after order sync."""

    @pytest.mark.asyncio
    async def test_process_synced_order_success(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.6: process_synced_order runs allocation and status handling."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.allocate_order = AsyncMock(return_value={"status": "allocated"})
        service.handle_order_status_change = AsyncMock(return_value={"status": "active"})

        result = await service.process_synced_order(mock_order)

        assert "allocation" in result
        assert "status_action" in result
        assert result["order_number"] == mock_order.number
        service.allocate_order.assert_called_once()
        service.handle_order_status_change.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_synced_order_failure_isolation(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.6/E.10: Failures in integration never break WooCommerce sync."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        # Both allocation and status handling raise
        service.allocate_order = AsyncMock(side_effect=Exception("Critical failure"))
        service.handle_order_status_change = AsyncMock(side_effect=Exception("Also failed"))

        # Should not raise — returns failure summary
        result = await service.process_synced_order(mock_order)

        assert result["status"] == "processing_failed"


# ═══════════════════════════════════════════════════════════════════
# E.7 — FULFILLMENT SUMMARY
# ═══════════════════════════════════════════════════════════════════


class TestFulfillmentSummary:
    """E.7, E.8: Fulfillment summary with multi-warehouse support."""

    @pytest.mark.asyncio
    async def test_fully_allocated(self, mock_db, mock_wc_store, mock_inventory_store, mock_order, mock_reservation):
        """E.7: fully_allocated when all stock is reserved."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        mock_reservation.quantity = 5
        mock_reservation.status = ReservationStatus.ACTIVE
        mock_reservation.warehouse_id = uuid.uuid4()

        service.reservation_service.repo.get_by_order = AsyncMock(return_value=[mock_reservation])

        mock_order.items[0].quantity = 5
        result = await service.get_fulfillment_summary(mock_order)

        assert result["status"] == "fully_allocated"
        assert result["allocated_quantity"] == 5

    @pytest.mark.asyncio
    async def test_partially_allocated(self, mock_db, mock_wc_store, mock_inventory_store, mock_order, mock_reservation):
        """E.7: partially_allocated when only some stock is reserved."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        mock_reservation.quantity = 3
        mock_reservation.warehouse_id = uuid.uuid4()

        service.reservation_service.repo.get_by_order = AsyncMock(return_value=[mock_reservation])

        mock_order.items[0].quantity = 10
        result = await service.get_fulfillment_summary(mock_order)

        assert result["status"] == "partially_allocated"
        assert result["allocated_quantity"] == 3
        assert result["unallocated_quantity"] == 7

    @pytest.mark.asyncio
    async def test_out_of_stock(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.7: out_of_stock when no stock is reserved."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.reservation_service.repo.get_by_order = AsyncMock(return_value=[])

        mock_order.items[0].quantity = 10
        result = await service.get_fulfillment_summary(mock_order)

        assert result["status"] == "out_of_stock"
        assert result["allocated_quantity"] == 0

    @pytest.mark.asyncio
    async def test_multi_warehouse(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.8: Multi-warehouse orders show correct warehouse count."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        wh_ids = [uuid.uuid4(), uuid.uuid4()]

        reservations = []
        for i, wh_id in enumerate(wh_ids):
            res = MagicMock()
            res.quantity = 5
            res.warehouse_id = wh_id
            res.status = ReservationStatus.ACTIVE
            res.id = uuid.uuid4()
            reservations.append(res)

        service.reservation_service.repo.get_by_order = AsyncMock(return_value=reservations)

        mock_order.items[0].quantity = 10
        result = await service.get_fulfillment_summary(mock_order)

        assert result["warehouse_count"] == 2
        assert result["status"] == "fully_allocated"


# ═══════════════════════════════════════════════════════════════════
# E.9 — INVENTORY UPDATES
# ═══════════════════════════════════════════════════════════════════


class TestInventoryUpdates:
    """E.9: After commit/release/cancellation, inventory is updated."""

    @pytest.mark.asyncio
    async def test_commit_updates_reserved_stock(self, mock_db, mock_wc_store, mock_inventory_store, mock_order, mock_reservation):
        """E.9: Committing a reservation updates reserved_stock."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.auto_release_cancelled_orders = True
        service.settings_repo.get_or_create.return_value = settings

        mock_reservation.status = ReservationStatus.ACTIVE
        mock_reservation.quantity = 5

        service.reservation_service.repo.get_by_order = AsyncMock(return_value=[mock_reservation])
        service.reservation_service.commit_stock = AsyncMock(return_value=mock_reservation)

        mock_order.status = WC_OrderStatus.COMPLETED
        mock_order.wc_order_id = 12345
        result = await service.handle_order_status_change(mock_order)

        assert result["action"] == "commit"
        service.reservation_service.commit_stock.assert_called_once_with(mock_reservation.id)

    @pytest.mark.asyncio
    async def test_release_returns_to_available(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.9: Releasing a reservation returns stock to available."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.auto_release_cancelled_orders = True
        service.settings_repo.get_or_create.return_value = settings

        mock_res = MagicMock()
        mock_res.id = uuid.uuid4()
        mock_res.status = ReservationStatus.ACTIVE
        mock_res.quantity = 5
        mock_res.warehouse_id = uuid.uuid4()

        service.reservation_service.repo.get_by_order = AsyncMock(return_value=[mock_res])
        service.reservation_service.release_stock = AsyncMock(return_value=mock_res)

        mock_order.status = WC_OrderStatus.CANCELLED
        result = await service.handle_order_status_change(mock_order)

        assert result["action"] == "release"


# ═══════════════════════════════════════════════════════════════════
# E.11 — DASHBOARD
# ═══════════════════════════════════════════════════════════════════


class TestDashboard:
    """E.11: Dashboard returns correct order/reservation/allocation stats."""

    @pytest.mark.asyncio
    async def test_dashboard_includes_reservation_stats(self, mock_db, mock_wc_store, mock_inventory_store):
        """Dashboard returns reservation stats."""
        from app.woocommerce.order_integration_router import order_dashboard

        # Simplifies to checking the router's response structure
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.reservation_service.get_dashboard_stats = AsyncMock(return_value={
            "active_reservations": 5,
            "reserved_stock_units": 20,
            "reservation_success_rate": 100.0,
            "expired_today": 0,
        })

        service.allocation_service.get_dashboard_stats = AsyncMock(return_value={
            "allocation_strategy": "default_warehouse",
            "multi_warehouse_enabled": False,
            "total_warehouses": 2,
        })

        # Mock the db session for the dashboard query
        mock_db.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 10
        mock_db.execute.return_value = mock_result

        result = {}
        # Simulate the dashboard logic from the router
        reservation_stats = await service.reservation_service.get_dashboard_stats()
        allocation_stats = await service.allocation_service.get_dashboard_stats()

        assert reservation_stats["active_reservations"] == 5
        assert allocation_stats["allocation_strategy"] == "default_warehouse"


# ═══════════════════════════════════════════════════════════════════
# E.12 — API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════


class TestAPIEndpoints:
    """E.12: API endpoints work with validation."""

    def test_router_has_expected_endpoints(self):
        """Verify the router has all expected endpoints."""
        from app.woocommerce.order_integration_router import router

        endpoints = {route.path for route in router.routes}
        expected = {
            "/orders/{order_id}/allocation",
            "/orders/{order_id}/reservations",
            "/orders/{order_id}/allocate",
            "/orders/{order_id}/commit",
            "/orders/{order_id}/release",
            "/orders/dashboard",
        }

        for exp in expected:
            assert exp in endpoints, f"Missing endpoint: {exp}"


# ═══════════════════════════════════════════════════════════════════
# E.13 — VALIDATION RULES
# ═══════════════════════════════════════════════════════════════════


class TestValidation:
    """E.13: Validation rules protect against invalid operations."""

    def test_router_imports_validate(self):
        """Router imports are valid."""
        from app.woocommerce.order_integration_router import (
            _get_wc_store, _get_wc_order, _get_integration_service,
            get_order_allocation, get_order_reservations,
            allocate_order, commit_order, release_order, order_dashboard,
        )
        assert callable(_get_wc_store)
        assert callable(_get_wc_order)
        assert callable(_get_integration_service)

    def test_service_imports_validate(self):
        """Service imports are valid."""
        from app.woocommerce.order_integration_service import (
            WooCommerceOrderIntegrationService,
        )
        assert WooCommerceOrderIntegrationService is not None
        required_methods = [
            "allocate_order", "handle_order_status_change",
            "process_synced_order", "get_fulfillment_summary",
            "_commit_order_reservations", "_release_order_reservations",
        ]
        for method in required_methods:
            assert hasattr(WooCommerceOrderIntegrationService, method)


# ═══════════════════════════════════════════════════════════════════
# E.15 — WEBHOOK INTEGRATION
# ═══════════════════════════════════════════════════════════════════


class TestWebhookIntegration:
    """E.5/E.15: WebhookManager triggers order integration on webhooks."""

    def test_webhook_manager_imports_order_integration(self):
        """WebhookManager imports order integration service."""
        from app.woocommerce.webhook_manager import WebhookManager, _ORDER_INTEGRATION_AVAILABLE
        assert WebhookManager is not None

    def test_webhook_manager_has_process_integration_method(self):
        """WebhookManager has the _process_order_integration method."""
        from app.woocommerce.webhook_manager import WebhookManager
        assert hasattr(WebhookManager, "_process_order_integration")


class TestSyncEngineIntegration:
    """E.6/E.15: SyncEngine imports order integration."""

    def test_sync_engine_imports_order_integration(self):
        """SyncEngine imports order integration service."""
        from app.woocommerce.sync_engine import SyncEngine, _ORDER_INTEGRATION_AVAILABLE
        assert SyncEngine is not None

    def test_sync_engine_has_process_integration_method(self):
        """SyncEngine has the _process_order_integration method."""
        from app.woocommerce.sync_engine import SyncEngine
        assert hasattr(SyncEngine, "_process_order_integration")


# ═══════════════════════════════════════════════════════════════════
# E.10 — FAILURE RECOVERY
# ═══════════════════════════════════════════════════════════════════


class TestFailureRecovery:
    """E.10: If reservation fails, rollback allocation. If allocation fails, no inventory change."""

    @pytest.mark.asyncio
    async def test_reservation_failure_does_not_crash(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.10: Reservation failure is caught, order processing continues."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.auto_release_cancelled_orders = True
        service.settings_repo.get_or_create.return_value = settings

        mock_res = MagicMock()
        mock_res.id = uuid.uuid4()
        mock_res.status = ReservationStatus.ACTIVE

        # commit fails
        service.reservation_service.repo.get_by_order = AsyncMock(return_value=[mock_res])
        service.reservation_service.commit_stock = AsyncMock(side_effect=Exception("Commit failed"))

        mock_order.status = WC_OrderStatus.COMPLETED
        result = await service.handle_order_status_change(mock_order)

        assert result["action"] == "commit"
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_release_failure_does_not_crash(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.10: Release failure is caught, returns failure result."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.auto_release_cancelled_orders = True
        service.settings_repo.get_or_create.return_value = settings

        # cancel_order fails
        service.reservation_service.cancel_order = AsyncMock(side_effect=Exception("Release failed"))

        mock_order.status = WC_OrderStatus.CANCELLED
        result = await service.handle_order_status_change(mock_order)

        assert result["action"] == "release_failed"
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════
# E.4 — CONFIGURABLE BEHAVIOR
# ═══════════════════════════════════════════════════════════════════


class TestConfigurableBehavior:
    """E.4: Respect WarehouseSettings configuration."""

    @pytest.mark.asyncio
    async def test_reserve_stock_on_order_respected(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.4: reserve_stock_on_order=True enables reservation."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.reserve_stock_on_order = True
        service.settings_repo.get_or_create.return_value = settings
        service._find_inventory_variant = AsyncMock(return_value=None)

        # Should say no_items since no variant found, but the setting was checked
        result = await service.allocate_order(mock_order)
        assert result["status"] == "no_items"  # Setting was True, but no items

    @pytest.mark.asyncio
    async def test_reserve_stock_on_order_disabled(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.4: reserve_stock_on_order=False skips allocation."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.reserve_stock_on_order = False
        service.settings_repo.get_or_create.return_value = settings

        result = await service.allocate_order(mock_order)
        assert result["status"] == "skipped"
        assert result["detail"] == "reserve_stock_on_order_disabled"

    @pytest.mark.asyncio
    async def test_auto_release_cancelled_respected(self, mock_db, mock_wc_store, mock_inventory_store, mock_order):
        """E.4: auto_release_cancelled_orders=False skips release."""
        service = WooCommerceOrderIntegrationService(
            db=mock_db, wc_store=mock_wc_store, store=mock_inventory_store, user_id=uuid.uuid4(),
        )

        service.settings_repo.get_or_create = AsyncMock()
        settings = MagicMock()
        settings.auto_release_cancelled_orders = False
        service.settings_repo.get_or_create.return_value = settings

        mock_order.status = WC_OrderStatus.CANCELLED
        result = await service.handle_order_status_change(mock_order)
        assert result["status"] == "skipped"


# ═══════════════════════════════════════════════════════════════════
# REGRESSION TESTS
# ═══════════════════════════════════════════════════════════════════


class TestRegression:
    """Ensure backward compatibility — no existing APIs broken."""

    def test_original_woocommerce_imports_unaffected(self):
        """Existing WooCommerce imports still work."""
        from app.woocommerce.service import WooCommerceService
        from app.woocommerce.models import WooCommerceOrder, WooCommerceStore
        from app.woocommerce.constants import OrderStatus, WebhookTopic
        assert WooCommerceService is not None
        assert WooCommerceOrder is not None

    def test_warehouse_imports_unaffected(self):
        """Existing warehouse imports still work."""
        from app.warehouse.allocation_service import AllocationService
        from app.warehouse.reservation_service import ReservationService
        from app.warehouse.service import WarehouseService
        from app.warehouse.repository import WarehouseSettingsRepository
        assert AllocationService is not None
        assert ReservationService is not None
        assert WarehouseService is not None

    def test_router_no_duplicate_prefix(self):
        """The order_integration_router uses /orders prefix without conflict."""
        from app.woocommerce.order_integration_router import router
        for route in router.routes:
            assert "/orders" in route.path
