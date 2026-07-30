"""
Tests for Phase 2 Part B — Default Warehouse Configuration.

Covers:
- Repository: get_default, clear_default, set_default, ensure_single_default
- Service: get/set/clear default warehouse, settings, deactivate/delete clears default
- WooCommerce sync uses configured default, skips when no default
- Schema validation
- Model fields
"""

import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.warehouse.repository import WarehouseRepository
from app.warehouse.service import WarehouseService
from app.warehouse.schemas import (
    WarehouseSettingsOut, DefaultWarehouseResponse,
    DefaultWarehouseSetResponse, WarehouseSettingsUpdateRequest,
)
from app.warehouse.exceptions import (
    WarehouseNotFoundError, WarehouseInactiveError,
    WarehouseSettingsNotFoundError, WarehouseSettingsValidationError,
)
from app.inventory.constants import WarehouseStatus, AllocationStrategy

# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


def _make_mock_db():
    """Create a minimal AsyncSession mock."""
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


def _make_mock_user(user_id=None):
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.full_name = "Test User"
    return user


def _make_mock_warehouse(store_id=None, wh_id=None, is_default=False, is_active=True):
    wh = MagicMock()
    wh.id = wh_id or uuid.uuid4()
    wh.store_id = store_id or uuid.uuid4()
    wh.code = "WH-TEST"
    wh.name = "Test Warehouse"
    wh.is_default = is_default
    wh.is_active = is_active
    wh.status = WarehouseStatus.ACTIVE if is_active else WarehouseStatus.INACTIVE
    wh.capacity = 1000
    wh.capacity_unit = "units"
    return wh


# ═══════════════════════════════════════════════════════════════════
# Repo Tests
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_default_found():
    db = _make_mock_db()
    repo = WarehouseRepository(db)
    store_id = uuid.uuid4()
    wh = _make_mock_warehouse(store_id=store_id, is_default=True)

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = wh
    db.execute.return_value = result_mock

    result = await repo.get_default(store_id)
    assert result is not None
    assert result.id == wh.id
    assert result.is_default is True


