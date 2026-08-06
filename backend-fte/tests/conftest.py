"""
Pytest configuration for Inventory Management module tests.

Architecture:
- Uses a PostgreSQL test database (configurable via TEST_DATABASE_URL env var)
- Database engine is created lazily — tests using mocks can run without PostgreSQL
- All tables are created once per session, dropped at session end
- Each test gets an isolated async session with auto-rollback
- FastAPI dependencies (get_db, get_current_user, get_store_for_user) are overridden
- ShopifyClient is mocked at the class level for service/webhook tests

Usage:
    cd backend-fte
    TEST_DATABASE_URL=postgresql+asyncpg://postgres:pass@localhost:5432/test_db pytest tests/ -v
"""

import os
import sys
import asyncio
from typing import AsyncGenerator, AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

# Ensure the backend-fte directory is on sys.path so we can import app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import Base, get_db
from app.dependencies import get_current_user
from app.inventory.dependencies import get_store_for_user
from app.models import RegisteredStudent, Store, Category, Product, ProductVariant
from app.main import app


# ═══════════════════════════════════════════════════════════════════
# Lazy Test Database
# ═══════════════════════════════════════════════════════════════════
# Engine is created lazily so mocked tests can run without PostgreSQL.
# Integration tests that need a real DB will be skipped gracefully.

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/test_digital_fte",
)

_test_engine = None
_test_session_maker = None


def _get_test_engine():
    """Get or create the test engine lazily."""
    global _test_engine
    if _test_engine is None:
        _test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, pool_pre_ping=True)
    return _test_engine


