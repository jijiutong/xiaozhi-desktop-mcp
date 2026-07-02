from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from ..config import Settings
from ..responses import fail, ok
from .apps import close_app
from .cc_session import (
    close_terminal,
    send_decision,
    send_instruction,
    send_slash_command,
    stop_session,
    switch_model,
)

ALLOWED_ACTION_TYPES = frozenset(
    {
        "app_close",
        "cc_close_terminal",
        "cc_continue",
        "cc_send_instruction",
        "cc_send_slash_command",
        "cc_stop",
        "cc_switch_model",
        "desktop_ask_cc",
        "desktop_ask_cc_project",
    }
)

_ALLOWED_PARAM_KEYS: dict[str, frozenset[str]] = {
    "app_close": frozenset({"app_name"}),
    "cc_close_terminal": frozenset({"terminal"}),
    "cc_continue": frozenset({"session_id", "allow_frontmost"}),
    "cc_send_instruction": frozenset({"text", "session_id", "allow_frontmost"}),
    "cc_send_slash_command": frozenset({"command", "args", "session_id", "allow_frontmost"}),
    "cc_stop": frozenset({"session_id", "allow_frontmost"}),
    "cc_switch_model": frozenset({"model", "session_id", "allow_frontmost"}),
    "desktop_ask_cc": frozenset(
        {"text", "project_path", "session_id", "cli", "terminal", "open_if_needed", "allow_frontmost"}
    ),
    "desktop_ask_cc_project": frozenset(
        {"project", "text", "session_id", "cli", "terminal", "open_if_needed", "allow_frontmost"}
    ),
}


@dataclass
class PendingAction:
    action_id: str
    action_type: str
    params: dict[str, Any]
    title: str
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: datetime | None = None
    result: dict | None = None


_pending_actions: dict[str, PendingAction] = {}


def create_pending_action(action_type: str, params: dict | None = None, title: str = "") -> dict:
    """Create a pending action that can be confirmed later."""
    normalized = action_type.strip()
    if normalized not in ALLOWED_ACTION_TYPES:
        allowed = ", ".join(sorted(ALLOWED_ACTION_TYPES))
        return fail(
            f"pending action type is not allowlisted: {normalized}. allowed: {allowed}",
            "这个待确认动作类型不在白名单里，我没有创建。",
        )
    clean_params = dict(params or {})
    validation_error = _validate_params(normalized, clean_params)
    if validation_error:
        return fail(validation_error, "待确认动作参数不完整或格式不对，我没有创建。")
    action_id = uuid4().hex[:12]
    clean_title = title.strip() or _default_title(normalized, clean_params)
    action = PendingAction(
        action_id=action_id,
        action_type=normalized,
        params=clean_params,
        title=clean_title,
    )
    _pending_actions[action_id] = action
    return ok(
        {"action": _serialize(action)},
        f"已创建待确认动作：{clean_title}。",
        "created pending action",
    )


def list_pending_actions(status: str = "pending") -> dict:
    """List pending actions by status. Empty status means all actions."""
    normalized = status.strip().lower()
    actions = []
    for action in sorted(_pending_actions.values(), key=lambda item: item.created_at):
        if normalized and action.status != normalized:
            continue
        actions.append(_serialize(action))
    if normalized == "pending":
        spoken = f"当前有 {len(actions)} 个待确认动作。"
    else:
        spoken = f"查到 {len(actions)} 个动作。"
    return ok(
        {
            "count": len(actions),
            "actions": actions,
        },
        spoken,
        "listed pending actions",
    )


def cancel_pending_action(action_id: str) -> dict:
    """Cancel a pending action without executing it."""
    action = _pending_actions.get(action_id.strip())
    if not action:
        return fail("pending action not found", "我没有找到这个待确认动作。")
    if action.status != "pending":
        return fail(f"pending action is already {action.status}", "这个动作已经处理过了。")
    action.status = "cancelled"
    action.resolved_at = datetime.now()
    return ok(
        {"action": _serialize(action)},
        f"已取消：{action.title}。",
        "cancelled pending action",
    )


def confirm_pending_action(settings: Settings, action_id: str) -> dict:
    """Confirm and execute a pending action."""
    action = _pending_actions.get(action_id.strip())
    if not action:
        return fail("pending action not found", "我没有找到这个待确认动作。")
    if action.status != "pending":
        return fail(f"pending action is already {action.status}", "这个动作已经处理过了。")
    result = _execute(settings, action)
    action.result = result
    action.resolved_at = datetime.now()
    action.status = "completed" if result.get("success") else "failed"
    response = ok(
        {
            "action": _serialize(action),
            "execution_result": result,
        },
        f"已确认并执行：{action.title}。" if result.get("success") else f"确认后执行失败：{action.title}。",
        "confirmed pending action",
    )
    if not result.get("success"):
        response["success"] = False
        response["error"] = result.get("error", "pending action execution failed")
        response["error_spoken_message"] = result.get("error_spoken_message", "确认后执行失败。")
    return response


