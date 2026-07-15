from __future__ import annotations

from typing import Any

from ..config import Settings
from ..responses import fail
from .accessibility import accessibility_capabilities, accessibility_tree
from .apps import app_capabilities, app_status, close_app, focus_app, open_app
from .browser import (
    browser_capabilities,
    browser_control,
    browser_current,
    browser_open_url,
    browser_search,
    browser_tabs,
)
from .cc_session import send_slash_command, switch_model
from .clipboard import clipboard_get, clipboard_set
from .desktop_config import category_registry
from .finder import finder_open_path
from .music import (
    music_capabilities,
    music_control,
    music_search,
    music_search_app,
    music_set_volume,
    music_status,
)
from .obsidian import append_daily_note, append_note, create_note, open_note, save_memory, search_notes
from .pending_actions import create_pending_action
from .perception import capture_display, capture_window, ocr_desktop
from .projects import ask_cc_project
from .workflows import ask_cc, check_cc, continue_cc, focus_cc, open_cc_project, stop_cc
from .xcode import open_xcode_project, xcode_build, xcode_clean, xcode_last_errors, xcode_test


def desktop_intent(settings: Settings, category: str, intent: str, params: dict[str, Any] | None = None) -> dict:
    """Route a generic desktop intent to a safe built-in capability."""
    normalized_category = category.strip().lower().replace("-", "_")
    normalized_intent = intent.strip().lower().replace("-", "_")
    clean_params = dict(params or {})
    if not normalized_category or not normalized_intent:
        return fail("category and intent are required", "分类和意图不能为空。")
    handler = _HANDLERS.get((normalized_category, normalized_intent))
    if handler is None:
        return fail(
            f"unsupported desktop intent: {normalized_category}.{normalized_intent}",
            "这个桌面意图还不支持。",
            {
                "category": normalized_category,
                "intent": normalized_intent,
                "registry": category_registry(settings).get("categories", {}),
            },
        )
    result = handler(settings, clean_params)
    if result.get("success"):
        result["category"] = normalized_category
        result["intent"] = normalized_intent
    return result


def desktop_intent_catalog(settings: Settings) -> dict:
    """Return category registry plus common intent examples."""
    result = category_registry(settings)
    result["examples"] = [
        {"category": "music", "intent": "next", "params": {}},
        {"category": "docs", "intent": "search", "params": {"query": "desktop mcp"}},
        {"category": "ai", "intent": "send", "params": {"text": "继续修复测试"}},
        {"category": "dev", "intent": "build", "params": {"scheme": "App"}},
        {"category": "browser", "intent": "open", "params": {"url": "https://example.com"}},
        {"category": "system", "intent": "clipboard_set", "params": {"text": "hello"}},
    ]
    return result


def _app_open(settings: Settings, params: dict[str, Any]) -> dict:
    return open_app(settings, _str(params, "app_name") or _str(params, "app"))


def _app_close(settings: Settings, params: dict[str, Any]) -> dict:
    pending_params = {"app_name": _str(params, "app_name") or _str(params, "app")}
    if not _bool(params, "confirm"):
        return create_pending_action("app_close", pending_params, settings=settings)
    return close_app(settings, pending_params["app_name"])


def _app_focus(settings: Settings, params: dict[str, Any]) -> dict:
    return focus_app(settings, _str(params, "app_name") or _str(params, "app"))


def _app_status(settings: Settings, params: dict[str, Any]) -> dict:
    return app_status(settings, _str(params, "app_name") or _str(params, "app"))


def _app_capabilities(settings: Settings, params: dict[str, Any]) -> dict:
    return app_capabilities(settings, _str(params, "app_name") or _str(params, "app"))


def _docs_create(settings: Settings, params: dict[str, Any]) -> dict:
    return create_note(
        settings,
        _str(params, "note_path") or _str(params, "path"),
        _str(params, "text"),
        _bool(params, "overwrite"),
    )


def _docs_append(settings: Settings, params: dict[str, Any]) -> dict:
    return append_note(
        settings,
        _str(params, "note_path") or _str(params, "path"),
        _str(params, "text"),
        _str(params, "heading"),
    )


