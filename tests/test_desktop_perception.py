from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from xiaozhi_desktop_mcp.api_v2 import dispatch


def test_llm_can_capture_a_display_as_image_data(settings, monkeypatch):
    def fake_run(command, **_kwargs):
        if command[0] == "/usr/sbin/screencapture":
            Path(command[-1]).write_bytes(b"\x89PNG\r\n\x1a\nimage")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch(
        settings,
        "desktop_screenshot",
        {"display_id": 1, "max_width": 0},
        "capture-1",
        "test",
    )

    assert result["success"] is True
    assert result["data"]["media_type"] == "image/png"
    assert result["data"]["image_base64"] == "iVBORw0KGgppbWFnZQ=="
    assert result["data"]["display_id"] == 1


def test_display_capture_resizes_large_images_before_returning_them(settings, monkeypatch):
    def fake_run(command, **_kwargs):
        image_path = Path(command[-1])
        if command[0] == "/usr/sbin/screencapture":
            image_path.write_bytes(b"original-image")
        elif command[0] == "/usr/bin/sips":
            image_path.write_bytes(b"resized-image")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch(
        settings,
        "desktop_screenshot",
        {"display_id": 1, "max_width": 800},
        "capture-resized",
        "test",
    )

    assert result["success"] is True
    assert result["data"]["image_base64"] == "cmVzaXplZC1pbWFnZQ=="


def test_display_capture_reports_a_stable_timeout_error(settings, monkeypatch):
    def timeout(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, 20)

    monkeypatch.setattr(subprocess, "run", timeout)

    result = dispatch(
        settings,
        "desktop_screenshot",
        {"display_id": 1},
        "capture-timeout",
        "test",
    )

    assert result["success"] is False
    assert result["error_code"] == "TIMEOUT"


def test_llm_can_capture_an_allowlisted_app_window(settings, monkeypatch):
    def fake_run(command, **_kwargs):
        if command[0] == "/usr/bin/osascript":
            return subprocess.CompletedProcess(command, 0, "100\t200\t800\t600\tGoogle Chrome\n", "")
        if command[0] == "/usr/sbin/screencapture":
            Path(command[-1]).write_bytes(b"\x89PNG\r\n\x1a\nwindow")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch(
        settings,
        "desktop_window_screenshot",
        {"app_name": "chrome", "window_index": 1, "max_width": 0},
        "capture-window-1",
        "test",
    )

    assert result["success"] is True
    assert result["data"]["source"] == "window"
    assert result["data"]["app"] == "Google Chrome"
    assert result["data"]["bounds"] == {"x": 100, "y": 200, "width": 800, "height": 600}
    assert result["data"]["image_base64"] == "iVBORw0KGgp3aW5kb3c="


def test_llm_can_ocr_a_display_with_structured_text_blocks(settings, monkeypatch):
    def fake_run(command, **_kwargs):
        if command[0] == "/usr/sbin/screencapture":
            Path(command[-1]).write_bytes(b"\x89PNG\r\n\x1a\nocr")
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[0] == "/usr/bin/swift":
            output = (
                '{"text":"保存 文件","blocks":['
                '{"text":"保存","confidence":0.98,"bounds":{"x":0.1,"y":0.2,"width":0.2,"height":0.1}},'
                '{"text":"文件","confidence":0.95,"bounds":{"x":0.4,"y":0.2,"width":0.2,"height":0.1}}]}'
            )
            return subprocess.CompletedProcess(command, 0, output, "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch(
        settings,
        "desktop_ocr",
        {"source": "display", "display_id": 1, "languages": "zh-Hans,en-US"},
        "ocr-1",
        "test",
    )

    assert result["success"] is True
    assert result["data"]["text"] == "保存 文件"
    assert result["data"]["count"] == 2
    assert result["data"]["blocks"][0]["confidence"] == 0.98


