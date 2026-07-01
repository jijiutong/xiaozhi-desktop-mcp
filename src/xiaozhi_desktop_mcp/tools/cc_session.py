from __future__ import annotations

import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pexpect

from ..config import Settings
from ..responses import fail, ok
from ..safety import SafetyError, ensure_allowed_cli, ensure_allowed_project, slash_policy


# 第一版只做进程内受管 session，不写日志、不做摘要。
_MAX_BUFFER_CHARS = 200_000


@dataclass
class ManagedSession:
    """一个受控的 Claude Code/Codex CLI 会话。"""

    session_id: str
    cli: str
    project_path: Path
    child: pexpect.spawn
    buffer: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    last_activity_at: datetime = field(default_factory=datetime.now)


@dataclass
class VisibleSession:
    """一个由 Terminal/iTerm 承载的可见 Claude Code/Codex 会话。"""

    session_id: str
    terminal: str
    cli: str
    project_path: Path
    title: str
    args: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_activity_at: datetime = field(default_factory=datetime.now)


_sessions: dict[str, ManagedSession] = {}
_visible_sessions: dict[str, VisibleSession] = {}


def start_session(
    settings: Settings,
    project_path: str = "",
    cli: str = "",
    cli_args: str = "",
    session_id: str = "default",
) -> dict:
    """打开可见 Terminal/iTerm 会话。

    现在 cc 统一走可见终端，不再默认启动后台 pty。
    """
    result = open_visible_session(settings, project_path, cli, cli_args, "Terminal", session_id)
    if result.get("success"):
        result["status"] = "visible"
        result["message"] = "opened visible terminal cc session"
    return result


def open_visible_session(
    settings: Settings,
    project_path: str = "",
    cli: str = "",
    cli_args: str = "",
    terminal: str = "Terminal",
    session_id: str = "default",
) -> dict:
    """打开一个用户可见的 Terminal/iTerm 窗口并启动 Claude Code/Codex。

    这不是后台 pty 会话，后续输入由用户在可见终端里操作。为了避免变成任意
    shell 执行器，这里仍然只允许配置白名单里的项目目录、CLI 和 CLI 参数。
    """
    try:
        normalized_session_id = _normalize_session_id(session_id)
        project = ensure_allowed_project(
            project_path or settings.default_project_root or _first_allowed_project(settings),
            settings.cc_allowed_projects,
        )
        cli_name = ensure_allowed_cli(cli or settings.cc_default_cli, settings.cc_allowed_clis)
        args = _parse_cli_args(cli_args, settings.cc_allowed_cli_args)
        terminal_name = _ensure_visible_terminal(terminal, settings.cc_visible_terminals)
        title = _session_title(normalized_session_id)
        shell_command = _build_shell_command(project, cli_name, args)
        script = _terminal_script(terminal_name, shell_command, title)
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
        _visible_sessions[normalized_session_id] = VisibleSession(
            session_id=normalized_session_id,
            terminal=terminal_name,
            cli=cli_name,
            project_path=project,
            title=title,
            args=args,
        )
        return ok(
            {
                "session_id": normalized_session_id,
                "terminal": terminal_name,
                "title": title,
                "cli": cli_name,
                "args": args,
                "project_path": str(project),
                "command": shell_command,
            },
            f"已在 {terminal_name} 打开 {cli_name} 会话。",
            "opened visible cc session",
        )
    except (SafetyError, subprocess.CalledProcessError, ValueError) as exc:
        return fail(str(exc), "Claude Code 会话没有打开成功。")