def _ai_send(settings: Settings, params: dict[str, Any]) -> dict:
    if _str(params, "project"):
        pending_params = {
            "project": _str(params, "project"),
            "text": _str(params, "text"),
            "session_id": _str(params, "session_id", "default"),
            "cli": _str(params, "cli"),
            "terminal": _str(params, "terminal", "Terminal"),
            "open_if_needed": _bool(params, "open_if_needed", True),
            "allow_frontmost": _bool(params, "allow_frontmost", False),
        }
        if not _bool(params, "confirm"):
            return create_pending_action("desktop_ask_cc_project", pending_params, settings=settings)
        return ask_cc_project(
            settings,
            pending_params["project"],
            pending_params["text"],
            pending_params["session_id"],
            pending_params["cli"],
            pending_params["terminal"],
            bool(pending_params["open_if_needed"]),
            bool(pending_params["allow_frontmost"]),
        )
    pending_params = {
        "text": _str(params, "text"),
        "project_path": _str(params, "project_path"),
        "session_id": _str(params, "session_id", "default"),
        "cli": _str(params, "cli"),
        "terminal": _str(params, "terminal", "Terminal"),
        "open_if_needed": _bool(params, "open_if_needed", True),
        "allow_frontmost": _bool(params, "allow_frontmost", False),
    }
    if not _bool(params, "confirm"):
        return create_pending_action("desktop_ask_cc", pending_params, settings=settings)
    return ask_cc(
        settings,
        pending_params["text"],
        pending_params["project_path"],
        pending_params["session_id"],
        pending_params["cli"],
        pending_params["terminal"],
        bool(pending_params["open_if_needed"]),
        bool(pending_params["allow_frontmost"]),
    )


def _ai_slash(settings: Settings, params: dict[str, Any]) -> dict:
    pending_params = {
        "command": _str(params, "command"),
        "args": _str(params, "args"),
        "session_id": _str(params, "session_id", "default"),
        "allow_frontmost": _bool(params, "allow_frontmost", False),
    }
    if not _bool(params, "confirm"):
        return create_pending_action("cc_send_slash_command", pending_params, settings=settings)
    return send_slash_command(
        settings,
        pending_params["command"],
        pending_params["args"],
        pending_params["session_id"],
        True,
        bool(pending_params["allow_frontmost"]),
    )


def _ai_model(settings: Settings, params: dict[str, Any]) -> dict:
    pending_params = {
        "model": _str(params, "model"),
        "session_id": _str(params, "session_id", "default"),
        "allow_frontmost": _bool(params, "allow_frontmost", False),
    }
    if not _bool(params, "confirm"):
        return create_pending_action("cc_switch_model", pending_params, settings=settings)
    return switch_model(
        settings,
        pending_params["model"],
        pending_params["session_id"],
        True,
        bool(pending_params["allow_frontmost"]),
    )


def _dev_xcode(settings: Settings, params: dict[str, Any], action: str) -> dict:
    pending_params = {
        "project_path": _str(params, "project_path"),
        "xcode_path": _str(params, "xcode_path"),
        "scheme": _str(params, "scheme"),
        "configuration": _str(params, "configuration"),
        "destination": _str(params, "destination"),
    }
    if action in {"build", "test", "clean"} and not _bool(params, "confirm"):
        return create_pending_action(f"xcode_{action}", pending_params, settings=settings)
    runner = {"open": open_xcode_project, "build": xcode_build, "test": xcode_test, "clean": xcode_clean}[action]
    if action == "open":
        return runner(settings, pending_params["project_path"], pending_params["xcode_path"])
    return runner(settings, **pending_params)


def _music_app(params: dict[str, Any]) -> str:
    return _str(params, "app_name") or _str(params, "app")


def _music_open(settings: Settings, params: dict[str, Any]) -> dict:
    return open_app(settings, _music_app(params) or "Music")


def _music_play(settings: Settings, params: dict[str, Any]) -> dict:
    return music_control(settings, "play", _music_app(params))


def _music_pause(settings: Settings, params: dict[str, Any]) -> dict:
    return music_control(settings, "pause", _music_app(params))


def _music_toggle(settings: Settings, params: dict[str, Any]) -> dict:
    return music_control(settings, "toggle", _music_app(params))


def _music_next(settings: Settings, params: dict[str, Any]) -> dict:
    return music_control(settings, "next", _music_app(params))


