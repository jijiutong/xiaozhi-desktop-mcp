from __future__ import annotations

from fastapi.testclient import TestClient

from xiaozhi_desktop_mcp.http_server import app


def test_http_exposes_api_v1_only(monkeypatch):
    monkeypatch.delenv("DESKTOP_MCP_AUTH_TOKEN", raising=False)
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/actions").status_code == 200
    assert client.post("/tools/desktop/ask-cc", json={}).status_code == 404


def test_http_api_requires_token_when_configured(monkeypatch):
    monkeypatch.setenv("DESKTOP_MCP_AUTH_TOKEN", "secret")
    client = TestClient(app)

    response = client.get("/api/v1/actions")

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert response.headers["x-request-id"]


def test_http_api_accepts_bearer_token(monkeypatch):
    monkeypatch.setenv("DESKTOP_MCP_AUTH_TOKEN", "secret")
    client = TestClient(app)

    response = client.get("/api/v1/actions", headers={"Authorization": "Bearer secret", "X-Request-Id": "req-1"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-1"


def test_http_api_accepts_desktop_token_header(monkeypatch):
    monkeypatch.setenv("DESKTOP_MCP_AUTH_TOKEN", "secret")
    client = TestClient(app)

    response = client.get("/api/v1/actions", headers={"X-Desktop-Mcp-Token": "secret"})

    assert response.status_code == 200
