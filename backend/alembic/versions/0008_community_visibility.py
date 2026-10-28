"""Add explicit private and workspace visibility to community posts."""

from sqlalchemy import Column, String, inspect

from alembic import op

revision = "0008_community_visibility"
down_revision = "0007_demo_chunk_flag"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("community_posts")}
    if "visibility" not in columns:
        op.add_column(
            "community_posts",
            Column("visibility", String(length=16), nullable=False, server_default="private"),
        )


def downgrade():
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("community_posts")}
    if "visibility" in columns:
        op.drop_column("community_posts", "visibility")
