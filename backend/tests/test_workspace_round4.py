import runpy
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import create_engine, func, select, text

from app import config
from app.db import SessionLocal, session_scope
from app.models import (
    Base,
    Case,
    CaseEvent,
    Client,
    CommunityPost,
    CommunityReply,
    Document,
    DocumentChunk,
    DocumentPage,
    Draft,
    ExtractionField,
    FilingBundle,
    Hearing,
    Task,
    User,
)
from app.services.vector_store import store


def test_debug_ingest_artifact_is_never_written_into_the_checkout():
    checkout_artifact = Path(__file__).resolve().parents[1] / "tmp_ingest_test.txt"
    assert not checkout_artifact.exists()


def test_data_dirs_derive_separate_database_files_with_independent_rows(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    roots = [tmp_path / "one", tmp_path / "two"]
    engines = []
    try:
        for root in roots:
            monkeypatch.setenv("TANTARA_DATA_DIR", str(root))
            settings = config.Settings(_env_file=None)
            settings.data_dir.mkdir(parents=True, exist_ok=True)
            assert settings.data_dir == root.resolve()
            assert settings.database_url == f"sqlite:///{root.resolve() / 'tantara.db'}"
            engine = create_engine(settings.database_url)
            engines.append(engine)
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE marker (value TEXT)"))
                connection.execute(text("INSERT INTO marker VALUES (:value)"), {"value": root.name})
        assert engines[0].url.database != engines[1].url.database
        assert engines[0].connect().execute(text("SELECT value FROM marker")).scalar() == "one"
        assert engines[1].connect().execute(text("SELECT value FROM marker")).scalar() == "two"
        assert (
            config.Settings(
                _env_file=None,
                data_dir=roots[0],
                database_url="sqlite:///explicit.db",
            ).database_url
            == "sqlite:///explicit.db"
        )
    finally:
        for engine in engines:
            engine.dispose()
    monkeypatch.setenv("TANTARA_LOCAL_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    assert config.Settings(_env_file=None).local_llm_base_url == "http://127.0.0.1:9/v1"


def test_database_and_faiss_store_share_resolved_data_root(client):
    settings = config.get_settings()
    assert Path(settings.database_url.removeprefix("sqlite:///")).resolve().parent == settings.data_dir
    assert store().root.resolve() == settings.data_dir / "index"


def test_demo_seed_has_multpage_content_calendar_extractions_and_feed(client, monkeypatch, capsys):
    seed_source = (Path(__file__).resolve().parents[2] / "scripts" / "seed.py").read_text()
    for raw_event_type in ("first_hearing", "all_day_event", "document_uploaded", "deadline_set"):
        assert raw_event_type not in seed_source
    monkeypatch.setattr(sys, "argv", ["seed.py", "--demo"])
    runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "seed.py"), run_name="seed_test")[
        "main"
    ]()
    seed_output = capsys.readouterr().out
    today = datetime.now(UTC).date()
    with SessionLocal() as session:
        documents = session.scalars(select(Document).where(Document.is_demo.is_(True))).all()
        assert len(documents) >= 8
        assert all(document.page_count >= 5 for document in documents)
        assert sum(document.page_count for document in documents) >= 40
        assert any("scanned" in document.filename for document in documents)
        assert any("contract" in document.filename for document in documents)
        assert any("page-three-motion" in document.filename for document in documents)
        assert sum("near-duplicate" in document.filename for document in documents) >= 2
        pages = session.scalars(select(DocumentPage).where(DocumentPage.is_demo.is_(True))).all()
        assert any(page.warnings and "manual review" in str(page.warnings).lower() for page in pages)
        scanned = next(document for document in documents if "scanned" in document.filename)
        scanned_pages = [page for page in pages if page.document_id == scanned.id]
        assert len(scanned_pages) >= 5
        assert any("seat shall be mumbai" in page.text.lower() for page in scanned_pages)
        assert session.scalar(select(func.count(ExtractionField.id))) > 0
        chunks = session.scalars(select(DocumentChunk)).all()
        assert chunks and all(chunk.is_demo for chunk in chunks)
        events = session.scalars(select(CaseEvent).where(CaseEvent.is_demo.is_(True))).all()
        assert events and any(
            event.occurred_at.date().year == today.year and event.occurred_at.date().month == today.month
            for event in events
        )
        assert session.scalar(select(func.count(CommunityPost.id))) >= 5
        assert session.scalar(select(func.count(CommunityReply.id))) >= 5
        tasks = session.scalars(select(Task).where(Task.is_demo.is_(True), Task.status != "done")).all()
        assert len(tasks) == 18
        task_title_counts = {}
        for task in tasks:
            task_title_counts[task.title] = task_title_counts.get(task.title, 0) + 1
        assert len(task_title_counts) >= 10
        assert max(task_title_counts.values()) <= 2
        assert any(task.due_at is None for task in tasks)
        assert any(task.due_at and task.due_at.date() < today for task in tasks)
        assert any(task.due_at and task.due_at.date() == today for task in tasks)
        assert sum(task.due_at is None for task in tasks) == 3
        assert sum(task.due_at is not None and task.due_at.date() < today for task in tasks) == 4
        assert sum(task.due_at is not None and task.due_at.date() == today for task in tasks) == 2
        assert sum(task.due_at is not None and task.due_at.date() > today for task in tasks) == 9
        assert all(row.is_demo for row in documents + pages + events)
        demo_clients = session.scalars(select(Client).where(Client.is_demo.is_(True))).all()
        assert any(
            session.scalar(select(func.count(Case.id)).where(Case.client_id == row.id)) == 0
            for row in demo_clients
        )
        demo_cases = session.scalars(select(Case).where(Case.is_demo.is_(True))).all()
        assert any(row.status == "closed" for row in demo_cases)
        past_only = next(row for row in demo_cases if row.title.startswith("ABC Pvt."))
        future_pair = next(row for row in demo_cases if row.title.startswith("TechBuild"))
        past_hearings = session.scalars(select(Hearing).where(Hearing.case_id == past_only.id)).all()
        future_hearings = session.scalars(select(Hearing).where(Hearing.case_id == future_pair.id)).all()
        assert past_hearings and all(hearing.at.date() < today for hearing in past_hearings)
        assert len([hearing for hearing in future_hearings if hearing.at.date() > today]) >= 2
        future_expected = min(hearing.at for hearing in future_hearings if hearing.at.date() > today)
        owner_id = session.scalar(select(User.id).where(User.email == "advocate@tantara.local"))
        junior_id = session.scalar(select(User.id).where(User.email == "researcher@tantara.local"))
        staff_id = session.scalar(select(User.id).where(User.email == "staff@tantara.local"))
        root_post_id = session.scalar(
            select(CommunityPost.id).where(
                CommunityPost.owner_id == owner_id,
                CommunityPost.visibility == "private",
            )
        )
        foreign_private_demo_ids = set(
            session.scalars(
                select(CommunityPost.id).where(
                    CommunityPost.is_demo.is_(True),
                    CommunityPost.visibility == "private",
                    CommunityPost.owner_id != owner_id,
                )
            ).all()
        )
        root_case_id = session.scalar(select(Case.id).where(Case.owner_id == owner_id))
        root_client_id = session.scalar(select(Client.id).where(Client.owner_id == owner_id))
        for model in (Client, Case, Document, Task, FilingBundle, Hearing):
            owner_counts = dict(
                session.execute(select(model.owner_id, func.count()).group_by(model.owner_id)).all()
            )
            advocate_count = int(owner_counts.get(owner_id, 0))
            researcher_count = int(owner_counts.get(junior_id, 0))
            total_count = sum(int(count) for count in owner_counts.values())
            assert (
                f"{model.__tablename__}: advocate@tantara.local={advocate_count} "
                f"researcher@tantara.local={researcher_count} "
                f"other={total_count - advocate_count - researcher_count} total={total_count}"
            ) in seed_output
        assert junior_id and junior_id != owner_id
        assert staff_id and staff_id not in {owner_id, junior_id}
        shared_demo_posts = session.scalars(
            select(CommunityPost).where(
                CommunityPost.is_demo.is_(True),
                CommunityPost.visibility == "workspace",
                CommunityPost.owner_id.in_([junior_id, staff_id]),
            )
        ).all()
        assert len(shared_demo_posts) >= 4
        assert all(post.owner_id in {junior_id, staff_id} for post in shared_demo_posts)
        for post in shared_demo_posts:
            assert (
                len(
                    set(
                        session.scalars(
                            select(CommunityReply.owner_id).where(CommunityReply.post_id == post.id)
                        ).all()
                    )
                )
                >= 2
            )
        junior_counts = {
            model.__name__: session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.owner_id == junior_id, model.is_demo.is_(True))
            )
            for model in (Client, Case, Document, Task, Hearing, Draft, FilingBundle, CommunityPost)
        }
        assert all(count >= 1 for count in junior_counts.values())

    from app.security import create_token

    headers = {"Authorization": f"Bearer {create_token(owner_id)}"}
    advocate_feed = client.get("/api/v1/community/posts", headers=headers).json()
    assert set(advocate_feed) == {"items", "total", "page", "page_size", "pages"}
    assert {post["author_name"] for post in advocate_feed["items"]} >= {
        "Workspace Advocate",
        "Mira Shah",
        "Dev Patel",
    }
    assert not foreign_private_demo_ids.intersection(post["id"] for post in advocate_feed["items"])
    client_list = client.get("/api/v1/clients", headers=headers).json()["items"]
    empty_client = next(row for row in client_list if row["name"] == "No Active Matters Ltd.")
    assert empty_client["case_count"] == 0
    case_list = client.get("/api/v1/cases", headers=headers).json()["items"]
    past_case = next(row for row in case_list if row["title"].startswith("ABC Pvt."))
    assert past_case["next_hearing_at"] is None
    future_case = next(row for row in case_list if row["title"].startswith("TechBuild"))
    expected_iso = future_expected.isoformat()
    assert future_case["next_hearing_at"].startswith(expected_iso[:19])
    assert any(row["status"] == "closed" for row in case_list)
    phrase = client.get(
        "/api/v1/search/documents",
        headers=headers,
        params={"query": '"Sapphire Pavilion on the third calendar day"'},
    ).json()
    assert phrase["items"][0]["document_title"] == "Page Three Motion"
    assert phrase["items"][0]["page_number"] == 3
    semantic = client.get(
        "/api/v1/search/documents",
        headers=headers,
        params={"query": "where will the tribunal sit"},
    ).json()
    assert semantic["items"]
    assert any("seat shall be mumbai" in hit["snippet"].lower() for hit in semantic["items"])
    unique = client.get("/api/v1/search/documents", headers=headers, params={"query": "ZXQORBITKEY"}).json()
    assert unique["items"][0]["document_title"] == "Unique Term Evidence"
    unrelated = client.get(
        "/api/v1/search/documents", headers=headers, params={"query": "violet saxophone excavation quantum"}
    ).json()
    assert unrelated["items"] == []
    assert unrelated["total"] == 0
    gibberish = client.get(
        "/api/v1/search/documents", headers=headers, params={"query": "zzyz quuxorp plinth"}
    ).json()
    assert gibberish["items"] == [] and gibberish["total"] == 0
    probes = (
        "governing law arbitration conciliation act",
        "arbitral award interest costs termination",
        "seat of arbitration Mumbai neutral tribunal",
        "force majeure supply chain delay damages",
    )
    top_sets = []
    for query in probes:
        response = client.get("/api/v1/search/documents", headers=headers, params={"query": query}).json()
        top_sets.append({hit["document_id"] for hit in response["items"][:3]})
    assert len(set(map(frozenset, top_sets))) >= 2, (probes, top_sets, response)
    assert top_sets[1] != top_sets[2]
    force_majeure = client.get(
        "/api/v1/search/documents",
        headers=headers,
        params={"query": "force majeure supply chain delay damages", "page_size": 100},
    ).json()
    assert force_majeure["items"]
    assert len(force_majeure["items"]) < 100
    assert all(hit["document_title"] == "Construction Contract" for hit in force_majeure["items"])
    only_doc = client.get(
        "/api/v1/search/documents",
        headers=headers,
        params={"query": "ZXQORBITKEY", "page_size": 100},
    ).json()
    assert only_doc["items"] and {hit["document_title"] for hit in only_doc["items"]} == {
        "Unique Term Evidence"
    }

    junior_login = client.post(
        "/api/v1/auth/login", json={"email": "researcher@tantara.local", "password": "tantara-local"}
    )
    assert junior_login.status_code == 200
    junior_headers = {"Authorization": f"Bearer {junior_login.json()['access_token']}"}
    junior_feed = client.get("/api/v1/community/posts", headers=junior_headers).json()
    assert {post["author_name"] for post in junior_feed["items"]} >= {
        "Workspace Advocate",
        "Dev Patel",
        "Mira Shah",
    }
    assert not foreign_private_demo_ids.intersection(post["id"] for post in junior_feed["items"])
    junior_clients = client.get("/api/v1/clients", headers=junior_headers).json()["items"]
    assert [row["name"] for row in junior_clients] == ["Junior Demo Client"]
    assert junior_clients[0]["case_count"] == 1
    junior_cases = client.get("/api/v1/cases", headers=junior_headers).json()["items"]
    assert [row["title"] for row in junior_cases] == ["Junior Demo Matter"]
    junior_docs = client.get("/api/v1/documents", headers=junior_headers).json()["items"]
    assert [row["title"] for row in junior_docs] == ["Junior Demo Evidence"]
    root_doc = next(row for row in documents if row.owner_id == owner_id)
    for foreign_path in (
        f"/api/v1/documents/{root_doc.id}",
        f"/api/v1/cases/{root_case_id}",
        f"/api/v1/clients/{root_client_id}",
    ):
        response = client.get(foreign_path, headers=junior_headers)
        assert response.status_code == 404, (foreign_path, response.text)
        assert "ABC Pvt." not in response.text and "Aarav" not in response.text
        body = (
            {"description": "stolen"}
            if "/cases/" in foreign_path
            else {"notes": "stolen"}
            if "/clients/" in foreign_path
            else {"title": "stolen"}
        )
        mutation = client.patch(foreign_path, headers=junior_headers, json=body)
        assert mutation.status_code == 403, (foreign_path, mutation.status_code, mutation.text)
    junior_summary = client.get("/api/v1/dashboard/summary", headers=junior_headers).json()
    assert junior_summary["active_cases"] == 1 and junior_summary["documents_processed"] == 1
    junior_calendar = client.get("/api/v1/calendar", headers=junior_headers).json()
    assert "ABC Pvt. Ltd." not in str(junior_calendar)
    junior_search = client.get(
        "/api/v1/search/documents", headers=junior_headers, params={"query": "Mumbai"}
    ).json()
    assert all(hit["document_id"] != root_doc.id for hit in junior_search["items"])
    assert client.get(
        f"/api/v1/community/posts/{root_post_id}/replies", headers=junior_headers
    ).status_code in {403, 404}


