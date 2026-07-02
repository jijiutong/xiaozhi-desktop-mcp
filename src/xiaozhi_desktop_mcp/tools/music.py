from __future__ import annotations

import subprocess
from urllib.parse import quote_plus

from ..config import Settings
from ..responses import fail, ok
from ..safety import SafetyError, ensure_allowed_app

_COMMANDS = {
    "play": "play",
    "pause": "pause",
    "toggle": "playpause",
    "play_pause": "playpause",
    "next": "next track",
    "previous": "previous track",
}


def music_control(settings: Settings, command: str = "toggle", app_name: str = "") -> dict:
    """Control an allowlisted macOS music app with AppleScript."""
    normalized = command.strip().lower().replace("-", "_") or "toggle"
    if normalized not in _COMMANDS:
        return fail(f"unsupported music command: {command}", "这个音乐控制命令还不支持。")
    app = app_name.strip() or _default_music_app(settings)
    try:
        allowed_app = ensure_allowed_app(app, settings.allowed_apps)
    except SafetyError as exc:
        return fail(str(exc), f"{app or '音乐 App'} 不在白名单里，我没有操作。")
    script = f'tell application "{allowed_app}" to {_COMMANDS[normalized]}'
    completed = subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return fail(completed.stderr.strip() or completed.stdout.strip(), "音乐控制没有成功。", {"app": allowed_app})
    return ok({"app": allowed_app, "command": normalized}, "音乐操作完成。", "music command completed")


def music_search(settings: Settings, query: str, app_name: str = "") -> dict:
    """Open a music search URL; useful when app-specific search scripting is unavailable."""
    from .browser import browser_open_url

    clean = query.strip()
    if not clean:
        return fail("music search query is empty", "歌曲或歌手名是空的。")
    url = "https://music.apple.com/search?term=" + quote_plus(clean)
    return browser_open_url(settings, url, app_name or _default_browser_for_music(settings))


def _default_music_app(settings: Settings) -> str:
    for app in ("Music", "Spotify", "网易云音乐"):
        if app in settings.allowed_apps:
            return app
    return "Music"


def _default_browser_for_music(settings: Settings) -> str:
    for app in ("Google Chrome", "Safari", "Microsoft Edge", "Arc"):
        if app in settings.allowed_apps:
            return app
    return "Google Chrome"
