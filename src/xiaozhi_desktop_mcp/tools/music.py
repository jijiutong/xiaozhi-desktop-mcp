from __future__ import annotations

from urllib.parse import quote_plus

from ..config import Settings
from ..responses import fail, ok
from ..safety import SafetyError
from .apps import automation_app_name, resolve_app_name
from .music_drivers import music_driver


def music_control(settings: Settings, command: str = "toggle", app_name: str = "") -> dict:
    """Control an allowlisted macOS music app with AppleScript."""
    driver = _resolve_music_driver(settings, app_name)
    if isinstance(driver, dict):
        return driver
    return driver.control(command)


def music_search(settings: Settings, query: str, app_name: str = "", provider: str = "") -> dict:
    """Open a music search URL; useful when app-specific search scripting is unavailable."""
    from .browser import browser_open_url

    clean = query.strip()
    if not clean:
        return fail("music search query is empty", "歌曲或歌手名是空的。")
    normalized_provider = provider.strip().lower().replace("-", "_")
    if not normalized_provider and app_name.strip() in {"网易云音乐", "NetEase Cloud Music"}:
        normalized_provider = "netease"
    if normalized_provider in {"netease", "netease_music", "网易云", "网易云音乐"}:
        url = "https://music.163.com/#/search/m/?s=" + quote_plus(clean)
    else:
        url = "https://music.apple.com/search?term=" + quote_plus(clean)
    browser_app = "" if app_name.strip() in {"网易云音乐", "NetEase Cloud Music", "Music", "Spotify"} else app_name
    return browser_open_url(settings, url, browser_app or _default_browser_for_music(settings))


def music_status(settings: Settings, app_name: str = "") -> dict:
    driver = _resolve_music_driver(settings, app_name)
    if isinstance(driver, dict):
        return driver
    return driver.status()


def music_set_volume(settings: Settings, volume: int, app_name: str = "") -> dict:
    driver = _resolve_music_driver(settings, app_name)
    if isinstance(driver, dict):
        return driver
    return driver.set_volume(volume)


def music_search_app(settings: Settings, query: str, app_name: str = "") -> dict:
    driver = _resolve_music_driver(settings, app_name or "网易云音乐")
    if isinstance(driver, dict):
        return driver
    return driver.search_app(query)


def music_capabilities(settings: Settings, app_name: str = "") -> dict:
    driver = _resolve_music_driver(settings, app_name)
    if isinstance(driver, dict):
        return driver
    return ok(
        {"app": driver.app_name, "driver": driver.family, "capabilities": driver.capabilities()},
        "已返回音乐 App 能力。",
        "returned music capabilities",
    )


def _resolve_music_driver(settings: Settings, app_name: str):
    app = app_name.strip() or _default_music_app(settings)
    try:
        allowed_app = resolve_app_name(settings, app)
    except SafetyError as exc:
        return fail(str(exc), f"{app or '音乐 App'} 不在白名单里，我没有操作。")
    driver = music_driver(allowed_app, automation_app_name(settings, allowed_app))
    if driver is None:
        return fail(f"music driver is unavailable for: {allowed_app}", "这个音乐 App 暂时没有控制 Driver。")
    return driver


def _default_music_app(settings: Settings) -> str:
    for app in ("Music", "网易云音乐", "NetEase Cloud Music", "Spotify"):
        if app in settings.allowed_apps:
            return app
    return "Music"


def _default_browser_for_music(settings: Settings) -> str:
    for app in ("Google Chrome", "Safari", "Microsoft Edge", "Arc"):
        if app in settings.allowed_apps:
            return app
    return "Google Chrome"