def test_demo_seed_refuses_nonempty_workspace_without_changing_counts(client, monkeypatch, capsys):
    with SessionLocal() as session:
        owner_id = session.scalar(select(User.id).where(User.email == "advocate@tantara.local"))
    with session_scope() as session:
        session.add(Client(id="refusal-client", owner_id=owner_id, name="Existing workspace client"))
        session.add(
            Case(id="refusal-case", owner_id=owner_id, title="Existing workspace case", is_demo=False)
        )
        session.add(
            Task(id="refusal-task", owner_id=owner_id, title="Existing workspace task", is_demo=False)
        )

    seed = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "scripts" / "seed.py"), run_name="seed_refusal"
    )
    with SessionLocal() as session:
        before = seed["workspace_table_counts"](session)
    monkeypatch.setattr(sys, "argv", ["seed.py", "--demo"])
    with pytest.raises(SystemExit) as result:
        seed["main"]()
    assert result.value.code == 2
    output = capsys.readouterr().out
    assert str(config.get_settings().data_dir) in output
    assert "clients=1" in output
    assert "cases=1" in output
    assert "tasks=1" in output
    with SessionLocal() as session:
        after = seed["workspace_table_counts"](session)
    assert after == before


def test_force_reset_removes_demo_rows_files_and_vectors_but_preserves_user_data(client, monkeypatch):
    from app.config import get_settings

    with SessionLocal() as session:
        owner_id = session.scalar(select(User.id).where(User.email == "advocate@tantara.local"))
    data_dir = get_settings().data_dir
    uploads = data_dir / "uploads"
    bundles = data_dir / "bundles"
    uploads.mkdir(parents=True, exist_ok=True)
    bundles.mkdir(parents=True, exist_ok=True)
    demo_upload = uploads / "demo-reset.pdf"
    user_upload = uploads / "user-preserved.pdf"
    demo_bundle = bundles / "demo-reset.pdf"
    demo_upload.write_bytes(b"demo document")
    user_upload.write_bytes(b"user document")
    demo_bundle.write_bytes(b"demo bundle")
    demo_document_id, user_document_id = str(uuid.uuid4()), str(uuid.uuid4())
    demo_chunk_id, user_chunk_id = str(uuid.uuid4()), str(uuid.uuid4())
    with session_scope() as session:
        demo_case = Case(id="demo-reset-case", owner_id=owner_id, title="Demo reset case", is_demo=True)
        session.add(demo_case)
        session.add(Client(id="demo-reset-client", owner_id=owner_id, name="Demo reset", is_demo=True))
        session.add(Client(id="user-preserved-client", owner_id=owner_id, name="User data", is_demo=False))
        session.add(
            FilingBundle(
                id="demo-reset-bundle",
                owner_id=owner_id,
                case_id=demo_case.id,
                name="Demo reset bundle",
                output_path="bundles/demo-reset.pdf",
                is_demo=True,
            )
        )
        session.add(
            Document(
                id=demo_document_id,
                owner_id=owner_id,
                case_id=demo_case.id,
                title="Demo reset document",
                filename=demo_upload.name,
                stored_path="uploads/demo-reset.pdf",
                content_hash="b" * 64,
                is_demo=True,
            )
        )
        session.add(
            Document(
                id=user_document_id,
                owner_id=owner_id,
                title="User preserved document",
                filename=user_upload.name,
                stored_path="uploads/user-preserved.pdf",
                content_hash="c" * 64,
                is_demo=False,
            )
        )
        session.add_all(
            [
                DocumentChunk(
                    id=demo_chunk_id,
                    document_id=demo_document_id,
                    chunk_index=0,
                    content="demo indexed chunk",
                    embedding_blob=np.ones(384, dtype="float32").tobytes(),
                    is_demo=True,
                ),
                DocumentChunk(
                    id=user_chunk_id,
                    document_id=user_document_id,
                    chunk_index=0,
                    content="user indexed chunk",
                    embedding_blob=np.ones(384, dtype="float32").tobytes(),
                    is_demo=False,
                ),
            ]
        )
        session.flush()
        session.add(
            CaseEvent(
                id="demo-reset-event",
                owner_id=owner_id,
                case_id=demo_case.id,
                type="all_day_event",
                occurred_at=datetime.now(UTC).replace(tzinfo=None),
                detail="demo event",
                is_demo=True,
            )
        )
    store().add(
        [
            (demo_chunk_id, np.ones(384, dtype="float32")),
            (user_chunk_id, np.ones(384, dtype="float32")),
        ]
    )
    (data_dir / "demo-fixtures").mkdir(parents=True, exist_ok=True)
    (data_dir / "demo-fixtures" / "generated.pdf").write_bytes(b"generated fixture")

    seed = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "scripts" / "seed.py"), run_name="seed_reset"
    )

    class ResetReached(Exception):
        pass

    remove_demo_data = seed["remove_demo_data"]

    def reset_then_stop():
        remove_demo_data()
        raise ResetReached

    seed["main"].__globals__["remove_demo_data"] = reset_then_stop
    monkeypatch.setattr(sys, "argv", ["seed.py", "--demo", "--force-reset"])
    with pytest.raises(ResetReached):
        seed["main"]()
    with SessionLocal() as session:
        assert session.get(Case, "demo-reset-case") is None
        assert session.get(Client, "demo-reset-client") is None
        assert session.get(FilingBundle, "demo-reset-bundle") is None
        assert session.get(Document, demo_document_id) is None
        assert session.get(Document, user_document_id) is not None
        assert session.get(Client, "user-preserved-client") is not None
        assert session.get(DocumentChunk, demo_chunk_id) is None
        assert session.get(DocumentChunk, user_chunk_id) is not None
    assert not demo_upload.exists()
    assert not demo_bundle.exists()
    assert user_upload.exists()
    assert not (data_dir / "demo-fixtures").exists()
    assert store().id_set() == {user_chunk_id}


