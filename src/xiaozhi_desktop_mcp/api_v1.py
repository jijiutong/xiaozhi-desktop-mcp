from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from .action_registry import api_action_specs
from .config import Settings
from .responses import fail, ok
from .tools.apps import app_status, close_app, focus_app, open_app
from .tools.browser import browser_open_url, browser_search
from .tools.catalog import tool_catalog
from .tools.cc_session import cleanup_sessions, send_slash_command, switch_model
from .tools.diagnostics import config_summary, health_detail
from .tools.intent import desktop_intent, desktop_intent_catalog
from .tools.music import music_control, music_search
from .tools.obsidian import append_daily_note, append_note, create_note, open_note, recent_memories, search_notes
from .tools.pending_actions import (
    cancel_pending_action,
    confirm_pending_action,
    create_pending_action,
    list_pending_actions,
)
from .tools.projects import ask_cc_project, list_projects, open_cc_project_named, resolve_project
from .tools.workflows import (
    ask_cc,
    check_cc,
    continue_cc,
    focus_cc,
    open_cc_project,
    remember,
    stop_cc,
)
from .tools.xcode import open_xcode_project, xcode_build, xcode_clean, xcode_last_errors, xcode_test

ActionHandler = Callable[[Settings, dict[str, Any]], dict]
logger = logging.getLogger(__name__)


def dispatch(settings: Settings, action: str, params: dict | None = None, request_id: str = "") -> dict:
    """Dispatch a language-agnostic HTTP action and wrap the result in a stable envelope."""
    started_at = time.monotonic()
    normalized = _normalize_action(action)
    handler = _ACTION_HANDLERS.get(normalized)
    if handler is None:
        result = fail(
            f"unknown action: {action}",
            "未知动作，我没有执行。",
            {"known_actions": sorted(_ACTION_HANDLERS)},
        )
    else:
        try:
            result = handler(settings, dict(params or {}))
        except TypeError as exc:
            result = fail(f"invalid params for action {normalized}: {exc}", "参数不完整或格式不对，我没有执行。")
        except Exception:
            logger.exception("action %s failed", normalized)
            result = fail(f"action {normalized} failed", "执行动作时发生异常。")
    envelope = _envelope(normalized or action, result, request_id)
    _log_dispatch(normalized or action, envelope, params or {}, started_at)
    return envelope


def actions_catalog() -> dict:
    """Return machine-friendly action definitions for API clients."""
    actions = [spec.catalog_entry() for spec in api_action_specs()]
    return ok(
        {"version": "v1", "actions": actions, "count": len(actions)},
        f"已返回 {len(actions)} 个 API 动作说明。",
        "returned api v1 actions",
    )


def api_health(settings: Settings) -> dict:
    """Return a structured API health response."""
    detail = health_detail(settings)
    return _envelope("health", detail, "")


def _envelope(action: str, result: dict, request_id: str) -> dict:
    success = bool(result.get("success"))
    data = {
        key: value
        for key, value in result.items()
        if key not in {"success", "spoken_message", "error_spoken_message", "error"}
    }
    return {
        "success": success,
        "request_id": request_id,
        "action": action,
        "spoken_message": result.get("spoken_message", ""),
        "error_spoken_message": result.get("error_spoken_message", ""),
        "error": result.get("error", ""),
        "data": data,
    }


def _normalize_action(action: str) -> str:
    return action.strip().lower().replace("-", "_")


def _log_dispatch(action: str, envelope: dict, params: dict[str, Any], started_at: float) -> None:
    cost_ms = int((time.monotonic() - started_at) * 1000)
    success = bool(envelope.get("success"))
    log_method = logger.info if success else logger.warning
    log_method(
        "desktop_mcp_action request_id=%s action=%s success=%s cost_ms=%s param_keys=%s error=%s",
        envelope.get("request_id", ""),
        action,
        success,
        cost_ms,
        sorted(params.keys()),
        envelope.get("error", ""),
    )


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


def _remember(settings: Settings, params: dict[str, Any]) -> dict:
    return remember(settings, _str(params, "text"), _str(params, "tags", "xiaozhi,voice-memory"))


def _app_close(settings: Settings, params: dict[str, Any]) -> dict:
    pending_params = {"app_name": _str(params, "app_name")}
    return _confirm_or_pending(
        params,
        "app_close",
        pending_params,
        lambda: close_app(settings, pending_params["app_name"]),
        f"关闭 {pending_params['app_name']}",
    )


def _open_cc_project(settings: Settings, params: dict[str, Any]) -> dict:
    return open_cc_project(
        settings,
        _str(params, "project_path"),
        _str(params, "session_id", "default"),
        _str(params, "cli"),
        _str(params, "terminal", "Terminal"),
        _str(params, "cli_args"),
    )