def _music_previous(settings: Settings, params: dict[str, Any]) -> dict:
    return music_control(settings, "previous", _music_app(params))


def _music_search(settings: Settings, params: dict[str, Any]) -> dict:
    return music_search(settings, _str(params, "query"), _str(params, "browser"), _str(params, "provider"))


def _music_search_app(settings: Settings, params: dict[str, Any]) -> dict:
    pending_params = {"query": _str(params, "query"), "app_name": _music_app(params)}
    if not _bool(params, "confirm"):
        return create_pending_action("music_search_app", pending_params, settings=settings)
    return music_search_app(settings, **pending_params)


def _music_status(settings: Settings, params: dict[str, Any]) -> dict:
    return music_status(settings, _music_app(params))


def _music_volume(settings: Settings, params: dict[str, Any]) -> dict:
    return music_set_volume(settings, _int(params, "volume", 50), _music_app(params))


def _music_capabilities(settings: Settings, params: dict[str, Any]) -> dict:
    return music_capabilities(settings, _music_app(params))


def _docs_remember(settings: Settings, params: dict[str, Any]) -> dict:
    return save_memory(settings, _str(params, "text"), _str(params, "tags", "xiaozhi,voice-memory"))


def _docs_search(settings: Settings, params: dict[str, Any]) -> dict:
    return search_notes(settings, _str(params, "query"), _int(params, "limit", 5))


def _docs_open(settings: Settings, params: dict[str, Any]) -> dict:
    return open_note(settings, _str(params, "note_path") or _str(params, "path"))


def _docs_daily(settings: Settings, params: dict[str, Any]) -> dict:
    return append_daily_note(
        settings,
        _str(params, "text"),
        _str(params, "date"),
        _str(params, "folder", "daily"),
    )


def _ai_open(settings: Settings, params: dict[str, Any]) -> dict:
    return open_cc_project(
        settings,
        _str(params, "project_path"),
        _str(params, "session_id", "default"),
        _str(params, "cli"),
        _str(params, "terminal", "Terminal"),
        _str(params, "cli_args"),
    )


def _ai_continue(settings: Settings, params: dict[str, Any]) -> dict:
    return continue_cc(
        settings,
        _str(params, "session_id", "default"),
        _bool(params, "confirm"),
        _bool(params, "allow_frontmost"),
    )


def _ai_status(settings: Settings, params: dict[str, Any]) -> dict:
    return check_cc(settings, _str(params, "session_id", "default"), _int(params, "max_chars"))


def _ai_stop(settings: Settings, params: dict[str, Any]) -> dict:
    return stop_cc(_str(params, "session_id", "default"), _bool(params, "allow_frontmost"))


def _browser_app(params: dict[str, Any]) -> str:
    return _str(params, "app_name") or _str(params, "app")


def _browser_open(settings: Settings, params: dict[str, Any]) -> dict:
    return browser_open_url(settings, _str(params, "url"), _browser_app(params))


def _browser_search(settings: Settings, params: dict[str, Any]) -> dict:
    return browser_search(settings, _str(params, "query"), _browser_app(params), _str(params, "engine", "google"))


def _browser_tabs(settings: Settings, params: dict[str, Any]) -> dict:
    return browser_tabs(settings, _browser_app(params))


def _browser_current(settings: Settings, params: dict[str, Any]) -> dict:
    return browser_current(settings, _browser_app(params))


def _browser_capabilities(settings: Settings, params: dict[str, Any]) -> dict:
    return browser_capabilities(settings, _browser_app(params))


def _browser_control(settings: Settings, params: dict[str, Any]) -> dict:
    pending_params = {
        "command": _str(params, "command"),
        "app_name": _browser_app(params),
        "window_index": _int(params, "window_index", 1),
        "tab_index": _int(params, "tab_index", 1),
    }
    if not _bool(params, "confirm"):
        return create_pending_action("browser_control", pending_params, settings=settings)
    return browser_control(settings, **pending_params)


def _desktop_ui_action(settings: Settings, params: dict[str, Any]) -> dict:
    pending_params = {
        "app_name": _str(params, "app_name") or _str(params, "app"),
        "command": _str(params, "command"),
        "element_id": _str(params, "element_id"),
        "target_element_id": _str(params, "target_element_id"),
        "text": _str(params, "text"),
        "direction": _str(params, "direction", "down"),
        "amount": _int(params, "amount", 1),
        "path": _str(params, "path"),
        "window_index": _int(params, "window_index", 1),
    }
    return create_pending_action("accessibility_action", pending_params, settings=settings)


