"""create RAG tables and support chat handoffs

The RAG models existed in code but had no migration, so the tables were
never created. Tables are created straight from the model definitions
(checkfirst, so it is safe on databases that already have them).

Revision ID: rag_support_chat_001
Revises: merge_bilal_kulsoom
"""

from alembic import op

revision = "rag_support_chat_001"
down_revision = "merge_bilal_kulsoom"
branch_labels = None
depends_on = None


def _tables():
    import app.models  # noqa: F401
    import app.organizations.models  # noqa: F401  (FK target: organizations)
    import app.ai.models  # noqa: F401  (FK targets: ai_agents, ai_agent_tasks)
    from app.ai.rag_models import KnowledgeBase, RAGDocument, RAGChunk, RAGRetrieval
    from app.support_chat.models import SupportHandoff

    # Order matters: parents before children.
    return [KnowledgeBase, RAGDocument, RAGChunk, RAGRetrieval, SupportHandoff]


def upgrade() -> None:
    bind = op.get_bind()
    for model in _tables():
        model.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for model in reversed(_tables()):
        model.__table__.drop(bind=bind, checkfirst=True)