def list_sessions() -> dict:
    """列出当前进程登记过的可见 Claude Code/Codex 会话。"""
    sessions = []
    for session in sorted(_visible_sessions.values(), key=lambda item: item.session_id):
        sessions.append(
            {
                "session_id": session.session_id,
                "terminal": session.terminal,
                "title": session.title,
                "cli": session.cli,
                "args": session.args,
                "project_path": str(session.project_path),
                "active": _visible_session_exists(session),
                "created_at": session.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "last_activity_at": session.last_activity_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    count = len(sessions)
    return ok(
        {
            "count": count,
            "sessions": sessions,
        },
        f"当前记住了 {count} 个 Claude Code 会话。",
        "listed visible cc sessions",
    )


def cleanup_sessions() -> dict:
    """Remove registered visible sessions whose Terminal/iTerm target no longer exists."""
    kept = []
    removed = []
    for session_id, session in list(_visible_sessions.items()):
        serialized = {
            "session_id": session.session_id,
            "terminal": session.terminal,
            "title": session.title,
            "cli": session.cli,
            "project_path": str(session.project_path),
        }
        if _visible_session_exists(session):
            kept.append(serialized)
        else:
            removed.append(serialized)
            _visible_sessions.pop(session_id, None)
    return ok(
        {
            "kept_count": len(kept),
            "removed_count": len(removed),
            "kept": kept,
            "removed": removed,
        },
        f"已清理 {len(removed)} 个失效会话，保留 {len(kept)} 个会话。",
        "cleaned visible cc sessions",
    )


def session_status(settings: Settings, session_id: str = "default", max_chars: int = 0) -> dict:
    """读取可见终端当前会话最近输出并判断状态。"""
    try:
        session_id = _normalize_session_id(session_id)
        visible_session = _visible_sessions.get(session_id)
        terminal = visible_session.terminal if visible_session else "Terminal"
        limit = _return_limit(settings, max_chars or settings.cc_status_tail_chars)
        if visible_session:
            tail = _read_visible_session_contents(visible_session, limit)
        else:
            tail = _read_visible_terminal_contents(terminal, limit)
        status = _detect_status_text(tail)
        if visible_session:
            visible_session.last_activity_at = datetime.now()
        summary = _status_summary(status, tail)
        return ok(
            {
                "session_id": session_id,
                "terminal": terminal,
                "registered": visible_session is not None,
                "targeted": visible_session is not None,
                "status": status,
                "summary": summary,
                "tail": tail,
            },
            summary,
            _status_message(status),
        )
    except (SafetyError, subprocess.CalledProcessError) as exc:
        return fail(str(exc), "我没能读取 Claude Code 当前状态。")


def send_instruction(settings: Settings, text: str, session_id: str = "default") -> dict:
    """向可见终端中的 Claude Code/Codex 会话发送一段自然语言指令。"""
    try:
        session_id = _normalize_session_id(session_id)
        visible_session = _visible_sessions.get(session_id)
        terminal = visible_session.terminal if visible_session else "Terminal"
        if not text.strip():
            raise SafetyError("instruction is empty")
        if visible_session:
            _send_to_visible_session(visible_session, text.strip())
        else:
            _send_to_visible_terminal(terminal, text.strip())
        if visible_session:
            visible_session.last_activity_at = datetime.now()
        return ok(
            {
                "session_id": session_id,
                "terminal": terminal,
                "registered": visible_session is not None,
                "targeted": visible_session is not None,
            },
            "已发送给 Claude Code。",
            "sent instruction to visible terminal",
        )
    except (SafetyError, subprocess.CalledProcessError) as exc:
        return fail(str(exc), "我没能把这句话发送给 Claude Code。")


def send_decision(
    settings: Settings,
    decision: str,
    session_id: str = "default",
    confirm: bool = False,
) -> dict:
    """发送 yes/no/cancel 决策；策略默认允许，也可用配置收紧。"""
    try:
        session_id = _normalize_session_id(session_id)
        visible_session = _visible_sessions.get(session_id)
        terminal = visible_session.terminal if visible_session else "Terminal"
        normalized = decision.strip().lower()
        aliases = {
            "y": "yes",
            "yes": "yes",
            "同意": "yes",
            "继续": "yes",
            "n": "no",
            "no": "no",
            "拒绝": "no",
            "不要": "no",
            "cancel": "cancel",
            "取消": "cancel",
        }
        value = aliases.get(normalized)
        if value is None:
            raise SafetyError("decision must be yes, no, or cancel")

        policy = _decision_policy(value, settings)
        if policy == "deny":
            return fail(
                f"decision denied: {value}",
                "这个确认动作被策略拦截了，我没有发送。",
                {"policy": policy},
            )
        if policy == "confirm" and not confirm:
            return fail(
                "decision requires confirm=true",
                "这个确认动作需要你再次确认。",
                {"policy": policy, "decision": value},
            )

        if visible_session:
            _send_to_visible_session(visible_session, value)
        else:
            _send_to_visible_terminal(terminal, value)
        if visible_session:
            visible_session.last_activity_at = datetime.now()
        spoken = {"yes": "已发送同意。", "no": "已发送拒绝。", "cancel": "已发送取消。"}[value]
        return ok(
            {
                "policy": policy,
                "session_id": session_id,
                "terminal": terminal,
                "registered": visible_session is not None,
                "targeted": visible_session is not None,
                "decision": value,
            },
            spoken,
            "sent decision to visible terminal",
        )
    except (SafetyError, subprocess.CalledProcessError) as exc:
        return fail(str(exc), "我没能发送这个确认选择。")


def send_slash_command(
    settings: Settings,
    command: str,
    args: str = "",
    session_id: str = "default",
    confirm: bool = False,
) -> dict:
    """发送 Claude Code/Codex 内部 slash 命令，例如 /init、/compact、/model。"""
    try:
        session_id = _normalize_session_id(session_id)
        visible_session = _visible_sessions.get(session_id)
        terminal = visible_session.terminal if visible_session else "Terminal"
        slash = command.strip()
        if args.strip():
            slash = f"{slash} {args.strip()}"
        policy = slash_policy(
            slash,
            settings.cc_slash_default_policy,
            settings.cc_slash_allow,
            settings.cc_slash_confirm,
            settings.cc_slash_deny,
        )
        if policy == "deny":
            return fail(
                "slash command denied",
                "这个斜杠命令被策略拦截了，我没有发送。",
                {"policy": policy, "command": slash},
            )
        if policy == "confirm" and not confirm:
            return fail(
                "slash command requires confirm=true",
                "这个斜杠命令需要你再次确认。",
                {"policy": policy, "command": slash},
            )

        if visible_session:
            _send_to_visible_session(visible_session, slash)
        else:
            _send_to_visible_terminal(terminal, slash)
        if visible_session:
            visible_session.last_activity_at = datetime.now()
        return ok(
            {
                "policy": policy,
                "session_id": session_id,
                "terminal": terminal,
                "registered": visible_session is not None,
                "targeted": visible_session is not None,
                "command": slash,
            },
            f"已发送命令 {slash}。",
            "sent slash command to visible terminal",
        )
    except (SafetyError, subprocess.CalledProcessError) as exc:
        return fail(str(exc), "我没能发送这个斜杠命令。")


def switch_model(
    settings: Settings,
    model: str,
    session_id: str = "default",
    confirm: bool = False,
) -> dict:
    """切换 Claude Code/Codex 模型，底层发送 `/model <model>`。

    默认不限制模型名；如果配置了 CC_ALLOWED_MODELS，则只允许清单里的模型。
    `/model` 本身仍然走 slash command 策略，可配置成 allow/confirm/deny。
    """
    try:
        model_name = _ensure_allowed_model(model, settings.cc_allowed_models)
        return send_slash_command(settings, "/model", model_name, session_id, confirm)
    except SafetyError as exc:
        return fail(str(exc), "模型没有切换成功。")


def focus_session(session_id: str = "default") -> dict:
    """把登记过的可见 Claude Code/Codex 会话窗口拉到前台。"""
    try:
        session_id = _normalize_session_id(session_id)
        visible_session = _visible_sessions.get(session_id)
        if not visible_session:
            raise SafetyError(f"visible session is not registered: {session_id}")
        _focus_visible_session(visible_session)
        visible_session.last_activity_at = datetime.now()
        return ok(
            {
                "session_id": session_id,
                "terminal": visible_session.terminal,
                "title": visible_session.title,
            },
            "已把 Claude Code 窗口切到前台。",
            "focused visible cc session",
        )
    except (SafetyError, subprocess.CalledProcessError) as exc:
        return fail(str(exc), "我没能找到并聚焦这个 Claude Code 会话。")


def stop_session(session_id: str = "default") -> dict:
    """退出可见 Terminal 里的 Claude Code/Codex，并关闭前台 Terminal 窗口。"""
    try:
        session_id = _normalize_session_id(session_id)
        visible_session = _visible_sessions.get(session_id)
        terminal = visible_session.terminal if visible_session else "Terminal"
        if visible_session:
            _send_to_visible_session(visible_session, "/exit")
        else:
            _send_to_visible_terminal(terminal, "/exit")
        time.sleep(0.4)
        if visible_session:
            _close_visible_session(visible_session)
        else:
            _close_visible_terminal(terminal)
        _visible_sessions.pop(session_id, None)
        return ok(
            {
                "session_id": session_id,
                "terminal": terminal,
                "registered": visible_session is not None,
                "targeted": visible_session is not None,
                "status": "stopped",
            },
            "已退出 Claude Code 并关闭窗口。",
            "sent /exit and closed visible terminal window",
        )
    except (SafetyError, subprocess.CalledProcessError) as exc:
        return fail(str(exc), "我没能关闭 Claude Code 会话。")


def close_terminal(terminal: str = "Terminal") -> dict:
    """关闭前台 Terminal/iTerm 窗口；给语音“关闭终端/关闭cc”这类命令使用。"""
    try:
        terminal_name = _ensure_known_terminal(terminal)
        _close_visible_terminal(terminal_name)
        return ok(
            {
                "terminal": terminal_name,
                "status": "closed",
            },
            f"已关闭前台 {terminal_name} 窗口。",
            "closed visible terminal window",
        )
    except (SafetyError, subprocess.CalledProcessError) as exc:
        return fail(str(exc), "我没能关闭这个终端窗口。")


def _normalize_session_id(session_id: str) -> str:
    value = (session_id or "default").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value):
        raise SafetyError("session_id may only contain letters, numbers, dot, underscore, and dash")
    return value


def _parse_cli_args(cli_args: str, allowed_args: frozenset[str]) -> list[str]:
    tokens = shlex.split(cli_args or "")
    if not tokens:
        return []
    for token in tokens:
        if token not in allowed_args:
            allowed = ", ".join(sorted(allowed_args))
            raise SafetyError(f"cli arg is not allowlisted: {token}. allowed: {allowed}")
    return tokens


def _first_allowed_project(settings: Settings) -> str:
    """没有默认项目时，取允许项目列表中的第一个作为启动目录。"""
    if not settings.cc_allowed_projects:
        raise SafetyError("CC_ALLOWED_PROJECTS is empty")
    return str(sorted(str(path) for path in settings.cc_allowed_projects)[0])


def _ensure_visible_terminal(terminal: str, allowed: frozenset[str]) -> str:
    value = (terminal or "Terminal").strip()
    aliases = {
        "terminal": "Terminal",
        "terminal.app": "Terminal",
        "iterm": "iTerm",
        "iterm2": "iTerm",
        "iterm.app": "iTerm",
    }
    normalized = aliases.get(value.lower(), value)
    if normalized not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        raise SafetyError(f"terminal is not allowlisted: {normalized}. allowed: {allowed_text}")
    return normalized


def _ensure_known_terminal(terminal: str) -> str:
    """只允许关闭我们支持的终端 App，避免把本机变成任意 AppleScript 控制器。"""
    value = (terminal or "Terminal").strip()
    aliases = {
        "terminal": "Terminal",
        "terminal.app": "Terminal",
        "iterm": "iTerm",
        "iterm2": "iTerm",
        "iterm.app": "iTerm",
    }
    normalized = aliases.get(value.lower(), value)
    if normalized not in {"Terminal", "iTerm"}:
        raise SafetyError(f"unsupported terminal: {normalized}")
    return normalized


def _ensure_allowed_model(model: str, allowed_models: frozenset[str]) -> str:
    value = model.strip()
    if not value:
        raise SafetyError("model is empty")
    if allowed_models and value not in allowed_models:
        allowed = ", ".join(sorted(allowed_models))
        raise SafetyError(f"model is not allowlisted: {value}. allowed: {allowed}")
    return value


def _build_shell_command(project: Path, cli: str, args: list[str]) -> str:
    command = " ".join([shlex.quote(cli), *(shlex.quote(arg) for arg in args)])
    return f"cd {shlex.quote(str(project))} && {command}"


def _session_title(session_id: str) -> str:
    return f"xiaozhi-desktop-mcp:{session_id}"


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _terminal_script(terminal: str, shell_command: str, title: str) -> str:
    escaped = _escape_applescript(shell_command)
    escaped_title = _escape_applescript(title)
    if terminal == "iTerm":
        return (
            'tell application "iTerm"\n'
            '  activate\n'
            '  create window with default profile\n'
            f'  set name of current session of current window to "{escaped_title}"\n'
            f'  tell current session of current window to write text "{escaped}"\n'
            'end tell'
        )
    return (
        'tell application "Terminal"\n'
        '  activate\n'
        f'  do script "{escaped}"\n'
        f'  set custom title of selected tab of front window to "{escaped_title}"\n'
        'end tell'
    )


def _send_to_visible_terminal(terminal: str, text: str) -> None:
    """把一行文本发送到可见 Terminal/iTerm 当前会话。"""
    if not text.strip():
        raise SafetyError("terminal input is empty")
    escaped = _escape_applescript(text)
    if terminal == "iTerm":
        script = (
            'tell application "iTerm"\n'
            '  activate\n'
            f'  tell current session of current window to write text "{escaped}"\n'
            'end tell'
        )
    else:
        script = (
            'tell application "Terminal"\n'
            '  activate\n'
            '  if not (exists front window) then error "Terminal has no front window"\n'
            f'  do script "{escaped}" in selected tab of front window\n'
            'end tell'
        )
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)


