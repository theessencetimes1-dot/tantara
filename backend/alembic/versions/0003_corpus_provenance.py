"""Add verifiable public-corpus provenance to uploaded documents."""

from sqlalchemy import JSON, Column, DateTime, String, Text, inspect

from alembic import op

revision = "0003_corpus_provenance"
down_revision = "0002_typed_domain_schema"
branch_labels = None
depends_on = None
COLUMNS = [
    Column("source_url", String(1000)),
    Column("publisher", String(240)),
    Column("official_title", String(400)),
    Column("doc_date", String(40)),
    Column("retrieved_at", DateTime),
    Column("license_note", Text),
    Column("citation_metadata", JSON, nullable=False, server_default="{}"),
]


def upgrade():
    existing = {x["name"] for x in inspect(op.get_bind()).get_columns("documents")}
    for col in COLUMNS:
        if col.name not in existing:
            op.add_column("documents", col)


def downgrade():
    existing = {x["name"] for x in inspect(op.get_bind()).get_columns("documents")}
    for col in reversed(COLUMNS):
        if col.name in existing:
            op.drop_column("documents", col.name)
