from sqlalchemy import select

from app.db import SessionLocal
from app.models import SavedItem, User
from app.security import hash_password


def _ensure_user(email, name, role):
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                id=f"community-{role}",
                name=name,
                email=email,
                password_hash=hash_password("tantara-local"),
                role=role,
            )
            session.add(user)
            session.commit()
        return user.id


def _auth(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "tantara-local"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _post(client, headers, title, visibility="private"):
    response = client.post(
        "/api/v1/community/posts",
        headers=headers,
        json={"title": title, "body": f"Body for {title}", "visibility": visibility},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_private_posts_stay_private_and_workspace_posts_are_shared_with_author_identity(client):
    researcher_id = _ensure_user("researcher@tantara.local", "Mira Shah", "researcher")
    _ensure_user("staff@tantara.local", "Dev Patel", "staff")
    advocate = _auth(client, "advocate@tantara.local")
    researcher = _auth(client, "researcher@tantara.local")
    staff = _auth(client, "staff@tantara.local")

    private = _post(client, researcher, "Mira's private note")
    workspace = _post(client, researcher, "Mira's shared question", "workspace")
    staff_workspace = _post(client, staff, "Dev's shared discussion", "workspace")

    assert client.get(f"/api/v1/community/posts/{private['id']}", headers=advocate).status_code == 404
    assert client.get(f"/api/v1/community/posts/{private['id']}", headers=staff).status_code == 404
    assert (
        client.post(
            f"/api/v1/community/posts/{private['id']}/replies",
            headers=advocate,
            json={"body": "not allowed"},
        ).status_code
        == 404
    )
    assert client.post(f"/api/v1/community/posts/{private['id']}/save", headers=advocate).status_code == 404

    own_feed = client.get("/api/v1/community/posts", headers=researcher)
    assert own_feed.status_code == 200
    own = own_feed.json()
    assert set(own) == {"items", "total", "page", "page_size", "pages"}
    assert {post["id"] for post in own["items"]} >= {private["id"], workspace["id"], staff_workspace["id"]}
    assert all(
        "author_name" in post and "author_role" in post and post["created_at"] for post in own["items"]
    )
    assert any(
        post["id"] == staff_workspace["id"]
        and post["author"] == {"display_name": "Dev Patel", "role": "staff"}
        for post in own["items"]
    )

    other_feed = client.get("/api/v1/community/posts", headers=advocate).json()
    assert private["id"] not in {post["id"] for post in other_feed["items"]}
    assert {workspace["id"], staff_workspace["id"]} <= {post["id"] for post in other_feed["items"]}
    assert any(
        post["author_name"] == "Mira Shah" and post["author_role"] == "researcher"
        for post in other_feed["items"]
    )
    assert (
        client.get(f"/api/v1/community/posts/{workspace['id']}", headers=advocate).json()["author_name"]
        == "Mira Shah"
    )

    response = client.post(
        f"/api/v1/community/posts/{workspace['id']}/replies",
        headers=advocate,
        json={"body": "Shared reply from the advocate."},
    )
    assert response.status_code == 200
    reply = response.json()
    assert reply["author"] == {"display_name": "Workspace Advocate", "role": "advocate"}
    reply_list = client.get(f"/api/v1/community/posts/{workspace['id']}/replies", headers=researcher).json()
    assert reply_list["total"] == 1 and reply_list["items"][0]["id"] == reply["id"]

    saved = client.post(f"/api/v1/community/posts/{workspace['id']}/save", headers=advocate)
    assert saved.status_code == 200 and saved.json()["saved"] is True
    advocate_saved = client.get("/api/v1/community/posts?saved=true", headers=advocate).json()
    researcher_saved = client.get("/api/v1/community/posts?saved=true", headers=researcher).json()
    assert [post["id"] for post in advocate_saved["items"]] == [workspace["id"]]
    assert workspace["id"] not in {post["id"] for post in researcher_saved["items"]}
    with SessionLocal() as session:
        assert (
            session.scalar(
                select(SavedItem.id).where(
                    SavedItem.owner_id == researcher_id,
                    SavedItem.item_type == "community_post",
                    SavedItem.item_id == workspace["id"],
                )
            )
            is None
        )


def test_read_only_accounts_may_post_and_reply_but_case_edits_are_forbidden(client):
    _ensure_user("researcher@tantara.local", "Mira Shah", "researcher")
    advocate = _auth(client, "advocate@tantara.local")
    researcher = _auth(client, "researcher@tantara.local")
    case = client.post("/api/v1/cases", headers=advocate, json={"title": "Advocate case"}).json()
    assert (
        client.patch(f"/api/v1/cases/{case['id']}", headers=researcher, json={"title": "Changed"}).status_code
        == 403
    )
    shared = _post(client, advocate, "Open workspace post", "workspace")
    created = _post(client, researcher, "Researcher can post")
    assert created["visibility"] == "private"
    changed = client.patch(
        f"/api/v1/community/posts/{created['id']}",
        headers=researcher,
        json={"visibility": "workspace"},
    )
    assert changed.status_code == 200 and changed.json()["visibility"] == "workspace"
    response = client.post(
        f"/api/v1/community/posts/{shared['id']}/replies",
        headers=researcher,
        json={"body": "Researcher reply"},
    )
    assert response.status_code == 200
    assert response.json()["author_name"] == "Mira Shah"
    invalid = client.patch(
        f"/api/v1/community/posts/{created['id']}",
        headers=researcher,
        json={"visibility": "public"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"
    assert set(invalid.json()["error"]) >= {"code", "message", "details"}


def test_reply_delete_is_author_or_admin_only_and_uses_404_for_private_posts(client):
    _ensure_user("researcher@tantara.local", "Mira Shah", "researcher")
    _ensure_user("staff@tantara.local", "Dev Patel", "staff")
    _ensure_user("admin@tantara.local", "Admin User", "admin")
    advocate = _auth(client, "advocate@tantara.local")
    researcher = _auth(client, "researcher@tantara.local")
    staff = _auth(client, "staff@tantara.local")
    admin = _auth(client, "admin@tantara.local")

    private = _post(client, advocate, "Private thread")
    private_reply = client.post(
        f"/api/v1/community/posts/{private['id']}/replies",
        headers=advocate,
        json={"body": "Owner reply"},
    ).json()
    assert (
        client.delete(
            f"/api/v1/community/posts/{private['id']}/replies/{private_reply['id']}", headers=staff
        ).status_code
        == 404
    )

    shared = _post(client, advocate, "Shared thread", "workspace")
    advocate_reply = client.post(
        f"/api/v1/community/posts/{shared['id']}/replies", headers=advocate, json={"body": "Advocate"}
    ).json()
    researcher_reply = client.post(
        f"/api/v1/community/posts/{shared['id']}/replies", headers=researcher, json={"body": "Researcher"}
    ).json()
    staff_reply = client.post(
        f"/api/v1/community/posts/{shared['id']}/replies", headers=staff, json={"body": "Staff"}
    ).json()
    assert (
        client.delete(
            f"/api/v1/community/posts/{shared['id']}/replies/{advocate_reply['id']}", headers=staff
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/api/v1/community/posts/{shared['id']}/replies/{researcher_reply['id']}", headers=researcher
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/v1/community/posts/{shared['id']}/replies/{advocate_reply['id']}", headers=advocate
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/v1/community/posts/{shared['id']}/replies/{staff_reply['id']}", headers=admin
        ).status_code
        == 200
    )


def test_feed_anonymous_pagination_and_empty_state_contract(client):
    _ensure_user("researcher@tantara.local", "Mira Shah", "researcher")
    assert client.get("/api/v1/community/posts").status_code == 401
    advocate = _auth(client, "advocate@tantara.local")
    assert client.get("/api/v1/community/posts?page_size=0", headers=advocate).status_code == 422
    empty = client.get("/api/v1/community/posts", headers=advocate).json()
    assert empty == {"items": [], "total": 0, "page": 1, "page_size": 20, "pages": 0}
    created = [_post(client, advocate, f"Feed post {index}", "workspace") for index in range(3)]
    first = client.get("/api/v1/community/posts", headers=advocate, params={"page": 1, "page_size": 2}).json()
    assert first["total"] == 3 and first["page"] == 1 and first["page_size"] == 2 and first["pages"] == 2
    assert len(first["items"]) == 2
    beyond = client.get("/api/v1/community/posts", headers=advocate, params={"page": 999}).json()
    assert beyond["items"] == [] and beyond["total"] == 3 and beyond["page"] == 999
    assert len({post["id"] for post in created}) == 3