def _send_to_visible_session(session: VisibleSession, text: str) -> None:
    """把一行文本发送到已打标的可见会话。"""
    if not text.strip():
        raise SafetyError("terminal input is empty")
    escaped_text = _escape_applescript(text)
    escaped_title = _escape_applescript(session.title)
    if session.terminal == "iTerm":
        script = (
            'tell application "iTerm"\n'
            f'  set targetSession to my findSession("{escaped_title}")\n'
            f'  tell targetSession to write text "{escaped_text}"\n'
            'end tell\n'
            f'{_iterm_find_session_handler()}'
        )
    else:
        script = (
            'tell application "Terminal"\n'
            f'  set foundRefs to my findTab("{escaped_title}")\n'
            '  set targetTab to item 1 of foundRefs\n'
            f'  do script "{escaped_text}" in targetTab\n'
            'end tell\n'
            f'{_terminal_find_tab_handler()}'
        )
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)


def _read_visible_terminal_contents(terminal: str, limit: int) -> str:
    """读取可见 Terminal/iTerm 当前会话文本尾部。"""
    if terminal == "iTerm":
        script = (
            'tell application "iTerm"\n'
            '  if not (exists current window) then return ""\n'
            '  return contents of current session of current window\n'
            'end tell'
        )
    else:
        script = (
            'tell application "Terminal"\n'
            '  if not (exists front window) then return ""\n'
            '  return contents of selected tab of front window\n'
            'end tell'
        )
    result = subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
    return result.stdout[-limit:]


