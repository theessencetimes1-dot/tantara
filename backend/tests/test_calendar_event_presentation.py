from datetime import timedelta

from app.timezone import workspace_now


def test_calendar_event_keeps_type_and_presents_case_context(client):
    login = client.post(
        "/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"}
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    case_title = "Northstar evidence review matter"
    case = client.post("/api/v1/cases", headers=headers, json={"title": case_title})
    assert case.status_code == 201, case.text
    case_id = case.json()["id"]

    day = workspace_now().date() + timedelta(days=1)
    event_type = "document_uploaded"
    detail = "Supplemental witness exhibits uploaded for review"
    event = client.post(
        f"/api/v1/cases/{case_id}/events",
        headers=headers,
        json={
            "type": event_type,
            "occurred_at": f"{day.isoformat()}T00:00:00+05:30",
            "detail": detail,
        },
    )
    assert event.status_code == 200, event.text

    params = {"from": day.isoformat(), "to": (day + timedelta(days=1)).isoformat()}
    calendar = client.get("/api/v1/calendar", headers=headers, params=params)
    assert calendar.status_code == 200, calendar.text
    item = next(row for row in calendar.json() if row["id"] == event.json()["id"])
    assert item["type"] == "event"
    assert item["event_type"] == event_type
    assert item["title"] == detail
    assert item["detail"] == detail
    assert item["case_id"] == case_id
    assert item["case_title"] == case_title
    assert item["all_day"] is True
    assert item["title"] not in {event_type, "event"}

    fallback_event = client.post(
        f"/api/v1/cases/{case_id}/events",
        headers=headers,
        json={"type": "first_hearing", "occurred_at": f"{day.isoformat()}T00:00:00+05:30", "detail": ""},
    )
    assert fallback_event.status_code == 200, fallback_event.text
    calendar = client.get("/api/v1/calendar", headers=headers, params=params)
    fallback_item = next(row for row in calendar.json() if row["id"] == fallback_event.json()["id"])
    assert fallback_item["title"] == "First hearing"
    assert fallback_item["detail"] == "First hearing"
    assert fallback_item["title"] != fallback_item["event_type"]

    upcoming = client.get("/api/v1/dashboard/upcoming?days=3", headers=headers)
    assert upcoming.status_code == 200, upcoming.text
    upcoming_item = next(row for row in upcoming.json() if row["id"] == event.json()["id"])
    assert {key: upcoming_item[key] for key in ("type", "event_type", "title", "detail", "case_title")} == {
        "type": "event",
        "event_type": event_type,
        "title": detail,
        "detail": detail,
        "case_title": case_title,
    }
