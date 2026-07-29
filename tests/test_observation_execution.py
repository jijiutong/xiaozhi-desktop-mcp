from __future__ import annotations

import json
import sqlite3
import subprocess
import threading
from datetime import datetime, timedelta, timezone

from xiaozhi_desktop_mcp.api_v2 import dispatch
from xiaozhi_desktop_mcp.execution import _verify


def test_client_can_create_a_bounded_desktop_observation(settings, monkeypatch):
    def fake_run(command, **_kwargs):
        payload = (
            '{"process_name":"Google Chrome",'
            '"window":{"title":"Example","bounds":{"x":10,"y":20,"width":800,"height":600}},'
            '"elements":[{"element_id":"ax:1","role":"AXButton","title":"保存",'
            '"enabled":true,"value":"private input","actions":["AXPress"],'
            '"bounds":{"x":20,"y":40,"width":80,"height":30}}],'
            '"truncated":false}'
        )
        return subprocess.CompletedProcess(command, 0, payload, "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch(
        settings,
        "desktop_observe",
        {"app_name": "chrome", "window_index": 1},
        "observe-1",
        "test-client",
    )

    assert result["success"] is True
    assert result["data"]["observation_id"].startswith("obs_")
    assert result["data"]["app"] == "Google Chrome"
    assert result["data"]["window"]["title"] == "Example"
    assert result["data"]["tree_fingerprint"].startswith("sha256:")
    assert result["data"]["identity_strength"] in {"strong", "weak"}
    assert result["data"]["elements"][0]["element_id"] == "ax:1"
    assert "private input" not in str(result)
    assert result["data"]["expires_at"] > result["data"]["captured_at"]