@pytest.mark.asyncio
async def test_get_default_none():
    db = _make_mock_db()
    repo = WarehouseRepository(db)

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    result = await repo.get_default(uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_clear_default():
    db = _make_mock_db()
    repo = WarehouseRepository(db)
    # clear_default now calls db.execute twice: once for locking, once for UPDATE
    # Mock both calls
    lock_result = MagicMock()
    lock_result.all.return_value = []
    update_result = MagicMock()
    db.execute.side_effect = [lock_result, update_result]

    await repo.clear_default(uuid.uuid4())
    # Should have called execute at least once
    assert db.execute.called
    # The second call should contain the UPDATE
    second_call_str = str(db.execute.call_args_list[1][0][0]).lower()
    assert "update" in second_call_str


@pytest.mark.asyncio
async def test_set_default():
    db = _make_mock_db()
    store_id = uuid.uuid4()
    wh_id = uuid.uuid4()
    repo = WarehouseRepository(db)

    wh = _make_mock_warehouse(store_id=store_id, wh_id=wh_id)
    # set_default calls execute multiple times: lock target, lock defaults, update
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = wh
    # Use a side_effect that always returns the scalar_result for the first call
    lock_defaults_result = MagicMock()
    lock_defaults_result.all.return_value = []
    update_result = MagicMock()

    db.execute.side_effect = [scalar_result, lock_defaults_result, update_result]

    result = await repo.set_default(wh_id, store_id)
    assert result is not None
    assert result.is_default is True


@pytest.mark.asyncio
async def test_set_default_inactive():
    """set_default should reject inactive warehouses."""
    db = _make_mock_db()
    store_id = uuid.uuid4()
    wh_id = uuid.uuid4()
    repo = WarehouseRepository(db)

    wh = _make_mock_warehouse(store_id=store_id, wh_id=wh_id, is_active=False)
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = wh
    db.execute.return_value = scalar_result

    result = await repo.set_default(wh_id, store_id)
    assert result is None  # Inactive warehouse should be rejected


@pytest.mark.asyncio
async def test_set_default_wrong_store():
    db = _make_mock_db()
    store_id = uuid.uuid4()
    wh_id = uuid.uuid4()
    repo = WarehouseRepository(db)

    wh = _make_mock_warehouse(store_id=uuid.uuid4(), wh_id=wh_id)
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = wh
    db.execute.return_value = scalar_result

    result = await repo.set_default(wh_id, store_id)
    assert result is None


@pytest.mark.asyncio
async def test_set_default_not_found():
    db = _make_mock_db()
    repo = WarehouseRepository(db)

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = None
    db.execute.return_value = scalar_result

    result = await repo.set_default(uuid.uuid4(), uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_ensure_single_default_existing():
    db = _make_mock_db()
    store_id = uuid.uuid4()
    repo = WarehouseRepository(db)
    wh = _make_mock_warehouse(store_id=store_id, is_default=True)

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = wh
    db.execute.return_value = scalar_result

    result = await repo.ensure_single_default(store_id)
    assert result is not None
    assert result.id == wh.id


@pytest.mark.asyncio
async def test_ensure_single_default_no_warehouses():
    db = _make_mock_db()
    store_id = uuid.uuid4()
    repo = WarehouseRepository(db)

    # get_default returns None
    none_result = MagicMock()
    none_result.scalar_one_or_none.return_value = None

    # count_active returns 0
    count_result = MagicMock()
    count_result.scalar.return_value = 0

    db.execute.side_effect = [none_result, count_result]

    result = await repo.ensure_single_default(store_id)
    assert result is None


@pytest.mark.asyncio
async def test_ensure_single_default_auto_assign():
    db = _make_mock_db()
    store_id = uuid.uuid4()
    repo = WarehouseRepository(db)
    wh = _make_mock_warehouse(store_id=store_id, is_default=False)

    # get_default returns None
    none_result = MagicMock()
    none_result.scalar_one_or_none.return_value = None

    # count_active returns 1
    count_result = MagicMock()
    count_result.scalar.return_value = 1

    # select with for_update returns the warehouse
    lock_result = MagicMock()
    lock_result.scalar_one_or_none.return_value = wh

    db.execute.side_effect = [none_result, count_result, lock_result]

    result = await repo.ensure_single_default(store_id)
    assert result is not None
    assert result.is_default is True  # should have been set to True


# ═══════════════════════════════════════════════════════════════════
# Service Tests
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_service_get_default():
    db = _make_mock_db()
    store = _make_mock_store()
    user = _make_mock_user()
    service = WarehouseService(db=db, store=store, user_id=user.id)

    mock_wh = _make_mock_warehouse(store_id=store.id, is_default=True)

    with patch.object(service.repo, 'get_default', new=AsyncMock(return_value=mock_wh)):
        with patch.object(service.repo, 'ensure_single_default', new=AsyncMock(return_value=None)):
            result = await service.get_default_warehouse()
            assert result is not None
            assert result.id == mock_wh.id
            assert result.is_default is True


@pytest.mark.asyncio
async def test_service_get_default_none():
    db = _make_mock_db()
    store = _make_mock_store()
    user = _make_mock_user()
    service = WarehouseService(db=db, store=store, user_id=user.id)

    with patch.object(service.repo, 'get_default', new=AsyncMock(return_value=None)):
        with patch.object(service.repo, 'ensure_single_default', new=AsyncMock(return_value=None)):
            result = await service.get_default_warehouse()
            assert result is None


@pytest.mark.asyncio
async def test_service_set_default():
    db = _make_mock_db()
    store = _make_mock_store()
    user = _make_mock_user()
    service = WarehouseService(db=db, store=store, user_id=user.id)

    wh_id = uuid.uuid4()
    mock_wh = _make_mock_warehouse(store_id=store.id, wh_id=wh_id, is_active=True)

    mock_settings = MagicMock()
    mock_settings.default_warehouse_id = wh_id

    with patch.object(service, 'get_warehouse', new=AsyncMock(return_value=mock_wh)):
        with patch.object(service.repo, 'set_default', new=AsyncMock(return_value=mock_wh)):
            with patch('app.warehouse.service.WarehouseSettingsRepository') as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.get_or_create = AsyncMock(return_value=mock_settings)
                mock_repo_cls.return_value = mock_repo
                result = await service.set_default_warehouse(wh_id)
                assert result is not None
                assert result.id == wh_id
                assert mock_settings.default_warehouse_id == wh_id


@pytest.mark.asyncio
async def test_service_set_default_inactive():
    db = _make_mock_db()
    store = _make_mock_store()
    user = _make_mock_user()
    service = WarehouseService(db=db, store=store, user_id=user.id)

    wh_id = uuid.uuid4()
    mock_wh = _make_mock_warehouse(store_id=store.id, wh_id=wh_id, is_active=False)

    with patch.object(service, 'get_warehouse', new=AsyncMock(return_value=mock_wh)):
        with pytest.raises(WarehouseInactiveError):
            await service.set_default_warehouse(wh_id)


@pytest.mark.asyncio
async def test_service_set_default_not_found():
    db = _make_mock_db()
    store = _make_mock_store()
    user = _make_mock_user()
    service = WarehouseService(db=db, store=store, user_id=user.id)

    with patch.object(service, 'get_warehouse', side_effect=WarehouseNotFoundError("not-found")):
        with pytest.raises(WarehouseNotFoundError):
            await service.set_default_warehouse(uuid.uuid4())


@pytest.mark.asyncio
async def test_service_clear_default():
    db = _make_mock_db()
    store = _make_mock_store()
    user = _make_mock_user()
    service = WarehouseService(db=db, store=store, user_id=user.id)

    mock_settings = MagicMock()

    with patch.object(service.repo, 'clear_default', new=AsyncMock()):
        with patch('app.warehouse.service.WarehouseSettingsRepository') as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo.get_or_create = AsyncMock(return_value=mock_settings)
            mock_repo_cls.return_value = mock_repo
            result = await service.clear_default_warehouse()
            assert "cleared" in result["message"].lower()
            assert mock_settings.default_warehouse_id is None


@pytest.mark.asyncio
async def test_service_get_settings():
    db = _make_mock_db()
    store = _make_mock_store()
    user = _make_mock_user()
    service = WarehouseService(db=db, store=store, user_id=user.id)

    mock_wh = _make_mock_warehouse(store_id=store.id, is_default=True)
    mock_settings = MagicMock()
    mock_settings.id = uuid.uuid4()
    mock_settings.store_id = store.id
    mock_settings.auto_allocate_inventory = True
    mock_settings.multi_warehouse_enabled = False
    mock_settings.allocation_strategy = "default_warehouse"
    mock_settings.allow_negative_stock = False
    mock_settings.reserve_stock_on_order = True
    mock_settings.auto_release_cancelled_orders = True
    mock_settings.created_at = datetime.now(timezone.utc)
    mock_settings.updated_at = datetime.now(timezone.utc)

    with patch.object(service, 'get_default_warehouse', new=AsyncMock(return_value=mock_wh)):
        # Now uses count_by_store and count_active instead of list_by_store
        with patch.object(service.repo, 'count_by_store', new=AsyncMock(return_value=2)):
            with patch.object(service.repo, 'count_active', new=AsyncMock(return_value=1)):
                with patch('app.warehouse.service.WarehouseSettingsRepository') as mock_repo_cls:
                    mock_repo = MagicMock()
                    mock_repo.get_or_create = AsyncMock(return_value=mock_settings)
                    mock_repo_cls.return_value = mock_repo
                    settings = await service.get_warehouse_settings()
                    assert settings["has_default"] is True
                    assert settings["default_warehouse_id"] == str(mock_wh.id)
                    assert settings["total_warehouses"] == 2
                    assert settings["active_warehouses"] == 1
                    assert settings["auto_allocate_inventory"] is True
                    assert settings["allocation_strategy"] == "default_warehouse"


@pytest.mark.asyncio
async def test_service_get_settings_no_default():
    db = _make_mock_db()
    store = _make_mock_store()
    user = _make_mock_user()
    service = WarehouseService(db=db, store=store, user_id=user.id)

    mock_settings = MagicMock()
    mock_settings.id = uuid.uuid4()
    mock_settings.store_id = store.id
    mock_settings.auto_allocate_inventory = True
    mock_settings.multi_warehouse_enabled = False
    mock_settings.allocation_strategy = "default_warehouse"
    mock_settings.allow_negative_stock = False
    mock_settings.reserve_stock_on_order = True
    mock_settings.auto_release_cancelled_orders = True
    mock_settings.created_at = datetime.now(timezone.utc)
    mock_settings.updated_at = datetime.now(timezone.utc)

    with patch.object(service, 'get_default_warehouse', new=AsyncMock(return_value=None)):
        with patch.object(service.repo, 'count_by_store', new=AsyncMock(return_value=0)):
            with patch.object(service.repo, 'count_active', new=AsyncMock(return_value=0)):
                with patch('app.warehouse.service.WarehouseSettingsRepository') as mock_repo_cls:
                    mock_repo = MagicMock()
                    mock_repo.get_or_create = AsyncMock(return_value=mock_settings)
                    mock_repo_cls.return_value = mock_repo
                    settings = await service.get_warehouse_settings()
                    assert settings["has_default"] is False
                    assert settings["default_warehouse_id"] is None
                    assert settings["active_warehouses"] == 0


@pytest.mark.asyncio
async def test_deactivate_clears_default():
    db = _make_mock_db()
    store = _make_mock_store()
    user = _make_mock_user()
    service = WarehouseService(db=db, store=store, user_id=user.id)

    wh_id = uuid.uuid4()
    mock_wh = _make_mock_warehouse(store_id=store.id, wh_id=wh_id, is_default=True)

    mock_settings = MagicMock()
    mock_settings.default_warehouse_id = wh_id

    with patch.object(service, 'get_warehouse', new=AsyncMock(return_value=mock_wh)):
        with patch.object(service.repo, 'clear_default', new=AsyncMock()) as mock_clear:
            with patch.object(service.repo, 'update', new=AsyncMock(return_value=mock_wh)):
                with patch('app.warehouse.service.WarehouseSettingsRepository') as mock_repo_cls:
                    mock_repo = MagicMock()
                    mock_repo.get_or_create = AsyncMock(return_value=mock_settings)
                    mock_repo_cls.return_value = mock_repo
                    await service.deactivate_warehouse(wh_id)
                    mock_clear.assert_called_once_with(store.id)
                    # Should also clear settings reference
                    assert mock_settings.default_warehouse_id is None


@pytest.mark.asyncio
async def test_delete_clears_default():
    db = _make_mock_db()
    store = _make_mock_store()
    user = _make_mock_user()
    service = WarehouseService(db=db, store=store, user_id=user.id)

    wh_id = uuid.uuid4()
    mock_wh = _make_mock_warehouse(store_id=store.id, wh_id=wh_id, is_default=True, is_active=True)

    mock_settings = MagicMock()
    mock_settings.default_warehouse_id = wh_id

    with patch.object(service, 'get_warehouse', new=AsyncMock(return_value=mock_wh)):
        with patch.object(service.repo, 'clear_default', new=AsyncMock()) as mock_clear:
            with patch.object(service.repo, 'delete', new=AsyncMock(return_value=True)):
                with patch('app.warehouse.service.WarehouseSettingsRepository') as mock_repo_cls:
                    mock_repo = MagicMock()
                    mock_repo.get_by_store = AsyncMock(return_value=mock_settings)
                    mock_repo_cls.return_value = mock_repo
                    await service.delete_warehouse(wh_id)
                    mock_clear.assert_called_once_with(store.id)
                    # Should clear settings reference before deletion
                    assert mock_settings.default_warehouse_id is None


# ═══════════════════════════════════════════════════════════════════
# WooCommerce Sync — Default Warehouse Integration
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_wc_sync_uses_configured_default():
    from app.warehouse.woocommerce_sync_service import WarehouseInventorySyncService

    db = _make_mock_db()
    service = WarehouseInventorySyncService(db)

    default_wh_id = uuid.uuid4()
    mock_variant = MagicMock()
    mock_variant.id = uuid.uuid4()
    mock_variant.product_id = uuid.uuid4()
    mock_wh_inv = MagicMock()
    mock_wh_inv.available_stock = 0

    mock_wh = _make_mock_warehouse(wh_id=default_wh_id, is_default=True)

    with patch.object(service, '_find_inventory_store', new=AsyncMock(return_value=_make_mock_store())):
        with patch.object(service, '_find_or_create_variant', new=AsyncMock(return_value=mock_variant)):
            with patch.object(service, '_get_default_warehouse', new=AsyncMock(return_value=mock_wh)):
                with patch.object(service.inv_repo, 'get_or_create', new=AsyncMock(return_value=mock_wh_inv)):
                    wc_product = MagicMock(wc_product_id=12345, sku="TEST-SKU", name="Test")
                    wc_store = MagicMock(owner_id=uuid.uuid4(), store_name="Test Store")

                    result = await service.sync_wc_product_to_warehouse(
                        wc_store=wc_store, wc_product=wc_product, stock_quantity=50,
                    )
                    assert result["status"] == "synced"
                    assert str(mock_wh.id) == result["warehouse_id"]


@pytest.mark.asyncio
async def test_wc_sync_skips_when_no_default():
    from app.warehouse.woocommerce_sync_service import WarehouseInventorySyncService

    db = _make_mock_db()
    service = WarehouseInventorySyncService(db)

    with patch.object(service, '_find_inventory_store', new=AsyncMock(return_value=_make_mock_store())):
        with patch.object(service, '_find_or_create_variant', new=AsyncMock(return_value=MagicMock(id=uuid.uuid4()))):
            with patch.object(service, '_get_default_warehouse', new=AsyncMock(return_value=None)):
                wc_product = MagicMock(wc_product_id=12345, sku="TEST-SKU", name="Test")
                wc_store = MagicMock(owner_id=uuid.uuid4(), store_name="Test Store")

                result = await service.sync_wc_product_to_warehouse(
                    wc_store=wc_store, wc_product=wc_product, stock_quantity=50,
                )
                assert result["status"] == "skipped"
                assert result["reason"] == "no_warehouse"


# ═══════════════════════════════════════════════════════════════════
# Schema Tests
# ═══════════════════════════════════════════════════════════════════


def test_settings_out():
    data = {
        "default_warehouse_id": str(uuid.uuid4()),
        "default_warehouse_name": "Main",
        "total_warehouses": 3,
        "active_warehouses": 2,
        "has_default": True,
    }
    schema = WarehouseSettingsOut(**data)
    assert schema.has_default is True
    assert schema.total_warehouses == 3


def test_settings_out_empty():
    schema = WarehouseSettingsOut()
    assert schema.has_default is False
    assert schema.default_warehouse_id is None


def test_default_warehouse_response():
    data = {
        "default_warehouse_id": str(uuid.uuid4()),
        "default_warehouse_name": "Main",
        "total_warehouses": 1,
        "active_warehouses": 1,
        "has_default": True,
    }
    schema = DefaultWarehouseResponse(**data)
    assert schema.default_warehouse_id == data["default_warehouse_id"]


def test_default_warehouse_set_response():
    data = {
        "warehouse_id": str(uuid.uuid4()),
        "warehouse_name": "Main",
        "message": "Now default",
    }
    schema = DefaultWarehouseSetResponse(**data)
    assert schema.warehouse_name == "Main"


def test_settings_update_with_id():
    wh_id = uuid.uuid4()
    schema = WarehouseSettingsUpdateRequest(default_warehouse_id=wh_id)
    assert schema.default_warehouse_id == wh_id


def test_settings_update_clear():
    schema = WarehouseSettingsUpdateRequest(default_warehouse_id=None)
    assert schema.default_warehouse_id is None


# ═══════════════════════════════════════════════════════════════════
# Model-level tests
# ═══════════════════════════════════════════════════════════════════


def test_warehouse_out_has_is_default_field():
    from app.warehouse.schemas import WarehouseOut
    assert "is_default" in WarehouseOut.model_fields


def test_warehouse_out_is_default_defaults_to_false():
    from app.warehouse.schemas import WarehouseOut
    field = WarehouseOut.model_fields["is_default"]
    assert field.default is False


# ═══════════════════════════════════════════════════════════════════
# WarehouseSettings CRUD Tests
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_settings_repo_get_or_create():
    """Repository: get_or_create returns default settings for a store."""
    from app.warehouse.repository import WarehouseSettingsRepository
    db = _make_mock_db()
    repo = WarehouseSettingsRepository(db)

    # get_by_store returns None, so it will create
    mock_none = MagicMock()
    mock_none.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_none

    result = await repo.get_or_create(uuid.uuid4())
    assert result is not None
    assert db.add.called


@pytest.mark.asyncio
async def test_settings_repo_get_by_store():
    """Repository: get_by_store returns settings when they exist."""
    from app.warehouse.repository import WarehouseSettingsRepository
    db = _make_mock_db()
    repo = WarehouseSettingsRepository(db)

    mock_settings = MagicMock()
    mock_settings.store_id = uuid.uuid4()
    mock_settings.default_warehouse_id = uuid.uuid4()
    mock_settings.auto_allocate_inventory = True
    mock_settings.multi_warehouse_enabled = False
    mock_settings.allocation_strategy = "default_warehouse"
    mock_settings.allow_negative_stock = False
    mock_settings.reserve_stock_on_order = True
    mock_settings.auto_release_cancelled_orders = True

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_settings
    db.execute.return_value = mock_result

    result = await repo.get_by_store(mock_settings.store_id)
    assert result is not None
    assert result.store_id == mock_settings.store_id


@pytest.mark.asyncio
async def test_settings_repo_update():
    """Repository: update modifies settings fields."""
    from app.warehouse.repository import WarehouseSettingsRepository
    db = _make_mock_db()
    repo = WarehouseSettingsRepository(db)

    mock_settings = MagicMock()
    mock_settings.auto_allocate_inventory = True
    mock_settings.multi_warehouse_enabled = False

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_settings
    db.execute.return_value = mock_result

    result = await repo.update(uuid.uuid4(), {"auto_allocate_inventory": False})
    assert result is not None
    assert result.auto_allocate_inventory is False


@pytest.mark.asyncio
async def test_service_get_settings_all_fields():
    """Service: get_warehouse_settings returns all B.1 fields."""
    db = _make_mock_db()
    store = _make_mock_store()
    user = _make_mock_user()
    service = WarehouseService(db=db, store=store, user_id=user.id)

    mock_wh = _make_mock_warehouse(store_id=store.id, is_default=True)
    mock_settings = MagicMock()
    mock_settings.id = uuid.uuid4()
    mock_settings.store_id = store.id
    mock_settings.default_warehouse_id = mock_wh.id
    mock_settings.auto_allocate_inventory = True
    mock_settings.multi_warehouse_enabled = True
    mock_settings.allocation_strategy = "highest_stock"
    mock_settings.allow_negative_stock = False
    mock_settings.reserve_stock_on_order = True
    mock_settings.auto_release_cancelled_orders = True
    mock_settings.created_at = datetime.now(timezone.utc)
    mock_settings.updated_at = datetime.now(timezone.utc)

    with patch.object(service, 'get_default_warehouse', new=AsyncMock(return_value=mock_wh)):
        with patch.object(service.repo, 'count_by_store', new=AsyncMock(return_value=3)):
            with patch.object(service.repo, 'count_active', new=AsyncMock(return_value=2)):
                with patch('app.warehouse.service.WarehouseSettingsRepository') as mock_repo_cls:
                    mock_repo = MagicMock()
                    mock_repo.get_or_create = AsyncMock(return_value=mock_settings)
                    mock_repo_cls.return_value = mock_repo

                    settings = await service.get_warehouse_settings()
                    assert settings["auto_allocate_inventory"] is True
                    assert settings["multi_warehouse_enabled"] is True
                    assert settings["allocation_strategy"] == "highest_stock"
                    assert settings["allow_negative_stock"] is False
                    assert settings["reserve_stock_on_order"] is True
                    assert settings["auto_release_cancelled_orders"] is True
                    assert settings["has_default"] is True
                    assert settings["total_warehouses"] == 3


@pytest.mark.asyncio
async def test_service_get_settings_defaults():
    """Service: get_warehouse_settings returns defaults when no custom settings."""
    db = _make_mock_db()
    store = _make_mock_store()
    user = _make_mock_user()
    service = WarehouseService(db=db, store=store, user_id=user.id)

    mock_settings = MagicMock()
    mock_settings.id = uuid.uuid4()
    mock_settings.store_id = store.id
    mock_settings.default_warehouse_id = None
    mock_settings.auto_allocate_inventory = True
    mock_settings.multi_warehouse_enabled = False
    mock_settings.allocation_strategy = "default_warehouse"
    mock_settings.allow_negative_stock = False
    mock_settings.reserve_stock_on_order = True
    mock_settings.auto_release_cancelled_orders = True
    mock_settings.created_at = datetime.now(timezone.utc)
    mock_settings.updated_at = datetime.now(timezone.utc)

    with patch.object(service, 'get_default_warehouse', new=AsyncMock(return_value=None)):
        with patch.object(service.repo, 'count_by_store', new=AsyncMock(return_value=0)):
            with patch.object(service.repo, 'count_active', new=AsyncMock(return_value=0)):
                with patch('app.warehouse.service.WarehouseSettingsRepository') as mock_repo_cls:
                    mock_repo = MagicMock()
                    mock_repo.get_or_create = AsyncMock(return_value=mock_settings)
                    mock_repo_cls.return_value = mock_repo

                    settings = await service.get_warehouse_settings()
                    assert settings["allocation_strategy"] == "default_warehouse"
                    assert settings["multi_warehouse_enabled"] is False
                    assert settings["allow_negative_stock"] is False
                    assert settings["has_default"] is False


@pytest.mark.asyncio
async def test_service_update_settings_allocation_strategy():
    """Service: update_warehouse_settings validates allocation_strategy."""
    db = _make_mock_db()
    store = _make_mock_store()
    user = _make_mock_user()
    service = WarehouseService(db=db, store=store, user_id=user.id)

    payload = MagicMock()
    payload.allocation_strategy = "invalid_strategy"
    payload.default_warehouse_id = None
    payload.auto_allocate_inventory = None
    payload.multi_warehouse_enabled = None
    payload.allow_negative_stock = None
    payload.reserve_stock_on_order = None
    payload.auto_release_cancelled_orders = None

    payload.model_dump.return_value = {
        "allocation_strategy": "invalid_strategy",
        "default_warehouse_id": None,
    }

    result = service.update_warehouse_settings(payload)
    with pytest.raises(Exception):
        await result


@pytest.mark.asyncio
async def test_service_update_settings_bool_fields():
    """Service: update_warehouse_settings sets boolean fields."""
    db = _make_mock_db()
    store = _make_mock_store()
    user = _make_mock_user()
    service = WarehouseService(db=db, store=store, user_id=user.id)

    mock_settings = MagicMock()
    mock_settings.id = uuid.uuid4()
    mock_settings.store_id = store.id
    mock_settings.auto_allocate_inventory = True
    mock_settings.multi_warehouse_enabled = False
    mock_settings.allocation_strategy = "default_warehouse"
    mock_settings.allow_negative_stock = False
    mock_settings.reserve_stock_on_order = True
    mock_settings.auto_release_cancelled_orders = True
    mock_settings.created_at = datetime.now(timezone.utc)
    mock_settings.updated_at = datetime.now(timezone.utc)

    with patch('app.warehouse.service.WarehouseSettingsRepository') as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.get_or_create = AsyncMock(return_value=mock_settings)
        mock_repo.update = AsyncMock(return_value=mock_settings)
        mock_repo_cls.return_value = mock_repo

        with patch.object(service, 'get_default_warehouse', new=AsyncMock(return_value=None)):
            with patch.object(service.repo, 'count_by_store', new=AsyncMock(return_value=0)):
                with patch.object(service.repo, 'count_active', new=AsyncMock(return_value=0)):

                    payload = MagicMock()
                    payload.default_warehouse_id = None
                    payload.auto_allocate_inventory = False
                    payload.multi_warehouse_enabled = True
                    payload.allocation_strategy = None
                    payload.allow_negative_stock = True
                    payload.reserve_stock_on_order = False
                    payload.auto_release_cancelled_orders = False
                    payload.model_dump.return_value = {
                        "default_warehouse_id": None,
                        "auto_allocate_inventory": False,
                        "multi_warehouse_enabled": True,
                        "allocation_strategy": None,
                        "allow_negative_stock": True,
                        "reserve_stock_on_order": False,
                        "auto_release_cancelled_orders": False,
                    }

                    settings = await service.update_warehouse_settings(payload)
                    assert settings is not None
                    assert mock_repo.update.called


# ═══════════════════════════════════════════════════════════════════
# Schema Validation Tests
# ═══════════════════════════════════════════════════════════════════


def test_settings_out_full():
    """Schema: WarehouseSettingsOut includes all B.1 fields."""
    data = {
        "id": uuid.uuid4(),
        "store_id": uuid.uuid4(),
        "default_warehouse_id": str(uuid.uuid4()),
        "default_warehouse_name": "Main",
        "auto_allocate_inventory": True,
        "multi_warehouse_enabled": True,
        "allocation_strategy": "highest_stock",
        "allow_negative_stock": False,
        "reserve_stock_on_order": True,
        "auto_release_cancelled_orders": True,
        "total_warehouses": 3,
        "active_warehouses": 2,
        "has_default": True,
    }
    schema = WarehouseSettingsOut(**data)
    assert schema.auto_allocate_inventory is True
    assert schema.multi_warehouse_enabled is True
    assert schema.allocation_strategy == "highest_stock"
    assert schema.allow_negative_stock is False
    assert schema.reserve_stock_on_order is True
    assert schema.auto_release_cancelled_orders is True
    assert schema.has_default is True


def test_settings_update_request_all_fields():
    """Schema: WarehouseSettingsUpdateRequest accepts all B.1 fields."""
    wh_id = uuid.uuid4()
    data = {
        "default_warehouse_id": wh_id,
        "auto_allocate_inventory": False,
        "multi_warehouse_enabled": True,
        "allocation_strategy": "highest_stock",
        "allow_negative_stock": True,
        "reserve_stock_on_order": False,
        "auto_release_cancelled_orders": True,
    }
    schema = WarehouseSettingsUpdateRequest(**data)
    assert schema.default_warehouse_id == wh_id
    assert schema.auto_allocate_inventory is False
    assert schema.multi_warehouse_enabled is True
    assert schema.allocation_strategy == "highest_stock"
    assert schema.allow_negative_stock is True
    assert schema.reserve_stock_on_order is False
    assert schema.auto_release_cancelled_orders is True


def test_settings_update_request_empty():
    """Schema: WarehouseSettingsUpdateRequest accepts empty payload (PATCH semantics)."""
    schema = WarehouseSettingsUpdateRequest()
    assert schema.default_warehouse_id is None
    assert schema.auto_allocate_inventory is None
    assert schema.multi_warehouse_enabled is None
    assert schema.allocation_strategy is None
    assert schema.allow_negative_stock is None
    assert schema.reserve_stock_on_order is None
    assert schema.auto_release_cancelled_orders is None


def test_allocation_strategy_enum():
    """Constants: AllocationStrategy has expected values."""
    assert AllocationStrategy.DEFAULT_WAREHOUSE.value == "default_warehouse"
    assert AllocationStrategy.HIGHEST_STOCK.value == "highest_stock"
    assert AllocationStrategy.NEAREST_WAREHOUSE.value == "nearest_warehouse"
    assert AllocationStrategy.MANUAL.value == "manual"


def test_warehouse_settings_not_found_error():
    """Exception: WarehouseSettingsNotFoundError has correct structure."""
    exc = WarehouseSettingsNotFoundError("store-123")
    assert "store-123" in exc.message
    assert exc.detail["store_id"] == "store-123"


def test_warehouse_settings_validation_error():
    """Exception: WarehouseSettingsValidationError has correct structure."""
    exc = WarehouseSettingsValidationError("Invalid strategy", {"field": "allocation_strategy"})
    assert "Invalid strategy" in exc.message
    assert exc.detail["field"] == "allocation_strategy"
