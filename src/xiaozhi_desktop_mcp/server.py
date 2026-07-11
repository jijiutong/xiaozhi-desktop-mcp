"""小智桌面工作流 MCP 服务入口。

这个进程不直接连接 ESP32 硬件。小智服务器或 MCP bridge 会通过 stdio
启动它，再调用这里暴露的工具来执行本机动作，例如写入 Obsidian、打开
白名单 App、创建 cc/Codex 待办任务。
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import Callable
from functools import wraps
from ipaddress import ip_address

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .api_v2 import dispatch as api_v2_dispatch
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
from .tools.intent import (
    desktop_intent as desktop_intent_impl,
    desktop_intent_catalog as desktop_intent_catalog_impl,
)
from .tools.obsidian import (
    append_daily_note as append_daily_note_impl,
    append_note as append_note_impl,
    create_note as create_note_impl,
    open_note as open_note_impl,
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
from .tools.xcode import (
    open_xcode_project as xcode_open_project_impl,
    xcode_build as xcode_build_impl,
    xcode_clean as xcode_clean_impl,
    xcode_last_errors as xcode_last_errors_impl,
    xcode_test as xcode_test_impl,
)

logger = logging.getLogger(__name__)

# FastMCP 会把下面用 @mcp.tool 标记的函数暴露给小智/LLM 调用。
mcp = FastMCP(
    "Xiaozhi Desktop MCP",
    host=os.getenv("DESKTOP_MCP_STREAMABLE_HOST", "127.0.0.1"),
    port=int(os.getenv("DESKTOP_MCP_STREAMABLE_PORT", "8766")),
    streamable_http_path=os.getenv("DESKTOP_MCP_STREAMABLE_PATH", "/mcp"),
    log_level=os.getenv("DESKTOP_MCP_LOG_LEVEL", "INFO"),
)

# 配置在进程启动时加载一次，避免每次工具调用都重复解析环境变量。
settings = load_settings()


class StreamableHTTPAuthAndLoggingMiddleware:
    """Small ASGI wrapper for token auth and request observability."""

    def __init__(self, app: ASGIApp, auth_token: str = "") -> None:
        self.app = app
        self.auth_token = auth_token.strip()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = _headers_dict(scope)
        request_id = headers.get("x-request-id") or uuid.uuid4().hex
        started_at = time.monotonic()
        method = str(scope.get("method", ""))
        path = str(scope.get("path", ""))
        client = scope.get("client")
        client_host = client[0] if isinstance(client, tuple) and client else ""

        if self.auth_token and not _is_authorized(headers, self.auth_token):
            response = JSONResponse(
                {"error": "unauthorized"},
                status_code=401,
                headers={"X-Request-Id": request_id},
            )
            await response(scope, receive, send)
            _log_streamable_http_request(method, path, 401, started_at, request_id, client_host, False)
            return

        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode("utf-8")))
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            _log_streamable_http_request(method, path, 500, started_at, request_id, client_host, not self.auth_token)
            logger.exception(
                "desktop_mcp_streamable_http_exception request_id=%s method=%s path=%s client=%s",
                request_id,
                method,
                path,
                client_host,
            )
            raise

        _log_streamable_http_request(method, path, status_code, started_at, request_id, client_host, True)


def mcp_tool():
    """Register an MCP tool with lightweight observability."""

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            started_at = time.monotonic()
            try:
                result = func(*args, **kwargs)
            except Exception:
                cost_ms = int((time.monotonic() - started_at) * 1000)
                logger.exception("desktop_mcp_tool tool=%s success=false cost_ms=%s", func.__name__, cost_ms)
                raise
            cost_ms = int((time.monotonic() - started_at) * 1000)
            success = result.get("success") if isinstance(result, dict) else None
            logger.info("desktop_mcp_tool tool=%s success=%s cost_ms=%s", func.__name__, success, cost_ms)
            return result

        return mcp.tool()(wrapper)

    return decorator


@mcp_tool()
def obsidian_save_memory(text: str, tags: str = "xiaozhi,voice-memory") -> dict:
    """当用户说“记一下/保存想法/写到 Obsidian”时调用，保存一条语音记忆。"""
    return save_memory_impl(settings, text, tags)


@mcp_tool()
def obsidian_create_note(note_path: str, text: str = "", overwrite: bool = False) -> dict:
    """新建 Obsidian vault 内的 Markdown 笔记。"""
    return create_note_impl(settings, note_path, text, overwrite)


@mcp_tool()
def obsidian_open_note(note_path: str) -> dict:
    """打开 Obsidian vault 内的 Markdown 笔记。"""
    return open_note_impl(settings, note_path)


@mcp_tool()
def obsidian_append_note(note_path: str, text: str, heading: str = "") -> dict:
    """追加内容到 Obsidian vault 内指定 Markdown 笔记。"""
    return append_note_impl(settings, note_path, text, heading)


@mcp_tool()
def obsidian_append_daily_note(text: str, date: str = "", folder: str = "daily") -> dict:
    """追加内容到 Obsidian 每日笔记。"""
    return append_daily_note_impl(settings, text, date, folder)


@mcp_tool()
def obsidian_search(query: str, limit: int = 5) -> dict:
    """搜索 Obsidian vault 内 Markdown 笔记，返回少量片段。"""
    return search_notes_impl(settings, query, limit)


@mcp_tool()
def obsidian_recent_memories(limit: int = 5) -> dict:
    """读取最近几条语音记忆。"""
    return recent_memories_impl(settings, limit)


@mcp_tool()
def app_open(app_name: str) -> dict:
    """当用户说“打开某个 App”时调用；只允许打开配置白名单里的 macOS App。"""
    if _is_claude_code_alias(app_name):
        return cc_open_visible_session_impl(settings, "", "claude", "", "Terminal", "default")
    return open_app_impl(settings, app_name)


@mcp_tool()
def app_close(app_name: str) -> dict:
    """当用户说“关闭某个 App”时调用；只允许关闭配置白名单里的 macOS App。"""
    return close_app_impl(settings, app_name)


@mcp_tool()
def cc_create_task(
    title: str,
    instruction: str,
    project_path: str = "",
    priority: str = "normal",
) -> dict:
    """当用户说“让 cc/Codex/Claude Code 做...”时调用，只创建待办任务，不执行命令。"""
    return create_cc_task_impl(settings, title, instruction, project_path, priority)


@mcp_tool()
def cc_start_session(
    project_path: str = "",
    cli: str = "",
    cli_args: str = "",
    session_id: str = "default",
) -> dict:
    """启动受管 Claude Code/Codex CLI 会话；只能在配置允许的项目目录里启动。"""
    return cc_start_session_impl(settings, project_path, cli, cli_args, session_id)


@mcp_tool()
def cc_open_visible_session(
    project_path: str = "",
    cli: str = "",
    cli_args: str = "",
    terminal: str = "Terminal",
    session_id: str = "default",
) -> dict:
    """打开可见 Terminal/iTerm 窗口并启动 Claude Code/Codex；方便人工观看和接管。"""
    return cc_open_visible_session_impl(settings, project_path, cli, cli_args, terminal, session_id)


@mcp_tool()
def cc_open_claude_code(
    project_path: str = "",
    cli_args: str = "",
    terminal: str = "Terminal",
    session_id: str = "default",
) -> dict:
    """当用户说“打开 Claude Code/打开 cc”时调用，默认在可见 Terminal 中启动 claude。"""
    return cc_open_visible_session_impl(settings, project_path, "claude", cli_args, terminal, session_id)


@mcp_tool()
def cc_list_sessions() -> dict:
    """列出当前服务进程记住的可见 Claude Code/Codex 会话。"""
    return cc_list_sessions_impl()


@mcp_tool()
def cc_cleanup_sessions() -> dict:
    """清理已经不存在的 Claude Code/Codex 可见会话登记。"""
    return cc_cleanup_sessions_impl()


@mcp_tool()
def cc_session_status(session_id: str = "default", max_chars: int = 0) -> dict:
    """查看受管 CLI 当前状态，只读取最近输出：等待确认、报错、完成、运行中或空闲。"""
    return cc_session_status_impl(settings, session_id, max_chars)


@mcp_tool()
def cc_focus_session(session_id: str = "default") -> dict:
    """把指定 Claude Code/Codex 可见会话窗口拉到前台。"""
    return cc_focus_session_impl(session_id)


@mcp_tool()
def cc_send_instruction(text: str, session_id: str = "default", allow_frontmost: bool = False) -> dict:
    """向已启动的受管 CLI 会话发送自然语言任务说明。"""
    return cc_send_instruction_impl(settings, text, session_id, allow_frontmost)


@mcp_tool()
def cc_send_decision(
    decision: str,
    session_id: str = "default",
    confirm: bool = False,
    allow_frontmost: bool = False,
) -> dict:
    """当 CLI 等待确认时发送 yes/no/cancel；默认允许，可通过配置改成确认或禁止。"""
    return cc_send_decision_impl(settings, decision, session_id, confirm, allow_frontmost)


@mcp_tool()
def cc_send_slash_command(
    command: str,
    args: str = "",
    session_id: str = "default",
    confirm: bool = False,
    allow_frontmost: bool = False,
) -> dict:
    """发送 /init、/compact、/model 等内部命令；默认允许，可通过配置收紧。"""
    return cc_send_slash_command_impl(settings, command, args, session_id, confirm, allow_frontmost)


@mcp_tool()
def cc_switch_model(
    model: str,
    session_id: str = "default",
    confirm: bool = False,
    allow_frontmost: bool = False,
) -> dict:
    """切换受管 Claude Code/Codex 会话模型；默认允许所有模型，可用配置收紧。"""
    return cc_switch_model_impl(settings, model, session_id, confirm, allow_frontmost)


@mcp_tool()
def cc_stop_session(session_id: str = "default", allow_frontmost: bool = False) -> dict:
    """停止受管 Claude Code/Codex CLI 会话，并关闭前台 Terminal 窗口。"""
    return cc_stop_session_impl(session_id, allow_frontmost)


@mcp_tool()
def cc_close_terminal(terminal: str = "Terminal") -> dict:
    """当用户说“关闭终端/关闭cc窗口”时调用，关闭前台 Terminal/iTerm 窗口。"""
    return cc_close_terminal_impl(terminal)


@mcp_tool()
def desktop_remember(text: str, tags: str = "xiaozhi,voice-memory") -> dict:
    """语音友好入口：当用户说“记一下...”时保存到 Obsidian。"""
    return desktop_remember_impl(settings, text, tags)


@mcp_tool()
def desktop_open_cc_project(
    project_path: str = "",
    session_id: str = "default",
    cli: str = "",
    terminal: str = "Terminal",
    cli_args: str = "",
) -> dict:
    """语音友好入口：打开某个项目的 Claude Code/Codex 可见窗口。"""
    return desktop_open_cc_project_impl(settings, project_path, session_id, cli, terminal, cli_args)


@mcp_tool()
def desktop_list_projects() -> dict:
    """列出可以被桌面 MCP 打开的白名单项目。"""
    return desktop_list_projects_impl(settings)


@mcp_tool()
def desktop_resolve_project(project: str) -> dict:
    """把项目名、目录名或白名单路径解析为安全项目路径。"""
    return desktop_resolve_project_impl(settings, project)


@mcp_tool()
def desktop_open_cc_project_named(
    project: str,
    session_id: str = "default",
    cli: str = "",
    terminal: str = "Terminal",
    cli_args: str = "",
) -> dict:
    """按项目名/别名打开 Claude Code/Codex 可见窗口。"""
    return desktop_open_cc_project_named_impl(settings, project, session_id, cli, terminal, cli_args)


@mcp_tool()
def desktop_ask_cc_project(
    project: str,
    text: str,
    session_id: str = "default",
    cli: str = "",
    terminal: str = "Terminal",
    open_if_needed: bool = True,
    allow_frontmost: bool = False,
) -> dict:
    """按项目名/别名把任务交给 Claude Code/Codex。"""
    return desktop_ask_cc_project_impl(
        settings,
        project,
        text,
        session_id,
        cli,
        terminal,
        open_if_needed,
        allow_frontmost,
    )


@mcp_tool()
def desktop_ask_cc(
    text: str,
    project_path: str = "",
    session_id: str = "default",
    cli: str = "",
    terminal: str = "Terminal",
    open_if_needed: bool = True,
    allow_frontmost: bool = False,
) -> dict:
    """语音友好入口：把一句自然语言任务交给 Claude Code/Codex。"""
    return desktop_ask_cc_impl(settings, text, project_path, session_id, cli, terminal, open_if_needed, allow_frontmost)


@mcp_tool()
def desktop_check_cc(session_id: str = "default", max_chars: int = 0) -> dict:
    """语音友好入口：看看 Claude Code/Codex 当前在做什么或卡在哪。"""
    return desktop_check_cc_impl(settings, session_id, max_chars)


@mcp_tool()
def desktop_continue_cc(session_id: str = "default", confirm: bool = False, allow_frontmost: bool = False) -> dict:
    """语音友好入口：让 Claude Code/Codex 继续。"""
    return desktop_continue_cc_impl(settings, session_id, confirm, allow_frontmost)


@mcp_tool()
def desktop_focus_cc(session_id: str = "default") -> dict:
    """语音友好入口：把 Claude Code/Codex 窗口切到前台。"""
    return desktop_focus_cc_impl(session_id)


@mcp_tool()
def desktop_stop_cc(session_id: str = "default", allow_frontmost: bool = False) -> dict:
    """语音友好入口：退出 Claude Code/Codex 并关闭窗口。"""
    return desktop_stop_cc_impl(session_id, allow_frontmost)


@mcp_tool()
def xcode_open_project(project_path: str = "", xcode_path: str = "") -> dict:
    """打开白名单项目内的 .xcodeproj 或 .xcworkspace。"""
    return xcode_open_project_impl(settings, project_path, xcode_path)


@mcp_tool()
def xcode_build(
    project_path: str = "",
    xcode_path: str = "",
    scheme: str = "",
    configuration: str = "",
    destination: str = "",
) -> dict:
    """在白名单项目内执行 xcodebuild build。"""
    return xcode_build_impl(settings, project_path, xcode_path, scheme, configuration, destination)


@mcp_tool()
def xcode_test(
    project_path: str = "",
    xcode_path: str = "",
    scheme: str = "",
    configuration: str = "",
    destination: str = "",
) -> dict:
    """在白名单项目内执行 xcodebuild test。"""
    return xcode_test_impl(settings, project_path, xcode_path, scheme, configuration, destination)


@mcp_tool()
def xcode_clean(
    project_path: str = "",
    xcode_path: str = "",
    scheme: str = "",
    configuration: str = "",
    destination: str = "",
) -> dict:
    """在白名单项目内执行 xcodebuild clean。"""
    return xcode_clean_impl(settings, project_path, xcode_path, scheme, configuration, destination)


@mcp_tool()
def xcode_last_errors(limit: int = 20) -> dict:
    """读取最近一次 xcodebuild 输出中的错误线索。"""
    return xcode_last_errors_impl(limit)


@mcp_tool()
def desktop_health_detail() -> dict:
    """诊断桌面 MCP 环境：路径、CLI、终端 App、关键配置。"""
    return desktop_health_detail_impl(settings)


@mcp_tool()
def desktop_config_summary() -> dict:
    """返回脱敏配置摘要，方便排查桌面 MCP 环境。"""
    return desktop_config_summary_impl(settings)


@mcp_tool()
def desktop_tool_catalog() -> dict:
    """返回桌面 MCP 工具目录，帮助小智/Java 选择高层工具。"""
    return desktop_tool_catalog_impl()


@mcp_tool()
def desktop_category_registry() -> dict:
    """返回通用桌面能力分类，例如 music、docs、ai、dev、browser、system。"""
    return desktop_intent_catalog_impl(settings)


@mcp_tool()
def desktop_intent(category: str, intent: str, params: dict | None = None) -> dict:
    """通用桌面意图入口：按 category + intent 路由到底层安全能力。"""
    return desktop_intent_impl(settings, category, intent, params)


@mcp_tool()
def desktop_dispatch_v2(action: str, params: dict | None = None, client: str = "mcp") -> dict:
    """统一 v2 桌面动作入口：执行 Schema 校验、风险策略、审计和安全 dispatch。"""
    return api_v2_dispatch(settings, action, params or {}, "", client)


@mcp_tool()
def pending_action_create(action_type: str, params: dict | None = None, title: str = "") -> dict:
    """创建一个待确认动作；只允许白名单动作类型，不会立即执行。"""
    return pending_action_create_impl(action_type, params, title, settings=settings)


@mcp_tool()
def pending_action_list(status: str = "pending") -> dict:
    """列出待确认动作；status 为空时列出全部。"""
    return pending_action_list_impl(status, settings=settings)


@mcp_tool()
def pending_action_confirm(action_id: str) -> dict:
    """确认并执行一个待确认动作。"""
    return pending_action_confirm_impl(settings, action_id)


@mcp_tool()
def pending_action_cancel(action_id: str) -> dict:
    """取消一个待确认动作，不执行。"""
    return pending_action_cancel_impl(action_id, settings=settings)


def main() -> None:
    # stdio 是 MCP bridge 最容易启动和管理的传输方式。
    mcp.run(transport="stdio")


def main_streamable_http() -> None:
    """Run the standard MCP Streamable HTTP transport."""
    import uvicorn

    host = mcp.settings.host
    port = mcp.settings.port
    token = _auth_token()
    if not token and not _is_loopback_host(host):
        raise SystemExit("DESKTOP_MCP_AUTH_TOKEN is required when binding Streamable HTTP outside localhost")

    logger.info(
        "desktop_mcp_server_start transport=streamable-http host=%s port=%s path=%s auth=%s",
        host,
        port,
        mcp.settings.streamable_http_path,
        bool(token),
    )
    uvicorn.run(
        build_streamable_http_app(),
        host=host,
        port=port,
        log_level=str(mcp.settings.log_level).lower(),
    )


def build_streamable_http_app() -> ASGIApp:
    """Build a standards-compliant MCP Streamable HTTP app with local safeguards."""
    return StreamableHTTPAuthAndLoggingMiddleware(mcp.streamable_http_app(), _auth_token())


def _is_claude_code_alias(app_name: str) -> bool:
    """兼容 LLM 把“打开 Claude Code/cc”误当作普通 App 打开的情况。"""
    normalized = app_name.strip().lower().replace(" ", "").replace("-", "")
    return normalized in {"claudecode", "claude", "cc"}


def _auth_token() -> str:
    return os.getenv("DESKTOP_MCP_AUTH_TOKEN", "").strip()


def _is_loopback_host(host: str) -> bool:
    clean = host.strip().lower()
    if clean == "localhost":
        return True
    try:
        return ip_address(clean).is_loopback
    except ValueError:
        return False


def _headers_dict(scope: Scope) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw_key, raw_value in scope.get("headers", []):
        key = raw_key.decode("latin-1").lower()
        value = raw_value.decode("latin-1")
        headers[key] = value
    return headers


def _is_authorized(headers: dict[str, str], token: str) -> bool:
    if not token:
        return True
    auth = headers.get("authorization", "")
    bearer = _extract_bearer_token(auth)
    header_token = headers.get("x-desktop-mcp-token", "")
    return bearer == token or header_token == token


def _extract_bearer_token(value: str) -> str:
    if not value.lower().startswith("bearer "):
        return ""
    return value[7:].strip()


def _log_streamable_http_request(
    method: str,
    path: str,
    status_code: int,
    started_at: float,
    request_id: str,
    client_host: str,
    authorized: bool,
) -> None:
    cost_ms = int((time.monotonic() - started_at) * 1000)
    logger.info(
        "desktop_mcp_streamable_http request_id=%s method=%s path=%s status=%s cost_ms=%s client=%s authorized=%s",
        request_id,
        method,
        path,
        status_code,
        cost_ms,
        client_host,
        authorized,
    )


if __name__ == "__main__":
    main()