def test_creating_an_observation_prunes_expired_records(settings, monkeypatch):
    def fake_run(command, **_kwargs):
        payload = {
            "process_name": "Google Chrome",
            "window": {"title": "Example"},
            "elements": [],
            "truncated": False,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    dispatch(settings, "desktop_observe", {"app_name": "chrome"}, "first", "test-client")
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with sqlite3.connect(settings.state_db_path) as connection:
        connection.execute("UPDATE observations SET expires_at = ?", (expired_at,))

    dispatch(settings, "desktop_observe", {"app_name": "chrome"}, "second", "test-client")

    with sqlite3.connect(settings.state_db_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    assert count == 1


def test_confirmed_desktop_step_executes_once_and_verifies_the_result(settings, monkeypatch):
    tree_reads = 0
    actions = 0

    def fake_run(command, **_kwargs):
        nonlocal tree_reads, actions
        request = json.loads(command[-1])
        if request["command"] == "action":
            actions += 1
            return subprocess.CompletedProcess(
                command,
                0,
                '{"command":"click","element_id":"ax:1","performed":true}',
                "",
            )
        tree_reads += 1
        elements = (
            [{"element_id": "ax:1", "role": "AXButton", "title": "保存", "enabled": True}]
            if tree_reads < 3
            else []
        )
        payload = {
            "process_name": "Google Chrome",
            "window": {"title": "Example"},
            "elements": elements,
            "truncated": False,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload, ensure_ascii=False), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    observed = dispatch(settings, "desktop_observe", {"app_name": "chrome"}, "observe", "test-client")

    pending = dispatch(
        settings,
        "desktop_execute_step",
        {
            "observation_id": observed["data"]["observation_id"],
            "target": {"element_id": "ax:1"},
            "action": {"command": "click"},
            "expectation": {"kind": "element_absent"},
            "idempotency_key": "save-example-once",
        },
        "step",
        "test-client",
    )

    assert pending["success"] is True
    assert pending["data"]["action"]["status"] == "pending"

    confirmed = dispatch(
        settings,
        "pending_confirm",
        {"action_id": pending["data"]["action"]["action_id"]},
        "confirm",
        "test-client",
    )

    assert confirmed["success"] is True
    execution = confirmed["data"]["execution_result"]
    assert execution["verified"] is True
    assert execution["verification"]["kind"] == "element_absent"
    assert execution["after_observation_id"].startswith("obs_")
    assert actions == 1


def test_desktop_step_fails_closed_when_the_observed_target_has_changed(settings, monkeypatch):
    tree_reads = 0
    actions = 0

    def fake_run(command, **_kwargs):
        nonlocal tree_reads, actions
        request = json.loads(command[-1])
        if request["command"] == "action":
            actions += 1
            return subprocess.CompletedProcess(command, 0, '{"performed":true}', "")
        tree_reads += 1
        title = "保存" if tree_reads == 1 else "删除账户"
        payload = {
            "process_name": "Google Chrome",
            "window": {"title": "Example"},
            "elements": [{"element_id": "ax:1", "role": "AXButton", "title": title, "enabled": True}],
            "truncated": False,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload, ensure_ascii=False), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    observed = dispatch(settings, "desktop_observe", {"app_name": "chrome"}, "observe", "test-client")
    pending = dispatch(
        settings,
        "desktop_execute_step",
        {
            "observation_id": observed["data"]["observation_id"],
            "target": {"element_id": "ax:1"},
            "action": {"command": "click"},
        },
        "step",
        "test-client",
    )

    confirmed = dispatch(
        settings,
        "pending_confirm",
        {"action_id": pending["data"]["action"]["action_id"]},
        "confirm",
        "test-client",
    )

    assert confirmed["success"] is False
    assert confirmed["error_code"] == "TARGET_STALE"
    assert actions == 0


def test_idempotency_key_prevents_a_duplicate_desktop_action(settings, monkeypatch):
    actions = 0

    def fake_run(command, **_kwargs):
        nonlocal actions
        request = json.loads(command[-1])
        if request["command"] == "action":
            actions += 1
            return subprocess.CompletedProcess(command, 0, '{"performed":true}', "")
        payload = {
            "process_name": "Google Chrome",
            "window": {"title": "Example"},
            "elements": [{"element_id": "ax:1", "role": "AXButton", "title": "保存", "enabled": True}],
            "truncated": False,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload, ensure_ascii=False), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    observed = dispatch(settings, "desktop_observe", {"app_name": "chrome"}, "observe", "test-client")
    params = {
        "observation_id": observed["data"]["observation_id"],
        "target": {"element_id": "ax:1"},
        "action": {"command": "click"},
        "expectation": {"kind": "element_present"},
        "idempotency_key": "same-click",
    }

    for index in range(2):
        pending = dispatch(settings, "desktop_execute_step", params, f"step-{index}", "test-client")
        confirmed = dispatch(
            settings,
            "pending_confirm",
            {"action_id": pending["data"]["action"]["action_id"]},
            f"confirm-{index}",
            "test-client",
        )
        assert confirmed["success"] is True

    assert actions == 1


def test_execute_step_rejects_an_empty_target_before_creating_a_pending_action(settings):
    result = dispatch(
        settings,
        "desktop_execute_step",
        {
            "observation_id": "obs_missing",
            "target": {},
            "action": {"command": "click"},
            "expectation": {"kind": "anything"},
        },
        "invalid-step",
        "test-client",
    )

    assert result["success"] is False
    assert result["error_code"] == "INVALID_PARAMS"
    fields = {error["field"] for error in result["data"]["validation_errors"]}
    assert "target.element_id" in fields
    assert "expectation.kind" in fields


def test_desktop_step_checks_preconditions_before_acting(settings, monkeypatch):
    tree_reads = 0
    actions = 0

    def fake_run(command, **_kwargs):
        nonlocal tree_reads, actions
        request = json.loads(command[-1])
        if request["command"] == "action":
            actions += 1
            return subprocess.CompletedProcess(command, 0, '{"performed":true}', "")
        tree_reads += 1
        payload = {
            "process_name": "Google Chrome",
            "window": {"title": "Example"},
            "elements": [
                {
                    "element_id": "ax:1",
                    "role": "AXButton",
                    "title": "保存",
                    "enabled": tree_reads == 1,
                }
            ],
            "truncated": False,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload, ensure_ascii=False), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    observed = dispatch(settings, "desktop_observe", {"app_name": "chrome"}, "observe", "test-client")
    pending = dispatch(
        settings,
        "desktop_execute_step",
        {
            "observation_id": observed["data"]["observation_id"],
            "target": {"element_id": "ax:1"},
            "preconditions": {"enabled": True},
            "action": {"command": "click"},
        },
        "step",
        "test-client",
    )
    confirmed = dispatch(
        settings,
        "pending_confirm",
        {"action_id": pending["data"]["action"]["action_id"]},
        "confirm",
        "test-client",
    )

    assert confirmed["success"] is False
    assert confirmed["error_code"] == "PRECONDITION_FAILED"
    assert actions == 0


def test_desktop_step_rejects_a_changed_window_before_acting(settings, monkeypatch):
    tree_reads = 0
    actions = 0

    def fake_run(command, **_kwargs):
        nonlocal tree_reads, actions
        request = json.loads(command[-1])
        if request["command"] == "action":
            actions += 1
            return subprocess.CompletedProcess(command, 0, '{"performed":true}', "")
        tree_reads += 1
        payload = {
            "process_name": "Google Chrome",
            "window": {"title": "Example" if tree_reads == 1 else "Account deletion"},
            "elements": [{"element_id": "ax:1", "role": "AXButton", "title": "保存", "enabled": True}],
            "truncated": False,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload, ensure_ascii=False), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    observed = dispatch(settings, "desktop_observe", {"app_name": "chrome"}, "observe", "test-client")
    pending = dispatch(
        settings,
        "desktop_execute_step",
        {
            "observation_id": observed["data"]["observation_id"],
            "target": {"element_id": "ax:1"},
            "action": {"command": "click"},
        },
        "step",
        "test-client",
    )
    confirmed = dispatch(
        settings,
        "pending_confirm",
        {"action_id": pending["data"]["action"]["action_id"]},
        "confirm",
        "test-client",
    )

    assert confirmed["success"] is False
    assert confirmed["error_code"] == "WINDOW_CHANGED"
    assert actions == 0


def test_desktop_step_rejects_a_weak_window_identity_with_changed_bounds(settings, monkeypatch):
    tree_reads = 0
    actions = 0

    def fake_run(command, **_kwargs):
        nonlocal tree_reads, actions
        request = json.loads(command[-1])
        if request["command"] == "action":
            actions += 1
            return subprocess.CompletedProcess(command, 0, '{"performed":true}', "")
        tree_reads += 1
        payload = {
            "process_name": "Google Chrome",
            "window": {
                "title": "Example",
                "bounds": {"x": 0 if tree_reads == 1 else 100, "y": 0, "width": 800, "height": 600},
            },
            "elements": [{"element_id": "ax:1", "role": "AXButton", "title": "保存", "enabled": True}],
            "truncated": False,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload, ensure_ascii=False), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    observed = dispatch(settings, "desktop_observe", {"app_name": "chrome"}, "observe", "test-client")
    pending = dispatch(
        settings,
        "desktop_execute_step",
        {
            "observation_id": observed["data"]["observation_id"],
            "target": {"element_id": "ax:1"},
            "action": {"command": "click"},
        },
        "step",
        "test-client",
    )

    confirmed = dispatch(
        settings,
        "pending_confirm",
        {"action_id": pending["data"]["action"]["action_id"]},
        "confirm",
        "test-client",
    )

    assert confirmed["success"] is False
    assert confirmed["error_code"] == "WINDOW_CHANGED"
    assert actions == 0


def test_desktop_drag_revalidates_the_secondary_target(settings, monkeypatch):
    tree_reads = 0
    actions = 0

    def fake_run(command, **_kwargs):
        nonlocal tree_reads, actions
        request = json.loads(command[-1])
        if request["command"] == "action":
            actions += 1
            return subprocess.CompletedProcess(command, 0, '{"performed":true}', "")
        tree_reads += 1
        payload = {
            "process_name": "Google Chrome",
            "window": {"title": "Example"},
            "elements": [
                {"element_id": "ax:1", "role": "AXButton", "title": "Source", "enabled": True},
                {
                    "element_id": "ax:2",
                    "role": "AXButton",
                    "title": "Destination" if tree_reads == 1 else "Delete account",
                    "enabled": True,
                },
            ],
            "truncated": False,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    observed = dispatch(settings, "desktop_observe", {"app_name": "chrome"}, "observe", "test-client")
    pending = dispatch(
        settings,
        "desktop_execute_step",
        {
            "observation_id": observed["data"]["observation_id"],
            "target": {"element_id": "ax:1"},
            "action": {"command": "drag", "target_element_id": "ax:2"},
        },
        "step",
        "test-client",
    )

    confirmed = dispatch(
        settings,
        "pending_confirm",
        {"action_id": pending["data"]["action"]["action_id"]},
        "confirm",
        "test-client",
    )

    assert confirmed["success"] is False
    assert confirmed["error_code"] == "TARGET_STALE"
    assert actions == 0


def test_desktop_step_fails_closed_if_verification_moves_to_another_window(settings, monkeypatch):
    tree_reads = 0
    actions = 0

    def fake_run(command, **_kwargs):
        nonlocal tree_reads, actions
        request = json.loads(command[-1])
        if request["command"] == "action":
            actions += 1
            return subprocess.CompletedProcess(command, 0, '{"performed":true}', "")
        tree_reads += 1
        payload = {
            "process_name": "Google Chrome",
            "window": {"title": "Example" if tree_reads < 3 else "Different window"},
            "elements": [{"element_id": "ax:1", "role": "AXButton", "title": "Save", "enabled": True}],
            "truncated": False,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    observed = dispatch(settings, "desktop_observe", {"app_name": "chrome"}, "observe", "test-client")
    pending = dispatch(
        settings,
        "desktop_execute_step",
        {
            "observation_id": observed["data"]["observation_id"],
            "target": {"element_id": "ax:1"},
            "action": {"command": "click"},
            "expectation": {"kind": "tree_changed"},
        },
        "step",
        "test-client",
    )

    confirmed = dispatch(
        settings,
        "pending_confirm",
        {"action_id": pending["data"]["action"]["action_id"]},
        "confirm",
        "test-client",
    )

    assert confirmed["success"] is False
    assert confirmed["error_code"] == "RECOVERY_REQUIRED"
    assert actions == 1


def test_disabled_expectation_requires_an_explicit_enabled_state():
    result = _verify(
        {"kind": "element_disabled"},
        {"tree_fingerprint": "before"},
        {
            "tree_fingerprint": "after",
            "elements": [{"element_id": "ax:1", "role": "AXButton", "title": "Save"}],
        },
        {"element_id": "ax:1", "role": "AXButton", "title": "Save"},
    )

    assert result["satisfied"] is False


def test_desktop_step_waits_for_the_post_action_expectation(settings, monkeypatch):
    tree_reads = 0

    def fake_run(command, **_kwargs):
        nonlocal tree_reads
        request = json.loads(command[-1])
        if request["command"] == "action":
            return subprocess.CompletedProcess(command, 0, '{"performed":true}', "")
        tree_reads += 1
        elements = (
            [{"element_id": "ax:1", "role": "AXButton", "title": "保存", "enabled": True}]
            if tree_reads < 4
            else []
        )
        payload = {
            "process_name": "Google Chrome",
            "window": {"title": "Example"},
            "elements": elements,
            "truncated": False,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload, ensure_ascii=False), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    observed = dispatch(settings, "desktop_observe", {"app_name": "chrome"}, "observe", "test-client")
    pending = dispatch(
        settings,
        "desktop_execute_step",
        {
            "observation_id": observed["data"]["observation_id"],
            "target": {"element_id": "ax:1"},
            "action": {"command": "click"},
            "expectation": {"kind": "element_absent"},
            "timeout_ms": 1000,
        },
        "step",
        "test-client",
    )
    confirmed = dispatch(
        settings,
        "pending_confirm",
        {"action_id": pending["data"]["action"]["action_id"]},
        "confirm",
        "test-client",
    )

    assert confirmed["success"] is True
    assert confirmed["data"]["execution_result"]["verified"] is True
    assert tree_reads == 4


def test_desktop_step_rejects_an_ambiguous_semantic_target(settings, monkeypatch):
    tree_reads = 0
    actions = 0

    def fake_run(command, **_kwargs):
        nonlocal tree_reads, actions
        request = json.loads(command[-1])
        if request["command"] == "action":
            actions += 1
            return subprocess.CompletedProcess(command, 0, '{"performed":true}', "")
        tree_reads += 1
        elements = [{"element_id": "ax:1", "role": "AXButton", "title": "保存", "enabled": True}]
        if tree_reads > 1:
            elements.append({"element_id": "ax:2", "role": "AXButton", "title": "保存", "enabled": True})
        payload = {
            "process_name": "Google Chrome",
            "window": {"title": "Example"},
            "elements": elements,
            "truncated": False,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload, ensure_ascii=False), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    observed = dispatch(settings, "desktop_observe", {"app_name": "chrome"}, "observe", "test-client")
    pending = dispatch(
        settings,
        "desktop_execute_step",
        {
            "observation_id": observed["data"]["observation_id"],
            "target": {"element_id": "ax:1"},
            "action": {"command": "click"},
        },
        "step",
        "test-client",
    )
    confirmed = dispatch(
        settings,
        "pending_confirm",
        {"action_id": pending["data"]["action"]["action_id"]},
        "confirm",
        "test-client",
    )

    assert confirmed["success"] is False
    assert confirmed["error_code"] == "TARGET_AMBIGUOUS"
    assert actions == 0


def test_concurrent_idempotent_desktop_steps_never_duplicate_the_action(settings, monkeypatch):
    action_started = threading.Event()
    release_action = threading.Event()
    actions = 0

    def fake_run(command, **_kwargs):
        nonlocal actions
        request = json.loads(command[-1])
        if request["command"] == "action":
            actions += 1
            action_started.set()
            release_action.wait(timeout=5)
            return subprocess.CompletedProcess(command, 0, '{"performed":true}', "")
        payload = {
            "process_name": "Google Chrome",
            "window": {"title": "Example"},
            "elements": [{"element_id": "ax:1", "role": "AXButton", "title": "保存", "enabled": True}],
            "truncated": False,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload, ensure_ascii=False), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    observed = dispatch(settings, "desktop_observe", {"app_name": "chrome"}, "observe", "test-client")
    params = {
        "observation_id": observed["data"]["observation_id"],
        "target": {"element_id": "ax:1"},
        "action": {"command": "click"},
        "expectation": {"kind": "element_present"},
        "idempotency_key": "concurrent-click",
    }
    pending = [
        dispatch(settings, "desktop_execute_step", params, f"step-{index}", "test-client")
        for index in range(2)
    ]
    first_result: dict = {}

    def confirm_first():
        first_result.update(
            dispatch(
                settings,
                "pending_confirm",
                {"action_id": pending[0]["data"]["action"]["action_id"]},
                "confirm-first",
                "test-client",
            )
        )

    thread = threading.Thread(target=confirm_first)
    thread.start()
    assert action_started.wait(timeout=5)
    second = dispatch(
        settings,
        "pending_confirm",
        {"action_id": pending[1]["data"]["action"]["action_id"]},
        "confirm-second",
        "test-client",
    )
    release_action.set()
    thread.join(timeout=5)

    assert first_result["success"] is True
    assert second["success"] is False
    assert second["error_code"] == "RECOVERY_REQUIRED"
    assert actions == 1
