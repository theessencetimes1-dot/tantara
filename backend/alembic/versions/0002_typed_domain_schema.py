"""Rebuild prototype JSON tables as normalized typed domain tables.

The one-time prototype cutover preserves every incompatible prototype table as
`*_legacy_0002` in SQLite. Existing user rows remain intact. Domain payloads
inside legacy JSON columns are not migrated automatically because their shapes
were unvalidated; applications can inspect those archive tables before removing
old local data. A fresh or explicitly empty workspace upgrades directly.
"""

from sqlalchemy import inspect

from alembic import op
from app.models import Base

revision = "0002_typed_domain_schema"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS chunks_ai")
        op.execute("DROP TRIGGER IF EXISTS chunks_ad")
        op.execute("DROP TRIGGER IF EXISTS chunks_au")
        op.execute("DROP TABLE IF EXISTS chunk_fts")
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    for name, table in list(Base.metadata.tables.items()):
        if name not in existing:
            continue
        actual = {col["name"] for col in inspector.get_columns(name)}
        required = {col.name for col in table.columns}
        # Keep the users table if its typed auth columns exist; additive legacy
        # fields such as owner_id do not prevent the model from using it.
        if name == "users" and {"id", "name", "email", "password_hash", "role"} <= actual:
            continue
        if required <= actual:
            continue
        archived = f"{name}_legacy_0002"
        if archived in existing:
            continue
        op.rename_table(name, archived)
        existing.remove(name)
        existing.add(archived)
    Base.metadata.create_all(bind, checkfirst=True)
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
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS chunks_ai")
        op.execute("DROP TRIGGER IF EXISTS chunks_ad")
        op.execute("DROP TRIGGER IF EXISTS chunks_au")
        op.execute("DROP TABLE IF EXISTS chunk_fts")
    # Drop only current typed tables; preserved prototype archives are retained.
    for table in reversed(Base.metadata.sorted_tables):
        table.drop(bind, checkfirst=True)
