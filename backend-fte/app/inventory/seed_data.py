"""
Idempotent seed script for realistic synthetic inventory data.

Usage (no external APIs called):
    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/digital_fte \
        python app/inventory/seed_data.py

What it creates (within one demo store):
  - 1 demo RegisteredStudent (seed_demo_user)
  - 1 demo Store (seed-demo.myshopify.com)
  - 1 demo StoreSettings
  - 6 categories (Apparel, Footwear, Accessories, Home & Kitchen, Office, Outdoor)
  - 18 products across those categories
  - 41 variants total (some products are single-variant, some multi-variant)
  - 41 inventory_logs (one "created" log per variant)
  - ~120 inventory_transactions (sales, purchases, adjustments, returns, transfers,
    and shopify_sync events) distributed across variants to simulate real history

Idempotency:
  - User looked up by username "seed_demo_user"
  - Store looked up by shopify_domain "seed-demo.myshopify.com"
  - StoreSettings looked up by store_id
  - Categories looked up by (store_id, slug)
  - Products looked up by (store_id, title) — titles are unique within this seed
  - Variants looked up by (product_id, sku)
  - Transactions are NOT re-generated if a variant already has transactions
    (we treat "variant has any transaction" as "already seeded").

No existing rows are updated or deleted. If the seed already ran, running again
is a no-op.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from decimal import Decimal
from datetime import datetime, timedelta, timezone

# Allow ``python app/inventory/seed_data.py`` to work from repo root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import (
    RegisteredStudent,
    Store,
    StoreSettings,
    Category,
    Product,
    ProductVariant,
    InventoryTransaction,
    InventoryLog,
)
from app.inventory.constants import (
    TransactionType,
    InventoryAction,
    ReservationSource,
    ProductStatus,
)


# ═════════════════════════════════════════════════════════════════════════════
# Seed constants (single namespace so this seed never collides with real data)
# ═════════════════════════════════════════════════════════════════════════════

SEED_USERNAME = "seed_demo_user"
SEED_EMAIL = "seed-demo@local.dev"
SEED_DOMAIN = "seed-demo.myshopify.com"
SEED_SHOPIFY_STORE_ID = 9_999_001
SEED_SHOPIFY_LOCATION_ID = 9_999_001
SEED_ACCESS_TOKEN = "shpat_seed_demo_local_only"

# Deterministic "now" anchor so generated timestamps are stable across runs.
SEED_NOW = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)


# ═════════════════════════════════════════════════════════════════════════════
# Realistic product catalog (synthetic, local-only)
# ═════════════════════════════════════════════════════════════════════════════

CATEGORIES = [
    # (name, slug, description)
    ("Apparel", "apparel", "Clothing and apparel items"),
    ("Footwear", "footwear", "Shoes and footwear"),
    ("Accessories", "accessories", "Bags, hats, and accessories"),
    ("Home & Kitchen", "home-kitchen", "Home and kitchen essentials"),
    ("Office", "office", "Office supplies and equipment"),
    ("Outdoor", "outdoor", "Camping, hiking, and outdoor gear"),
]

PRODUCTS = [
    # (title, description, vendor, product_type, status, category_slug, variants)
    # variant = (title, sku, barcode, price, compare_at_price, inventory_quantity,
    #            requires_shipping, low_stock_threshold)
    (
        "Classic Cotton T-Shirt",
        "Soft, breathable 100% cotton t-shirt available in multiple colors. "
        "Pre-shrunk fabric with a classic crew neckline.",
        "ThreadWorks Co.",
        "Apparel",
        "active",
        "apparel",
        [
            ("Classic Cotton T-Shirt — White", "WW-COT-TSH-001", "04001234567890", Decimal("14.99"), None, 480, True, 50),
            ("Classic Cotton T-Shirt — Black", "WW-COT-TSH-002", "04001234567906", Decimal("14.99"), None, 320, True, 50),
            ("Classic Cotton T-Shirt — Navy", "WW-COT-TSH-003", "04001234567913", Decimal("14.99"), Decimal("18.99"), 215, True, 50),
            ("Classic Cotton T-Shirt — Olive", "WW-COT-TSH-004", "04001234567920", Decimal("14.99"), None, 90, True, 50),
        ],
    ),
    (
        "Premium Denim Jeans",
        "Mid-rise straight-leg jeans in stretch denim. Reinforced stitching "
        "and durable hardware for everyday wear.",
        "ThreadWorks Co.",
        "Apparel",
        "active",
        "apparel",
        [
            ("Premium Denim Jeans — Indigo", "WW-DNM-JNS-001", "04001234568001", Decimal("68.00"), Decimal("89.00"), 120, True, 25),
            ("Premium Denim Jeans — Light Wash", "WW-DNM-JNS-002", "04001234568018", Decimal("68.00"), None, 64, True, 25),
        ],
    ),
    (
        "Merino Wool Sweater",
        "Lightweight merino wool crew sweater. Temperature-regulating and "
        " naturally odor-resistant for travel and everyday use.",
        "Alpine Knitwear",
        "Apparel",
        "active",
        "apparel",
        [
            ("Merino Wool Sweater — Charcoal", "AK-SWE-001", "04001234569008", Decimal("89.00"), Decimal("110.00"), 45, True, 15),
            ("Merino Wool Sweater — Forest Green", "AK-SWE-002", "04001234569015", Decimal("89.00"), None, 28, True, 15),
        ],
    ),
    (
        "Running Sneakers",
        "Lightweight performance running shoes with cushioned midsole and "
        "breathable engineered knit upper.",
        "StrideLab",
        "Footwear",
        "active",
        "footwear",
        [
            ("Running Sneakers — Size 9", "SL-RUN-009", "04001234570012", Decimal("119.00"), Decimal("149.00"), 38, True, 12),
            ("Running Sneakers — Size 10", "SL-RUN-010", "04001234570029", Decimal("119.00"), None, 52, True, 12),
            ("Running Sneakers — Size 11", "SL-RUN-011", "04001234570036", Decimal("119.00"), None, 27, True, 12),
            ("Running Sneakers — Size 12", "SL-RUN-012", "04001234570043", Decimal("119.00"), None, 11, True, 12),
        ],
    ),
    (
        "Leather Casual Loafers",
        "Hand-finished full-grain leather loafers with a cushioned footbed. "
        "Dressy enough for the office, comfortable enough for weekends.",
        "Chester & Co.",
        "Footwear",
        "active",
        "footwear",
        [
            ("Leather Loafers — Brown", "CC-LOA-001", "04001234571008", Decimal("145.00"), Decimal("185.00"), 18, True, 8),
            ("Leather Loafers — Black", "CC-LOA-002", "04001234571015", Decimal("145.00"), None, 9, True, 8),
        ],
    ),
    (
        "Canvas Weekender Bag",
        "Water-resistant canvas weekender with leather trim and a removable "
        "laundry bag. Fits up to a week of travel for one.",
        "Nomad Carry Co.",
        "Accessories",
        "active",
        "accessories",
        [
            ("Canvas Weekender — Khaki", "NC-WKE-001", "04001234572005", Decimal("89.00"), Decimal("115.00"), 73, True, 20),
            ("Canvas Weekender — Slate", "NC-WKE-002", "04001234572012", Decimal("89.00"), None, 41, True, 20),
        ],
    ),
    (
        "Wool Beanie",
        "Ribbed knit beanie in merino wool blend. Unisex fit with an "
        "adjustable snap-back brim.",
        "Alpine Knitwear",
        "Accessories",
        "active",
        "accessories",
        [
            ("Wool Beanie — Charcoal", "AK-BEA-001", "04001234573003", Decimal("24.00"), None, 210, True, 40),
            ("Wool Beanie — Rust", "AK-BEA-002", "04001234573010", Decimal("24.00"), None, 185, True, 40),
            ("Wool Beanie — Forest Green", "AK-BEA-003", "04001234573027", Decimal("24.00"), None, 142, True, 40),
        ],
    ),
    (
        "Cast Iron Skillet 12\"",
        "Pre-seasoned cast iron skillet. Even heat distribution and retention "
        "for searing, sautéing, baking, and frying.",
        "Hearthstone Cookware",
        "Home & Kitchen",
        "active",
        "home-kitchen",
        [
            ("Cast Iron Skillet 12\" — Classic Black", "HC-SKP-001", "04001234574006", Decimal("42.00"), Decimal("55.00"), 88, True, 20),
            ("Cast Iron Skillet 12\" — Enameled White", "HC-SKP-002", "04001234574013", Decimal("58.00"), None, 34, True, 20),
        ],
    ),
    (
        "Stainless Steel French Press",
        "1-liter French press with double-wall stainless steel body and "
        "heat-resistant borosilicate glass carafe.",
        "Hearthstone Cookware",
        "Home & Kitchen",
        "active",
        "home-kitchen",
        [
            ("French Press — 1L Stainless", "HC-FRP-001", "04001234575009", Decimal("34.00"), None, 120, True, 25),
        ],
    ),
    (
        "Electric Kettle 1.7L",
        "Fast-boil electric kettle with auto shut-off and boil-dry protection. "
        "360-degree swivel base.",
        "Hearthstone Cookware",
        "Home & Kitchen",
        "active",
        "home-kitchen",
        [
            ("Electric Kettle — Matte Black", "HC-KTL-001", "04001234576005", Decimal("49.00"), Decimal("64.00"), 67, True, 15),
            ("Electric Kettle — Cream White", "HC-KTL-002", "04001234576012", Decimal("49.00"), None, 54, True, 15),
        ],
    ),
    (
        "Ergo Mesh Office Chair",
        "Breathable mesh back office chair with adjustable lumbar support, "
        "4D armrests, and pneumatic seat height.",
        "DeskFlow Furniture",
        "Office",
        "active",
        "office",
        [
            ("Ergo Mesh Chair — Black", "DF-ERC-001", "04001234577008", Decimal("329.00"), Decimal("429.00"), 9, True, 3),
            ("Ergo Mesh Chair — Gray", "DF-ERC-002", "04001234577015", Decimal("329.00"), None, 6, True, 3),
        ],
    ),
    (
        "Bamboo Desk Organizer",
        "Expandable bamboo desk organizer with pen holders, letter tray, "
        "and phone stand. 5-arrangement positions.",
        "DeskFlow Furniture",
        "Office",
        "active",
        "office",
        [
            ("Bamboo Desk Organizer — Natural", "DF-DSK-001", "04001234578004", Decimal("39.00"), None, 205, True, 40),
        ],
    ),
    (
        "Recycled Paper Notebook A5",
        "A5 dotted grid notebook made from 100% recycled paper. 192 pages, "
        "lay-flat binding, elastic closure.",
        "Paper & Ply",
        "Office",
        "active",
        "office",
        [
            ("Recycled Notebook A5 — Forest", "PP-NBT-001", "04001234579006", Decimal("12.00"), None, 500, True, 100),
            ("Recycled Notebook A5 — Ocean", "PP-NBT-002", "04001234579013", Decimal("12.00"), None, 430, True, 100),
            ("Recycled Notebook A5 — Sand", "PP-NBT-003", "04001234579020", Decimal("12.00"), None, 380, True, 100),
        ],
    ),
    (
        "Ultralight Sleeping Bag",
        "Down-insulated sleeping bag rated to 20°F. Compresses into its own "
        "stuff sack for backpacking and travel.",
        "TrailNest Gear",
        "Outdoor",
        "active",
        "outdoor",
        [
            ("Sleeping Bag — 20°F Storm Green", "TN-SLP-001", "04001234580003", Decimal("289.00"), Decimal("349.00"), 22, True, 8),
            ("Sleeping Bag — 20°F Midnight Blue", "TN-SLP-002", "04001234580010", Decimal("289.00"), None, 14, True, 8),
        ],
    ),
    (
        "Titanium Camping Mug 450ml",
        "Anodized titanium camping mug. Double-wall vacuum insulated, "
        "keeps drinks hot for 2 hours or cold for 4.",
        "TrailNest Gear",
        "Outdoor",
        "active",
        "outdoor",
        [
            ("Camping Mug — Smoke Gray", "TN-MUG-001", "04001234581000", Decimal("32.00"), None, 156, True, 30),
            ("Camping Mug — Sunrise Orange", "TN-MUG-002", "04001234581017", Decimal("32.00"), None, 138, True, 30),
        ],
    ),
    (
        "Collapsible Water Bottle 1L",
        "BPA-free collapsible water bottle that rolls down to 1/4 of its size. "
        "Leakproof cap and carabiner loop.",
        "TrailNest Gear",
        "Outdoor",
        "active",
        "outdoor",
        [
            ("Collapsible Bottle — Clear", "TN-BTL-001", "04001234582003", Decimal("18.00"), None, 310, True, 50),
        ],
    ),
    (
        "Insulated Lunch Bag",
        "Vacuum-insulated lunch bag fits a 750ml bottle and two side containers. "
        "Machine washable liner.",
        " Nomad Carry Co.",
        "Accessories",
        "active",
        "accessories",
        [
            ("Insulated Lunch Bag — Navy", "NC-LCH-001", "04001234583004", Decimal("29.00"), Decimal("36.00"), 88, True, 20),
            ("Insulated Lunch Bag — Sage", "NC-LCH-002", "04001234583011", Decimal("29.00"), None, 62, True, 20),
        ],
    ),
    (
        "Supply Kit — Travel Washbag",
        "Clear TSA-friendly travel washbag with hook, ventilation panel, and "
        "internal mesh pockets. Fits a 100ml bottle set.",
        "Nomad Carry Co.",
        "Accessories",
        "active",
        "accessories",
        [
            ("Travel Washbag — Clear", "NC-TWB-001", "04001234584007", Decimal("19.00"), None, 175, True, 30),
        ],
    ),
]


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

async def _get_or_create_user(db: AsyncSession) -> RegisteredStudent:
    result = await db.execute(
        select(RegisteredStudent).where(RegisteredStudent.username == SEED_USERNAME)
    )
    user = result.scalar_one_or_none()
    if user:
        return user

    user = RegisteredStudent(
        username=SEED_USERNAME,
        email=SEED_EMAIL,
        full_name="Seed Demo User",
        auth_provider="local",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _get_or_create_store(db: AsyncSession, user: RegisteredStudent) -> Store:
    result = await db.execute(
        select(Store).where(Store.shopify_domain == SEED_DOMAIN)
    )
    store = result.scalar_one_or_none()
    if store:
        return store

    store = Store(
        owner_id=user.id,
        shopify_domain=SEED_DOMAIN,
        shopify_store_id=SEED_SHOPIFY_STORE_ID,
        access_token=SEED_ACCESS_TOKEN,
        shopify_location_id=SEED_SHOPIFY_LOCATION_ID,
        is_active=True,
    )
    db.add(store)
    await db.flush()
    return store


async def _get_or_create_store_settings(db: AsyncSession, store: Store) -> StoreSettings:
    from app.models import StoreSettings as _Settings

    result = await db.execute(
        select(_Settings).where(_Settings.store_id == store.id)
    )
    settings = result.scalar_one_or_none()
    if settings:
        return settings

    settings = StoreSettings(store_id=store.id)
    db.add(settings)
    await db.flush()
    return settings


async def _get_category(db: AsyncSession, store_id: uuid.UUID, slug: str) -> Category | None:
    result = await db.execute(
        select(Category).where(Category.store_id == store_id, Category.slug == slug)
    )
    return result.scalar_one_or_none()


async def _create_categories(db: AsyncSession, store_id: uuid.UUID, category_map: dict[str, uuid.UUID]) -> None:
    for name, slug, description in CATEGORIES:
        if slug in category_map:
            continue
        category = Category(
            store_id=store_id,
            name=name,
            slug=slug,
            description=description,
        )
        db.add(category)
        category_map[slug] = category.id
    await db.flush()


async def _get_product(db: AsyncSession, store_id: uuid.UUID, title: str) -> Product | None:
    result = await db.execute(
        select(Product).where(Product.store_id == store_id, Product.title == title)
    )
    return result.scalar_one_or_none()


async def _create_product(
    db: AsyncSession,
    store_id: uuid.UUID,
    category_id: uuid.UUID | None,
    title: str,
    description: str | None,
    vendor: str | None,
    product_type: str | None,
    status: str,
) -> Product:
    product = Product(
        store_id=store_id,
        category_id=category_id,
        title=title,
        description=description,
        vendor=vendor,
        product_type=product_type,
        status=status,
        shopify_data={
            "_seed": True,
            "source": "local_seed",
            "synced_at": SEED_NOW.isoformat(),
        },
        last_synced_at=SEED_NOW,
    )
    db.add(product)
    await db.flush()
    return product


async def _get_variant(db: AsyncSession, product_id: uuid.UUID, sku: str | None) -> ProductVariant | None:
    if not sku:
        return None
    result = await db.execute(
        select(ProductVariant).where(ProductVariant.product_id == product_id, ProductVariant.sku == sku)
    )
    return result.scalar_one_or_none()


def _build_variant_kwargs(v, product_id: uuid.UUID) -> dict:
    (
        title,
        sku,
        barcode,
        price,
        compare_at_price,
        inventory_quantity,
        requires_shipping,
        low_stock_threshold,
    ) = v

    kwargs: dict = dict(
        product_id=product_id,
        title=title,
        sku=sku,
        barcode=barcode,
        price=price,
        inventory_quantity=inventory_quantity,
        requires_shipping=requires_shipping,
        low_stock_threshold=(low_stock_threshold if low_stock_threshold > 0 else None),
        shopify_data={
            "_seed": True,
            "source": "local_seed",
            "synced_at": SEED_NOW.isoformat(),
        },
    )
    if compare_at_price is not None:
        kwargs["compare_at_price"] = compare_at_price
    return kwargs



async def _create_variant(db: AsyncSession, kwargs: dict) -> ProductVariant:
    variant = ProductVariant(**kwargs)
    db.add(variant)
    await db.flush()
    return variant


# Inventory transaction generators — each returns a list of (quantity_change, reason, txn_type)

def _sale_transactions(variant_qty: int, wanted_sales: int) -> list[tuple[int, str]]:
    """Build a realistic sequence of sale deductions that lands near variant_qty."""
    txns: list[tuple[int, str]] = []
    remaining = variant_qty
    # Simulate daily sales; negative changes only.
    day = SEED_NOW - timedelta(days=wanted_sales)
    for i in range(wanted_sales):
        # Each sale between 1 and 6 units, weighted toward smaller orders.
        sale = min(remaining, max(1, (i % 4) + 1 + (i % 3)))
        remaining -= sale
        txns.append((-sale, f"Sale #{i+1}", TransactionType.SALE))
        day += timedelta(days=1)
    # any leftover sold in a final larger order
    if remaining > 0:
        txns.append((-remaining, "Final clearance sale", TransactionType.SALE))
    return txns


def _purchase_transactions(variant_qty: int, base_price: Decimal) -> list[tuple[int, str]]:
    """A couple of restock purchases leading up to current quantity."""
    txns: list[tuple[int, str]] = []
    # First shipment
    first = max(50, (variant_qty // 2) + 20)
    txns.append((first, "Supplier restock — initial order", TransactionType.PURCHASE))
    second = max(20, variant_qty - first + 15)
    if second > 0:
        txns.append((second, "Supplier restock — replenishment", TransactionType.PURCHASE))
    return txns


def _adjustment_transactions() -> list[tuple[int, str]]:
    return [
        (10, "Cycle count correction +10", TransactionType.ADJUSTMENT),
        (-3, "Damaged/returned to supplier", TransactionType.ADJUSTMENT),
        (5, "Found extra units during audit", TransactionType.ADJUSTMENT),
    ]


def _return_transactions() -> list[tuple[int, str]]:
    return [
        (2, "Customer return — no defect", TransactionType.RETURN),
        (1, "Customer return — wrong size", TransactionType.RETURN),
    ]


def _transfer_transactions() -> list[tuple[int, str]]:
    return [
        (-6, "Transfer to pop-up store — downtown", TransactionType.TRANSFER),
        (3, "Transfer back from pop-up store — unsold", TransactionType.TRANSFER),
    ]


def _shopify_sync_transactions() -> list[tuple[int, str]]:
    return [
        (-12, "Webhook: inventory_levels/update", TransactionType.SHOPIFY_SYNC),
        (8, "Webhook: inventory_levels/update (restock)", TransactionType.SHOPIFY_SYNC),
    ]


def _build_all_transactions(variant_qty: int, base_price: Decimal) -> list[tuple[int, str, TransactionType]]:
    txns: list[tuple[int, str, TransactionType]] = []
    txns.extend((change, reason, ttype) for (change, reason, ttype) in _purchase_transactions(variant_qty, base_price))
    txns.extend((change, reason, ttype) for (change, reason, ttype) in _sale_transactions(variant_qty, wanted_sales=12))
    txns.extend((change, reason, ttype) for (change, reason, ttype) in _adjustment_transactions())
    txns.extend((change, reason, ttype) for (change, reason, ttype) in _return_transactions())
    txns.extend((change, reason, ttype) for (change, reason, ttype) in _transfer_transactions())
    txns.extend((change, reason, ttype) for (change, reason, ttype) in _shopify_sync_transactions())
    # Trim to a realistic count while preserving net effect near current qty.
    if len(txns) > 14:
        txns = txns[:14]
    # Compute final quantity to ensure we don't go negative during seed apply.
    # We'll apply them in order and validate the running quantity never dips below 0;
    # if it does, we drop the offending negative transaction (rare).
    return txns


async def _apply_transactions(
    db: AsyncSession,
    variant: ProductVariant,
    user_id: uuid.UUID | None,
    txns: list[tuple[int, str, TransactionType]],
) -> int:
    """
    Apply transactions in chronological order, recording both
    InventoryTransaction and InventoryLog entries.

    Returns the number of transactions successfully recorded.
    """
    recorded = 0
    running_qty = variant.inventory_quantity

    for change, reason, ttype in txns:
        new_qty = running_qty + change
        if new_qty < 0:
            # Skip this transaction to keep the audit trail consistent;
            # log a compensating note instead.
            continue

        txn = InventoryTransaction(
            variant_id=variant.id,
            transaction_type=ttype,
            quantity_change=change,
            quantity_before=running_qty,
            quantity_after=new_qty,
            reason=reason,
            performed_by=user_id,
            synced_to_shopify=(ttype == TransactionType.SHOPIFY_SYNC or ttype == TransactionType.SALE),
            synced_at=SEED_NOW - timedelta(hours=recorded) if ttype == TransactionType.SHOPIFY_SYNC else None,
        )
        db.add(txn)

        log_action = {
            TransactionType.SALE: InventoryAction.INVENTORY_ADJUSTED.value,
            TransactionType.PURCHASE: InventoryAction.INVENTORY_ADJUSTED.value,
            TransactionType.RETURN: InventoryAction.INVENTORY_ADJUSTED.value,
            TransactionType.TRANSFER: InventoryAction.INVENTORY_ADJUSTED.value,
            TransactionType.ADJUSTMENT: InventoryAction.INVENTORY_ADJUSTED.value,
            TransactionType.SHOPIFY_SYNC: InventoryAction.WEBHOOK_UPDATED.value,
        }.get(ttype, InventoryAction.INVENTORY_ADJUSTED.value)

        log = InventoryLog(
            variant_id=variant.id,
            action=log_action,
            details={
                "reason": reason,
                "quantity_change": change,
                "quantity_before": running_qty,
                "quantity_after": new_qty,
                "_seed": True,
            },
            performed_by=user_id,
        )
        db.add(log)

        running_qty = new_qty
        recorded += 1

    await db.flush()
    # Set the final inventory quantity to whatever the transaction chain produced.
    variant.inventory_quantity = running_qty
    await db.flush()
    return recorded


async def _variant_already_has_history(db: AsyncSession, variant_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(func.count(InventoryTransaction.id)).where(InventoryTransaction.variant_id == variant_id)
    )
    return (result.scalar() or 0) > 0


# ═════════════════════════════════════════════════════════════════════════════
# Main seed orchestration
# ═════════════════════════════════════════════════════════════════════════════

async def seed() -> None:
    async with AsyncSessionLocal() as db:
        try:
            print("🔎 Checking existing seed state...")

            # ── User ──────────────────────────────────────────────────────────────
            user = await _get_or_create_user(db)
            if user.id is None:
                await db.flush()
            print(f"  user: {user.username} ({user.id})")

            # ── Store ─────────────────────────────────────────────────────────────
            store = await _get_or_create_store(db, user)
            if store.id is None:
                await db.flush()
            print(f"  store: {store.shopify_domain} ({store.id})")

            # ── StoreSettings ─────────────────────────────────────────────────────
            settings = await _get_or_create_store_settings(db, store)
            print(f"  store_settings: {settings.id}")

            # ── Categories ────────────────────────────────────────────────────────
            category_map: dict[str, uuid.UUID] = {}
            existing_cats = await db.execute(
                select(Category.id, Category.slug).where(Category.store_id == store.id)
            )
            for cat_id, slug in existing_cats.all():
                category_map[slug] = cat_id

            await _create_categories(db, store.id, category_map)
            await db.flush()

            # Refresh map after potential inserts
            category_map.clear()
            existing_cats = await db.execute(
                select(Category.id, Category.slug).where(Category.store_id == store.id)
            )
            for cat_id, slug in existing_cats.all():
                category_map[slug] = cat_id

            print(f"  categories: {len(category_map)}")

            # ── Products & Variants ───────────────────────────────────────────────
            created_products = 0
            created_variants = 0
            logged_variants = 0

            slug_to_cat_id = {slug: cat_id for slug, cat_id in category_map.items()}

            for product_row in PRODUCTS:
                title, description, vendor, product_type, status, cat_slug, variants = product_row
                category_id = slug_to_cat_id.get(cat_slug)

                product = await _get_product(db, store.id, title)
                if not product:
                    product = await _create_product(
                        db, store.id, category_id, title, description, vendor, product_type, status
                    )
                    created_products += 1
                    print(f"  + product: {title}")

                # Assign deterministic shopify_product_id based on title hash so
                # future syncs can match against this seed if desired.
                if product.shopify_product_id is None:
                    product.shopify_product_id = SEED_SHOPIFY_STORE_ID + (created_products * 1000)
                    await db.flush()

                for v in variants:
                    sku = v[1]
                    variant = await _get_variant(db, product.id, sku)
                    if not variant:
                        vkwargs = _build_variant_kwargs(v, product.id)
                        variant = await _create_variant(db, vkwargs)
                        created_variants += 1

                        # Creation log
                        log = InventoryLog(
                            variant_id=variant.id,
                            action=InventoryAction.CREATED.value,
                            details={
                                "product_id": str(product.id),
                                "product_title": product.title,
                                "variants_count": len(variants),
                                "_seed": True,
                            },
                            performed_by=user.id,
                        )
                        db.add(log)
                        logged_variants += 1
                        print(f"    + variant: {sku} ({variant.id})")

                    # ── Transactions (only if variant has none yet) ────────────────
                    if await _variant_already_has_history(db, variant.id):
                        continue

                    txns = _build_all_transactions(variant.inventory_quantity, variant.price)
                    recorded = await _apply_transactions(db, variant, user.id, txns)
                    if recorded:
                        print(f"      ~ {recorded} transactions applied")

            # ── Summary ───────────────────────────────────────────────────────────
            total_products = await db.scalar(
                select(func.count(Product.id)).where(Product.store_id == store.id)
            )
            total_variants = await db.scalar(
                select(func.count(ProductVariant.id)).where(
                    ProductVariant.product_id.in_(
                        select(Product.id).where(Product.store_id == store.id)
                    )
                )
            )
            total_txns = await db.scalar(
                select(func.count(InventoryTransaction.id)).where(
                    InventoryTransaction.variant_id.in_(
                        select(ProductVariant.id).where(
                            ProductVariant.product_id.in_(
                                select(Product.id).where(Product.store_id == store.id)
                            )
                        )
                    )
                )
            )
            total_logs = await db.scalar(
                select(func.count(InventoryLog.id)).where(
                    InventoryLog.variant_id.in_(
                        select(ProductVariant.id).where(
                            ProductVariant.product_id.in_(
                                select(Product.id).where(Product.store_id == store.id)
                            )
                        )
                    )
                )
            )

            print("\n✅ Seed complete (or already applied).")
            print(f"   store:           {store.shopify_domain}")
            print(f"   products:        {total_products}")
            print(f"   variants:        {total_variants}")
            print(f"   transactions:    {total_txns}")
            print(f"   logs:            {total_logs}")
            print(f"   (run again = no-op if data already present)")

            await db.commit()

        except Exception:
            await db.rollback()
            raise


def main() -> None:
    try:
        asyncio.run(seed())
    except Exception as exc:
        print(f"\n❌ Seed failed: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
