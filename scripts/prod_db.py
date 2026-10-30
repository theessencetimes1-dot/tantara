#!/usr/bin/env python3
"""Operate the production Supabase workspace database (Tantra on Cloud Run).

Subcommands:

    migrate     apply the real Alembic history to Supabase Postgres
    harden      remove PostgREST/anon access to application tables
    inventory   row counts per table
    account     create or reset a production account (email + role)
    prune-probes remove the throwaway accounts a verification run created

The connection string and keys are read from ``sensitive/creds.yaml`` and stay
in the process environment; nothing prints a secret. The k8s QA database is a
different DATABASE_URL and is never touched by this script.

    backend/.venv/bin/python scripts/prod_db.py migrate
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

from prod_env import creds, production_database_url, production_password  # noqa: E402

WORK_DIR = "/tmp/tantara-prod-ops"


def configure_environment() -> None:
    """Point the application at Supabase before any app module reads settings.

    When the caller already supplied a production environment (the container
    gets its variables from Cloud Run, not from the operator's credential file),
    only the gaps are filled.
    """
    if os.environ.get("DATABASE_URL", "").startswith("postgresql") and os.environ.get("OBJECT_STORAGE") == "supabase":
        os.environ.setdefault("VECTOR_BACKEND", "postgres")
        os.environ.setdefault("EMBEDDING_PROVIDER", "fastembed")
        os.environ.setdefault("AI_PROVIDER", "anthropic")
        os.environ.setdefault("ENABLE_CLOUD_PROVIDERS", "true")
        from app.config import get_settings

        get_settings.cache_clear()
        return
    c = creds()
    os.environ["DATABASE_URL"] = production_database_url(c)
    os.environ["OBJECT_STORAGE"] = "supabase"
    os.environ["SUPABASE_URL"] = c["supabase_prod.SUPABASE_URL"]
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = c["supabase_prod.SUPABASE_SECRET_KEY"]
    os.environ["SUPABASE_STORAGE_BUCKET"] = os.environ.get("TANTARA_STORAGE_BUCKET", "tantara-documents")
    os.environ["VECTOR_BACKEND"] = "postgres"
    os.environ["DATA_DIR"] = WORK_DIR
    os.environ["TANTARA_DATA_DIR"] = WORK_DIR
    os.environ["EMBEDDING_PROVIDER"] = "fastembed"
    os.environ["AI_PROVIDER"] = "anthropic"
    os.environ["ENABLE_CLOUD_PROVIDERS"] = "true"
    os.environ["ANTHROPIC_API_KEY"] = c.get("CLAUDE_PROD.CLAUDE_API_KEY", "")
    from app.config import get_settings

    get_settings.cache_clear()


HARDENING_STATEMENTS = [
    # PostgREST exposes the public schema to the anon/authenticated roles. Tantra
    # serves every row through the FastAPI backend with its own bearer token, so
    # the REST surface must not be able to read users, documents or chunks.
    "REVOKE ALL ON SCHEMA public FROM anon, authenticated",
    "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated",
    "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated",
    "REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated",
    "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated",
    "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated",
    "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated",
]

INVENTORY_TABLES = [
    "users",
    "cases",
    "documents",
    "document_pages",
    "document_chunks",
    "ingestion_jobs",
    "knowledge_collections",
    "research_sessions",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["migrate", "harden", "inventory", "account", "prune-probes"])
    parser.add_argument("--email", help="account command: email to create or reset")
    parser.add_argument("--prefix", default="probe.", help="prune-probes: email prefix of verification accounts")
    parser.add_argument("--dry-run", action="store_true", help="prune-probes: report without deleting")
    parser.add_argument("--role", default="advocate", help="account command: role (default advocate)")
    parser.add_argument("--name", default="Tantra Library", help="account command: display name")
    args = parser.parse_args()

    configure_environment()
    from alembic import command
    from alembic.config import Config
    from app.db import SessionLocal, engine
    from app.models import User
    from app.security import hash_password
    from sqlalchemy import select, text

    if args.command == "migrate":
        cfg = Config(str(ROOT / "alembic.ini"))
        command.upgrade(cfg, "head")
        with engine().connect() as connection:
            version = connection.execute(text("select version_num from alembic_version")).scalar()
        print(f"alembic head applied: {version}")
        return 0

    if args.command == "harden":
        with SessionLocal() as session:
            for statement in HARDENING_STATEMENTS:
                session.execute(text(statement))
            session.commit()
            visible = session.execute(
                text(
                    "select table_name, pg_catalog.has_table_privilege('anon', table_name, 'select') "
                    "from information_schema.tables where table_schema='public' order by table_name"
                )
            ).all()
        leaked = [row[0] for row in visible if row[1]]
        print(f"anon-readable tables: {leaked or 'none'}")
        return 1 if leaked else 0

    if args.command == "inventory":
        with SessionLocal() as session:
            for table in INVENTORY_TABLES:
                try:
                    count = session.execute(text(f"select count(*) from {table}")).scalar()
                except Exception as exc:  # noqa: BLE001 - report and move on
                    count = f"unavailable ({type(exc).__name__})"
                    session.rollback()
                print(f"{table:18} {count}")
        return 0

    if args.command == "prune-probes":
        from app.models import Document
        from app.object_store import object_store

        if not args.prefix:
            parser.error("prune-probes needs a non-empty --prefix")
        with SessionLocal() as session:
            users = session.scalars(select(User).where(User.email.like(f"{args.prefix}%"))).all()
            ids = [user.id for user in users]
            documents = session.scalars(select(Document).where(Document.owner_id.in_(ids))).all() if ids else []
            print(
                f"accounts matching {args.prefix!r}: {len(users)}; "
                f"their documents: {len(documents)}; pages/chunks and stored objects go with them"
            )
            if args.dry_run or not users:
                return 0
            store = object_store()
            for document in documents:
                try:
                    store.delete(document.stored_path)
                except Exception as exc:  # noqa: BLE001 - the row cascade is what matters
                    print(f"  storage object still present for {document.id[:8]} ({type(exc).__name__})")
            for user in users:
                session.delete(user)
            session.commit()
        print(f"pruned {len(users)} verification accounts and {len(documents)} of their documents")
        return 0

    if not args.email:
        parser.error("account needs --email")
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == args.email))
        password = production_password()
        if user is None:
            import uuid

            user = User(
                id=str(uuid.uuid4()),
                name=args.name,
                email=args.email,
                password_hash=hash_password(password),
                role=args.role,
                avatar_initials="TL",
                title=args.role.capitalize(),
            )
            session.add(user)
            session.commit()
            print(f"created {args.email} (id {user.id[:8]}, role {args.role}); password written to operator config")
        else:
            user.password_hash = hash_password(password)
            session.commit()
            print(f"reset password for {args.email} (id {user.id[:8]}, role {user.role})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
