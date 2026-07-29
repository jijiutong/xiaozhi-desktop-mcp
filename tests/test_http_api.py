from __future__ import annotations

from fastapi.testclient import TestClient

from xiaozhi_desktop_mcp.http_server import app


def test_http_exposes_versioned_apis_without_legacy_tools(monkeypatch):
    monkeypatch.delenv("DESKTOP_MCP_AUTH_TOKEN", raising=False)
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/actions").status_code == 200
    assert client.get("/api/v2/actions").status_code == 200
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


def test_http_token_scopes_restrict_dispatched_actions(monkeypatch):
    monkeypatch.setenv("DESKTOP_MCP_AUTH_TOKEN", "secret")
    monkeypatch.setenv("DESKTOP_MCP_AUTH_SCOPES", "desktop:control")
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}

    allowed = client.post(
        "/api/v2/dispatch",
        headers=headers,
        json={"action": "app_capabilities", "params": {"app_name": "Obsidian"}},
    )
    denied = client.post(
        "/api/v2/dispatch",
        headers=headers,
        json={"action": "config_summary", "params": {}},
    )

    assert allowed.status_code == 200
    assert allowed.json()["success"] is True
    assert denied.status_code == 403
    assert denied.json()["error_code"] == "SCOPE_DENIED"
    assert denied.json()["data"]["required_scope"] == "state:read"


def test_http_token_scopes_cannot_be_bypassed_through_composite_actions(monkeypatch):
    monkeypatch.setenv("DESKTOP_MCP_AUTH_TOKEN", "secret")
    monkeypatch.setenv("DESKTOP_MCP_AUTH_SCOPES", "desktop:control")
    client = TestClient(app)
    headers = {"Authorization": "Bearer secret"}

    intent = client.post(
        "/api/v2/dispatch",
        headers=headers,
        json={
            "action": "desktop_intent",
            "params": {"category": "desktop", "intent": "screenshot", "params": {}},
        },
    )
    workflow = client.post(
        "/api/v2/dispatch",
        headers=headers,
        json={
            "action": "workflow_plan",
            "params": {"steps": [{"action": "config_summary", "params": {}}]},
        },
    )

    assert intent.status_code == 403
    assert intent.json()["data"]["required_scope"] == "screen:read"
    assert workflow.status_code == 403
    assert workflow.json()["data"]["required_scope"] == "state:read"