def _get_test_session_maker():
    """Get or create the test session maker lazily."""
    global _test_session_maker
    if _test_session_maker is None:
        _test_session_maker = async_sessionmaker(
            bind=_get_test_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _test_session_maker


def _postgres_available() -> bool:
    """Check if PostgreSQL is reachable. Returns False if not."""
    import socket
    from urllib.parse import urlparse
    try:
        parsed = urlparse(TEST_DATABASE_URL)
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432
        sock = socket.create_connection((host, port), timeout=2)
        sock.close()
        return True
    except (OSError, ConnectionRefusedError, Exception):
        return False


# ═══════════════════════════════════════════════════════════════════
# Session-scoped fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture(scope="session")
async def setup_database():
    """Create all tables before the test session, drop them afterward.

    Skips gracefully if PostgreSQL is not available.
    """
    if not _postgres_available():
        pytest.skip(f"PostgreSQL not available at {TEST_DATABASE_URL}. Skipping database setup.")
        return

    engine = _get_test_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ═══════════════════════════════════════════════════════════════════
# Function-scoped fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def db_session(setup_database) -> AsyncIterator[AsyncSession]:
    """
    Provide an isolated async session per test.

    Requests the session-scoped ``setup_database`` fixture first so all
    tables exist before any query runs. Every test runs inside one outer
    transaction: fixture/test ``commit()`` calls become savepoints
    (``join_transaction_mode="create_savepoint"``) and the whole
    transaction is rolled back at teardown, so data never leaks between
    tests — even committed rows (unique emails, store domains, etc.).

    Skips if PostgreSQL is not available.
    """
    connection = await _get_test_engine().connect()
    trans = await connection.begin()
    session = AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> RegisteredStudent:
    """Create a test RegisteredStudent."""
    user = RegisteredStudent(
        username="inventory_tester",
        email="tester@example.com",
        full_name="Inventory Tester",
        auth_provider="local",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def test_store(db_session: AsyncSession, test_user: RegisteredStudent) -> Store:
    """Create a test Shopify Store with complete credentials."""
    store = Store(
        owner_id=test_user.id,
        shopify_domain="test-store.myshopify.com",
        shopify_store_id=123456,
        access_token="shpat_test_token_abc123",
        shopify_location_id=905684977,
        is_active=True,
    )
    db_session.add(store)
    await db_session.commit()
    return store


@pytest_asyncio.fixture
async def second_store(db_session: AsyncSession, test_user: RegisteredStudent) -> Store:
    """A second store owned by the same user (for ownership tests)."""
    store = Store(
        owner_id=test_user.id,
        shopify_domain="second-store.myshopify.com",
        shopify_store_id=789012,
        access_token="shpat_second_token",
        shopify_location_id=123456789,
        is_active=True,
    )
    db_session.add(store)
    await db_session.commit()
    return store


@pytest_asyncio.fixture
async def test_category(
    db_session: AsyncSession, test_store: Store
) -> Category:
    """Create a test Category."""
    category = Category(
        store_id=test_store.id,
        name="Test Category",
        slug="test-category",
        description="A category for testing",
    )
    db_session.add(category)
    await db_session.commit()
    return category


@pytest_asyncio.fixture
async def test_product(
    db_session: AsyncSession, test_store: Store, test_category: Category
) -> Product:
    """Create a test Product with one variant."""
    product = Product(
        store_id=test_store.id,
        category_id=test_category.id,
        title="Test Product",
        description="A product for testing",
        vendor="Test Vendor",
        product_type="Physical",
        status="active",
    )
    db_session.add(product)
    await db_session.flush()

    variant = ProductVariant(
        product_id=product.id,
        title="Default Title",
        sku="TEST-SKU-001",
        price=19.99,
        inventory_quantity=100,
        requires_shipping=True,
        low_stock_threshold=10,
    )
    db_session.add(variant)
    await db_session.commit()
    # Populate the relationship in async context so tests can safely
    # access ``test_product.variants`` without triggering a lazy load.
    await db_session.refresh(product, attribute_names=["variants"])
    return product


@pytest_asyncio.fixture
async def test_variant(test_product: Product) -> ProductVariant:
    """Return the sole variant of test_product."""
    # ``test_product`` already refreshes its ``variants`` relationship in
    # async context, so direct access here is safe (no async lazy load).
    return test_product.variants[0]


@pytest_asyncio.fixture
async def test_products_batch(
    db_session: AsyncSession, test_store: Store
) -> list[Product]:
    """Create a batch of products with variants for pagination/search tests."""
    products = []
    for i in range(1, 16):
        p = Product(
            store_id=test_store.id,
            title=f"Product {i}",
            description=f"Description {i}",
            vendor=f"Vendor {i % 3}",
            product_type="Type A" if i % 2 == 0 else "Type B",
            status="active",
        )
        db_session.add(p)
        await db_session.flush()

        v = ProductVariant(
            product_id=p.id,
            title=f"Variant {i}",
            sku=f"SKU-{i:04d}",
            price=10.00 + i,
            inventory_quantity=i * 10,
            requires_shipping=True,
        )
        db_session.add(v)
        products.append(p)

    await db_session.commit()
    # Populate the variants relationship on every product so tests can
    # access ``product.variants`` without an async lazy-load.
    for p in products:
        await db_session.refresh(p, attribute_names=["variants"])
    return products


# ═══════════════════════════════════════════════════════════════════
# FastAPI Dependency Overrides
# ═══════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    test_user: RegisteredStudent,
    test_store: Store,
) -> AsyncIterator[AsyncClient]:
    """
    Provide an httpx AsyncClient with all FastAPI dependencies overridden.

    The override captures the db_session, test_user, and test_store
    fixtures so every request uses the test's isolated session and data.
    """
    # ── Override dependencies ──
    async def _override_get_db():
        yield db_session

    def _override_get_current_user():
        return test_user

    def _override_get_store_for_user():
        return test_store

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    app.dependency_overrides[get_store_for_user] = _override_get_store_for_user

    # ── Create HTTP client ──
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # ── Cleanup ──
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════
# ShopifyClient Mock Patch (auto-applied to all tests)
# ═══════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def mock_shopify_client():
    """
    Automatically mock ShopifyClient for every test so no real HTTP
    requests are ever made. Individual tests can configure the mock
    return values via the returned MagicMock instance.
    """
    # Patch the class in the source module AND in every module that bound
    # it via ``from app.shopify.shopify_client import ShopifyClient``
    # (e.g. app.inventory.service) — otherwise services hit the real API.
    with patch("app.shopify.shopify_client.ShopifyClient", autospec=True) as mock, \
         patch("app.inventory.service.ShopifyClient", mock):
        # Default mock: all async methods return sensible defaults
        mock_instance = mock.return_value
        mock_instance.set_inventory_level = AsyncMock(return_value={"id": "gid://shopify/InventoryLevel/123", "available": 50})
        mock_instance.fetch_all_products = AsyncMock(return_value=[])
        mock_instance.fetch_variants = AsyncMock(return_value=[])
        mock_instance.fetch_inventory_level = AsyncMock(return_value=50)
        mock_instance.fetch_locations = AsyncMock(return_value=[{"id": 905684977, "name": "Primary", "primary": True}])
        mock_instance.get_primary_location_id = AsyncMock(return_value=905684977)
        mock_instance.close = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)

        # Use the real HMAC verification implementation while mocking HTTP calls
        from app.shopify.shopify_client import ShopifyClient as _RealShopifyClient
        mock.verify_webhook = _RealShopifyClient.verify_webhook

        yield mock
