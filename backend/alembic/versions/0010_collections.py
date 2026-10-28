"""Bridge databases stamped under the renamed 0010 revision identifier."""

from sqlalchemy import inspect
from alembic import op

revision = "0010_collections"
down_revision = "0010_knowledge_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if not inspector.has_table("knowledge_collections"):
        raise RuntimeError("Stamped knowledge-collections revision is missing its table")
    document_columns = {column["name"] for column in inspector.get_columns("documents")}
    if "collection_id" not in document_columns:
        raise RuntimeError("Stamped knowledge-collections revision is missing documents.collection_id")


def downgrade() -> None:
    # Keep the legacy schema when downgrading only across the identifier bridge.
    pass
