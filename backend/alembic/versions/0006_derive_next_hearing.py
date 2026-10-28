"""Drop the denormalized next hearing value; it is derived from hearings."""

from sqlalchemy import Column, DateTime, inspect

from alembic import op

revision = "0006_derive_next_hearing"
down_revision = "0005_bundle_page_ranges"
branch_labels = None
depends_on = None


def upgrade():
    if "next_hearing_at" in {c["name"] for c in inspect(op.get_bind()).get_columns("cases")}:
        with op.batch_alter_table("cases") as batch:
            batch.drop_column("next_hearing_at")


def downgrade():
    with op.batch_alter_table("cases") as batch:
        batch.add_column(Column("next_hearing_at", DateTime()))
