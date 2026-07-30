"""
WooCommerce Integration Module — Initial Migration

Creates all WooCommerce-specific tables:
- wc_stores
- wc_categories
- wc_tags
- wc_products
- wc_orders
- wc_order_items
- wc_customers
- wc_coupons
- wc_inventory_logs
- wc_alerts
- wc_sync_logs
- wc_settings

Revision ID: woocommerce_initial
Revises: 694d38b99c0b
Create Date: 2026-07-27
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "woocommerce_initial"
down_revision: Union[str, None] = "694d38b99c0b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enums ──
    sa.Enum("connected", "disconnected", "error", "pending_verification", name="wc_store_status_enum").create(op.get_bind(), checkfirst=True)
    sa.Enum("instock", "outofstock", "onbackorder", name="wc_stock_status_enum").create(op.get_bind(), checkfirst=True)
    sa.Enum("pending", "processing", "on_hold", "completed", "cancelled", "refunded", "failed", "trash", "draft", name="wc_order_status_enum").create(op.get_bind(), checkfirst=True)
    sa.Enum("low_stock", "out_of_stock", "sync_failed", "api_failure", "store_disconnected", "order_paid", "high_value_order", name="wc_alert_type_enum").create(op.get_bind(), checkfirst=True)
    sa.Enum("info", "warning", "critical", name="wc_alert_severity_enum").create(op.get_bind(), checkfirst=True)
    sa.Enum("pending", "in_progress", "completed", "failed", "partial", name="wc_sync_status_enum").create(op.get_bind(), checkfirst=True)
    sa.Enum("full", "incremental", "scheduled", "manual", "webhook", name="wc_sync_type_enum").create(op.get_bind(), checkfirst=True)

    # ── wc_stores ──
    op.create_table(
        "wc_stores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("registered_students.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("store_name", sa.String(255), nullable=False),
        sa.Column("store_url", sa.String(512), nullable=False, unique=True, index=True),
        sa.Column("consumer_key", sa.String(512), nullable=False),
        sa.Column("consumer_secret", sa.String(512), nullable=False),
        sa.Column("wc_store_id", sa.BigInteger(), nullable=True),
        sa.Column("wc_version", sa.String(50), nullable=True),
        sa.Column("status", sa.Enum("connected", "disconnected", "error", "pending_verification", name="wc_store_status_enum"), nullable=False, server_default="connected"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("webhook_secret", sa.String(255), nullable=True),
        sa.Column("webhooks_registered", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # ── wc_categories ──
    op.create_table(
        "wc_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wc_stores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("wc_category_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wc_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("wc_parent_id", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("image_url", sa.String(1024), nullable=True),
        sa.Column("display", sa.String(50), nullable=False, server_default="default"),
        sa.Column("menu_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("product_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("raw_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(op.f("ix_wc_categories_wc_category_id"), "wc_categories", ["wc_category_id"], unique=False)

    # ── wc_tags ──
    op.create_table(
        "wc_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wc_stores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("wc_tag_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("product_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("raw_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # ── wc_products ──
    op.create_table(
        "wc_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wc_stores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("wc_product_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("parent_id", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("type", sa.String(50), nullable=False, server_default="simple"),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("slug", sa.String(512), nullable=True),
        sa.Column("permalink", sa.String(1024), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("sku", sa.String(100), nullable=True, index=True),
        sa.Column("barcode", sa.String(100), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("regular_price", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("sale_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("on_sale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("purchasable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("featured_image_url", sa.String(1024), nullable=True),
        sa.Column("featured_image_id", sa.BigInteger(), nullable=True),
        sa.Column("gallery_image_urls", postgresql.JSONB(), nullable=True),
        sa.Column("manage_stock", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("stock_quantity", sa.Integer(), nullable=True),
        sa.Column("stock_status", sa.Enum("instock", "outofstock", "onbackorder", name="wc_stock_status_enum"), nullable=False, server_default="instock"),
        sa.Column("backorders", sa.String(20), nullable=False, server_default="no"),
        sa.Column("backorders_allowed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sold_individually", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("total_sales", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("weight", sa.String(50), nullable=True),
        sa.Column("dimensions", postgresql.JSONB(), nullable=True),
        sa.Column("shipping_class", sa.String(100), nullable=True),
        sa.Column("shipping_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("tax_status", sa.String(50), nullable=False, server_default="taxable"),
        sa.Column("tax_class", sa.String(100), nullable=True),
        sa.Column("attributes", postgresql.JSONB(), nullable=True),
        sa.Column("default_attributes", postgresql.JSONB(), nullable=True),
        sa.Column("category_ids", postgresql.JSONB(), nullable=True),
        sa.Column("tag_ids", postgresql.JSONB(), nullable=True),
        sa.Column("average_rating", sa.String(10), nullable=False, server_default="0"),
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("reviews_allowed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(50), nullable=False, server_default="publish"),
        sa.Column("raw_data", postgresql.JSONB(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # ── wc_customers ──
    op.create_table(
        "wc_customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wc_stores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("wc_customer_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("email", sa.String(255), nullable=False, index=True),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="customer"),
        sa.Column("avatar_url", sa.String(1024), nullable=True),
        sa.Column("billing", postgresql.JSONB(), nullable=True),
        sa.Column("shipping", postgresql.JSONB(), nullable=True),
        sa.Column("orders_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_spent", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("meta_data", postgresql.JSONB(), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # ── wc_orders ──
    op.create_table(
        "wc_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wc_stores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("wc_order_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("parent_id", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("number", sa.String(50), nullable=False),
        sa.Column("order_key", sa.String(255), nullable=True),
        sa.Column("status", sa.Enum("pending", "processing", "on_hold", "completed", "cancelled", "refunded", "failed", "trash", "draft", name="wc_order_status_enum"), nullable=False, server_default="pending"),
        sa.Column("currency", sa.String(10), nullable=False, server_default="USD"),
        sa.Column("customer_id", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("customer_ip_address", sa.String(50), nullable=True),
        sa.Column("customer_user_agent", sa.String(500), nullable=True),
        sa.Column("customer_note", sa.Text(), nullable=True),
        sa.Column("billing", postgresql.JSONB(), nullable=True),
        sa.Column("shipping", postgresql.JSONB(), nullable=True),
        sa.Column("payment_method", sa.String(100), nullable=True),
        sa.Column("payment_method_title", sa.String(255), nullable=True),
        sa.Column("transaction_id", sa.String(255), nullable=True),
        sa.Column("date_paid", sa.String(50), nullable=True),
        sa.Column("date_completed", sa.String(50), nullable=True),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("discount_total", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("discount_tax", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("shipping_total", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("shipping_tax", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("cart_tax", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("total_tax", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("prices_include_tax", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("coupon_lines", postgresql.JSONB(), nullable=True),
        sa.Column("fee_lines", postgresql.JSONB(), nullable=True),
        sa.Column("shipping_lines", postgresql.JSONB(), nullable=True),
        sa.Column("tax_lines", postgresql.JSONB(), nullable=True),
        sa.Column("refunds", postgresql.JSONB(), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # ── wc_order_items ──
    op.create_table(
        "wc_order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wc_orders.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("wc_order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("wc_product_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wc_products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("price", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("subtotal_tax", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("total_tax", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("meta_data", postgresql.JSONB(), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # ── wc_coupons ──
    op.create_table(
        "wc_coupons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wc_stores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("wc_coupon_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("code", sa.String(100), nullable=False, index=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0.00")),
        sa.Column("discount_type", sa.String(50), nullable=False, server_default="fixed_cart"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("date_expires", sa.String(50), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("individual_use", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("product_ids", postgresql.JSONB(), nullable=True),
        sa.Column("excluded_product_ids", postgresql.JSONB(), nullable=True),
        sa.Column("product_categories", postgresql.JSONB(), nullable=True),
        sa.Column("excluded_product_categories", postgresql.JSONB(), nullable=True),
        sa.Column("usage_limit", sa.Integer(), nullable=True),
        sa.Column("usage_limit_per_user", sa.Integer(), nullable=True),
        sa.Column("limit_usage_to_x_items", sa.Integer(), nullable=True),
        sa.Column("free_shipping", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("exclude_sale_items", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("minimum_amount", sa.String(20), nullable=True),
        sa.Column("maximum_amount", sa.String(20), nullable=True),
        sa.Column("email_restrictions", postgresql.JSONB(), nullable=True),
        sa.Column("used_by", postgresql.JSONB(), nullable=True),
        sa.Column("meta_data", postgresql.JSONB(), nullable=True),
        sa.Column("raw_data", postgresql.JSONB(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # ── wc_inventory_logs ──
    op.create_table(
        "wc_inventory_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wc_stores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wc_products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("wc_product_id", sa.BigInteger(), nullable=False),
        sa.Column("sku", sa.String(100), nullable=True),
        sa.Column("action", sa.String(50), nullable=False, index=True),
        sa.Column("quantity_before", sa.Integer(), nullable=True),
        sa.Column("quantity_after", sa.Integer(), nullable=True),
        sa.Column("quantity_change", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("performed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("registered_students.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # ── wc_alerts ──
    op.create_table(
        "wc_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wc_stores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("alert_type", sa.Enum("low_stock", "out_of_stock", "sync_failed", "api_failure", "store_disconnected", "order_paid", "high_value_order", name="wc_alert_type_enum"), nullable=False),
        sa.Column("severity", sa.Enum("info", "warning", "critical", name="wc_alert_severity_enum"), nullable=False, server_default="warning"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # ── wc_sync_logs ──
    op.create_table(
        "wc_sync_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wc_stores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("sync_type", sa.Enum("full", "incremental", "scheduled", "manual", "webhook", name="wc_sync_type_enum"), nullable=False),
        sa.Column("resource", sa.String(50), nullable=False),
        sa.Column("status", sa.Enum("pending", "in_progress", "completed", "failed", "partial", name="wc_sync_status_enum"), nullable=False, server_default="pending"),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_items", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_items", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_items", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("skipped_items", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", postgresql.JSONB(), nullable=True),
        sa.Column("meta_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # ── wc_settings ──
    op.create_table(
        "wc_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("wc_stores.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("auto_sync_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sync_interval_hours", sa.Integer(), nullable=False, server_default=sa.text("6")),
        sa.Column("sync_products", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sync_orders", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sync_customers", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sync_categories", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sync_coupons", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("low_stock_threshold", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.Column("low_stock_alerts", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sync_failure_alerts", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("email_alerts", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("alert_email", sa.String(255), nullable=True),
        sa.Column("webhook_callback_url", sa.String(1024), nullable=True),
        sa.Column("webhook_secret", sa.String(255), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default=sa.text("90")),
        sa.Column("archive_old_data", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    """Drop all WooCommerce tables in reverse order."""
    op.drop_table("wc_settings")
    op.drop_table("wc_sync_logs")
    op.drop_table("wc_alerts")
    op.drop_table("wc_inventory_logs")
    op.drop_table("wc_coupons")
    op.drop_table("wc_order_items")
    op.drop_table("wc_orders")
    op.drop_table("wc_customers")
    op.drop_table("wc_products")
    op.drop_table("wc_tags")
    op.drop_table("wc_categories")
    op.drop_table("wc_stores")

    # Drop enums
    sa.Enum(name="wc_store_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="wc_stock_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="wc_order_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="wc_alert_type_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="wc_alert_severity_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="wc_sync_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="wc_sync_type_enum").drop(op.get_bind(), checkfirst=True)
