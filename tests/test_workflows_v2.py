from __future__ import annotations

import json
import sqlite3
import subprocess
import threading
from datetime import datetime, timedelta, timezone

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


def test_workflow_retries_a_failed_low_risk_step_within_its_budget(settings, monkeypatch):
    attempts = 0

    def flaky_status(command, **_kwargs):
        nonlocal attempts
        attempts += 1
        return subprocess.CompletedProcess(
            command,
            1 if attempts == 1 else 0,
            "" if attempts == 1 else "true",
            "temporary failure" if attempts == 1 else "",
        )

    monkeypatch.setattr(subprocess, "run", flaky_status)
    planned = dispatch(
        settings,
        "workflow_plan",
        {
            "steps": [
                {
                    "action": "app_status",
                    "params": {"app_name": "Obsidian"},
                    "retry": {"max_attempts": 2},
                }
            ]
        },
        "workflow-plan",
        "test-client",
    )

    result = dispatch(
        settings,
        "workflow_execute",
        {"workflow_id": planned["data"]["workflow"]["workflow_id"]},
        "workflow-execute",
        "test-client",
    )

    assert result["success"] is True
    step = result["data"]["workflow"]["steps"][0]
    assert step["status"] == "completed"
    assert step["attempts"] == 2
    assert attempts == 2


def test_workflow_rejects_retry_for_a_low_risk_write(settings):
    result = dispatch(
        settings,
        "workflow_plan",
        {
            "steps": [
                {
                    "action": "remember",
                    "params": {"text": "do not duplicate"},
                    "retry": {"max_attempts": 2},
                }
            ]
        },
        "workflow-plan",
        "test-client",
    )

    assert result["success"] is False
    assert "read-only" in result["error"]


def test_workflow_rejects_wait_with_a_low_risk_write(settings):
    result = dispatch(
        settings,
        "workflow_plan",
        {
            "steps": [
                {
                    "kind": "wait",
                    "action": "remember",
                    "params": {"text": "do not poll writes"},
                    "until": {"field": "data.success", "equals": True},
                }
            ]
        },
        "workflow-plan",
        "test-client",
    )

    assert result["success"] is False
    assert "read-only" in result["error"]


def test_workflow_runs_a_declared_safe_compensation_after_failure(settings):
    planned = dispatch(
        settings,
        "workflow_plan",
        {
            "steps": [
                {
                    "action": "browser_open",
                    "params": {"url": "file:///etc/passwd"},
                    "compensation": {"action": "config_summary", "params": {}},
                }
            ]
        },
        "workflow-plan",
        "test-client",
    )

    result = dispatch(
        settings,
        "workflow_execute",
        {"workflow_id": planned["data"]["workflow"]["workflow_id"]},
        "workflow-execute",
        "test-client",
    )

    assert result["success"] is False
    step = result["data"]["workflow"]["steps"][0]
    assert step["status"] == "failed"
    assert step["compensation"]["status"] == "completed"
    assert step["compensation"]["result"]["success"] is True


def test_workflow_waits_until_a_read_only_condition_is_satisfied(settings, monkeypatch):
    attempts = 0

    def app_becomes_ready(command, **_kwargs):
        nonlocal attempts
        attempts += 1
        return subprocess.CompletedProcess(command, 0, "true" if attempts == 2 else "false", "")

    monkeypatch.setattr(subprocess, "run", app_becomes_ready)
    planned = dispatch(
        settings,
        "workflow_plan",
        {
            "steps": [
                {
                    "kind": "wait",
                    "action": "app_status",
                    "params": {"app_name": "Obsidian"},
                    "until": {"field": "data.running", "equals": True},
                    "max_attempts": 3,
                    "interval_ms": 0,
                }
            ]
        },
        "workflow-plan",
        "test-client",
    )

    waiting = dispatch(
        settings,
        "workflow_execute",
        {"workflow_id": planned["data"]["workflow"]["workflow_id"]},
        "workflow-wait",
        "test-client",
    )
    result = dispatch(
        settings,
        "workflow_execute",
        {"workflow_id": planned["data"]["workflow"]["workflow_id"]},
        "workflow-resume",
        "test-client",
    )

    assert waiting["success"] is True
    assert waiting["data"]["workflow"]["status"] == "waiting_condition"
    assert result["success"] is True
    step = result["data"]["workflow"]["steps"][0]
    assert step["kind"] == "wait"
    assert step["attempts"] == 2
    assert step["status"] == "completed"


