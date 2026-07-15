from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from ..action_registry import pending_action_types, pending_spec
from ..config import Settings
from ..responses import fail, ok
from ..storage import PendingActionStore
from .apps import close_app
from .cc_session import (
    close_terminal,
    send_decision,
    send_instruction,
    send_slash_command,
    stop_session,
    switch_model,
)

ALLOWED_ACTION_TYPES = pending_action_types()


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
_AX_ELEMENT_ID = re.compile(r"^ax:(?:root|[1-9]\d*(?:\.[1-9]\d*)*)$")
_AX_COMMANDS = frozenset({"click", "input", "scroll", "drag", "menu_select", "file_dialog_choose"})


def create_pending_action(
    action_type: str,
    params: dict | None = None,
    title: str = "",
    *,
    settings: Settings | None = None,
) -> dict:
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
    if settings is not None:
        record = PendingActionStore(settings).create(action_id, normalized, clean_params, clean_title)
        return ok(
            {"action": record},
            f"已创建待确认动作：{clean_title}。",
            "created pending action",
        )
    _pending_actions[action_id] = action
    return ok(
        {"action": _serialize(action)},
        f"已创建待确认动作：{clean_title}。",
        "created pending action",
    )


def list_pending_actions(status: str = "pending", *, settings: Settings | None = None) -> dict:
    """List pending actions by status. Empty status means all actions."""
    normalized = status.strip().lower()
    if settings is not None:
        actions = PendingActionStore(settings).list(normalized)
    else:
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


def cancel_pending_action(action_id: str, *, settings: Settings | None = None) -> dict:
    """Cancel a pending action without executing it."""
    if settings is not None:
        record, error = PendingActionStore(settings).cancel(action_id.strip())
        if not record:
            return fail("pending action not found", "我没有找到这个待确认动作。")
        if error:
            return fail(f"pending action is already {error}", "这个动作已经处理过了。")
        return ok(
            {"action": record},
            f"已取消：{record['title']}。",
            "cancelled pending action",
        )
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
    clean_id = action_id.strip()
    store = PendingActionStore(settings)
    record, claim_error = store.claim(clean_id)
    if record:
        if claim_error:
            return fail(f"pending action is already {claim_error}", "这个动作已经处理过了。")
        action = _from_record(record)
        result = _execute(settings, action)
        status = "completed" if result.get("success") else "failed"
        resolved = store.resolve(clean_id, status, result) or record
        return _confirmation_response(resolved, result)

    action = _pending_actions.get(clean_id)
    if not action:
        return fail("pending action not found", "我没有找到这个待确认动作。")
    if action.status != "pending":
        return fail(f"pending action is already {action.status}", "这个动作已经处理过了。")
    result = _execute(settings, action)
    action.result = result
    action.resolved_at = datetime.now()
    action.status = "completed" if result.get("success") else "failed"
    response = _confirmation_response(_serialize(action), result)
    return response


def _confirmation_response(action: dict, result: dict) -> dict:
    title = action.get("title", "待确认动作")
    response = ok(
        {"action": action, "execution_result": result},
        f"已确认并执行：{title}。" if result.get("success") else f"确认后执行失败：{title}。",
        "confirmed pending action",
    )
    if not result.get("success"):
        response["success"] = False
        response["error"] = result.get("error", "pending action execution failed")
        response["error_spoken_message"] = result.get("error_spoken_message", "确认后执行失败。")
    return response


def _from_record(record: dict) -> PendingAction:
    return PendingAction(
        action_id=str(record["action_id"]),
        action_type=str(record["action_type"]),
        params=dict(record.get("params", {})),
        title=str(record.get("title", "")),
        status=str(record.get("status", "executing")),
        created_at=datetime.fromisoformat(str(record["created_at"])),
    )


def _execute(settings: Settings, action: PendingAction) -> dict:
    params = action.params
    if action.action_type == "accessibility_action":
        from .accessibility import accessibility_action

        return accessibility_action(
            settings,
            str(params.get("app_name", "")),
            str(params.get("command", "")),
            str(params.get("element_id", "")),
            str(params.get("target_element_id", "")),
            str(params.get("text", "")),
            str(params.get("direction", "down")),
            int(params.get("amount", 1)),
            str(params.get("path", "")),
            int(params.get("window_index", 1)),
        )
    if action.action_type == "app_close":
        return close_app(settings, str(params.get("app_name", "")))
    if action.action_type == "browser_control":
        from .browser import browser_control

        return browser_control(
            settings,
            str(params.get("command", "")),
            str(params.get("app_name", "")),
            int(params.get("window_index", 1)),
            int(params.get("tab_index", 1)),
        )
    if action.action_type == "music_search_app":
        from .music import music_search_app

        return music_search_app(
            settings,
            str(params.get("query", "")),
            str(params.get("app_name", "")),
        )
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
    if action.action_type in {"xcode_build", "xcode_clean", "xcode_test"}:
        from .xcode import xcode_build, xcode_clean, xcode_test

        runner = {
            "xcode_build": xcode_build,
            "xcode_clean": xcode_clean,
            "xcode_test": xcode_test,
        }[action.action_type]
        return runner(
            settings,
            str(params.get("project_path", "")),
            str(params.get("xcode_path", "")),
            str(params.get("scheme", "")),
            str(params.get("configuration", "")),
            str(params.get("destination", "")),
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
    spec = pending_spec(action_type)
    allowed_keys = spec.pending_param_keys if spec else frozenset()
    unknown_keys = sorted(set(params) - allowed_keys)
    if unknown_keys:
        return f"unknown params for {action_type}: {', '.join(unknown_keys)}"
    required_fields = spec.pending_required_params if spec else ()
    for field_name in required_fields:
        if not str(params.get(field_name, "")).strip():
            return f"missing required param for {action_type}: {field_name}"
    if action_type == "cc_send_slash_command" and not str(params.get("command", "")).strip().startswith("/"):
        return "slash command must start with /"
    if action_type == "accessibility_action":
        command = str(params.get("command", "")).strip().lower().replace("-", "_")
        element_id = str(params.get("element_id", "")).strip()
        target_element_id = str(params.get("target_element_id", "")).strip()
        if command not in _AX_COMMANDS:
            return f"unsupported accessibility action: {command}"
        if command in {"click", "input", "menu_select", "drag"} and not element_id:
            return f"element_id is required for {command}"
        if element_id and not _AX_ELEMENT_ID.fullmatch(element_id):
            return "invalid element_id"
        if target_element_id and not _AX_ELEMENT_ID.fullmatch(target_element_id):
            return "invalid target_element_id"
        if command == "drag" and not target_element_id:
            return "target_element_id is required for drag"
        if command == "scroll":
            direction = str(params.get("direction", "down")).strip().lower()
            if direction not in {"up", "down", "left", "right"}:
                return "direction must be up, down, left, or right"
            try:
                amount = int(params.get("amount", 1))
            except (TypeError, ValueError):
                return "amount must be an integer"
            if not 1 <= amount <= 20:
                return "amount must be between 1 and 20"
        if command == "file_dialog_choose" and not str(params.get("path", "")).strip():
            return "path is required for file_dialog_choose"
        if len(str(params.get("text", ""))) > 20000:
            return "text exceeds 20000 characters"
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
    if action_type == "xcode_build":
        return "执行 Xcode build"
    if action_type == "xcode_clean":
        return "执行 Xcode clean"
    if action_type == "xcode_test":
        return "执行 Xcode test"
    return action_type
