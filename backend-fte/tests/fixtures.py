"""
Test data factories for the Inventory Management module.

These helpers create pre-configured ORM model instances that can be
used across repository, service, and API tests. They use the session
directly and call commit() so callers get persistent objects.
"""

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Store,
    Product,
    ProductVariant,
    InventoryTransaction,
    InventoryLog,
    Category,
)
from app.inventory.constants import TransactionType, InventoryAction


async def create_store(
    db: AsyncSession,
    owner_id: uuid.UUID,
    **overrides,
) -> Store:
    """Create a Store with sensible defaults."""
    defaults = dict(
        owner_id=owner_id,
        shopify_domain="fixture-store.myshopify.com",
        shopify_store_id=999999,
        access_token="shpat_fixture_token",
        shopify_location_id=111111,
        is_active=True,
    )
    defaults.update(overrides)
    store = Store(**defaults)
    db.add(store)
    await db.commit()
    return store


# Backward-compatible alias used by test_end_to_end.py
create_test_store = create_store


async def create_test_user(
    db: AsyncSession,
    **overrides,
):
    """Create a RegisteredStudent for end-to-end tests."""
    from app.models import RegisteredStudent

    defaults = dict(
        username="e2e_tester",
        email="e2e@example.com",
        full_name="E2E Tester",
        auth_provider="local",
        is_active=True,
        is_verified=True,
    )
    defaults.update(overrides)
    user = RegisteredStudent(**defaults)
    db.add(user)
    await db.commit()
    return user


def valid_product_payload(**overrides) -> dict:
    """Payload accepted by POST /inventory (ProductCreateRequest)."""
    payload = {
        "title": "E2E Product",
        "description": "End-to-end test product",
        "vendor": "E2E Vendor",
        "product_type": "Physical",
        "status": "active",
        "variants": [
            {
                "title": "Default",
                "sku": "E2E-SKU-001",
                "price": "19.99",
                "inventory_quantity": 0,
                "low_stock_threshold": 10,
            }
        ],
    }
    payload.update(overrides)
    return payload


def valid_adjust_payload(
    variant_id: uuid.UUID,
    quantity_change: int,
    reason: str = "Test adjustment",
) -> dict:
    """Payload accepted by POST /inventory/update-stock."""
    return {
        "variant_id": str(variant_id),
        "quantity_change": quantity_change,
        "reason": reason,
    }


async def create_category(
    db: AsyncSession,
    store_id: uuid.UUID,
    **overrides,
) -> Category:
    """Create a Category with sensible defaults."""
    defaults = dict(
        store_id=store_id,
        name="Default Category",
        slug="default-category",
    )
    defaults.update(overrides)
    cat = Category(**defaults)
    db.add(cat)
    await db.commit()
    return cat


async def create_product(
    db: AsyncSession,
    store_id: uuid.UUID,
    **overrides,
) -> Product:
    """Create a Product (without variants). Caller can add variants separately."""
    defaults = dict(
        store_id=store_id,
        title="Default Product",
        status="active",
    )
    defaults.update(overrides)
    product = Product(**defaults)
    db.add(product)
    await db.commit()
    return product


async def create_variant(
    db: AsyncSession,
    product_id: uuid.UUID,
    **overrides,
) -> ProductVariant:
    """Create a ProductVariant with sensible defaults."""
    defaults = dict(
        product_id=product_id,
        title="Default Variant",
        sku=f"SKU-{uuid.uuid4().hex[:8].upper()}",
        price=Decimal("29.99"),
        inventory_quantity=50,
        requires_shipping=True,
        low_stock_threshold=10,
    )
    defaults.update(overrides)
    variant = ProductVariant(**defaults)
    db.add(variant)
    await db.commit()
    return variant


async def create_product_with_variants(
    db: AsyncSession,
    store_id: uuid.UUID,
    variant_count: int = 2,
    **product_overrides,
) -> Product:
    """Create a product with N variants."""
    product = await create_product(db, store_id, **product_overrides)
    for i in range(variant_count):
        await create_variant(
            db,
            product_id=product.id,
            title=f"Variant {i + 1}",
            sku=f"SKU-{uuid.uuid4().hex[:8].upper()}",
        )
    return product


async def create_transaction(
    db: AsyncSession,
    variant_id: uuid.UUID,
    **overrides,
) -> InventoryTransaction:
    """Create an InventoryTransaction with sensible defaults."""
    defaults = dict(
        variant_id=variant_id,
        transaction_type=TransactionType.ADJUSTMENT,
        quantity_change=10,
        quantity_before=50,
        quantity_after=60,
        reason="Test adjustment",
    )
    defaults.update(overrides)
    txn = InventoryTransaction(**defaults)
    db.add(txn)
    await db.commit()
    return txn


async def create_log(
    db: AsyncSession,
    variant_id: uuid.UUID,
    **overrides,
) -> InventoryLog:
    """Create an InventoryLog entry with sensible defaults."""
    defaults = dict(
        variant_id=variant_id,
        action=InventoryAction.CREATED.value,
        details={"test": True},
    )
    defaults.update(overrides)
    log = InventoryLog(**defaults)
    db.add(log)
    await db.commit()
    return log


# ─── Shopify-style mock payloads ───

def shopify_product_payload(
    shopify_id: int = 1001,
    title: str = "Shopify Product",
    status: str = "active",
    variant_count: int = 2,
) -> dict:
    """Generate a payload resembling what Shopify sends in products/update webhook."""
    variants = []
    for i in range(variant_count):
        variants.append({
            "id": shopify_id * 100 + i,
            "title": f"Variant {i}",
            "sku": f"SHOP-SKU-{i}",
            "barcode": f"BARCODE-{i}",
            "price": f"{19.99 + i:.2f}",
            "compare_at_price": None,
            "inventory_quantity": 50 - i * 10,
            "requires_shipping": True,
            "inventory_item_id": shopify_id * 1000 + i,
        })
    return {
        "id": shopify_id,
        "title": title,
        "body_html": f"<p>{title} description</p>",
        "vendor": "Shopify Vendor",
        "product_type": "Physical",
        "status": status,
        "image": {"src": f"https://example.com/{shopify_id}.jpg"},
        "variants": variants,
    }


def shopify_inventory_payload(
    inventory_item_id: int = 1001000,
    location_id: int = 905684977,
    available: int = 25,
) -> dict:
    """Generate a payload resembling Shopify's inventory_levels/update webhook."""
    return {
        "inventory_item_id": inventory_item_id,
        "location_id": location_id,
        "available": available,
        "updated_at": "2026-01-15T10:00:00-05:00",
    }
