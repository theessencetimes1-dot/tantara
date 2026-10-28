import io
import uuid

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Draft, DraftVersion, User
from app.security import hash_password


def _login(client, email="advocate@tantara.local"):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "tantara-local"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _ensure_user(email, name, role):
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                id=str(uuid.uuid4()),
                name=name,
                email=email,
                password_hash=hash_password("tantara-local"),
                role=role,
            )
            session.add(user)
            session.commit()
        return user.id


def _create_draft(client, headers, content="Initial draft text."):
    response = client.post(
        "/api/v1/drafts",
        headers=headers,
        json={"title": "Version history test", "document_type": "Pleading", "content_markdown": content},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _version_rows(draft_id):
    with SessionLocal() as session:
        return session.scalars(
            select(DraftVersion)
            .where(DraftVersion.draft_id == draft_id)
            .order_by(DraftVersion.version_number)
        ).all()


def test_content_patches_snapshot_previous_text_in_sequence_and_newest_first(client):
    headers = _login(client)
    initial = "# Original\n\nExact bytes stay here.\n"
    draft = _create_draft(client, headers, initial)
    first_edit = "# First edit\n\nDifferent content.\n"
    second_edit = "# Second edit\n\nLatest content.\n"

    first = client.patch(
        f"/api/v1/drafts/{draft['id']}", headers=headers, json={"content_markdown": first_edit}
    )
    assert first.status_code == 200 and first.json()["content_markdown"] == first_edit
    first_versions = client.get(f"/api/v1/drafts/{draft['id']}/versions", headers=headers).json()
    assert first_versions["total"] == 1
    assert first_versions["items"][0]["content_markdown"] == initial
    assert first_versions["items"][0]["version_number"] == 1
    assert first_versions["items"][0]["change_note"] == "Edited in editor"
    assert _version_rows(draft["id"])[0].content_markdown == initial

    second = client.patch(
        f"/api/v1/drafts/{draft['id']}", headers=headers, json={"content_markdown": second_edit}
    )
    assert second.status_code == 200 and second.json()["content_markdown"] == second_edit
    result = client.get(f"/api/v1/drafts/{draft['id']}/versions", headers=headers).json()
    assert (result["total"], result["page"], result["page_size"], result["pages"]) == (2, 1, 20, 1)
    assert [row["version_number"] for row in result["items"]] == [2, 1]
    assert [row["content_markdown"] for row in result["items"]] == [first_edit, initial]
    assert [row.version_number for row in _version_rows(draft["id"])] == [1, 2]
    assert [row.content_markdown for row in _version_rows(draft["id"])] == [initial, first_edit]
    assert all(row.get("created_at") for row in result["items"])


def test_regenerate_section_snapshots_the_preceding_draft(client):
    headers = _login(client)
    content = "# Existing pleading\n\nOriginal section.\n"
    draft = _create_draft(client, headers, content)
    response = client.post(
        f"/api/v1/drafts/{draft['id']}/regenerate-section",
        headers=headers,
        json={"section_heading": "Verified facts", "instructions": "Add verified material."},
    )
    assert response.status_code == 200
    assert "## Verified facts" in response.json()["content_markdown"]
    versions = client.get(f"/api/v1/drafts/{draft['id']}/versions", headers=headers).json()
    assert versions["total"] == 1
    assert versions["items"][0]["content_markdown"] == content
    assert versions["items"][0]["change_note"] == "Regenerated section: Verified facts"
    with SessionLocal() as session:
        version = session.scalar(select(DraftVersion).where(DraftVersion.draft_id == draft["id"]))
        stored = session.get(Draft, draft["id"])
        assert version.content_markdown == content
        assert stored.content_markdown == response.json()["content_markdown"]


def test_explicit_snapshot_can_omit_content_and_never_trusts_supplied_snapshot_text(client):
    headers = _login(client)
    content = "Server-held version, not client-resubmitted text.\n"
    draft = _create_draft(client, headers, content)
    response = client.post(f"/api/v1/drafts/{draft['id']}/versions", headers=headers, json={})
    assert response.status_code == 200
    assert response.json()["content_markdown"] == content
    assert "change_note" not in response.json()
    with SessionLocal() as session:
        stored = session.get(Draft, draft["id"])
        version = session.get(DraftVersion, response.json()["id"])
        assert stored.content_markdown == content
        assert version.content_markdown == content

    next_content = "An explicitly submitted next draft state.\n"
    submitted = client.post(
        f"/api/v1/drafts/{draft['id']}/versions",
        headers=headers,
        json={"content_markdown": next_content, "change_note": "Client edit"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["content_markdown"] == content
    with SessionLocal() as session:
        assert session.get(DraftVersion, submitted.json()["id"]).content_markdown == content
        assert session.get(Draft, draft["id"]).content_markdown == next_content


def test_restore_snapshots_replaced_text_and_is_repeatable(client):
    headers = _login(client)
    original = "# Original pleading\n\nRecover this exact text.\n"
    changed = "# Newer pleading\n\nDo not lose me on restore.\n"
    draft = _create_draft(client, headers, original)
    client.patch(f"/api/v1/drafts/{draft['id']}", headers=headers, json={"content_markdown": changed})
    versions = client.get(f"/api/v1/drafts/{draft['id']}/versions", headers=headers).json()["items"]
    original_version = versions[0]

    for expected_number in (2, 3):
        restored = client.post(
            f"/api/v1/drafts/{draft['id']}/versions/{original_version['id']}/restore", headers=headers
        )
        assert restored.status_code == 200
        assert restored.json()["content_markdown"] == original
        current = client.get(f"/api/v1/drafts/{draft['id']}", headers=headers).json()
        assert current["content_markdown"] == original
        version_list = client.get(f"/api/v1/drafts/{draft['id']}/versions", headers=headers).json()
        assert version_list["items"][0]["version_number"] == expected_number
        expected_snapshot = changed if expected_number == 2 else original
        assert version_list["items"][0]["content_markdown"] == expected_snapshot
        assert version_list["items"][0]["change_note"] == "Restored from version 1"
        with SessionLocal() as session:
            state = session.get(Draft, draft["id"])
            newest = session.scalar(
                select(DraftVersion).where(
                    DraftVersion.draft_id == draft["id"],
                    DraftVersion.version_number == expected_number,
                )
            )
            assert state.content_markdown == original
            assert newest.content_markdown == expected_snapshot
            assert newest.change_note == "Restored from version 1"


def test_restore_owner_and_cross_user_authorization_matrix(client):
    researcher_id = _ensure_user("researcher@tantara.local", "Mira Shah", "researcher")
    staff_id = _ensure_user("staff@tantara.local", "Dev Patel", "staff")
    owner = _login(client)
    researcher = _login(client, "researcher@tantara.local")
    staff = _login(client, "staff@tantara.local")
    draft = _create_draft(client, owner, "Owner's private text.")
    client.patch(
        f"/api/v1/drafts/{draft['id']}", headers=owner, json={"content_markdown": "Changed owner text."}
    )
    version = client.get(f"/api/v1/drafts/{draft['id']}/versions", headers=owner).json()["items"][0]
    own_restore = client.post(f"/api/v1/drafts/{draft['id']}/versions/{version['id']}/restore", headers=owner)
    assert own_restore.status_code == 200
    assert own_restore.json()["content_markdown"] == "Owner's private text."

    for headers in (researcher, staff):
        assert (
            client.get(f"/api/v1/drafts/{draft['id']}/versions/{version['id']}", headers=headers).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/v1/drafts/{draft['id']}/versions/{version['id']}/restore", headers=headers
            ).status_code
            == 404
        )
    assert client.get(f"/api/v1/drafts/{draft['id']}/versions").status_code == 401
    assert client.post(f"/api/v1/drafts/{draft['id']}/versions/{version['id']}/restore").status_code == 401
    assert (
        client.get(f"/api/v1/drafts/{draft['id']}/versions/{uuid.uuid4()}", headers=owner).status_code == 404
    )

    # Researchers can read their own draft history but remain read-only for restore.
    researcher_draft_id = str(uuid.uuid4())
    with SessionLocal() as session:
        session.add(
            Draft(
                id=researcher_draft_id,
                owner_id=researcher_id,
                title="Researcher-owned historical draft",
                document_type="Research Note",
                content_markdown="Researcher version text.",
            )
        )
        session.flush()
        researcher_version = DraftVersion(
            id=str(uuid.uuid4()),
            owner_id=researcher_id,
            draft_id=researcher_draft_id,
            version_number=1,
            content_markdown="Researcher version text.",
        )
        session.add(researcher_version)
        session.commit()
        researcher_version_id = researcher_version.id
    own_version = client.get(
        f"/api/v1/drafts/{researcher_draft_id}/versions/{researcher_version_id}", headers=researcher
    )
    assert own_version.status_code == 200
    assert (
        client.post(
            f"/api/v1/drafts/{researcher_draft_id}/versions/{researcher_version_id}/restore",
            headers=researcher,
        ).status_code
        == 403
    )
    with SessionLocal() as session:
        assert session.get(Draft, researcher_draft_id).content_markdown == "Researcher version text."
        assert session.get(User, staff_id).role == "staff"


def test_blank_patch_missing_document_type_and_empty_export_are_rejected(client):
    headers = _login(client)
    draft = _create_draft(client, headers, "Non-empty initial content.")
    for value in ("", " \n\t "):
        response = client.patch(
            f"/api/v1/drafts/{draft['id']}", headers=headers, json={"content_markdown": value}
        )
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert set(error) >= {"code", "message", "details"}
        assert any(
            detail.get("loc", [])[-1:] == ["content_markdown"]
            and "Draft content cannot be empty" in detail.get("msg", "")
            for detail in error["details"]
        )
    missing_type = client.post("/api/v1/drafts", headers=headers, json={"title": "No type"})
    assert missing_type.status_code == 422
    assert any(
        detail.get("loc", [])[-1:] == ["document_type"] for detail in missing_type.json()["error"]["details"]
    )

    empty = _create_draft(client, headers, "")
    exported = client.get(f"/api/v1/drafts/{empty['id']}/export", headers=headers)
    assert exported.status_code == 409
    assert exported.json() == {
        "error": {"code": "conflict", "message": "Draft content is empty and cannot be exported"}
    }
    with SessionLocal() as session:
        assert session.get(Draft, empty["id"]).content_markdown == ""


def test_deleted_draft_history_is_not_recoverable_and_two_patches_both_survive(client):
    headers = _login(client)
    draft = _create_draft(client, headers, "State zero")
    first = client.patch(
        f"/api/v1/drafts/{draft['id']}", headers=headers, json={"content_markdown": "State one"}
    )
    second = client.patch(
        f"/api/v1/drafts/{draft['id']}", headers=headers, json={"content_markdown": "State two"}
    )
    assert first.status_code == second.status_code == 200
    history = client.get(f"/api/v1/drafts/{draft['id']}/versions", headers=headers).json()
    assert [version["content_markdown"] for version in history["items"]] == ["State one", "State zero"]
    recoverable = [
        client.get(f"/api/v1/drafts/{draft['id']}/versions/{version['id']}", headers=headers).json()[
            "content_markdown"
        ]
        for version in history["items"]
    ]
    with SessionLocal() as session:
        db_history = [row.content_markdown for row in _version_rows(draft["id"])]
        assert db_history == ["State zero", "State one"]
        assert recoverable == ["State one", "State zero"]
        assert session.get(Draft, draft["id"]).content_markdown == "State two"

    removed = client.delete(f"/api/v1/drafts/{draft['id']}", headers=headers)
    assert removed.status_code == 200
    assert client.get(f"/api/v1/drafts/{draft['id']}/versions", headers=headers).status_code == 404
    with SessionLocal() as session:
        assert session.get(Draft, draft["id"]) is None
        assert session.scalar(select(DraftVersion.id).where(DraftVersion.draft_id == draft["id"])) is None


def test_whitespace_version_save_is_rejected_without_mutating_content_or_history(client):
    headers = _login(client)
    draft = _create_draft(client, headers, "Verified draft content")
    response = client.post(
        f"/api/v1/drafts/{draft['id']}/versions",
        headers=headers,
        json={"content_markdown": "   \n  "},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    current = client.get(f"/api/v1/drafts/{draft['id']}", headers=headers).json()
    assert current["content_markdown"] == "Verified draft content"
    assert client.get(f"/api/v1/drafts/{draft['id']}/versions", headers=headers).json()["total"] == 0


def test_pdf_export_wraps_long_paragraph_and_keeps_markdown_heading(client):
    from pypdf import PdfReader

    headers = _login(client)
    paragraph = "It is submitted that " + "the respondent remains liable under the arbitration agreement " * 12
    draft = _create_draft(client, headers, f"## Submissions\n\n{paragraph}")
    response = client.get(f"/api/v1/drafts/{draft['id']}/export?format=pdf", headers=headers)
    assert response.status_code == 200
    reader = PdfReader(io.BytesIO(response.content))
    extracted = " ".join(page.extract_text() or "" for page in reader.pages)
    assert "Submissions" in extracted
    assert "the respondent remains liable under the arbitration agreement" in extracted
    assert "arbitration agreement" in extracted
