"""
Bulk Operations for WooCommerce Products.

Provides bulk import and bulk update capabilities.
Supports CSV and JSON input formats for importing/updating
thousands of products at once.
"""

import csv
import io
import json
import uuid
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.woocommerce.models import WooCommerceProduct, WooCommerceInventoryLog, WooCommerceStore
from app.woocommerce.exceptions import ProductNotFoundError, StoreNotFoundError, StoreInactiveError

logger = logging.getLogger(__name__)


from dataclasses import dataclass, field


@dataclass
class BulkImportResult:
    """Result of a bulk import operation."""
    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "failed": self.failed,
            "errors": self.errors[:50],  # Limit error details
        }


async def bulk_import_products(
    db: AsyncSession,
    store_id: uuid.UUID,
    items: list[dict],
    user_id: Optional[uuid.UUID] = None,
) -> BulkImportResult:
    """
    Bulk import or update products from a list of dicts.

    Each item should contain at minimum:
    - sku (str) or wc_product_id (int) — used for matching existing products
    - name (str) — product name
    - price (str|Decimal) — product price
    - stock_quantity (int) — current stock level

    Additional fields are optional and matched by field name.
    Matches existing products by SKU first, then by wc_product_id.
    Creates new products if no match is found.

    Args:
        db: Database session
        store_id: Store UUID
        items: List of product dicts
        user_id: Optional user ID for audit logging

    Returns:
        BulkImportResult with counts and errors
    """
    result = BulkImportResult()
    result.total = len(items)

    # Verify store exists and is active
    store_result = await db.execute(
        select(WooCommerceStore).where(
            WooCommerceStore.id == store_id,
            WooCommerceStore.is_active == True,
        )
    )
    store = store_result.scalar_one_or_none()
    if not store:
        raise StoreNotFoundError(str(store_id))

    supported_fields = {
        "name", "sku", "barcode", "price", "regular_price", "sale_price",
        "stock_quantity", "stock_status", "manage_stock", "status",
        "weight", "description", "short_description", "featured_image_url",
        "type", "tax_status", "tax_class", "shipping_class",
        "average_rating", "featured", "backorders",
    }

    for idx, item in enumerate(items):
        try:
            sku = item.get("sku", "").strip()
            wc_product_id = item.get("wc_product_id")
            name = item.get("name", "").strip()

            if not sku and not wc_product_id:
                result.skipped += 1
                result.errors.append({
                    "row": idx, "sku": sku,
                    "error": "Missing both sku and wc_product_id",
                })
                continue

            if not name:
                result.skipped += 1
                result.errors.append({
                    "row": idx, "sku": sku or str(wc_product_id),
                    "error": "Missing product name",
                })
                continue

            # Look for existing product
            existing = None
            if sku:
                existing_result = await db.execute(
                    select(WooCommerceProduct).where(
                        WooCommerceProduct.store_id == store_id,
                        WooCommerceProduct.sku == sku,
                    )
                )
                existing = existing_result.scalar_one_or_none()

            if not existing and wc_product_id:
                existing_result = await db.execute(
                    select(WooCommerceProduct).where(
                        WooCommerceProduct.store_id == store_id,
                        WooCommerceProduct.wc_product_id == wc_product_id,
                    )
                )
                existing = existing_result.scalar_one_or_none()

            # Filter to supported fields only
            update_data = {}
            for field in supported_fields:
                if field in item and item[field] is not None:
                    val = item[field]
                    # Convert price strings to Decimal
                    if field in ("price", "regular_price", "sale_price") and isinstance(val, (str, int, float)):
                        val = Decimal(str(val))
                    update_data[field] = val

            if existing:
                # Update existing product
                for field, value in update_data.items():
                    if hasattr(existing, field):
                        setattr(existing, field, value)

                # Also update wc_product_id if provided and not set
                if wc_product_id and not existing.wc_product_id:
                    existing.wc_product_id = wc_product_id

                existing.last_synced_at = datetime.now(timezone.utc)

                # Create inventory log if stock changed
                if "stock_quantity" in update_data:
                    log = WooCommerceInventoryLog(
                        store_id=store_id,
                        product_id=existing.id,
                        wc_product_id=existing.wc_product_id or 0,
                        sku=existing.sku,
                        action="bulk_import_update",
                        quantity_before=existing.stock_quantity,
                        quantity_after=update_data.get("stock_quantity"),
                        quantity_change=(
                            update_data.get("stock_quantity", 0) - (existing.stock_quantity or 0)
                        ),
                        reason="Bulk import update",
                        source="bulk_import",
                        performed_by=user_id,
                    )
                    db.add(log)

                result.updated += 1

            else:
                # Create new product
                wc_id = wc_product_id or 0
                create_data = {
                    "store_id": store_id,
                    "wc_product_id": wc_id,
                    "name": name,
                    **update_data,
                }

                # Set defaults
                if "type" not in create_data:
                    create_data["type"] = "simple"
                if "status" not in create_data:
                    create_data["status"] = "publish"
                if "manage_stock" not in create_data:
                    create_data["manage_stock"] = True
                if "stock_quantity" not in create_data:
                    create_data["stock_quantity"] = 0
                if "price" not in create_data:
                    create_data["price"] = Decimal("0.00")

                # Remove fields that aren't model attributes
                model_fields = {k: v for k, v in create_data.items()
                               if hasattr(WooCommerceProduct, k)}

                new_product = WooCommerceProduct(**model_fields)
                new_product.last_synced_at = datetime.now(timezone.utc)
                db.add(new_product)
                await db.flush()

                # Create inventory log
                log = WooCommerceInventoryLog(
                    store_id=store_id,
                    product_id=new_product.id,
                    wc_product_id=new_product.wc_product_id or 0,
                    sku=new_product.sku,
                    action="bulk_import_create",
                    quantity_before=0,
                    quantity_after=new_product.stock_quantity or 0,
                    quantity_change=new_product.stock_quantity or 0,
                    reason="Bulk import create",
                    source="bulk_import",
                    performed_by=user_id,
                )
                db.add(log)

                result.created += 1

        except Exception as exc:
            logger.error("Bulk import row %d failed: %s", idx, exc)
            result.failed += 1
            result.errors.append({
                "row": idx,
                "sku": item.get("sku", ""),
                "error": str(exc),
            })

    await db.commit()
    return result


