import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app


def _assert_error_envelope(response, status_code, code):
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) >= {"code", "message"}
    assert body["error"]["code"] == code
    assert "detail" not in body


def test_unmatched_and_wrong_method_routes_use_api_error_envelopes(client):
    not_found = client.get("/api/v1/this-route-does-not-exist")
    _assert_error_envelope(not_found, 404, "not_found")

    wrong_method = client.post("/api/v1/health")
    _assert_error_envelope(wrong_method, 405, "method_not_allowed")
    assert wrong_method.json()["error"]["details"]["allowed_methods"]


@pytest.mark.parametrize(
    ("method", "path", "body", "expected_status", "expected_code"),
    [
        ("get", "/api/v1/not-a-route", None, 404, "not_found"),
        ("post", "/api/v1/health", None, 405, "method_not_allowed"),
        ("post", "/api/v1/auth/login", "{broken-json", 422, "validation_error"),
        ("get", "/api/v1/cases", None, 401, "unauthorized"),
        ("post", "/api/v1/collections", {"name": "Envelope collision"}, 409, "duplicate"),
    ],
)
def test_error_codes_are_stable_for_common_http_failures(
    client, method, path, body, expected_status, expected_code
):
    headers = {}
    if expected_code == "duplicate":
        login = client.post("/api/v1/auth/login", json={"email": "advocate@tantara.local", "password": "tantara-local"})
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        created = client.post("/api/v1/collections", headers=headers, json=body)
        assert created.status_code == 201
    if isinstance(body, str):
        headers["Content-Type"] = "application/json"
        response = client.request(method, path, headers=headers, content=body)
    else:
        response = client.request(method, path, headers=headers, json=body)
    _assert_error_envelope(response, expected_status, expected_code)


def test_malformed_request_body_uses_validation_error_envelope(client):
    response = client.post(
        "/api/v1/auth/login",
        content="{malformed-json",
        headers={"Content-Type": "application/json"},
    )
    _assert_error_envelope(response, 422, "validation_error")
    assert "details" in response.json()["error"]


def test_unexpected_exception_returns_sanitized_internal_error_envelope(client):
    def controlled_failure():
        raise RuntimeError("private database connection detail")

    route = APIRoute("/api/v1/_test-controlled-failure", controlled_failure, methods=["GET"])
    app.router.routes.append(route)
    try:
        response = TestClient(app, raise_server_exceptions=False).get("/api/v1/_test-controlled-failure")
    finally:
        app.router.routes.remove(route)

    _assert_error_envelope(response, 500, "internal_error")
    assert response.json()["error"]["message"] == "Internal server error"
    assert "private database connection detail" not in response.text