def _open_cc_project_named(settings: Settings, params: dict[str, Any]) -> dict:
    return open_cc_project_named(
        settings,
        _str(params, "project"),
        _str(params, "session_id", "default"),
        _str(params, "cli"),
        _str(params, "terminal", "Terminal"),
        _str(params, "cli_args"),
    )


def _confirm_or_pending(
    params: dict[str, Any],
    action_type: str,
    pending_params: dict[str, Any],
    runner: Callable[[], dict],
    title: str = "",
) -> dict:
    if not _bool(params, "confirm"):
        return create_pending_action(action_type, pending_params, title)
    return runner()


def _ask_cc(settings: Settings, params: dict[str, Any]) -> dict:
    pending_params = {
        "text": _str(params, "text"),
        "project_path": _str(params, "project_path"),
        "session_id": _str(params, "session_id", "default"),
        "cli": _str(params, "cli"),
        "terminal": _str(params, "terminal", "Terminal"),
        "open_if_needed": _bool(params, "open_if_needed", True),
        "allow_frontmost": _bool(params, "allow_frontmost", False),
    }
    return _confirm_or_pending(
        params,
        "desktop_ask_cc",
        pending_params,
        lambda: ask_cc(
            settings,
            pending_params["text"],
            pending_params["project_path"],
            pending_params["session_id"],
            pending_params["cli"],
            pending_params["terminal"],
            bool(pending_params["open_if_needed"]),
            bool(pending_params["allow_frontmost"]),
        ),
        "发送任务给 Claude Code",
    )


def _ask_cc_project(settings: Settings, params: dict[str, Any]) -> dict:
    pending_params = {
        "project": _str(params, "project"),
        "text": _str(params, "text"),
        "session_id": _str(params, "session_id", "default"),
        "cli": _str(params, "cli"),
        "terminal": _str(params, "terminal", "Terminal"),
        "open_if_needed": _bool(params, "open_if_needed", True),
        "allow_frontmost": _bool(params, "allow_frontmost", False),
    }
    return _confirm_or_pending(
        params,
        "desktop_ask_cc_project",
        pending_params,
        lambda: ask_cc_project(
            settings,
            pending_params["project"],
            pending_params["text"],
            pending_params["session_id"],
            pending_params["cli"],
            pending_params["terminal"],
            bool(pending_params["open_if_needed"]),
            bool(pending_params["allow_frontmost"]),
        ),
        "按项目发送任务给 Claude Code",
    )


def _continue_cc(settings: Settings, params: dict[str, Any]) -> dict:
    session_id = _str(params, "session_id", "default")
    allow_frontmost = _bool(params, "allow_frontmost", False)
    pending_params = {"session_id": session_id, "allow_frontmost": allow_frontmost}
    return _confirm_or_pending(
        params,
        "cc_continue",
        pending_params,
        lambda: continue_cc(settings, session_id, True, allow_frontmost),
        "让 Claude Code 继续",
    )


def _cc_send_slash_command(settings: Settings, params: dict[str, Any]) -> dict:
    pending_params = {
        "command": _str(params, "command"),
        "args": _str(params, "args"),
        "session_id": _str(params, "session_id", "default"),
        "allow_frontmost": _bool(params, "allow_frontmost", False),
    }
    return _confirm_or_pending(
        params,
        "cc_send_slash_command",
        pending_params,
        lambda: send_slash_command(
            settings,
            pending_params["command"],
            pending_params["args"],
            pending_params["session_id"],
            True,
            bool(pending_params["allow_frontmost"]),
        ),
        f"发送命令 {pending_params['command']}",
    )


def _cc_switch_model(settings: Settings, params: dict[str, Any]) -> dict:
    pending_params = {
        "model": _str(params, "model"),
        "session_id": _str(params, "session_id", "default"),
        "allow_frontmost": _bool(params, "allow_frontmost", False),
    }
    return _confirm_or_pending(
        params,
        "cc_switch_model",
        pending_params,
        lambda: switch_model(
            settings,
            pending_params["model"],
            pending_params["session_id"],
            True,
            bool(pending_params["allow_frontmost"]),
        ),
        f"切换模型到 {pending_params['model']}",
    )


def _stop_cc(settings: Settings, params: dict[str, Any]) -> dict:
    session_id = _str(params, "session_id", "default")
    allow_frontmost = _bool(params, "allow_frontmost", False)
    pending_params = {"session_id": session_id, "allow_frontmost": allow_frontmost}
    return _confirm_or_pending(
        params,
        "cc_stop",
        pending_params,
        lambda: stop_cc(session_id, allow_frontmost),
        "停止 Claude Code 会话",
    )


def _xcode_action(action_type: str, params: dict[str, Any], runner) -> dict:
    pending_params = {
        "project_path": _str(params, "project_path"),
        "xcode_path": _str(params, "xcode_path"),
        "scheme": _str(params, "scheme"),
        "configuration": _str(params, "configuration"),
        "destination": _str(params, "destination"),
    }
    return _confirm_or_pending(params, action_type, pending_params, lambda: runner(**pending_params))


