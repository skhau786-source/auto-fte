# ═══════════════════════════════════════════════════════════════
# tests / conftest.py
#
# PURPOSE: Shared pytest fixtures for the Digital FTE test suite.
# ═══════════════════════════════════════════════════════════════

import pytest

from src.sdk.llm.client import LLMClient


# ─── LLM client fixtures ──────────────────────────────────────

@pytest.fixture
def llm_client_with_key() -> LLMClient:
    """LLM client with a fake API key — no real network calls made."""
    return LLMClient(api_key="test-fake-key", model="gemini-2.0-flash-exp")


@pytest.fixture
def llm_client_no_key() -> LLMClient:
    """LLM client with NO API key — should raise LLMError on first call."""
    return LLMClient(api_key="", model="gemini-2.0-flash-exp")


# ─── Database fixture (rolled back, never committed) ──────────

@pytest.fixture
async def db_session():
    """AsyncSession on the dev/test Postgres inside a transaction that is ALWAYS rolled back.

    Skips when the database is unreachable, so the suite still runs without Postgres.
    """
    import os

    import src.domains.auth.models  # noqa: F401  (registers the users table for FK resolution)
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from src.sdk.config import get_settings

    # Own engine without pooling: pooled connections are bound to the first test's event loop.
    url = os.environ.get("TEST_DATABASE_URL") or get_settings().DATABASE_URL
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        conn = await engine.connect()
    except Exception as exc:  # pragma: no cover - depends on local environment
        pytest.skip(f"database not reachable: {exc}")

    trans = await conn.begin()
    session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()