def test_empty_seed_retains_only_the_local_advocate_and_no_rows(client, monkeypatch):
    from app.config import get_settings

    with SessionLocal() as session:
        owner = session.scalar(select(User))
    storage = get_settings().data_dir / "uploads"
    storage.mkdir(parents=True, exist_ok=True)
    stored_path = storage / "seeded-test.pdf"
    stored_path.write_bytes(b"fixture")
    document_id = str(uuid.uuid4())
    with session_scope() as session:
        session.add(
            Document(
                id=document_id,
                owner_id=owner.id,
                title="Seed cleanup check",
                filename="seeded-test.pdf",
                stored_path=str(stored_path),
                content_hash="a" * 64,
                status="ready",
            )
        )
        session.flush()
        session.add(
            DocumentPage(
                id=str(uuid.uuid4()),
                owner_id=owner.id,
                document_id=document_id,
                page_number=1,
                text="Fixture page",
            )
        )
        session.add(
            DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=document_id,
                chunk_index=0,
                content="Fixture searchable chunk",
                page_number=1,
            )
        )
    monkeypatch.setattr(sys, "argv", ["seed.py", "--empty"])
    runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "scripts" / "seed.py"), run_name="empty_seed_test"
    )["main"]()
    with SessionLocal() as session:
        assert session.scalar(select(func.count(User.id))) == 1
        for table in Base.metadata.sorted_tables:
            if table.name != "users":
                assert session.execute(select(func.count()).select_from(table)).scalar() == 0, table.name
        assert session.execute(text("SELECT count(*) FROM rate_buckets")).scalar() == 0
    assert store().count() == 0
    assert not stored_path.exists()