def test_llm_can_read_an_allowlisted_app_accessibility_tree(settings, monkeypatch):
    def fake_run(command, **_kwargs):
        payload = (
            '{"process_name":"Google Chrome","window":{"title":"Example"},'
            '"elements":[{"element_id":"ax:1","role":"AXButton","title":"保存",'
            '"description":"保存文件","enabled":true,"selected":false,'
            '"actions":["AXPress"],"bounds":{"x":20,"y":40,"width":80,"height":30}}],'
            '"count":1,"truncated":false}'
        )
        return subprocess.CompletedProcess(command, 0, payload, "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch(
        settings,
        "accessibility_tree",
        {"app_name": "chrome", "window_index": 1, "max_depth": 5, "max_elements": 100},
        "ax-tree-1",
        "test",
    )

    assert result["success"] is True
    assert result["data"]["app"] == "Google Chrome"
    assert result["data"]["elements"][0]["element_id"] == "ax:1"
    assert result["data"]["elements"][0]["role"] == "AXButton"
    assert result["data"]["elements"][0]["actions"] == ["AXPress"]


def test_clicking_an_accessibility_element_requires_separate_confirmation(settings, monkeypatch):
    def fake_run(command, **_kwargs):
        payload = '{"command":"click","element_id":"ax:1","performed":true,"role":"AXButton","title":"保存"}'
        return subprocess.CompletedProcess(command, 0, payload, "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    pending = dispatch(
        settings,
        "accessibility_action",
        {"app_name": "chrome", "command": "click", "element_id": "ax:1"},
        "ax-click-1",
        "test",
    )

    assert pending["success"] is True
    assert pending["data"]["action"]["status"] == "pending"

    confirmed = dispatch(
        settings,
        "pending_confirm",
        {"action_id": pending["data"]["action"]["action_id"]},
        "ax-click-confirm-1",
        "test",
    )

    assert confirmed["success"] is True
    assert confirmed["data"]["execution_result"]["command"] == "click"
    assert confirmed["data"]["execution_result"]["performed"] is True


def test_text_input_requires_a_specific_accessibility_element(settings, monkeypatch):
    def should_not_run(*_args, **_kwargs):
        raise AssertionError("invalid input must be rejected before macOS automation")

    monkeypatch.setattr(subprocess, "run", should_not_run)
    pending = dispatch(
        settings,
        "accessibility_action",
        {"app_name": "chrome", "command": "input", "text": "hello"},
        "ax-input-invalid",
        "test",
    )

    assert pending["success"] is False
    assert "element_id is required for input" in pending["error"]


def test_scroll_rejects_unknown_direction_before_macos_automation(settings, monkeypatch):
    def should_not_run(*_args, **_kwargs):
        raise AssertionError("invalid scroll must be rejected before macOS automation")

    monkeypatch.setattr(subprocess, "run", should_not_run)
    pending = dispatch(
        settings,
        "accessibility_action",
        {"app_name": "chrome", "command": "scroll", "direction": "diagonal", "amount": 2},
        "ax-scroll-invalid",
        "test",
    )

    assert pending["success"] is False
    assert pending["error_code"] == "INVALID_PARAMS"


def test_scroll_amount_is_bounded_after_confirmation(settings, monkeypatch):
    def should_not_run(*_args, **_kwargs):
        raise AssertionError("oversized scroll must be rejected before macOS automation")

    monkeypatch.setattr(subprocess, "run", should_not_run)
    pending = dispatch(
        settings,
        "accessibility_action",
        {"app_name": "chrome", "command": "scroll", "direction": "down", "amount": 100},
        "ax-scroll-large",
        "test",
    )

    assert pending["success"] is False
    assert "amount must be between 1 and 20" in pending["error"]


def test_drag_requires_a_target_accessibility_element(settings, monkeypatch):
    def should_not_run(*_args, **_kwargs):
        raise AssertionError("incomplete drag must be rejected before macOS automation")

    monkeypatch.setattr(subprocess, "run", should_not_run)
    pending = dispatch(
        settings,
        "accessibility_action",
        {"app_name": "chrome", "command": "drag", "element_id": "ax:1"},
        "ax-drag-invalid",
        "test",
    )

    assert pending["success"] is False
    assert "target_element_id is required for drag" in pending["error"]


