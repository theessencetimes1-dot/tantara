from datetime import datetime, timedelta
import uuid

from app.db import session_scope
from app.models import Case, Hearing, User
from app.security import create_token, hash_password


def test_case_next_hearing_sort_is_null_safe_stable_and_rejects_unknown_keys(client):
    owner_id = str(uuid.uuid4())
    cases = {
        name: str(uuid.uuid4())
        for name in ("Zulu same day", "Alpha same day", "Middle later", "No hearing")
    }
    now = datetime.now()
    with session_scope() as session:
        session.add(
            User(
                id=owner_id,
                name="Case Sort Owner",
                email=f"case-sort-{owner_id}@example.local",
                password_hash=hash_password("local-test-password"),
                role="advocate",
            )
        )
        session.flush()
        for title, case_id in cases.items():
            session.add(Case(id=case_id, owner_id=owner_id, title=title, status="active"))
        for title, at in (("Zulu same day", now + timedelta(days=2)),
                          ("Alpha same day", now + timedelta(days=2)),
                          ("Middle later", now + timedelta(days=5))):
            session.add(
                Hearing(
                    id=str(uuid.uuid4()),
                    owner_id=owner_id,
                    case_id=cases[title],
                    title=f"{title} hearing",
                    at=at,
                )
            )

    headers = {"Authorization": f"Bearer {create_token(owner_id)}"}
    response = client.get("/api/v1/cases?page_size=20&sort=next_hearing_at", headers=headers)
    assert response.status_code == 200
    rows = response.json()["items"]
    assert [row["id"] for row in rows] == [
        cases["Alpha same day"],
        cases["Zulu same day"],
        cases["Middle later"],
        cases["No hearing"],
    ]
    assert [row["next_hearing_at"] is None for row in rows] == [False, False, False, True]

    invalid = client.get("/api/v1/cases?sort=nonsense_field", headers=headers)
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert invalid.json()["error"]["message"] == "Unsupported sort key"
