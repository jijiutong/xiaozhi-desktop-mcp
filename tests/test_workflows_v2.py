from __future__ import annotations

import subprocess
import threading

from xiaozhi_desktop_mcp.api_v2 import dispatch


def test_workflow_plan_validates_without_executing(settings, monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch(
        settings,
        "workflow_plan",
        {"name": "research", "steps": [{"action": "browser_open", "params": {"url": "https://example.com"}}]},
        "workflow-plan",
        "test-client",
    )

    assert result["success"] is True
    assert result["data"]["workflow"]["status"] == "planned"
    assert calls == []


def test_workflow_cannot_embed_pending_confirmation(settings):
    result = dispatch(
        settings,
        "workflow_plan",
        {"steps": [{"action": "pending_confirm", "params": {"action_id": "existing-action"}}]},
        "workflow-plan",
        "test-client",
    )

    assert result["success"] is False
    assert "not allowed" in result["error"]


def test_workflow_executes_low_risk_steps(settings):
    planned = dispatch(
        settings,
        "workflow_plan",
        {
            "name": "inspect",
            "steps": [
                {"action": "config_summary", "params": {}},
                {"action": "audit_list", "params": {"limit": 5}},
            ],
        },
        "workflow-plan",
        "test-client",
    )
    workflow_id = planned["data"]["workflow"]["workflow_id"]

    result = dispatch(
        settings,
        "workflow_execute",
        {"workflow_id": workflow_id},
        "workflow-execute",
        "test-client",
    )

    assert result["success"] is True
    assert result["data"]["workflow"]["status"] == "completed"
    assert all(step["status"] == "completed" for step in result["data"]["workflow"]["steps"])


def test_workflow_pauses_for_pending_action(settings):
    planned = dispatch(
        settings,
        "workflow_plan",
        {
            "name": "close app safely",
            "steps": [
                {"action": "app_close", "params": {"app_name": "Obsidian"}},
                {"action": "config_summary", "params": {}},
            ],
        },
        "workflow-plan",
        "test-client",
    )
    workflow_id = planned["data"]["workflow"]["workflow_id"]

    result = dispatch(settings, "workflow_execute", {"workflow_id": workflow_id}, "workflow-execute", "test-client")

    assert result["success"] is True
    assert result["data"]["workflow"]["status"] == "waiting_confirmation"
    assert result["data"]["workflow"]["steps"][0]["pending_action_id"]


def test_workflow_resumes_after_pending_action_confirmation(settings, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, "", ""),
    )
    planned = dispatch(
        settings,
        "workflow_plan",
        {
            "steps": [
                {"action": "app_close", "params": {"app_name": "Obsidian"}},
                {"action": "config_summary", "params": {}},
            ]
        },
        "workflow-plan",
        "test-client",
    )
    workflow_id = planned["data"]["workflow"]["workflow_id"]
    waiting = dispatch(settings, "workflow_execute", {"workflow_id": workflow_id}, "execute-1", "test-client")
    pending_id = waiting["data"]["workflow"]["steps"][0]["pending_action_id"]

    confirmed = dispatch(settings, "pending_confirm", {"action_id": pending_id}, "confirm-1", "test-client")
    resumed = dispatch(settings, "workflow_execute", {"workflow_id": workflow_id}, "execute-2", "test-client")

    assert confirmed["success"] is True
    assert resumed["success"] is True
    assert resumed["data"]["workflow"]["status"] == "completed"


def test_workflow_cancel_stops_after_inflight_step(settings, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def slow_open(command, **_kwargs):
        started.set()
        release.wait(timeout=5)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", slow_open)
    planned = dispatch(
        settings,
        "workflow_plan",
        {
            "steps": [
                {"action": "browser_open", "params": {"url": "https://example.com"}},
                {"action": "remember", "params": {"text": "must not run"}},
            ]
        },
        "workflow-plan",
        "test-client",
    )
    workflow_id = planned["data"]["workflow"]["workflow_id"]
    execution_result = {}

    def execute():
        execution_result.update(
            dispatch(settings, "workflow_execute", {"workflow_id": workflow_id}, "execute", "test-client")
        )

    thread = threading.Thread(target=execute)
    thread.start()
    assert started.wait(timeout=5)
    cancelled = dispatch(settings, "workflow_cancel", {"workflow_id": workflow_id}, "cancel", "test-client")
    release.set()
    thread.join(timeout=5)
    current = dispatch(settings, "workflow_get", {"workflow_id": workflow_id}, "get", "test-client")

    assert cancelled["success"] is True
    assert current["data"]["workflow"]["status"] == "cancelled"
    assert current["data"]["workflow"]["steps"][1]["status"] == "planned"
    assert execution_result["success"] is False
