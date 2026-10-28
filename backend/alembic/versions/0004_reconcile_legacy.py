"""Export prototype JSON rows and remove archive tables; add shared rate buckets."""

import json
from datetime import date, datetime

from sqlalchemy import Column, Integer, String, inspect, text

from alembic import op
from app.config import get_settings

revision = "0004_reconcile_legacy"
down_revision = "0003_corpus_provenance"
branch_labels = None
depends_on = None


def _json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def upgrade():
    bind = op.get_bind()
    names = set(inspect(bind).get_table_names())
    archived = sorted(name for name in names if name.endswith("_legacy_0002"))
    tables = {}
    for name in archived:
        rows = bind.execute(text(f'SELECT * FROM "{name}"')).mappings().all()
        tables[name] = [{key: _json_value(value) for key, value in row.items()} for row in rows]
    if tables:
        output = get_settings().data_dir / "archive" / "legacy_export.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"format": 1, "tables": tables}, indent=2, default=str))
        for name in archived:
            op.drop_table(name)
    if "rate_buckets" not in names:
        op.create_table(
            "rate_buckets",
            Column("client_key", String, primary_key=True),
            Column("route_key", String, primary_key=True),
            Column("minute", Integer, primary_key=True),
            Column("count", Integer, nullable=False),
        )


def downgrade():
    op.drop_table("rate_buckets")