def _str(params: dict[str, Any], key: str, default: str = "") -> str:
    return str(params.get(key, default))


def _bool(params: dict[str, Any], key: str, default: bool = False) -> bool:
    value = params.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _int(params: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(params.get(key, default))
    except (TypeError, ValueError):
        return default


_HANDLERS = {
    ("desktop", "screenshot"): lambda settings, params: capture_display(
        _int(params, "display_id", 1), _int(params, "max_width", 1600)
    ),
    ("desktop", "window_screenshot"): lambda settings, params: capture_window(
        settings,
        _str(params, "app_name") or _str(params, "app"),
        _int(params, "window_index", 1),
        _int(params, "max_width", 1600),
    ),
    ("desktop", "ocr"): lambda settings, params: ocr_desktop(
        settings,
        _str(params, "source", "display"),
        _str(params, "app_name") or _str(params, "app"),
        _int(params, "window_index", 1),
        _int(params, "display_id", 1),
        _str(params, "languages", "zh-Hans,en-US"),
    ),
    ("desktop", "ui_tree"): lambda settings, params: accessibility_tree(
        settings,
        _str(params, "app_name") or _str(params, "app"),
        _int(params, "window_index", 1),
        _int(params, "max_depth", 5),
        _int(params, "max_elements", 200),
        _bool(params, "include_values", False),
    ),
    ("desktop", "ui_action"): _desktop_ui_action,
    ("desktop", "capabilities"): lambda settings, params: accessibility_capabilities(
        settings, _str(params, "app_name") or _str(params, "app")
    ),
    ("app", "open"): _app_open,
    ("app", "close"): _app_close,
    ("app", "focus"): _app_focus,
    ("app", "status"): _app_status,
    ("app", "capabilities"): _app_capabilities,
    ("music", "open"): _music_open,
    ("music", "play"): _music_play,
    ("music", "pause"): _music_pause,
    ("music", "toggle"): _music_toggle,
    ("music", "next"): _music_next,
    ("music", "previous"): _music_previous,
    ("music", "search"): _music_search,
    ("music", "search_app"): _music_search_app,
    ("music", "status"): _music_status,
    ("music", "volume"): _music_volume,
    ("music", "capabilities"): _music_capabilities,
    ("docs", "remember"): _docs_remember,
    ("docs", "search"): _docs_search,
    ("docs", "create"): _docs_create,
    ("docs", "open"): _docs_open,
    ("docs", "append"): _docs_append,
    ("docs", "daily"): _docs_daily,
    ("ai", "open"): _ai_open,
    ("ai", "send"): _ai_send,
    ("ai", "continue"): _ai_continue,
    ("ai", "status"): _ai_status,
    ("ai", "focus"): lambda settings, params: focus_cc(_str(params, "session_id", "default")),
    ("ai", "stop"): _ai_stop,
    ("ai", "slash"): _ai_slash,
    ("ai", "model"): _ai_model,
    ("dev", "open"): lambda settings, params: _dev_xcode(settings, params, "open"),
    ("dev", "build"): lambda settings, params: _dev_xcode(settings, params, "build"),
    ("dev", "test"): lambda settings, params: _dev_xcode(settings, params, "test"),
    ("dev", "clean"): lambda settings, params: _dev_xcode(settings, params, "clean"),
    ("dev", "errors"): lambda settings, params: xcode_last_errors(_int(params, "limit", 20)),
    ("browser", "open"): _browser_open,
    ("browser", "search"): _browser_search,
    ("browser", "tabs"): _browser_tabs,
    ("browser", "current"): _browser_current,
    ("browser", "control"): _browser_control,
    ("browser", "capabilities"): _browser_capabilities,
    ("system", "open"): lambda settings, params: finder_open_path(settings, _str(params, "path"), False),
    ("system", "reveal"): lambda settings, params: finder_open_path(settings, _str(params, "path"), True),
    ("system", "clipboard_get"): lambda settings, params: clipboard_get(),
    ("system", "clipboard_set"): lambda settings, params: clipboard_set(_str(params, "text")),
}
