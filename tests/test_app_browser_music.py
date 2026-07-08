from __future__ import annotations

import subprocess

from xiaozhi_desktop_mcp.api_v1 import actions_catalog, dispatch
from xiaozhi_desktop_mcp.tools.apps import app_status, focus_app
from xiaozhi_desktop_mcp.tools.browser import browser_open_url
from xiaozhi_desktop_mcp.tools.music import music_search


def test_app_focus_uses_allowlisted_app(settings, monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = focus_app(settings, "Obsidian")

    assert result["success"] is True
    assert calls[0][0] == "osascript"
    assert 'tell application "Obsidian" to activate' in calls[0]


def test_app_status_reports_running(settings, monkeypatch):
    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, "true\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = app_status(settings, "Obsidian")

    assert result["success"] is True
    assert result["running"] is True


def test_browser_open_rejects_non_http_url(settings):
    result = browser_open_url(settings, "file:///etc/passwd", "Google Chrome")

    assert result["success"] is False
    assert "http" in result["error"]


def test_api_browser_search_uses_allowlisted_browser(settings, monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch(settings, "browser_search", {"query": "desktop mcp", "app_name": "Google Chrome"}, "req-1")

    assert result["success"] is True
    assert calls[0][:3] == ["open", "-a", "Google Chrome"]
    assert "desktop+mcp" in calls[0][3]


def test_music_search_supports_netease_provider(settings, monkeypatch):
    opened = []

    def fake_browser_open_url(_settings, url, app_name=""):
        opened.append((url, app_name))
        return {"success": True, "url": url, "app": app_name}

    monkeypatch.setattr("xiaozhi_desktop_mcp.tools.browser.browser_open_url", fake_browser_open_url)

    result = music_search(settings, "周杰伦", provider="netease")

    assert result["success"] is True
    assert opened[0][0].startswith("https://music.163.com/#/search/m/?s=")
    assert opened[0][1] == "Google Chrome"


def test_api_actions_catalog_lists_app_browser_music_actions():
    result = actions_catalog()

    names = {action["name"] for action in result["actions"]}
    assert {"app_focus", "app_status", "browser_open", "browser_search", "music_control", "music_search"}.issubset(
        names
    )
