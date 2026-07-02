"""小智桌面工作流 MCP 服务入口。

这个进程不直接连接 ESP32 硬件。小智服务器或 MCP bridge 会通过 stdio
启动它，再调用这里暴露的工具来执行本机动作，例如写入 Obsidian、打开
白名单 App、创建 cc/Codex 待办任务。
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .config import load_settings
from .tools.apps import close_app as close_app_impl, open_app as open_app_impl
from .tools.catalog import tool_catalog as desktop_tool_catalog_impl
from .tools.cc_session import (
    cleanup_sessions as cc_cleanup_sessions_impl,
    close_terminal as cc_close_terminal_impl,
    focus_session as cc_focus_session_impl,
    list_sessions as cc_list_sessions_impl,
    open_visible_session as cc_open_visible_session_impl,
    send_decision as cc_send_decision_impl,
    send_instruction as cc_send_instruction_impl,
    send_slash_command as cc_send_slash_command_impl,
    session_status as cc_session_status_impl,
    start_session as cc_start_session_impl,
    stop_session as cc_stop_session_impl,
    switch_model as cc_switch_model_impl,
)
from .tools.cc_task import create_task as create_cc_task_impl
from .tools.diagnostics import (
    config_summary as desktop_config_summary_impl,
    health_detail as desktop_health_detail_impl,
)
from .tools.obsidian import (
    append_daily_note as append_daily_note_impl,
    append_note as append_note_impl,
    recent_memories as recent_memories_impl,
    save_memory as save_memory_impl,
    search_notes as search_notes_impl,
)
from .tools.pending_actions import (
    cancel_pending_action as pending_action_cancel_impl,
    confirm_pending_action as pending_action_confirm_impl,
    create_pending_action as pending_action_create_impl,
    list_pending_actions as pending_action_list_impl,
)
from .tools.projects import (
    ask_cc_project as desktop_ask_cc_project_impl,
    list_projects as desktop_list_projects_impl,
    open_cc_project_named as desktop_open_cc_project_named_impl,
    resolve_project as desktop_resolve_project_impl,
)
from .tools.workflows import (
    ask_cc as desktop_ask_cc_impl,
    check_cc as desktop_check_cc_impl,
    continue_cc as desktop_continue_cc_impl,
    focus_cc as desktop_focus_cc_impl,
    open_cc_project as desktop_open_cc_project_impl,
    remember as desktop_remember_impl,
    stop_cc as desktop_stop_cc_impl,
)

# FastMCP 会把下面用 @mcp.tool 标记的函数暴露给小智/LLM 调用。
mcp = FastMCP("Xiaozhi Desktop MCP")

# 配置在进程启动时加载一次，避免每次工具调用都重复解析环境变量。
settings = load_settings()


@mcp.tool()
def obsidian_save_memory(text: str, tags: str = "xiaozhi,voice-memory") -> dict:
    """当用户说“记一下/保存想法/写到 Obsidian”时调用，保存一条语音记忆。"""
    return save_memory_impl(settings, text, tags)


@mcp.tool()
def obsidian_append_note(note_path: str, text: str, heading: str = "") -> dict:
    """追加内容到 Obsidian vault 内指定 Markdown 笔记。"""
    return append_note_impl(settings, note_path, text, heading)


@mcp.tool()
def obsidian_append_daily_note(text: str, date: str = "", folder: str = "daily") -> dict:
    """追加内容到 Obsidian 每日笔记。"""
    return append_daily_note_impl(settings, text, date, folder)


@mcp.tool()
def obsidian_search(query: str, limit: int = 5) -> dict:
    """搜索 Obsidian vault 内 Markdown 笔记，返回少量片段。"""
    return search_notes_impl(settings, query, limit)


@mcp.tool()
def obsidian_recent_memories(limit: int = 5) -> dict:
    """读取最近几条语音记忆。"""
    return recent_memories_impl(settings, limit)


@mcp.tool()
def app_open(app_name: str) -> dict:
    """当用户说“打开某个 App”时调用；只允许打开配置白名单里的 macOS App。"""
    if _is_claude_code_alias(app_name):
        return cc_open_visible_session_impl(settings, "", "claude", "", "Terminal", "default")
    return open_app_impl(settings, app_name)


@mcp.tool()
def app_close(app_name: str) -> dict:
    """当用户说“关闭某个 App”时调用；只允许关闭配置白名单里的 macOS App。"""
    return close_app_impl(settings, app_name)


@mcp.tool()
def cc_create_task(
    title: str,
    instruction: str,
    project_path: str = "",
    priority: str = "normal",
) -> dict:
    """当用户说“让 cc/Codex/Claude Code 做...”时调用，只创建待办任务，不执行命令。"""
    return create_cc_task_impl(settings, title, instruction, project_path, priority)


@mcp.tool()
def cc_start_session(
    project_path: str = "",
    cli: str = "",
    cli_args: str = "",
    session_id: str = "default",
) -> dict:
    """启动受管 Claude Code/Codex CLI 会话；只能在配置允许的项目目录里启动。"""
    return cc_start_session_impl(settings, project_path, cli, cli_args, session_id)


@mcp.tool()
def cc_open_visible_session(
    project_path: str = "",
    cli: str = "",
    cli_args: str = "",
    terminal: str = "Terminal",
    session_id: str = "default",
) -> dict:
    """打开可见 Terminal/iTerm 窗口并启动 Claude Code/Codex；方便人工观看和接管。"""
    return cc_open_visible_session_impl(settings, project_path, cli, cli_args, terminal, session_id)


@mcp.tool()
def cc_open_claude_code(
    project_path: str = "",
    cli_args: str = "",
    terminal: str = "Terminal",
    session_id: str = "default",
) -> dict:
    """当用户说“打开 Claude Code/打开 cc”时调用，默认在可见 Terminal 中启动 claude。"""
    return cc_open_visible_session_impl(settings, project_path, "claude", cli_args, terminal, session_id)


@mcp.tool()
def cc_list_sessions() -> dict:
    """列出当前服务进程记住的可见 Claude Code/Codex 会话。"""
    return cc_list_sessions_impl()


@mcp.tool()
def cc_cleanup_sessions() -> dict:
    """清理已经不存在的 Claude Code/Codex 可见会话登记。"""
    return cc_cleanup_sessions_impl()


@mcp.tool()
def cc_session_status(session_id: str = "default", max_chars: int = 0) -> dict:
    """查看受管 CLI 当前状态，只读取最近输出：等待确认、报错、完成、运行中或空闲。"""
    return cc_session_status_impl(settings, session_id, max_chars)


@mcp.tool()
def cc_focus_session(session_id: str = "default") -> dict:
    """把指定 Claude Code/Codex 可见会话窗口拉到前台。"""
    return cc_focus_session_impl(session_id)


@mcp.tool()
def cc_send_instruction(text: str, session_id: str = "default") -> dict:
    """向已启动的受管 CLI 会话发送自然语言任务说明。"""
    return cc_send_instruction_impl(settings, text, session_id)


@mcp.tool()
def cc_send_decision(decision: str, session_id: str = "default", confirm: bool = False) -> dict:
    """当 CLI 等待确认时发送 yes/no/cancel；默认允许，可通过配置改成确认或禁止。"""
    return cc_send_decision_impl(settings, decision, session_id, confirm)


@mcp.tool()
def cc_send_slash_command(
    command: str,
    args: str = "",
    session_id: str = "default",
    confirm: bool = False,
) -> dict:
    """发送 /init、/compact、/model 等内部命令；默认允许，可通过配置收紧。"""
    return cc_send_slash_command_impl(settings, command, args, session_id, confirm)


@mcp.tool()
def cc_switch_model(model: str, session_id: str = "default", confirm: bool = False) -> dict:
    """切换受管 Claude Code/Codex 会话模型；默认允许所有模型，可用配置收紧。"""
    return cc_switch_model_impl(settings, model, session_id, confirm)


@mcp.tool()
def cc_stop_session(session_id: str = "default") -> dict:
    """停止受管 Claude Code/Codex CLI 会话，并关闭前台 Terminal 窗口。"""
    return cc_stop_session_impl(session_id)


@mcp.tool()
def cc_close_terminal(terminal: str = "Terminal") -> dict:
    """当用户说“关闭终端/关闭cc窗口”时调用，关闭前台 Terminal/iTerm 窗口。"""
    return cc_close_terminal_impl(terminal)


@mcp.tool()
def desktop_remember(text: str, tags: str = "xiaozhi,voice-memory") -> dict:
    """语音友好入口：当用户说“记一下...”时保存到 Obsidian。"""
    return desktop_remember_impl(settings, text, tags)


@mcp.tool()
def desktop_open_cc_project(
    project_path: str = "",
    session_id: str = "default",
    cli: str = "",
    terminal: str = "Terminal",
    cli_args: str = "",
) -> dict:
    """语音友好入口：打开某个项目的 Claude Code/Codex 可见窗口。"""
    return desktop_open_cc_project_impl(settings, project_path, session_id, cli, terminal, cli_args)


@mcp.tool()
def desktop_list_projects() -> dict:
    """列出可以被桌面 MCP 打开的白名单项目。"""
    return desktop_list_projects_impl(settings)


@mcp.tool()
def desktop_resolve_project(project: str) -> dict:
    """把项目名、目录名或白名单路径解析为安全项目路径。"""
    return desktop_resolve_project_impl(settings, project)


@mcp.tool()
def desktop_open_cc_project_named(
    project: str,
    session_id: str = "default",
    cli: str = "",
    terminal: str = "Terminal",
    cli_args: str = "",
) -> dict:
    """按项目名/别名打开 Claude Code/Codex 可见窗口。"""
    return desktop_open_cc_project_named_impl(settings, project, session_id, cli, terminal, cli_args)


@mcp.tool()
def desktop_ask_cc_project(
    project: str,
    text: str,
    session_id: str = "default",
    cli: str = "",
    terminal: str = "Terminal",
    open_if_needed: bool = True,
) -> dict:
    """按项目名/别名把任务交给 Claude Code/Codex。"""
    return desktop_ask_cc_project_impl(settings, project, text, session_id, cli, terminal, open_if_needed)


@mcp.tool()
def desktop_ask_cc(
    text: str,
    project_path: str = "",
    session_id: str = "default",
    cli: str = "",
    terminal: str = "Terminal",
    open_if_needed: bool = True,
) -> dict:
    """语音友好入口：把一句自然语言任务交给 Claude Code/Codex。"""
    return desktop_ask_cc_impl(settings, text, project_path, session_id, cli, terminal, open_if_needed)


@mcp.tool()
def desktop_check_cc(session_id: str = "default", max_chars: int = 0) -> dict:
    """语音友好入口：看看 Claude Code/Codex 当前在做什么或卡在哪。"""
    return desktop_check_cc_impl(settings, session_id, max_chars)


@mcp.tool()
def desktop_continue_cc(session_id: str = "default", confirm: bool = False) -> dict:
    """语音友好入口：让 Claude Code/Codex 继续。"""
    return desktop_continue_cc_impl(settings, session_id, confirm)


@mcp.tool()
def desktop_focus_cc(session_id: str = "default") -> dict:
    """语音友好入口：把 Claude Code/Codex 窗口切到前台。"""
    return desktop_focus_cc_impl(session_id)


@mcp.tool()
def desktop_stop_cc(session_id: str = "default") -> dict:
    """语音友好入口：退出 Claude Code/Codex 并关闭窗口。"""
    return desktop_stop_cc_impl(session_id)


@mcp.tool()
def desktop_health_detail() -> dict:
    """诊断桌面 MCP 环境：路径、CLI、终端 App、关键配置。"""
    return desktop_health_detail_impl(settings)


@mcp.tool()
def desktop_config_summary() -> dict:
    """返回脱敏配置摘要，方便排查桌面 MCP 环境。"""
    return desktop_config_summary_impl(settings)


@mcp.tool()
def desktop_tool_catalog() -> dict:
    """返回桌面 MCP 工具目录，帮助小智/Java 选择高层工具。"""
    return desktop_tool_catalog_impl()


@mcp.tool()
def pending_action_create(action_type: str, params: dict | None = None, title: str = "") -> dict:
    """创建一个待确认动作；只允许白名单动作类型，不会立即执行。"""
    return pending_action_create_impl(action_type, params, title)


@mcp.tool()
def pending_action_list(status: str = "pending") -> dict:
    """列出待确认动作；status 为空时列出全部。"""
    return pending_action_list_impl(status)


@mcp.tool()
def pending_action_confirm(action_id: str) -> dict:
    """确认并执行一个待确认动作。"""
    return pending_action_confirm_impl(settings, action_id)


@mcp.tool()
def pending_action_cancel(action_id: str) -> dict:
    """取消一个待确认动作，不执行。"""
    return pending_action_cancel_impl(action_id)


def main() -> None:
    # stdio 是 MCP bridge 最容易启动和管理的传输方式。
    mcp.run(transport="stdio")


def _is_claude_code_alias(app_name: str) -> bool:
    """兼容 LLM 把“打开 Claude Code/cc”误当作普通 App 打开的情况。"""
    normalized = app_name.strip().lower().replace(" ", "").replace("-", "")
    return normalized in {"claudecode", "claude", "cc"}


if __name__ == "__main__":
    main()
