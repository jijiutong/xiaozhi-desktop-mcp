from __future__ import annotations

import subprocess
from dataclasses import replace

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


def test_app_focus_resolves_alias(settings, monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = focus_app(settings, "chrome")

    assert result["success"] is True
    assert 'tell application "Google Chrome" to activate' in calls[0]


def test_app_focus_resolves_allowlisted_app_case_insensitively(settings, monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = focus_app(settings, "google chrome")

    assert result["success"] is True
    assert 'tell application "Google Chrome" to activate' in calls[0]


def test_app_focus_uses_configured_automation_name(settings, monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = focus_app(settings, "netease")

    assert result["success"] is True
    assert result["app"] == "网易云音乐"
    assert 'tell application "NeteaseMusic" to activate' in calls[0]


def test_app_status_reports_running(settings, monkeypatch):
    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, "true\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = app_status(settings, "Obsidian")

    assert result["success"] is True
    assert result["running"] is True


def test_app_status_uses_process_aliases(settings, monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "false\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = app_status(settings, "netease")

    assert result["success"] is True
    assert result["app"] == "网易云音乐"
    assert "NetEaseMusic" in result["process_names"]
    assert "NetEaseMusic" in calls[0][2]


def test_browser_open_rejects_non_http_url(settings):
    result = browser_open_url(settings, "file:///etc/passwd", "Google Chrome")

    assert result["success"] is False
    assert "http" in result["error"]


def test_browser_open_enforces_optional_domain_allowlist(settings):
    restricted = replace(settings, browser_allowed_domains=frozenset({"example.com"}))

    result = browser_open_url(restricted, "https://accounts.example.net/login", "Google Chrome")

    assert result["success"] is False
    assert "domain" in result["error"]


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


def test_api_browser_search_resolves_browser_alias(settings, monkeypatch):
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch(settings, "browser_search", {"query": "desktop mcp", "app_name": "chrome"}, "req-1")

    assert result["success"] is True
    assert calls[0][:3] == ["open", "-a", "Google Chrome"]


def test_api_browser_tabs_returns_structured_tabs(settings, monkeypatch):
    def fake_run(command, **_kwargs):
        output = "1\t1\tHome\thttps://example.com\n1\t2\tDocs\thttps://docs.example.com\n"
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch(settings, "browser_tabs", {"app_name": "chrome"}, "req-tabs")

    assert result["success"] is True
    assert result["data"]["count"] == 2
    assert result["data"]["tabs"][1]["title"] == "Docs"


def test_api_browser_current_reads_active_tab(settings, monkeypatch):
    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, "1\t2\tActive\thttps://active.example.com\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch(settings, "browser_current", {"app_name": "chrome"}, "req-current")

    assert result["success"] is True
    assert result["data"]["tab"]["tab_index"] == 2
    assert result["data"]["tab"]["title"] == "Active"


def test_api_browser_current_handles_no_open_windows(settings, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, "", ""),
    )

    result = dispatch(settings, "browser_current", {"app_name": "chrome"}, "req-current-empty")

    assert result["success"] is True
    assert result["data"]["tab"] is None


def test_api_browser_close_tab_requires_confirmation(settings):
    result = dispatch(
        settings,
        "browser_control",
        {"command": "close_tab", "app_name": "chrome", "window_index": 1, "tab_index": 2},
        "req-control",
    )

    assert result["success"] is True
    assert result["data"]["action"]["action_type"] == "browser_control"


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


def test_api_music_status_returns_current_apple_music_track(settings, monkeypatch):
    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, "playing\tSong\tArtist\tAlbum\t55\n", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = dispatch(settings, "music_status", {"app_name": "Music"}, "req-music")

    assert result["success"] is True
    assert result["data"]["track"]["name"] == "Song"
    assert result["data"]["volume"] == 55


def test_api_netease_search_app_requires_confirmation(settings):
    result = dispatch(
        settings,
        "music_search_app",
        {"query": "周杰伦", "app_name": "netease"},
        "req-netease-search",
    )

    assert result["success"] is True
    assert result["data"]["action"]["action_type"] == "music_search_app"


def test_netease_search_reports_accessibility_permission(settings, monkeypatch):
    def denied(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, "", "osascript is not allowed to send keystrokes. (1002)")

    monkeypatch.setattr(subprocess, "run", denied)

    result = dispatch(
        settings,
        "music_search_app",
        {"query": "周杰伦", "app_name": "netease", "confirm": True},
        "req-netease-permission",
    )

    assert result["success"] is False
    assert "辅助功能" in result["error_spoken_message"]


def test_netease_rejects_inexact_play_pause_commands(settings):
    result = dispatch(settings, "music_control", {"command": "pause", "app_name": "netease"}, "req-netease")

    assert result["success"] is False
    assert "use toggle" in result["error"]


def test_api_app_capabilities_exposes_driver_commands(settings):
    result = dispatch(settings, "app_capabilities", {"app_name": "chrome"}, "req-capabilities")

    assert result["success"] is True
    assert result["data"]["driver"] == "chromium"
    assert "tabs" in result["data"]["capabilities"]


def test_api_actions_catalog_lists_app_browser_music_actions():
    result = actions_catalog()

    names = {action["name"] for action in result["actions"]}
    assert {"app_focus", "app_status", "browser_open", "browser_search", "music_control", "music_search"}.issubset(
        names
    )