def _read_visible_session_contents(session: VisibleSession, limit: int) -> str:
    """读取已打标可见会话的文本尾部。"""
    escaped_title = _escape_applescript(session.title)
    if session.terminal == "iTerm":
        script = (
            'tell application "iTerm"\n'
            f'  set targetSession to my findSession("{escaped_title}")\n'
            '  return contents of targetSession\n'
            'end tell\n'
            f'{_iterm_find_session_handler()}'
        )
    else:
        script = (
            'tell application "Terminal"\n'
            f'  set foundRefs to my findTab("{escaped_title}")\n'
            '  set targetTab to item 1 of foundRefs\n'
            '  return contents of targetTab\n'
            'end tell\n'
            f'{_terminal_find_tab_handler()}'
        )
    result = subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)
    return result.stdout[-limit:]


def _focus_visible_session(session: VisibleSession) -> None:
    """把已打标的可见会话所在窗口拉到前台。"""
    escaped_title = _escape_applescript(session.title)
    if session.terminal == "iTerm":
        script = (
            'tell application "iTerm"\n'
            '  activate\n'
            f'  set targetSession to my findSession("{escaped_title}")\n'
            '  select targetSession\n'
            'end tell\n'
            f'{_iterm_find_session_handler()}'
        )
    else:
        script = (
            'tell application "Terminal"\n'
            '  activate\n'
            f'  set foundRefs to my findTab("{escaped_title}")\n'
            '  set targetTab to item 1 of foundRefs\n'
            '  set targetWindow to item 2 of foundRefs\n'
            '  set selected tab of targetWindow to targetTab\n'
            '  set index of targetWindow to 1\n'
            'end tell\n'
            f'{_terminal_find_tab_handler()}'
        )
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)