def _execute(settings: Settings, action: PendingAction) -> dict:
    params = action.params
    if action.action_type == "app_close":
        return close_app(settings, str(params.get("app_name", "")))
    if action.action_type == "cc_close_terminal":
        return close_terminal(str(params.get("terminal", "Terminal")))
    if action.action_type == "cc_continue":
        return send_decision(
            settings,
            "yes",
            str(params.get("session_id", "default")),
            True,
            bool(params.get("allow_frontmost", False)),
        )
    if action.action_type == "cc_send_instruction":
        return send_instruction(
            settings,
            str(params.get("text", "")),
            str(params.get("session_id", "default")),
            bool(params.get("allow_frontmost", False)),
        )
    if action.action_type == "cc_send_slash_command":
        return send_slash_command(
            settings,
            str(params.get("command", "")),
            str(params.get("args", "")),
            str(params.get("session_id", "default")),
            True,
            bool(params.get("allow_frontmost", False)),
        )
    if action.action_type == "cc_stop":
        return stop_session(str(params.get("session_id", "default")), bool(params.get("allow_frontmost", False)))
    if action.action_type == "cc_switch_model":
        return switch_model(
            settings,
            str(params.get("model", "")),
            str(params.get("session_id", "default")),
            True,
            bool(params.get("allow_frontmost", False)),
        )
    if action.action_type == "desktop_ask_cc":
        from .workflows import ask_cc

        return ask_cc(
            settings,
            str(params.get("text", "")),
            str(params.get("project_path", "")),
            str(params.get("session_id", "default")),
            str(params.get("cli", "")),
            str(params.get("terminal", "Terminal")),
            bool(params.get("open_if_needed", True)),
            bool(params.get("allow_frontmost", False)),
        )
    if action.action_type == "desktop_ask_cc_project":
        from .projects import ask_cc_project

        return ask_cc_project(
            settings,
            str(params.get("project", "")),
            str(params.get("text", "")),
            str(params.get("session_id", "default")),
            str(params.get("cli", "")),
            str(params.get("terminal", "Terminal")),
            bool(params.get("open_if_needed", True)),
            bool(params.get("allow_frontmost", False)),
        )
    return fail(f"unsupported pending action type: {action.action_type}")


def _serialize(action: PendingAction) -> dict:
    result = {
        "action_id": action.action_id,
        "action_type": action.action_type,
        "params": action.params,
        "title": action.title,
        "status": action.status,
        "created_at": action.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if action.resolved_at:
        result["resolved_at"] = action.resolved_at.strftime("%Y-%m-%d %H:%M:%S")
    if action.result is not None:
        result["result"] = action.result
    return result


def _validate_params(action_type: str, params: dict[str, Any]) -> str:
    allowed_keys = _ALLOWED_PARAM_KEYS.get(action_type, frozenset())
    unknown_keys = sorted(set(params) - allowed_keys)
    if unknown_keys:
        return f"unknown params for {action_type}: {', '.join(unknown_keys)}"
    required_fields = {
        "app_close": ("app_name",),
        "cc_send_instruction": ("text",),
        "cc_send_slash_command": ("command",),
        "cc_switch_model": ("model",),
        "desktop_ask_cc": ("text",),
        "desktop_ask_cc_project": ("project", "text"),
    }.get(action_type, ())
    for field_name in required_fields:
        if not str(params.get(field_name, "")).strip():
            return f"missing required param for {action_type}: {field_name}"
    if action_type == "cc_send_slash_command" and not str(params.get("command", "")).strip().startswith("/"):
        return "slash command must start with /"
    return ""


def _default_title(action_type: str, params: dict[str, Any]) -> str:
    if action_type == "app_close":
        return f"关闭 {params.get('app_name', 'App')}"
    if action_type == "cc_close_terminal":
        return f"关闭 {params.get('terminal', 'Terminal')} 窗口"
    if action_type == "cc_continue":
        return "让 Claude Code 继续"
    if action_type == "cc_send_instruction":
        return "发送任务给 Claude Code"
    if action_type == "cc_send_slash_command":
        return f"发送命令 {params.get('command', '')}"
    if action_type == "cc_stop":
        return "退出 Claude Code"
    if action_type == "cc_switch_model":
        return f"切换模型到 {params.get('model', '')}"
    if action_type == "desktop_ask_cc":
        return "发送任务给 Claude Code"
    if action_type == "desktop_ask_cc_project":
        return f"发送任务到项目 {params.get('project', '')}"
    return action_type
