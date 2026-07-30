"""init (auth + inventory models)

Revision ID: 694d38b99c0b
Revises: 
Create Date: 2026-07-15 17:42:45.346116

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '694d38b99c0b'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Auth: registered_students ──
    op.create_table('registered_students',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=150), nullable=True),
        sa.Column('hashed_password', sa.String(length=255), nullable=True),
        sa.Column('auth_provider', sa.Enum('LOCAL', 'GOOGLE', name='auth_provider_enum'), nullable=False),
        sa.Column('google_id', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_verified', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('google_id'),
    )
    op.create_index(op.f('ix_registered_students_email'), 'registered_students', ['email'], unique=True)
    op.create_index(op.f('ix_registered_students_username'), 'registered_students', ['username'], unique=True)

    # ── Auth: login_users ──
    op.create_table('login_users',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('login_method', sa.Enum('LOCAL', 'GOOGLE', name='login_method_enum'), nullable=False),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('logged_in_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['student_id'], ['registered_students.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_login_users_student_id'), 'login_users', ['student_id'], unique=False)

    # ══════════════════════════════════════════════════════════════
    # INVENTORY: Store
    # ══════════════════════════════════════════════════════════════
    op.create_table('stores',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('shopify_domain', sa.String(length=255), nullable=False),
        sa.Column('shopify_store_id', sa.BigInteger(), nullable=True),
        sa.Column('access_token', sa.String(length=512), nullable=False),
        sa.Column('shopify_location_id', sa.BigInteger(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['registered_students.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shopify_store_id'),
    )
    op.create_index(op.f('ix_stores_owner_id'), 'stores', ['owner_id'], unique=False)
    op.create_index(op.f('ix_stores_shopify_domain'), 'stores', ['shopify_domain'], unique=True)

    # ══════════════════════════════════════════════════════════════
    # INVENTORY: Category
    # ══════════════════════════════════════════════════════════════
    op.create_table('categories',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('store_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('parent_id', sa.UUID(), nullable=True),
        sa.Column('shopify_category_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['categories.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shopify_category_id'),
    )
    op.create_index(op.f('ix_categories_store_id'), 'categories', ['store_id'], unique=False)
    op.create_index(op.f('ix_categories_slug'), 'categories', ['slug'], unique=False)

    # ══════════════════════════════════════════════════════════════
    # INVENTORY: Product
    # ══════════════════════════════════════════════════════════════
    op.create_table('products',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('store_id', sa.UUID(), nullable=False),
        sa.Column('category_id', sa.UUID(), nullable=True),
        sa.Column('shopify_product_id', sa.BigInteger(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('vendor', sa.String(length=255), nullable=True),
        sa.Column('product_type', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column('featured_image_url', sa.String(length=1024), nullable=True),
        sa.Column('shopify_data', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shopify_product_id'),
    )
    op.create_index(op.f('ix_products_store_id'), 'products', ['store_id'], unique=False)

    # ══════════════════════════════════════════════════════════════
    # INVENTORY: ProductVariant
    # ══════════════════════════════════════════════════════════════
    op.create_table('product_variants',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('product_id', sa.UUID(), nullable=False),
        sa.Column('shopify_variant_id', sa.BigInteger(), nullable=True),
        sa.Column('shopify_inventory_item_id', sa.BigInteger(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('sku', sa.String(length=100), nullable=True),
        sa.Column('barcode', sa.String(length=100), nullable=True),
        sa.Column('price', sa.Numeric(12, 2), nullable=False, server_default=sa.text('0.00')),
        sa.Column('compare_at_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('inventory_quantity', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('requires_shipping', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('low_stock_threshold', sa.Integer(), nullable=True, server_default=sa.text('10')),
        sa.Column('shopify_data', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shopify_variant_id'),
        sa.UniqueConstraint('shopify_inventory_item_id'),
    )
    op.create_index(op.f('ix_product_variants_product_id'), 'product_variants', ['product_id'], unique=False)
    op.create_index(op.f('ix_product_variants_sku'), 'product_variants', ['sku'], unique=False)
    op.create_index(op.f('ix_product_variants_shopify_variant_id'), 'product_variants', ['shopify_variant_id'], unique=False)
    op.create_index(op.f('ix_product_variants_shopify_inventory_item_id'), 'product_variants', ['shopify_inventory_item_id'], unique=False)

    # ══════════════════════════════════════════════════════════════
    # INVENTORY: InventoryTransaction (Audit Trail)
    # ══════════════════════════════════════════════════════════════
    op.create_table('inventory_transactions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('variant_id', sa.UUID(), nullable=False),
        sa.Column('transaction_type',
                  sa.Enum('ADJUSTMENT', 'SALE', 'PURCHASE', 'RETURN', 'TRANSFER', 'SHOPIFY_SYNC',
                          name='transaction_type_enum'),
                  nullable=False),
        sa.Column('quantity_change', sa.Integer(), nullable=False),
        sa.Column('quantity_before', sa.Integer(), nullable=False),
        sa.Column('quantity_after', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('reference_id', sa.String(length=255), nullable=True),
        sa.Column('performed_by', sa.UUID(), nullable=True),
        sa.Column('synced_to_shopify', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['performed_by'], ['registered_students.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_inventory_transactions_variant_id'), 'inventory_transactions', ['variant_id'], unique=False)

    # ══════════════════════════════════════════════════════════════
    # INVENTORY: InventoryLog (Activity Log)
    # ══════════════════════════════════════════════════════════════
    op.create_table('inventory_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('variant_id', sa.UUID(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('performed_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['performed_by'], ['registered_students.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_inventory_logs_variant_id'), 'inventory_logs', ['variant_id'], unique=False)
    op.create_index(op.f('ix_inventory_logs_action'), 'inventory_logs', ['action'], unique=False)


def downgrade() -> None:
    # Drop inventory tables first (reverse order of creation)
    op.drop_index(op.f('ix_inventory_logs_action'), table_name='inventory_logs')
    op.drop_index(op.f('ix_inventory_logs_variant_id'), table_name='inventory_logs')
    op.drop_table('inventory_logs')

    op.drop_index(op.f('ix_inventory_transactions_variant_id'), table_name='inventory_transactions')
    op.drop_table('inventory_transactions')

    op.drop_index(op.f('ix_product_variants_shopify_inventory_item_id'), table_name='product_variants')
    op.drop_index(op.f('ix_product_variants_shopify_variant_id'), table_name='product_variants')
    op.drop_index(op.f('ix_product_variants_sku'), table_name='product_variants')
    op.drop_index(op.f('ix_product_variants_product_id'), table_name='product_variants')
    op.drop_table('product_variants')

    op.drop_index(op.f('ix_products_store_id'), table_name='products')
    op.drop_table('products')

    op.drop_index(op.f('ix_categories_slug'), table_name='categories')
    op.drop_index(op.f('ix_categories_store_id'), table_name='categories')
    op.drop_table('categories')

    op.drop_index(op.f('ix_stores_shopify_domain'), table_name='stores')
    op.drop_index(op.f('ix_stores_owner_id'), table_name='stores')
    op.drop_table('stores')

    # Drop auth tables
    sa.Enum(name='transaction_type_enum').drop(op.get_bind(), checkfirst=True)

    op.drop_index(op.f('ix_login_users_student_id'), table_name='login_users')
    op.drop_table('login_users')

    op.drop_index(op.f('ix_registered_students_username'), table_name='registered_students')
    op.drop_index(op.f('ix_registered_students_email'), table_name='registered_students')
    op.drop_table('registered_students')

    # Drop enums
    sa.Enum(name='auth_provider_enum').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='login_method_enum').drop(op.get_bind(), checkfirst=True)
