"""Allow bundle items to include an explicit inclusive source page range."""

from sqlalchemy import Column, Integer, inspect

from alembic import op

revision = "0005_bundle_page_ranges"
down_revision = "0004_reconcile_legacy"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("bundle_items")}
    if "page_start" not in columns:
        op.add_column("bundle_items", Column("page_start", Integer, nullable=True))
    if "page_end" not in columns:
        op.add_column("bundle_items", Column("page_end", Integer, nullable=True))


def downgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("bundle_items")}
    if "page_end" in columns:
        op.drop_column("bundle_items", "page_end")
    if "page_start" in columns:
        op.drop_column("bundle_items", "page_start")
