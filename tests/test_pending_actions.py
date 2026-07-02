from __future__ import annotations

from xiaozhi_desktop_mcp.api_v1 import dispatch
from xiaozhi_desktop_mcp.tools.pending_actions import create_pending_action


def test_pending_create_rejects_empty_text():
    result = create_pending_action("desktop_ask_cc", {"text": ""})

    assert result["success"] is False
    assert "text" in result["error"]


def test_pending_create_rejects_unknown_params():
    result = create_pending_action("desktop_ask_cc", {"text": "hello", "surprise": True})

    assert result["success"] is False
    assert "unknown params" in result["error"]


def test_pending_create_rejects_empty_project_alias():
    result = create_pending_action("desktop_ask_cc_project", {"project": "", "text": "hello"})

    assert result["success"] is False
    assert "project" in result["error"]


def test_api_ask_cc_creates_pending_action(settings):
    result = dispatch(settings, "ask_cc", {"text": "hello"}, "req-1")

    assert result["success"] is True
    assert result["data"]["action"]["action_type"] == "desktop_ask_cc"
    assert result["data"]["action"]["params"]["allow_frontmost"] is False


def test_api_ask_cc_rejects_empty_text(settings):
    result = dispatch(settings, "ask_cc", {"text": ""}, "req-1")

    assert result["success"] is False
    assert "text" in result["error"]


def test_api_cc_switch_model_creates_pending_action(settings):
    result = dispatch(settings, "cc_switch_model", {"model": "sonnet"}, "req-1")

    assert result["success"] is True
    assert result["data"]["action"]["action_type"] == "cc_switch_model"
    assert result["data"]["action"]["params"]["model"] == "sonnet"


def test_api_xcode_build_creates_pending_action(settings):
    result = dispatch(settings, "xcode_build", {"scheme": "App"}, "req-1")

    assert result["success"] is True
    assert result["data"]["action"]["action_type"] == "xcode_build"
    assert result["data"]["action"]["params"]["scheme"] == "App"


def test_api_app_close_creates_pending_action(settings):
    result = dispatch(settings, "app_close", {"app_name": "Obsidian"}, "req-1")

    assert result["success"] is True
    assert result["data"]["action"]["action_type"] == "app_close"


def test_api_create_note_creates_file(settings):
    result = dispatch(settings, "create_note", {"note_path": "voice/new-note", "text": "hello"}, "req-1")

    assert result["success"] is True
    assert (settings.obsidian_vault / "voice" / "new-note.md").exists()
