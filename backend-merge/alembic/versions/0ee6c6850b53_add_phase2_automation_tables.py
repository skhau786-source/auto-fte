"""add_phase2_automation_tables

Revision ID: 0ee6c6850b53
Revises: 694d38b99c0b
Create Date: 2026-08-20 14:34:04.669746

"""
from alembic import op
import sqlalchemy as sa


revision = '0ee6c6850b53'
down_revision = '694d38b99c0b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('generated_posts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('student_id', sa.UUID(), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('caption', sa.Text(), nullable=True),
    sa.Column('image_path', sa.String(length=500), nullable=True),
    sa.Column('image_model', sa.String(length=100), nullable=True),
    sa.Column('aspect_ratio', sa.String(length=20), server_default='1:1', nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('instagram_media_id', sa.String(length=100), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['registered_students.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_generated_posts_student_id'), 'generated_posts', ['student_id'], unique=False)

    op.create_table('instagram_accounts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('student_id', sa.UUID(), nullable=False),
    sa.Column('ig_user_id', sa.String(length=100), nullable=False),
    sa.Column('ig_username', sa.String(length=150), nullable=False),
    sa.Column('account_type', sa.String(length=50), nullable=True),
    sa.Column('facebook_page_id', sa.String(length=100), nullable=True),
    sa.Column('access_token', sa.Text(), nullable=False),
    sa.Column('token_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('connected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['registered_students.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_instagram_accounts_student_id'), 'instagram_accounts', ['student_id'], unique=False)

    op.create_table('brand_profiles',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('student_id', sa.UUID(), nullable=False),
    sa.Column('tone', sa.String(length=100), nullable=False),
    sa.Column('sample_captions', sa.Text(), nullable=True),
    sa.Column('prohibited_words', sa.Text(), nullable=True),
    sa.Column('emoji_preference', sa.String(length=50), nullable=False),
    sa.Column('target_audience', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['registered_students.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_brand_profiles_student_id'), 'brand_profiles', ['student_id'], unique=True)

    op.create_table('notifications',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('student_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.String(length=50), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('is_read', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['registered_students.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_student_id'), 'notifications', ['student_id'], unique=False)

    op.create_table('post_analytics',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('post_id', sa.UUID(), nullable=False),
    sa.Column('likes', sa.Integer(), nullable=False),
    sa.Column('comments', sa.Integer(), nullable=False),
    sa.Column('reach', sa.Integer(), nullable=False),
    sa.Column('impressions', sa.Integer(), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['post_id'], ['generated_posts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_post_analytics_post_id'), 'post_analytics', ['post_id'], unique=False)

    op.create_table('post_comments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('post_id', sa.UUID(), nullable=False),
    sa.Column('comment_id', sa.String(length=100), nullable=False),
    sa.Column('commenter_username', sa.String(length=150), nullable=False),
    sa.Column('comment_text', sa.Text(), nullable=False),
    sa.Column('ai_reply', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('replied_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['post_id'], ['generated_posts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_post_comments_comment_id'), 'post_comments', ['comment_id'], unique=True)
    op.create_index(op.f('ix_post_comments_post_id'), 'post_comments', ['post_id'], unique=False)

    op.create_table('scheduled_posts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('post_id', sa.UUID(), nullable=False),
    sa.Column('student_id', sa.UUID(), nullable=False),
    sa.Column('scheduled_time', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['post_id'], ['generated_posts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['student_id'], ['registered_students.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scheduled_posts_post_id'), 'scheduled_posts', ['post_id'], unique=True)
    op.create_index(op.f('ix_scheduled_posts_scheduled_time'), 'scheduled_posts', ['scheduled_time'], unique=False)
    op.create_index(op.f('ix_scheduled_posts_student_id'), 'scheduled_posts', ['student_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_scheduled_posts_student_id'), table_name='scheduled_posts')
    op.drop_index(op.f('ix_scheduled_posts_scheduled_time'), table_name='scheduled_posts')
    op.drop_index(op.f('ix_scheduled_posts_post_id'), table_name='scheduled_posts')
    op.drop_table('scheduled_posts')
    op.drop_index(op.f('ix_post_comments_post_id'), table_name='post_comments')
    op.drop_index(op.f('ix_post_comments_comment_id'), table_name='post_comments')
    op.drop_table('post_comments')
    op.drop_index(op.f('ix_post_analytics_post_id'), table_name='post_analytics')
    op.drop_table('post_analytics')
    op.drop_index(op.f('ix_notifications_student_id'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_brand_profiles_student_id'), table_name='brand_profiles')
    op.drop_table('brand_profiles')
    op.drop_index(op.f('ix_instagram_accounts_student_id'), table_name='instagram_accounts')
    op.drop_table('instagram_accounts')
    op.drop_index(op.f('ix_generated_posts_student_id'), table_name='generated_posts')
    op.drop_table('generated_posts')