def test_file_dialog_rejects_paths_outside_safe_roots(settings, monkeypatch):
    def should_not_run(*_args, **_kwargs):
        raise AssertionError("unsafe path must be rejected before macOS automation")

    monkeypatch.setattr(subprocess, "run", should_not_run)
    pending = dispatch(
        settings,
        "accessibility_action",
        {"app_name": "chrome", "command": "file_dialog_choose", "path": "/etc/hosts"},
        "ax-file-unsafe",
        "test",
    )
    confirmed = dispatch(
        settings,
        "pending_confirm",
        {"action_id": pending["data"]["action"]["action_id"]},
        "ax-file-unsafe-confirm",
        "test",
    )

    assert confirmed["success"] is False
    assert "path is outside allowed roots" in confirmed["error"]


@pytest.mark.parametrize(
    ("command", "params"),
    [
        ("input", {"element_id": "ax:1.2", "text": "hello"}),
        ("scroll", {"element_id": "ax:root", "direction": "down", "amount": 2}),
        ("drag", {"element_id": "ax:1", "target_element_id": "ax:2"}),
        ("menu_select", {"element_id": "ax:3.1"}),
    ],
)
def test_semantic_accessibility_actions_execute_after_confirmation(settings, monkeypatch, command, params):
    def fake_run(os_command, **_kwargs):
        request = json.loads(os_command[-1])
        assert request["action"] == command
        return subprocess.CompletedProcess(
            os_command,
            0,
            json.dumps({"command": command, "element_id": request["element_id"], "performed": True}),
            "",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    pending = dispatch(
        settings,
        "accessibility_action",
        {"app_name": "chrome", "command": command, **params},
        f"ax-{command}",
        "test",
    )
    confirmed = dispatch(
        settings,
        "pending_confirm",
        {"action_id": pending["data"]["action"]["action_id"]},
        f"ax-{command}-confirm",
        "test",
    )

    assert confirmed["success"] is True
    assert confirmed["data"]["execution_result"]["command"] == command
    assert confirmed["data"]["execution_result"]["performed"] is True


def test_file_dialog_can_choose_an_existing_path_inside_safe_roots(settings, monkeypatch):
    safe_file = Path(settings.default_project_root) / "upload.txt"
    safe_file.write_text("upload", encoding="utf-8")

    def fake_run(command, **_kwargs):
        request = json.loads(command[-1])
        assert request["path"] == str(safe_file.resolve())
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps({"command": "file_dialog_choose", "element_id": "ax:root", "performed": True}),
            "",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    pending = dispatch(
        settings,
        "accessibility_action",
        {"app_name": "chrome", "command": "file_dialog_choose", "path": str(safe_file)},
        "ax-file-safe",
        "test",
    )
    confirmed = dispatch(
        settings,
        "pending_confirm",
        {"action_id": pending["data"]["action"]["action_id"]},
        "ax-file-safe-confirm",
        "test",
    )

    assert confirmed["success"] is True
    assert confirmed["data"]["execution_result"]["command"] == "file_dialog_choose"


def test_client_can_discover_desktop_perception_and_ui_capabilities(settings):
    result = dispatch(
        settings,
        "accessibility_capabilities",
        {"app_name": "chrome"},
        "ax-capabilities",
        "test",
    )

    assert result["success"] is True
    assert result["data"]["app"] == "Google Chrome"
    assert "tree" in result["data"]["read_capabilities"]
    assert "drag" in result["data"]["action_capabilities"]
    assert result["data"]["actions_require_confirmation"] is True


def test_mcp_screenshot_returns_a_real_image_content_block(monkeypatch):
    from xiaozhi_desktop_mcp import server

    monkeypatch.setattr(
        server,
        "desktop_screenshot_impl",
        lambda display_id, max_width: {
            "success": True,
            "display_id": display_id,
            "max_width": max_width,
            "media_type": "image/png",
            "image_base64": "iVBORw0KGgppbWFnZQ==",
        },
    )

    result = asyncio.run(server.mcp.call_tool("desktop_screenshot", {"display_id": 1, "max_width": 800}))

    assert len(result.content) == 2
    assert result.content[0].type == "text"
    assert result.content[1].type == "image"
    assert result.content[1].mimeType == "image/png"
    assert result.structuredContent["display_id"] == 1
