from __future__ import annotations

from xiaozhi_desktop_mcp.config import load_settings


def test_load_settings_reads_app_aliases_from_yaml_and_env(tmp_path, monkeypatch):
    config_path = tmp_path / "desktop-mcp.yaml"
    config_path.write_text(
        """
{
  "app_aliases": {
    "browser": "Google Chrome",
    "cloudmusic": "网易云音乐"
  },
  "app_process_aliases": {
    "网易云音乐": ["网易云音乐", "NetEaseMusic"]
  },
  "app_automation_aliases": {
    "网易云音乐": "NeteaseMusic"
  }
}
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DESKTOP_MCP_CONFIG", str(config_path))
    monkeypatch.setenv("APP_ALIASES", "chrome=Google Chrome,netease=网易云音乐")
    monkeypatch.setenv("APP_PROCESS_ALIASES", "Google Chrome=Google Chrome|Chrome Helper")
    monkeypatch.setenv("APP_AUTOMATION_ALIASES", "Google Chrome=Google Chrome")
    monkeypatch.setenv("DESKTOP_MCP_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("DESKTOP_MCP_PENDING_TTL_SECONDS", "900")
    monkeypatch.setenv("DESKTOP_MCP_BROWSER_ALLOWED_DOMAINS", "example.com,docs.example.com")

    settings = load_settings()

    assert settings.app_aliases["browser"] == "Google Chrome"
    assert settings.app_aliases["chrome"] == "Google Chrome"
    assert settings.app_aliases["netease"] == "网易云音乐"
    assert settings.app_process_aliases["网易云音乐"] == ("网易云音乐", "NetEaseMusic")
    assert settings.app_process_aliases["google chrome"] == ("Google Chrome", "Chrome Helper")
    assert settings.app_automation_aliases["网易云音乐"] == "NeteaseMusic"
    assert settings.app_automation_aliases["google chrome"] == "Google Chrome"
    assert settings.state_db_path == (tmp_path / "state.db").resolve()
    assert settings.pending_ttl_seconds == 900
    assert settings.browser_allowed_domains == frozenset({"example.com", "docs.example.com"})
