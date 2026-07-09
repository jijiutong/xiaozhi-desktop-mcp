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
  }
}
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DESKTOP_MCP_CONFIG", str(config_path))
    monkeypatch.setenv("APP_ALIASES", "chrome=Google Chrome,netease=网易云音乐")
    monkeypatch.setenv("APP_PROCESS_ALIASES", "Google Chrome=Google Chrome|Chrome Helper")

    settings = load_settings()

    assert settings.app_aliases["browser"] == "Google Chrome"
    assert settings.app_aliases["chrome"] == "Google Chrome"
    assert settings.app_aliases["netease"] == "网易云音乐"
    assert settings.app_process_aliases["网易云音乐"] == ("网易云音乐", "NetEaseMusic")
    assert settings.app_process_aliases["google chrome"] == ("Google Chrome", "Chrome Helper")
