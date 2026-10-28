"""SQLAlchemy session factory and local database bootstrap."""

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

_engine = None
_SessionLocal = None


def engine():
    global _engine, _SessionLocal
    if _engine is None:
        s = get_settings()
        s.data_dir.mkdir(parents=True, exist_ok=True)
        url = s.database_url
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {},
            future=True,
        )
        if url.startswith("sqlite"):

            @event.listens_for(_engine, "connect")
            def _sqlite_setup(conn, _record):
                cur = conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=30000")
                cur.close()

        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def SessionLocal():
    engine()
    return _SessionLocal()


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """Apply the real Alembic upgrade, then bootstrap the local advocate account."""
    from alembic.config import Config

    from alembic import command

    engine()  # establish data directories before Alembic opens SQLite
    root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(alembic_cfg, "head")
    from sqlalchemy import select

    from app.models import User

    with SessionLocal() as session:
        if session.scalar(select(User.id).limit(1)) is None:
            import uuid

            from app.security import hash_password

            session.add(
                User(
                    id=str(uuid.uuid4()),
                    name="Workspace Advocate",
                    email="advocate@tantara.local",
                    password_hash=hash_password(get_settings().tantara_admin_password),
                    role="advocate",
                    avatar_initials="AM",
                    title="Advocate",
                )
            )
            session.commit()


# Transitional name retained for optional external adapters only. Domain services use ORM sessions.
def connect():
    return engine().begin()


def db():
    """Optional Supabase adapter; disabled for local mode."""
    from supabase import create_client

    s = get_settings()
    if not s.enable_cloud_providers or not s.supabase_url or not s.supabase_service_role_key:
        raise RuntimeError("Supabase adapter disabled; configure ENABLE_CLOUD_PROVIDERS and credentials")
    return create_client(s.supabase_url, s.supabase_service_role_key)
