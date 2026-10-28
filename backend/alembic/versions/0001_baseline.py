"""Create the normalized identity/document baseline and FTS5 index."""

from alembic import op
from app.models import Base

revision = "0001_baseline"
down_revision = "0001_local_workspace"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(
        bind,
        tables=[Base.metadata.tables[n] for n in ("users", "documents", "document_chunks")],
        checkfirst=True,
    )
    if bind.dialect.name == "sqlite":
        op.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(chunk_id UNINDEXED, document_id UNINDEXED, content)"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON document_chunks BEGIN INSERT INTO chunk_fts(chunk_id,document_id,content) VALUES(new.id,new.document_id,new.content); END"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON document_chunks BEGIN DELETE FROM chunk_fts WHERE chunk_id=old.id; END"
        )
        op.execute(
            "CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON document_chunks BEGIN DELETE FROM chunk_fts WHERE chunk_id=old.id; INSERT INTO chunk_fts(chunk_id,document_id,content) VALUES(new.id,new.document_id,new.content); END"
        )


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS chunks_ai")
        op.execute("DROP TRIGGER IF EXISTS chunks_ad")
        op.execute("DROP TRIGGER IF EXISTS chunks_au")
        op.execute("DROP TABLE IF EXISTS chunk_fts")
    for n in ("document_chunks", "documents", "users"):
        Base.metadata.tables[n].drop(op.get_bind(), checkfirst=True)
