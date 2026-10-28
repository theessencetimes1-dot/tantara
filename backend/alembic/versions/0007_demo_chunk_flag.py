"""Carry the demo marker through page extraction into indexed chunks."""

from sqlalchemy import Boolean, Column, inspect

from alembic import op

revision = "0007_demo_chunk_flag"
down_revision = "0006_derive_next_hearing"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("document_chunks")}
    if "is_demo" not in columns:
        op.add_column("document_chunks", Column("is_demo", Boolean(), nullable=False, server_default="0"))


def downgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("document_chunks")}
    if "is_demo" in columns:
        op.drop_column("document_chunks", "is_demo")
