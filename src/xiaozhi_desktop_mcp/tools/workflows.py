from __future__ import annotations

from ..config import Settings
from ..responses import fail, ok
from .cc_session import (
    focus_session,
    open_visible_session,
    send_decision,
    send_instruction,
    session_status,
    stop_session,
)
from .obsidian import save_memory


def remember(settings: Settings, text: str, tags: str = "xiaozhi,voice-memory") -> dict:
    """Voice-friendly wrapper for saving a memory."""
    return save_memory(settings, text, tags)


def open_cc_project(
    settings: Settings,
    project_path: str = "",
    session_id: str = "default",
    cli: str = "",
    terminal: str = "Terminal",
    cli_args: str = "",
) -> dict:
    """Voice-friendly wrapper for opening a visible Claude Code/Codex session."""
    result = open_visible_session(settings, project_path, cli, cli_args, terminal, session_id)
    if result.get("success"):
        result["workflow"] = "desktop_open_cc_project"
        result["spoken_message"] = "已打开 Claude Code 项目窗口。"
    return result


def ask_cc(
    settings: Settings,
    text: str,
    project_path: str = "",
    session_id: str = "default",
    cli: str = "",
    terminal: str = "Terminal",
    open_if_needed: bool = True,
) -> dict:
    """Send an instruction to Claude Code; open a visible session first if requested."""
    instruction = text.strip()
    if not instruction:
        return fail("instruction is empty", "要发送给 Claude Code 的内容是空的。")

    opened = None
    if open_if_needed:
        sessions = session_status(settings, session_id, 1)
        if not sessions.get("success") or not sessions.get("registered"):
            opened = open_visible_session(settings, project_path, cli, "", terminal, session_id)
            if not opened.get("success"):
                opened["workflow"] = "desktop_ask_cc"
                return opened

    sent = send_instruction(settings, instruction, session_id)
    sent["workflow"] = "desktop_ask_cc"
    if sent.get("success"):
        sent["opened_session"] = bool(opened and opened.get("success"))
        sent["spoken_message"] = "已交给 Claude Code。"
    return sent


def check_cc(settings: Settings, session_id: str = "default", max_chars: int = 0) -> dict:
    """Voice-friendly wrapper for checking Claude Code status."""
    result = session_status(settings, session_id, max_chars)
    result["workflow"] = "desktop_check_cc"
    return result


def continue_cc(settings: Settings, session_id: str = "default", confirm: bool = False) -> dict:
    """Voice-friendly wrapper for sending yes/continue to Claude Code."""
    result = send_decision(settings, "yes", session_id, confirm)
    result["workflow"] = "desktop_continue_cc"
    if result.get("success"):
        result["spoken_message"] = "已让 Claude Code 继续。"
    return result


def focus_cc(session_id: str = "default") -> dict:
    """Voice-friendly wrapper for focusing a visible Claude Code session."""
    result = focus_session(session_id)
    result["workflow"] = "desktop_focus_cc"
    return result


def stop_cc(session_id: str = "default") -> dict:
    """Voice-friendly wrapper for stopping a visible Claude Code session."""
    result = stop_session(session_id)
    result["workflow"] = "desktop_stop_cc"
    return result
