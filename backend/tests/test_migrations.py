import json
import sqlite3
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app import config, db

ROOT = Path(__file__).resolve().parents[1]


def _upgrade(path, tmp_path, monkeypatch, revision="head"):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{path}")
    monkeypatch.setenv("TANTARA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATA_DIR", raising=False)
    config.get_settings.cache_clear()
    if db._engine is not None:
        db._engine.dispose()
    db._engine = None
    db._SessionLocal = None
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(cfg, revision)
    command.upgrade(cfg, revision)
    config.get_settings.cache_clear()
    return create_engine(f"sqlite:///{path}")


def test_fresh_upgrade_is_idempotent(tmp_path, monkeypatch):
    engine = _upgrade(tmp_path / "fresh.db", tmp_path, monkeypatch)
    names = set(inspect(engine).get_table_names())
    assert {
        "users",
        "clients",
        "cases",
        "documents",
        "document_chunks",
        "filing_bundles",
        "extraction_fields",
    } <= names
    assert "data" not in {c["name"] for c in inspect(engine).get_columns("cases")}
    assert "embedding" not in {c["name"] for c in inspect(engine).get_columns("document_chunks")}
    assert "visibility" in {c["name"] for c in inspect(engine).get_columns("community_posts")}
    engine.dispose()


def test_0008_migrates_existing_community_posts_to_private(tmp_path, monkeypatch):
    path = tmp_path / "existing-community.db"
    engine = _upgrade(path, tmp_path, monkeypatch, "0007_demo_chunk_flag")
    # Earlier revisions import current metadata, so remove the additive field to
    # model the actual pre-0008 schema this upgrade must preserve.
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE community_posts DROP COLUMN visibility")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users(id,name,email,password_hash,role,created_at) "
                "VALUES('owner','Owner','owner@example.local','hash','advocate',CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO community_posts "
                "(id,owner_id,is_demo,created_at,updated_at,title,body,kind,case_ref,tags) "
                "VALUES('legacy-post','owner',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,"
                "'Legacy private post','Existing text','discussion',NULL,'[]')"
            )
        )
    engine.dispose()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT body,visibility FROM community_posts WHERE id='legacy-post'")
        ).one() == ("Existing text", "private")
    engine.dispose()


def test_prototype_json_rows_are_exported_and_user_kept(tmp_path, monkeypatch):
    path = tmp_path / "prototype.db"
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE users(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,role TEXT NOT NULL,avatar_initials TEXT,title TEXT,owner_id TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    INSERT INTO users(id,name,email,password_hash,role) VALUES('u1','Local User','u@example.local','scrypt','advocate');
    CREATE TABLE cases(id TEXT PRIMARY KEY,owner_id TEXT,case_id TEXT,data TEXT NOT NULL,is_demo INTEGER DEFAULT 0,created_at TEXT,updated_at TEXT);
    INSERT INTO cases(id,owner_id,data) VALUES('c1','u1','{"title":"legacy"}');
    CREATE TABLE documents(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,case_id TEXT,title TEXT NOT NULL,document_type TEXT,jurisdiction TEXT,source_label TEXT,filename TEXT,stored_path TEXT,content_hash TEXT,status TEXT,text_content TEXT,warnings TEXT,page_count INTEGER,is_demo INTEGER,created_at TEXT);
    CREATE TABLE document_chunks(id TEXT PRIMARY KEY,owner_id TEXT,case_id TEXT,data TEXT NOT NULL);
    """)
    con.commit()
    con.close()
    engine = _upgrade(path, tmp_path, monkeypatch)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT email FROM users WHERE id='u1'")).scalar() == "u@example.local"
        assert conn.execute(text("SELECT count(*) FROM cases")).scalar() == 0
        assert "cases_legacy_0002" not in inspect(engine).get_table_names()
    exported = json.loads((tmp_path / "archive" / "legacy_export.json").read_text())
    assert exported["tables"]["cases_legacy_0002"][0]["data"] == '{"title":"legacy"}'
    engine.dispose()