def _visible_session_exists(session: VisibleSession) -> bool:
    escaped_title = _escape_applescript(session.title)
    if session.terminal == "iTerm":
        script = (
            'tell application "iTerm"\n'
            f'  return my sessionExists("{escaped_title}")\n'
            'end tell\n'
            f'{_iterm_session_exists_handler()}'
        )
    else:
        script = (
            'tell application "Terminal"\n'
            f'  return my tabExists("{escaped_title}")\n'
            'end tell\n'
            f'{_terminal_tab_exists_handler()}'
        )
    completed = subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True)
    return completed.returncode == 0 and completed.stdout.strip().lower() == "true"


def _close_visible_terminal(terminal: str) -> None:
    """关闭当前可见终端窗口。

    如果终端里仍有前台进程，macOS 可能弹出确认框；这比静默强杀更适合作为语音工具默认行为。
    """
    if terminal == "iTerm":
        script = (
            'tell application "iTerm"\n'
            '  activate\n'
            '  if not (exists current window) then error "iTerm has no current window"\n'
            '  close current window\n'
            'end tell'
        )
    else:
        script = (
            'tell application "Terminal"\n'
            '  activate\n'
            '  if not (exists front window) then error "Terminal has no front window"\n'
            '  close front window\n'
            'end tell'
        )
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)


