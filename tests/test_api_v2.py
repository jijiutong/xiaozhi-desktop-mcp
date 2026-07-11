from __future__ import annotations

import subprocess

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
    assert "next" in actions["music_control"]["param_schema"]["properties"]["command"]["enum"]


def test_api_v2_dispatch_adds_trace(settings):
    result = dispatch(settings, "config-summary", {}, "req-v2", "test-client")

    assert result["success"] is True
    assert result["api_version"] == "v2"
    assert result["trace"]["client"] == "test-client"
    assert result["trace"]["normalized_action"] == "config_summary"
    assert result["policy"]["default"] == "allow"


def test_api_v2_rejects_invalid_params_before_dispatch(settings):
    result = dispatch(settings, "browser_open", {"url": 123, "surprise": True}, "req-v2", "test-client")

    assert result["success"] is False
    assert result["error_code"] == "INVALID_PARAMS"
    assert result["data"]["validation_errors"]


def test_api_v2_rejects_missing_required_params(settings):
    result = dispatch(settings, "browser_open", {}, "req-v2", "test-client")

    assert result["success"] is False
    assert result["error_code"] == "INVALID_PARAMS"


def test_api_v2_rejects_values_outside_action_enum(settings):
    result = dispatch(settings, "music_control", {"command": "shuffle_everything"}, "req-v2", "test-client")

    assert result["success"] is False
    assert result["error_code"] == "INVALID_PARAMS"
    assert result["data"]["validation_errors"][0]["code"] == "enum"


def test_api_v2_maps_execution_failures_to_stable_error_codes(settings):
    result = dispatch(settings, "browser_open", {"url": "file:///etc/passwd"}, "req-v2", "test-client")

    assert result["success"] is False
    assert result["error_code"] == "POLICY_DENIED"


def test_api_v2_maps_accessibility_failures(settings, monkeypatch):
    def denied(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, "", "osascript is not allowed to send keystrokes. (1002)")

    monkeypatch.setattr(subprocess, "run", denied)
    planned = dispatch(
        settings,
        "music_search_app",
        {"query": "smoke", "app_name": "netease"},
        "permission-plan",
        "test-client",
    )
    action_id = planned["data"]["action"]["action_id"]

    result = dispatch(
        settings,
        "pending_confirm",
        {"action_id": action_id},
        "permission-confirm",
        "test-client",
    )

    assert result["success"] is False
    assert result["error_code"] == "PERMISSION_DENIED"


def test_api_v2_persists_redacted_audit_events(settings):
    dispatch(settings, "remember", {"text": "private note", "tags": "secret"}, "audit-1", "voice-client")

    result = dispatch(settings, "audit_list", {"limit": 10}, "audit-list", "admin-client")

    assert result["success"] is True
    event = next(item for item in result["data"]["events"] if item["request_id"] == "audit-1")
    assert event["action"] == "remember"
    assert event["client"] == "voice-client"
    assert event["param_keys"] == ["tags", "text"]
    assert "private note" not in str(event)


def test_api_v2_medium_action_cannot_bypass_pending_with_confirm(settings, monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch(settings, "app_close", {"app_name": "Obsidian", "confirm": True}, "risk-1", "voice-client")

    assert result["success"] is True
    assert result["data"]["action"]["status"] == "pending"
    assert calls == []


def test_http_api_v2_routes(settings, monkeypatch):
    monkeypatch.delenv("DESKTOP_MCP_AUTH_TOKEN", raising=False)
    monkeypatch.setattr("xiaozhi_desktop_mcp.http_server.settings", settings)
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
