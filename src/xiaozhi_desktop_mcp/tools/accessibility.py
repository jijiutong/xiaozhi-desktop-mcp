from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from ..config import Settings
from ..responses import fail, ok
from ..safety import SafetyError
from .apps import resolve_app_name
from .finder import resolve_allowed_path

_OSASCRIPT = "/usr/bin/osascript"
_ACCESSIBILITY_SCRIPT = Path(__file__).resolve().parent.parent / "macos_accessibility.js"
_ELEMENT_ID_PATTERN = re.compile(r"^ax:(?:root|[1-9]\d*(?:\.[1-9]\d*)*)$")
_ACTIONS = frozenset({"click", "input", "scroll", "drag", "menu_select", "file_dialog_choose"})


def accessibility_capabilities(settings: Settings, app_name: str) -> dict:
    """Describe semantic observation and action support for an allowlisted app."""
    try:
        app = resolve_app_name(settings, app_name)
    except SafetyError as error:
        return fail(str(error), f"{app_name.strip() or '这个 App'} 不在白名单里。")
    return ok(
        {
            "app": app,
            "read_capabilities": ["screenshot", "window_screenshot", "ocr", "tree"],
            "action_capabilities": sorted(_ACTIONS),
            "actions_require_confirmation": True,
            "element_id_format": "ax:<1-based child path>, for example ax:1.2",
            "permissions": ["Screen Recording", "Accessibility", "Automation:System Events"],
        },
        "已返回桌面感知和界面操作能力。",
        "returned accessibility capabilities",
    )


def accessibility_tree(
    settings: Settings,
    app_name: str,
    window_index: int = 1,
    max_depth: int = 5,
    max_elements: int = 200,
    include_values: bool = False,
) -> dict:
    """Return a bounded semantic tree for a window in an allowlisted app."""
    try:
        app = resolve_app_name(settings, app_name)
    except SafetyError as error:
        return fail(str(error), f"{app_name.strip() or '这个 App'} 不在白名单里，我没有读取界面。")
    if window_index < 1 or window_index > 50:
        return fail("window_index must be between 1 and 50", "窗口编号不正确。")
    if max_depth < 1 or max_depth > 12:
        return fail("max_depth must be between 1 and 12", "界面树深度设置不正确。")
    if max_elements < 1 or max_elements > 1000:
        return fail("max_elements must be between 1 and 1000", "界面元素数量设置不正确。")

    process_names = _process_names(settings, app)
    payload = {
        "command": "tree",
        "process_names": process_names,
        "window_index": window_index,
        "max_depth": max_depth,
        "max_elements": max_elements,
        "include_values": include_values,
    }
    completed = _run_accessibility(payload)
    if completed.returncode != 0:
        error = completed.stderr.strip() or completed.stdout.strip() or "accessibility tree failed"
        return fail(error, "读取界面结构失败，请检查辅助功能权限。", {"app": app})
    try:
        result = json.loads(completed.stdout)
        elements = result.get("elements", [])
        if not isinstance(elements, list):
            raise ValueError("elements is not an array")
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        return fail(f"invalid accessibility response: {error}", "界面结构返回格式不正确。", {"app": app})

    return ok(
        {
            "app": app,
            "process_name": result.get("process_name", ""),
            "window_index": window_index,
            "window": result.get("window", {}),
            "elements": elements,
            "count": len(elements),
            "truncated": bool(result.get("truncated")),
            "include_values": include_values,
        },
        f"已读取 {app} 的 {len(elements)} 个界面元素。",
        "read accessibility tree",
    )


def accessibility_action(
    settings: Settings,
    app_name: str,
    command: str,
    element_id: str = "",
    target_element_id: str = "",
    text: str = "",
    direction: str = "down",
    amount: int = 1,
    path: str = "",
    window_index: int = 1,
) -> dict:
    """Perform a confirmed semantic action on an Accessibility element."""
    try:
        app = resolve_app_name(settings, app_name)
    except SafetyError as error:
        return fail(str(error), f"{app_name.strip() or '这个 App'} 不在白名单里，我没有操作。")
    normalized = command.strip().lower().replace("-", "_")
    if normalized not in _ACTIONS:
        return fail(f"unsupported accessibility action: {command}", "这个界面操作还不支持。")
    if normalized in {"click", "input", "menu_select", "drag"} and not element_id.strip():
        return fail(f"element_id is required for {normalized}", "这个界面操作需要明确的元素编号。")
    if len(text) > 20000:
        return fail("text exceeds 20000 characters", "输入内容太长，我没有执行。")
    if normalized == "scroll" and not 1 <= amount <= 20:
        return fail("amount must be between 1 and 20", "滚动次数需要在 1 到 20 之间。")
    resolved_element_id = element_id.strip() or "ax:root"
    if not _ELEMENT_ID_PATTERN.fullmatch(resolved_element_id):
        return fail("invalid element_id", "界面元素编号不正确。")
    if target_element_id and not _ELEMENT_ID_PATTERN.fullmatch(target_element_id.strip()):
        return fail("invalid target_element_id", "拖拽目标元素编号不正确。")
    if normalized == "drag" and not target_element_id.strip():
        return fail("target_element_id is required for drag", "拖拽操作需要目标元素编号。")
    if window_index < 1 or window_index > 50:
        return fail("window_index must be between 1 and 50", "窗口编号不正确。")
    resolved_path = path
    if normalized == "file_dialog_choose":
        if not path.strip():
            return fail("path is required for file_dialog_choose", "文件对话框需要一个路径。")
        try:
            target_path = resolve_allowed_path(settings, path)
        except SafetyError as error:
            return fail(str(error), "这个路径不在允许范围内，我没有选择。")
        if not target_path.exists():
            return fail("path does not exist", "这个路径不存在，我没有选择。")
        resolved_path = str(target_path)

    payload = {
        "command": "action",
        "action": normalized,
        "process_names": _process_names(settings, app),
        "window_index": window_index,
        "element_id": resolved_element_id,
        "target_element_id": target_element_id.strip(),
        "text": text,
        "direction": direction.strip().lower(),
        "amount": amount,
        "path": resolved_path,
    }
    completed = _run_accessibility(payload)
    if completed.returncode != 0:
        error = completed.stderr.strip() or completed.stdout.strip() or "accessibility action failed"
        return fail(error, "界面操作失败，请重新读取界面或检查辅助功能权限。", {"app": app})
    try:
        result = json.loads(completed.stdout)
        if not isinstance(result, dict):
            raise ValueError("result is not an object")
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        return fail(f"invalid accessibility action response: {error}", "界面操作返回格式不正确。", {"app": app})
    return ok(
        {"app": app, "window_index": window_index, **result},
        f"已在 {app} 执行界面操作。",
        "performed accessibility action",
    )


def _process_names(settings: Settings, app: str) -> list[str]:
    aliases = settings.app_process_aliases.get(app) or settings.app_process_aliases.get(app.lower()) or ()
    return list(dict.fromkeys((app, *aliases)))


def _run_accessibility(payload: dict) -> subprocess.CompletedProcess[str]:
    command = [_OSASCRIPT, "-l", "JavaScript", str(_ACCESSIBILITY_SCRIPT), json.dumps(payload, ensure_ascii=False)]
    try:
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, 124, "", "accessibility command timed out after 30 seconds")
    except OSError as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))
