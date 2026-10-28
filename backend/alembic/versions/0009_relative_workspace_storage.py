"""Store uploads and generated bundles relative to the workspace data directory."""

from alembic import op
from sqlalchemy import text

revision = "0009_relative_storage"
down_revision = "0008_community_visibility"
branch_labels = None
depends_on = None


def _rewrite(table: str, column: str, category: str) -> None:
    connection = op.get_bind()
    rows = connection.execute(text(f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL")).all()
    for row_id, value in rows:
        normalized = value.replace("\\", "/")
        if normalized.startswith("/"):
            marker = f"/{category}/"
            if marker not in normalized:
                continue
            normalized = f"{category}/{normalized.rsplit(marker, 1)[1]}"
        elif not normalized.startswith(f"{category}/"):
            normalized = f"{category}/{normalized.rsplit('/', 1)[-1]}"
        connection.execute(text(f"UPDATE {table} SET {column}=:path WHERE id=:id"), {"path": normalized, "id": row_id})


def upgrade() -> None:
    _rewrite("documents", "stored_path", "uploads")
    _rewrite("filing_bundles", "output_path", "bundles")


def downgrade() -> None:
    # Relative paths are intentionally retained: reconstructing the original absolute
    # workspace path is impossible and would reintroduce the relocation defect.
    pass