def _pending_create(settings: Settings, params: dict[str, Any]) -> dict:
    pending_params = params.get("params", {})
    return create_pending_action(
        _str(params, "action_type"),
        pending_params if isinstance(pending_params, dict) else {},
        _str(params, "title"),
    )


_ACTION_HANDLERS: dict[str, ActionHandler] = {
    "remember": _remember,
    "app_open": lambda settings, params: open_app(settings, _str(params, "app_name")),
    "app_focus": lambda settings, params: focus_app(settings, _str(params, "app_name")),
    "app_status": lambda settings, params: app_status(settings, _str(params, "app_name")),
    "app_close": _app_close,
    "open_cc_project": _open_cc_project,
    "open_cc_project_named": _open_cc_project_named,
    "ask_cc": _ask_cc,
    "ask_cc_project": _ask_cc_project,
    "check_cc": lambda settings, params: check_cc(
        settings,
        _str(params, "session_id", "default"),
        _int(params, "max_chars"),
    ),
    "cc_send_slash_command": _cc_send_slash_command,
    "cc_switch_model": _cc_switch_model,
    "continue_cc": _continue_cc,
    "focus_cc": lambda settings, params: focus_cc(_str(params, "session_id", "default")),
    "stop_cc": _stop_cc,
    "search_obsidian": lambda settings, params: search_notes(
        settings,
        _str(params, "query"),
        _int(params, "limit", 5),
    ),
    "create_note": lambda settings, params: create_note(
        settings,
        _str(params, "note_path"),
        _str(params, "text"),
        _bool(params, "overwrite", False),
    ),
    "open_note": lambda settings, params: open_note(settings, _str(params, "note_path")),
    "append_note": lambda settings, params: append_note(
        settings,
        _str(params, "note_path"),
        _str(params, "text"),
        _str(params, "heading"),
    ),
    "append_daily_note": lambda settings, params: append_daily_note(
        settings,
        _str(params, "text"),
        _str(params, "date"),
        _str(params, "folder", "daily"),
    ),
    "recent_memories": lambda settings, params: recent_memories(settings, _int(params, "limit", 5)),
    "health": lambda settings, params: health_detail(settings),
    "config_summary": lambda settings, params: config_summary(settings),
    "tool_catalog": lambda settings, params: tool_catalog(),
    "category_registry": lambda settings, params: desktop_intent_catalog(settings),
    "desktop_intent": lambda settings, params: desktop_intent(
        settings,
        _str(params, "category"),
        _str(params, "intent"),
        params.get("params") if isinstance(params.get("params"), dict) else params,
    ),
    "list_projects": lambda settings, params: list_projects(settings),
    "resolve_project": lambda settings, params: resolve_project(settings, _str(params, "project")),
    "cleanup_sessions": lambda settings, params: cleanup_sessions(),
    "xcode_open_project": lambda settings, params: open_xcode_project(
        settings,
        _str(params, "project_path"),
        _str(params, "xcode_path"),
    ),
    "xcode_build": lambda settings, params: _xcode_action(
        "xcode_build",
        params,
        lambda **kwargs: xcode_build(settings, **kwargs),
    ),
    "xcode_test": lambda settings, params: _xcode_action(
        "xcode_test",
        params,
        lambda **kwargs: xcode_test(settings, **kwargs),
    ),
    "xcode_clean": lambda settings, params: _xcode_action(
        "xcode_clean",
        params,
        lambda **kwargs: xcode_clean(settings, **kwargs),
    ),
    "xcode_last_errors": lambda settings, params: xcode_last_errors(_int(params, "limit", 20)),
    "browser_open": lambda settings, params: browser_open_url(
        settings,
        _str(params, "url"),
        _str(params, "app_name") or _str(params, "app"),
    ),
    "browser_search": lambda settings, params: browser_search(
        settings,
        _str(params, "query"),
        _str(params, "app_name") or _str(params, "app"),
        _str(params, "engine", "google"),
    ),
    "music_control": lambda settings, params: music_control(
        settings,
        _str(params, "command", "toggle"),
        _str(params, "app_name") or _str(params, "app"),
    ),
    "music_search": lambda settings, params: music_search(
        settings,
        _str(params, "query"),
        _str(params, "browser"),
        _str(params, "provider"),
    ),
    "pending_create": _pending_create,
    "pending_list": lambda settings, params: list_pending_actions(_str(params, "status", "pending")),
    "pending_confirm": lambda settings, params: confirm_pending_action(settings, _str(params, "action_id")),
    "pending_cancel": lambda settings, params: cancel_pending_action(_str(params, "action_id")),
}