async def bulk_update_products(
    db: AsyncSession,
    store_id: uuid.UUID,
    items: list[dict],
    user_id: Optional[uuid.UUID] = None,
) -> BulkImportResult:
    """
    Bulk update existing products. Only updates fields provided.
    Matches by SKU or wc_product_id. Does NOT create new products.

    Args:
        db: Database session
        store_id: Store UUID
        items: List of product dicts with SKU/wc_product_id + fields to update
        user_id: Optional user ID for audit logging

    Returns:
        BulkImportResult with counts
    """
    result = BulkImportResult()
    result.total = len(items)

    supported_fields = {
        "name", "sku", "barcode", "price", "regular_price", "sale_price",
        "stock_quantity", "stock_status", "manage_stock", "status",
        "weight", "description", "short_description", "featured_image_url",
    }

    for idx, item in enumerate(items):
        try:
            sku = item.get("sku", "").strip()
            wc_product_id = item.get("wc_product_id")

            if not sku and not wc_product_id:
                result.skipped += 1
                result.errors.append({
                    "row": idx, "error": "Missing sku or wc_product_id for update",
                })
                continue

            # Find product
            existing = None
            if sku:
                existing_result = await db.execute(
                    select(WooCommerceProduct).where(
                        WooCommerceProduct.store_id == store_id,
                        WooCommerceProduct.sku == sku,
                    )
                )
                existing = existing_result.scalar_one_or_none()

            if not existing and wc_product_id:
                existing_result = await db.execute(
                    select(WooCommerceProduct).where(
                        WooCommerceProduct.store_id == store_id,
                        WooCommerceProduct.wc_product_id == wc_product_id,
                    )
                )
                existing = existing_result.scalar_one_or_none()

            if not existing:
                result.failed += 1
                result.errors.append({
                    "row": idx, "sku": sku or str(wc_product_id),
                    "error": "Product not found",
                })
                continue

            # Apply updates
            for field in supported_fields:
                if field in item and item[field] is not None:
                    val = item[field]
                    if field in ("price", "regular_price", "sale_price") and isinstance(val, (str, int, float)):
                        val = Decimal(str(val))
                    if hasattr(existing, field):
                        setattr(existing, field, val)

            existing.last_synced_at = datetime.now(timezone.utc)
            result.updated += 1

        except Exception as exc:
            logger.error("Bulk update row %d failed: %s", idx, exc)
            result.failed += 1
            result.errors.append({"row": idx, "error": str(exc)})

    await db.commit()
    return result


def parse_csv_to_items(csv_content: str) -> list[dict]:
    """
    Parse CSV content into a list of product dicts.
    Expects headers matching field names (sku, name, price, stock_quantity, etc.)
    """
    reader = csv.DictReader(io.StringIO(csv_content))
    items = []
    for row in reader:
        item = {}
        for key, value in row.items():
            if value and value.strip():
                key_clean = key.strip().lower().replace(" ", "_")
                val = value.strip()

                # Type conversion
                if key_clean in ("stock_quantity", "total_sales", "rating_count", "menu_order"):
                    try:
                        val = int(val)
                    except (ValueError, TypeError):
                        pass
                elif key_clean in ("price", "regular_price", "sale_price", "weight"):
                    try:
                        val = Decimal(str(val))
                    except (ValueError, TypeError):
                        pass
                elif key_clean in ("manage_stock", "on_sale", "featured", "backorders_allowed", "sold_individually"):
                    val = val.lower() in ("true", "yes", "1")

                item[key_clean] = val
        if item:
            items.append(item)
    return items


def parse_json_to_items(json_content: str) -> list[dict]:
    """Parse JSON string into a list of product dicts."""
    data = json.loads(json_content)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    if isinstance(data, dict) and "products" in data:
        return data["products"]
    raise ValueError("JSON must be an array or contain 'items'/'products' key")