def test_workflow_condition_selects_a_validated_branch_from_a_previous_result(settings):
    planned = dispatch(
        settings,
        "workflow_plan",
        {
            "steps": [
                {"action": "config_summary", "params": {}},
                {
                    "kind": "condition",
                    "if": {"step": 0, "field": "result.success", "equals": True},
                    "then": {"action": "config_summary", "params": {}},
                    "else": {"action": "browser_open", "params": {"url": "file:///etc/passwd"}},
                },
            ]
        },
        "workflow-plan",
        "test-client",
    )

    result = dispatch(
        settings,
        "workflow_execute",
        {"workflow_id": planned["data"]["workflow"]["workflow_id"]},
        "workflow-execute",
        "test-client",
    )

    assert result["success"] is True
    condition = result["data"]["workflow"]["steps"][1]
    assert condition["kind"] == "condition"
    assert condition["selected_branch"] == "then"
    assert condition["status"] == "completed"


def test_workflow_get_returns_redacted_execution_events(settings):
    planned = dispatch(
        settings,
        "workflow_plan",
        {"name": "evented", "steps": [{"action": "config_summary", "params": {}}]},
        "workflow-plan",
        "test-client",
    )
    workflow_id = planned["data"]["workflow"]["workflow_id"]
    dispatch(settings, "workflow_execute", {"workflow_id": workflow_id}, "workflow-execute", "test-client")

    result = dispatch(settings, "workflow_get", {"workflow_id": workflow_id}, "workflow-get", "test-client")

    event_types = [event["event_type"] for event in result["data"]["events"]]
    assert event_types == ["planned", "started", "step_completed", "completed"]
    assert "params" not in str(result["data"]["events"])


def test_workflow_recovers_a_stale_read_only_step(settings):
    planned = dispatch(
        settings,
        "workflow_plan",
        {"name": "recover read", "steps": [{"action": "config_summary", "params": {}}]},
        "workflow-plan",
        "test-client",
    )
    workflow_id = planned["data"]["workflow"]["workflow_id"]
    steps = planned["data"]["workflow"]["steps"]
    steps[0]["status"] = "running"
    stale_at = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    with sqlite3.connect(settings.state_db_path) as connection:
        connection.execute(
            """
            UPDATE workflows
            SET status = 'running', steps = ?, updated_at = ?,
                run_token = 'dead-run', lease_expires_at = ?
            WHERE workflow_id = ?
            """,
            (json.dumps(steps), stale_at, stale_at, workflow_id),
        )

    result = dispatch(settings, "workflow_execute", {"workflow_id": workflow_id}, "recover", "test-client")
    current = dispatch(settings, "workflow_get", {"workflow_id": workflow_id}, "get", "test-client")

    assert result["success"] is True
    assert result["data"]["workflow"]["status"] == "completed"
    assert "recovered" in [event["event_type"] for event in current["data"]["events"]]


def test_workflow_fails_closed_when_a_stale_write_step_has_unknown_outcome(settings, monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    planned = dispatch(
        settings,
        "workflow_plan",
        {"name": "do not replay", "steps": [{"action": "browser_open", "params": {"url": "https://example.com"}}]},
        "workflow-plan",
        "test-client",
    )
    workflow_id = planned["data"]["workflow"]["workflow_id"]
    steps = planned["data"]["workflow"]["steps"]
    steps[0]["status"] = "running"
    stale_at = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    with sqlite3.connect(settings.state_db_path) as connection:
        connection.execute(
            """
            UPDATE workflows
            SET status = 'running', steps = ?, updated_at = ?,
                run_token = 'dead-run', lease_expires_at = ?
            WHERE workflow_id = ?
            """,
            (json.dumps(steps), stale_at, stale_at, workflow_id),
        )

    result = dispatch(settings, "workflow_execute", {"workflow_id": workflow_id}, "recover", "test-client")
    current = dispatch(settings, "workflow_get", {"workflow_id": workflow_id}, "get", "test-client")

    assert result["success"] is False
    assert result["error_code"] == "RECOVERY_REQUIRED"
    assert current["data"]["workflow"]["status"] == "failed"
    assert "recovery_blocked" in [event["event_type"] for event in current["data"]["events"]]
    assert calls == []