def test_case_hearing_derivation_is_live_and_owner_scoped(client):
    login = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    case = client.post("/api/v1/cases", headers=headers, json={"title": "Hearing-derived case"}).json()
    cid = case["id"]
    overview = client.get(f"/api/v1/cases/{cid}/overview", headers=headers).json()
    assert overview["documents_count"] == 0 and overview["drafts_count"] == 0
    past = (datetime.now(UTC) - timedelta(days=2)).replace(tzinfo=None).isoformat()
    first = (datetime.now(UTC) + timedelta(days=4)).replace(tzinfo=None).isoformat()
    second = (datetime.now(UTC) + timedelta(days=9)).replace(tzinfo=None).isoformat()
    past_row = client.post(
        "/api/v1/hearings", headers=headers, json={"title": "Past", "at": past, "case_id": cid}
    ).json()
    from app.models import User
    from app.security import hash_password

    foreign_owner = str(uuid.uuid4())
    with session_scope() as session:
        session.add(
            User(
                id=foreign_owner,
                name="Foreign hearing owner",
                email=f"foreign-{foreign_owner}@local",
                password_hash=hash_password("password"),
                role="advocate",
            )
        )
        session.flush()
        session.add(
            Hearing(
                id=str(uuid.uuid4()),
                owner_id=foreign_owner,
                case_id=cid,
                title="Another user's hearing",
                at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
            )
        )
    assert client.get(f"/api/v1/cases/{cid}", headers=headers).json()["next_hearing_at"] is None
    hearing1 = client.post(
        "/api/v1/hearings", headers=headers, json={"title": "Sooner", "at": first, "case_id": cid}
    ).json()
    later_hearing = client.post(
        "/api/v1/hearings", headers=headers, json={"title": "Later", "at": second, "case_id": cid}
    ).json()
    expected = client.get(f"/api/v1/cases/{cid}", headers=headers).json()["next_hearing_at"]
    assert expected.startswith(first[:16])
    assert client.get("/api/v1/cases", headers=headers).json()["items"][0]["next_hearing_at"] == expected
    assert client.delete(f"/api/v1/hearings/{hearing1['id']}", headers=headers).status_code == 200
    after_delete = client.get(f"/api/v1/cases/{cid}", headers=headers).json()["next_hearing_at"]
    assert after_delete.startswith(second[:16])
    assert client.delete(f"/api/v1/hearings/{later_hearing['id']}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/cases/{cid}", headers=headers).json()["next_hearing_at"] is None
    assert client.delete(f"/api/v1/hearings/{past_row['id']}", headers=headers).status_code == 200


