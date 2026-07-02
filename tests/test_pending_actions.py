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
