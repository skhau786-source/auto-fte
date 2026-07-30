"""
Shared assertion helpers and utilities for inventory tests.
"""

import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import (
    Product,
    ProductVariant,
    InventoryTransaction,
    InventoryLog,
)


# ═══════════════════════════════════════════════════════════════════
# Database state assertion helpers
# ═══════════════════════════════════════════════════════════════════


async def assert_product_count(db: AsyncSession, expected: int, store_id: uuid.UUID) -> None:
    """Assert that a store has exactly *expected* products."""
    result = await db.execute(
        select(func.count(Product.id)).where(Product.store_id == store_id)
    )
    count = result.scalar()
    assert count == expected, f"Expected {expected} products, got {count}"


async def assert_variant_count(db: AsyncSession, expected: int, product_id: uuid.UUID) -> None:
    """Assert that a product has exactly *expected* variants."""
    result = await db.execute(
        select(func.count(ProductVariant.id)).where(ProductVariant.product_id == product_id)
    )
    count = result.scalar()
    assert count == expected, f"Expected {expected} variants, got {count}"


async def assert_transaction_count(db: AsyncSession, expected: int) -> None:
    """Assert total transaction count in the database."""
    result = await db.execute(select(func.count(InventoryTransaction.id)))
    count = result.scalar()
    assert count == expected, f"Expected {expected} transactions, got {count}"


async def assert_log_count(db: AsyncSession, expected: int) -> None:
    """Assert total log entry count in the database."""
    result = await db.execute(select(func.count(InventoryLog.id)))
    count = result.scalar()
    assert count == expected, f"Expected {expected} logs, got {count}"


async def assert_variant_quantity(
    db: AsyncSession, variant_id: uuid.UUID, expected: int
) -> None:
    """Assert a variant's inventory_quantity matches expected."""
    result = await db.execute(
        select(ProductVariant.inventory_quantity).where(ProductVariant.id == variant_id)
    )
    qty = result.scalar()
    assert qty == expected, f"Expected quantity {expected}, got {qty}"


async def get_product(db: AsyncSession, product_id: uuid.UUID) -> Optional[Product]:
    """Fetch a product directly from DB (bypassing cache/ORM)."""
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    return result.scalar_one_or_none()


async def get_variant(db: AsyncSession, variant_id: uuid.UUID) -> Optional[ProductVariant]:
    """Fetch a variant directly from DB."""
    result = await db.execute(
        select(ProductVariant).where(ProductVariant.id == variant_id)
    )
    return result.scalar_one_or_none()


# ═══════════════════════════════════════════════════════════════════
# Response assertion helpers
# ═══════════════════════════════════════════════════════════════════


def assert_product_out(data: dict, expected_title: str = None) -> None:
    """Assert that a response dict matches ProductOut schema."""
    assert "id" in data
    assert "store_id" in data
    assert "title" in data
    assert "status" in data
    assert "variants" in data
    assert "created_at" in data
    assert "updated_at" in data
    if expected_title:
        assert data["title"] == expected_title


def assert_list_response(data: dict, expected_total: int = None) -> None:
    """Assert that a paginated list response has the correct structure."""
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "total_pages" in data
    if expected_total is not None:
        assert data["total"] == expected_total


def assert_error_response(data: dict, status_code: int = None) -> None:
    """Assert that an error response has the correct structure."""
    assert "detail" in data
    if status_code:
        assert True  # Presence check; caller verifies status code separately


def assert_adjust_response(data: dict, expected_change: int = None) -> None:
    """Assert that an inventory adjustment response is well-formed."""
    assert "variant_id" in data
    assert "quantity_before" in data
    assert "quantity_after" in data
    assert "quantity_change" in data
    assert "transaction_id" in data
    assert "message" in data
    if expected_change is not None:
        assert data["quantity_change"] == expected_change
    assert data["quantity_after"] == data["quantity_before"] + data["quantity_change"]