def _close_visible_session(session: VisibleSession) -> None:
    """关闭已打标可见会话所在窗口。"""
    escaped_title = _escape_applescript(session.title)
    if session.terminal == "iTerm":
        script = (
            'tell application "iTerm"\n'
            '  activate\n'
            f'  set targetWindow to my findWindow("{escaped_title}")\n'
            '  close targetWindow\n'
            'end tell\n'
            f'{_iterm_find_window_handler()}'
        )
    else:
        script = (
            'tell application "Terminal"\n'
            '  activate\n'
            f'  set foundRefs to my findTab("{escaped_title}")\n'
            '  set targetWindow to item 2 of foundRefs\n'
            '  close targetWindow\n'
            'end tell\n'
            f'{_terminal_find_tab_handler()}'
        )
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True, text=True)


def _terminal_find_tab_handler() -> str:
    return """
on findTab(targetTitle)
  tell application "Terminal"
    repeat with w in windows
      repeat with t in tabs of w
        try
          if custom title of t is targetTitle then return {t, w}
        end try
      end repeat
    end repeat
  end tell
  error "visible Terminal session not found: " & targetTitle
end findTab
"""


def _terminal_tab_exists_handler() -> str:
    return """
on tabExists(targetTitle)
  tell application "Terminal"
    repeat with w in windows
      repeat with t in tabs of w
        try
          if custom title of t is targetTitle then return true
        end try
      end repeat
    end repeat
  end tell
  return false
end tabExists
"""


def _iterm_find_session_handler() -> str:
    return """
on findSession(targetTitle)
  tell application "iTerm"
    repeat with w in windows
      repeat with s in sessions of w
        try
          if name of s is targetTitle then return s
        end try
      end repeat
    end repeat
  end tell
  error "visible iTerm session not found: " & targetTitle
end findSession
"""


def _iterm_find_window_handler() -> str:
    return """
on findWindow(targetTitle)
  tell application "iTerm"
    repeat with w in windows
      repeat with s in sessions of w
        try
          if name of s is targetTitle then return w
        end try
      end repeat
    end repeat
  end tell
  error "visible iTerm session window not found: " & targetTitle
end findWindow
"""


def _iterm_session_exists_handler() -> str:
    return """
on sessionExists(targetTitle)
  tell application "iTerm"
    repeat with w in windows
      repeat with s in sessions of w
        try
          if name of s is targetTitle then return true
        end try
      end repeat
    end repeat
  end tell
  return false
end sessionExists
"""


