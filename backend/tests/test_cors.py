from app.config import DEFAULT_CORS_ORIGINS, Settings


def test_default_cors_origins_cover_local_frontend_ports():
    origins = DEFAULT_CORS_ORIGINS.split(",")
    assert len(origins) == 42
    assert "http://localhost:3000" in origins
    assert "http://localhost:3020" in origins
    assert "http://127.0.0.1:3000" in origins
    assert "http://127.0.0.1:3020" in origins


def test_cors_origins_can_be_overridden_by_both_environment_names(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://front.example,http://localhost:3012")
    monkeypatch.delenv("TANTARA_CORS_ORIGINS", raising=False)
    assert Settings(_env_file=None).cors_origins == "https://front.example,http://localhost:3012"
    monkeypatch.delenv("CORS_ORIGINS")
    monkeypatch.setenv("TANTARA_CORS_ORIGINS", "https://alt.example")
    assert Settings(_env_file=None).cors_origins == "https://alt.example"


def test_cors_preflight_echoes_supported_origins_and_rejects_others(client):
    for origin in ("http://localhost:3010", "http://127.0.0.1:3011"):
        response = client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,authorization",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
        assert response.headers["access-control-allow-credentials"] == "true"

    outside = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "https://outside.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert "access-control-allow-origin" not in outside.headers
    health = client.get("/api/v1/health")
    assert health.status_code == 200
