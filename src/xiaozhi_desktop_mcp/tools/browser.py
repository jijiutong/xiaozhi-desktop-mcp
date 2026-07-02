from __future__ import annotations

import subprocess
from urllib.parse import quote_plus, urlparse

from ..config import Settings
from ..responses import fail, ok
from ..safety import SafetyError, ensure_allowed_app


def browser_open_url(settings: Settings, url: str, app_name: str = "") -> dict:
    """Open an http(s) URL in an allowlisted browser app."""
    target_url = _normalize_url(url)
    if not target_url:
        return fail("url is empty", "网址是空的，我没有打开。")
    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"}:
        return fail("only http and https URLs are allowed", "我只能打开 http 或 https 链接。")
    app = app_name.strip() or _default_browser(settings)
    try:
        allowed_app = ensure_allowed_app(app, settings.allowed_apps)
    except SafetyError as exc:
        return fail(str(exc), f"{app or '浏览器'} 不在白名单里，我没有打开。")
    return _run_open(["open", "-a", allowed_app, target_url], "已打开网页。", {"url": target_url, "app": allowed_app})


def browser_search(settings: Settings, query: str, app_name: str = "", engine: str = "google") -> dict:
    """Search the web in an allowlisted browser."""
    clean_query = query.strip()
    if not clean_query:
        return fail("search query is empty", "搜索关键词是空的。")
    base_url = {
        "google": "https://www.google.com/search?q=",
        "bing": "https://www.bing.com/search?q=",
        "duckduckgo": "https://duckduckgo.com/?q=",
    }.get(engine.strip().lower(), "https://www.google.com/search?q=")
    return browser_open_url(settings, base_url + quote_plus(clean_query), app_name)


def _normalize_url(url: str) -> str:
    clean = url.strip()
    if not clean:
        return ""
    if "://" not in clean:
        return "https://" + clean
    return clean


def _default_browser(settings: Settings) -> str:
    for app in ("Google Chrome", "Safari", "Microsoft Edge", "Arc"):
        if app in settings.allowed_apps:
            return app
    return "Google Chrome"


def _run_open(command: list[str], spoken: str, data: dict) -> dict:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return fail(completed.stderr.strip() or completed.stdout.strip(), "浏览器操作没有成功。", data)
    return ok(data, spoken, "browser action completed")
