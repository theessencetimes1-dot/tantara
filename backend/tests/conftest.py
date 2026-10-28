import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.main import app
from app.routers import documents
from app.services import vector_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    documents.pool.shutdown(wait=True)
    documents.pool = documents.ThreadPoolExecutor(max_workers=2, thread_name_prefix="tantara-ingest")
    monkeypatch.setenv("TANTARA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    config.get_settings.cache_clear()
    if db._engine is not None:
        db._engine.dispose()
    db._engine = None
    db._SessionLocal = None
    if hasattr(vector_store, "_store"):
        del vector_store._store
    with TestClient(app) as c:
        yield c
    documents.pool.shutdown(wait=True)
    documents.pool = documents.ThreadPoolExecutor(max_workers=2, thread_name_prefix="tantara-ingest")
    if db._engine is not None:
        db._engine.dispose()
    db._engine = None
    db._SessionLocal = None
    if hasattr(vector_store, "_store"):
        del vector_store._store
    config.get_settings.cache_clear()