def _detect_status_text(tail: str) -> str:
    lower = tail.lower()
    if _looks_like_confirmation(lower):
        return "waiting_confirmation"
    if _looks_like_error(lower):
        return "error"
    if _looks_done(lower):
        return "done"
    if tail.strip():
        return "running"
    return "idle"


def _require_running(session_id: str) -> ManagedSession:
    session_id = _normalize_session_id(session_id)
    session = _sessions.get(session_id)
    if not session:
        raise SafetyError(f"session is not running: {session_id}")
    if not session.child.isalive():
        _drain(session)
        raise SafetyError(f"session has stopped: {session_id}")
    return session


def _drain(session: ManagedSession, timeout: float = 0) -> None:
    """尽量读取 CLI 已输出内容，但不阻塞。"""
    chunks: list[str] = []
    while True:
        try:
            chunk = session.child.read_nonblocking(size=4096, timeout=timeout)
            timeout = 0
            if not chunk:
                break
            chunks.append(chunk)
        except pexpect.TIMEOUT:
            break
        except pexpect.EOF:
            if session.child.before:
                chunks.append(str(session.child.before))
            break
    if chunks:
        session.buffer += "".join(chunks)
        session.buffer = session.buffer[-_MAX_BUFFER_CHARS:]
        session.last_activity_at = datetime.now()


def _detect_status(session: ManagedSession, tail: str) -> str:
    lower = tail.lower()
    if _looks_like_confirmation(lower):
        return "waiting_confirmation"
    if _looks_like_error(lower):
        return "error"
    if _looks_done(lower):
        return "done"
    if session.child.isalive():
        return "running"
    return "idle"


def _looks_like_confirmation(lower: str) -> bool:
    patterns = [
        r"do you want to continue",
        r"\bcontinue\?",
        r"\bproceed\?",
        r"\byes/no\b",
        r"\[y/n\]",
        r"\[yes/no\]",
        r"\ballow\?",
        r"\bapprove\?",
    ]
    return any(re.search(pattern, lower) for pattern in patterns)

def _looks_like_error(lower: str) -> bool:
    markers = [
        "error",
        "exception",
        "traceback",
        "failed",
        "build failure",
        "npm err!",
        "command not found",
        "permission denied",
    ]
    return any(marker in lower for marker in markers)


def _looks_done(lower: str) -> bool:
    markers = [
        "done",
        "complete",
        "build success",
        "tests passed",
        "finished",
        "no changes needed",
    ]
    return any(marker in lower for marker in markers)


def _status_message(status: str) -> str:
    return {
        "waiting_confirmation": "CLI is waiting for yes/no confirmation",
        "error": "CLI output looks like an error",
        "done": "CLI output looks complete",
        "running": "CLI is still running",
        "idle": "session is not running",
    }.get(status, status)


def _status_summary(status: str, tail: str) -> str:
    lines = [line.strip() for line in tail.splitlines() if line.strip()]
    last_line = lines[-1] if lines else ""
    if status == "waiting_confirmation":
        return "Claude Code 正在等待确认。"
    if status == "error":
        return f"Claude Code 的输出看起来有错误。最后一行是：{last_line}" if last_line else "Claude Code 的输出看起来有错误。"
    if status == "done":
        return f"Claude Code 看起来已经完成。最后一行是：{last_line}" if last_line else "Claude Code 看起来已经完成。"
    if status == "running":
        return f"Claude Code 看起来还在运行。最后一行是：{last_line}" if last_line else "Claude Code 看起来还在运行。"
    return "当前还没有可见输出。"


def _return_limit(settings: Settings, requested: int) -> int:
    if requested <= 0:
        requested = settings.cc_status_tail_chars
    return max(1, min(requested, settings.cc_max_return_chars))


def _decision_policy(decision: str, settings: Settings) -> str:
    key = f"decision:{decision}"
    if key in settings.cc_slash_deny:
        return "deny"
    if key in settings.cc_slash_confirm:
        return "confirm"
    return settings.cc_slash_default_policy if settings.cc_slash_default_policy in {"allow", "confirm", "deny"} else "allow"
