from __future__ import annotations

from fastapi.testclient import TestClient

from xiaozhi_desktop_mcp.api_v2 import actions_catalog, dispatch
from xiaozhi_desktop_mcp.http_server import app


def test_api_v2_actions_include_schema_and_policy():
    result = actions_catalog()

    actions = {action["name"]: action for action in result["actions"]}
    assert result["success"] is True
    assert result["version"] == "v2"
    assert actions["app_close"]["policy"]["default"] == "pending"
    assert actions["browser_open"]["param_schema"]["properties"]["url"]["type"] == "string"
    assert "url" in actions["browser_open"]["param_schema"]["required"]


def test_api_v2_dispatch_adds_trace(settings):
    result = dispatch(settings, "config-summary", {}, "req-v2", "test-client")

    assert result["success"] is True
    assert result["api_version"] == "v2"
    assert result["trace"]["client"] == "test-client"
    assert result["trace"]["normalized_action"] == "config_summary"
    assert result["policy"]["default"] == "allow"


def test_http_api_v2_routes(monkeypatch):
    monkeypatch.delenv("DESKTOP_MCP_AUTH_TOKEN", raising=False)
    client = TestClient(app)

    actions_response = client.get("/api/v2/actions")
    dispatch_response = client.post(
        "/api/v2/dispatch",
        json={"request_id": "req-v2", "action": "config_summary", "params": {}, "client": "pytest"},
    )

    assert actions_response.status_code == 200
    assert actions_response.json()["version"] == "v2"
    assert dispatch_response.status_code == 200
    assert dispatch_response.json()["api_version"] == "v2"
