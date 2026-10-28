"""Add owner-scoped knowledge collections and document membership."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0010_collections"
down_revision = "0009_relative_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("knowledge_collections"):
        op.create_table(
        "knowledge_collections",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_id", "name", name="uq_collection_owner_name"),
        )
    if "ix_knowledge_collections_owner_id" not in {i["name"] for i in inspect(op.get_bind()).get_indexes("knowledge_collections")}:
        op.create_index("ix_knowledge_collections_owner_id", "knowledge_collections", ["owner_id"])
    document_columns = {column["name"] for column in inspect(op.get_bind()).get_columns("documents")}
    if "collection_id" not in document_columns:
        op.add_column("documents", sa.Column("collection_id", sa.String(length=36), nullable=True))
    if "ix_documents_collection_id" not in {i["name"] for i in inspect(op.get_bind()).get_indexes("documents")}:
        op.create_index("ix_documents_collection_id", "documents", ["collection_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_collection_id", table_name="documents")
    op.drop_column("documents", "collection_id")
    op.drop_index("ix_knowledge_collections_owner_id", table_name="knowledge_collections")
    op.drop_table("knowledge_collections")