def test_client_case_count_is_owner_scoped_and_requires_auth(client):
    login = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    client_row = client.post("/api/v1/clients", headers=headers, json={"name": "Counted client"}).json()
    client.post("/api/v1/cases", headers=headers, json={"title": "Owned case", "client_id": client_row["id"]})
    from app.models import User
    from app.security import hash_password

    uid = str(uuid.uuid4())
    with session_scope() as session:
        session.add(
            User(
                id=uid,
                name="Other",
                email=f"other-{uid}@local",
                password_hash=hash_password("x"),
                role="advocate",
            )
        )
        session.flush()
        session.add(
            Case(
                id=str(uuid.uuid4()),
                owner_id=uid,
                title="Other's case",
                client_id=client_row["id"],
                status="active",
            )
        )
    listing = client.get("/api/v1/clients", headers=headers).json()
    assert next(item for item in listing["items"] if item["id"] == client_row["id"])["case_count"] == 1
    assert client.get(f"/api/v1/clients/{client_row['id']}", headers=headers).json()["case_count"] == 1
    assert client.get("/api/v1/clients").status_code == 401


def test_stale_faiss_index_is_reconciled_on_search_and_ask(client):
    login = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    uploaded = client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": ("evidence.txt", b"The arbitration seat is Mumbai. " * 20, "text/plain")},
    )
    did = uploaded.json()["document_id"]
    for _ in range(100):
        job = client.get(f"/api/v1/documents/{did}/job", headers=headers).json()
        if job["status"] in {"ready", "failed"}:
            break
        import time

        time.sleep(0.05)
    assert job["status"] == "ready"
    store().rebuild([])
    search = client.get(
        "/api/v1/search/documents", headers=headers, params={"query": "arbitration seat Mumbai"}
    )
    assert search.status_code == 200 and search.json()["status"] == "ok"
    assert store().count() > 0
    ask = client.post("/api/v1/ai/ask", headers=headers, json={"question": "What is the seat?"})
    assert ask.status_code == 200
    assert ask.json()["meta"]["retrieval_status"] == "ok"
