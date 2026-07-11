from __future__ import annotations

import subprocess
from urllib.parse import quote_plus, urlparse

from ..config import Settings
from ..responses import fail, ok
from ..safety import SafetyError
from .apps import resolve_app_name
from .browser_drivers import browser_driver


def browser_open_url(settings: Settings, url: str, app_name: str = "") -> dict:
    """Open an http(s) URL in an allowlisted browser app."""
    target_url = _normalize_url(url)
    if not target_url:
        return fail("url is empty", "网址是空的，我没有打开。")
    parsed = urlparse(target_url)
    if parsed.scheme not in {"http", "https"}:
        return fail("only http and https URLs are allowed", "我只能打开 http 或 https 链接。")
    if parsed.username or parsed.password:
        return fail("URLs containing credentials are not allowed", "包含账号信息的网址不能直接打开。")
    if settings.browser_allowed_domains and not _domain_allowed(
        parsed.hostname or "", settings.browser_allowed_domains
    ):
        return fail(
            f"browser domain is not allowlisted: {parsed.hostname or ''}",
            "这个网站不在浏览器域名白名单里，我没有打开。",
        )
    app = app_name.strip() or _default_browser(settings)
    try:
        allowed_app = resolve_app_name(settings, app)
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


def browser_tabs(settings: Settings, app_name: str = "") -> dict:
    driver = _resolve_driver(settings, app_name)
    if isinstance(driver, dict):
        return driver
    return driver.list_tabs()


def browser_current(settings: Settings, app_name: str = "") -> dict:
    driver = _resolve_driver(settings, app_name)
    if isinstance(driver, dict):
        return driver
    return driver.current_tab()


def browser_control(
    settings: Settings,
    command: str,
    app_name: str = "",
    window_index: int = 1,
    tab_index: int = 1,
) -> dict:
    driver = _resolve_driver(settings, app_name)
    if isinstance(driver, dict):
        return driver
    return driver.control(command, window_index, tab_index)


def browser_capabilities(settings: Settings, app_name: str = "") -> dict:
    driver = _resolve_driver(settings, app_name)
    if isinstance(driver, dict):
        return driver
    return ok(
        {"app": driver.app_name, "driver": driver.family, "capabilities": driver.capabilities()},
        "已返回浏览器能力。",
        "returned browser capabilities",
    )


def _resolve_driver(settings: Settings, app_name: str):
    if not settings.browser_control_enabled:
        return fail("browser control is disabled", "浏览器控制功能当前没有开启。")
    requested = app_name.strip() or _default_browser(settings)
    try:
        allowed_app = resolve_app_name(settings, requested)
    except SafetyError as exc:
        return fail(str(exc), f"{requested or '浏览器'} 不在白名单里，我没有操作。")
    driver = browser_driver(allowed_app)
    if driver is None:
        return fail(f"browser driver is unavailable for: {allowed_app}", "这个浏览器暂时没有控制 Driver。")
    return driver


def _normalize_url(url: str) -> str:
    clean = url.strip()
    if not clean:
        return ""
    if "://" not in clean:
        return "https://" + clean
    return clean


def _domain_allowed(hostname: str, allowed_domains: frozenset[str]) -> bool:
    host = hostname.strip().lower().rstrip(".")
    return any(host == domain.lower() or host.endswith("." + domain.lower()) for domain in allowed_domains)


def _default_browser(settings: Settings) -> str:
    for app in ("Google Chrome", "Safari", "Microsoft Edge", "Arc"):
        if app in settings.allowed_apps:
            return app
    return "Google Chrome"


def _run_open(command: list[str], spoken: str, data: dict) -> dict:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return fail("browser command timed out", "浏览器操作超时。", data)
    if completed.returncode != 0:
        return fail(completed.stderr.strip() or completed.stdout.strip(), "浏览器操作没有成功。", data)
    return ok(data, spoken, "browser action completed")
