"""HTTP 适配层，方便 Java 版小智 server 直接调用本机工具。

MCP stdio 适合标准 MCP bridge；Java 版当前更容易通过 HTTP 调本地服务。
这里把同一套工具函数包装成 HTTP API，不新增危险能力。
"""

from __future__ import annotations

import os
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .api_v1 import actions_catalog as api_v1_actions_catalog
from .api_v1 import api_health as api_v1_health
from .api_v1 import dispatch as api_v1_dispatch
from .config import load_settings
from .tools.apps import close_app, open_app
from .tools.catalog import tool_catalog as desktop_tool_catalog
from .tools.cc_session import (
    close_terminal,
    cleanup_sessions,
    focus_session,
    list_sessions,
    open_visible_session,
    send_decision,
    send_instruction,
    send_slash_command,
    session_status,
    start_session,
    stop_session,
    switch_model,
)
from .tools.cc_task import create_task
from .tools.diagnostics import (
    config_summary as desktop_config_summary,
    health_detail as desktop_health_detail,
)
from .tools.obsidian import append_daily_note, append_note, recent_memories, save_memory, search_notes
from .tools.pending_actions import (
    cancel_pending_action,
    confirm_pending_action,
    create_pending_action,
    list_pending_actions,
)
from .tools.projects import (
    ask_cc_project as desktop_ask_cc_project,
    list_projects as desktop_list_projects,
    open_cc_project_named as desktop_open_cc_project_named,
    resolve_project as desktop_resolve_project,
)
from .tools.workflows import (
    ask_cc as desktop_ask_cc,
    check_cc as desktop_check_cc,
    continue_cc as desktop_continue_cc,
    focus_cc as desktop_focus_cc,
    open_cc_project as desktop_open_cc_project,
    remember as desktop_remember,
    stop_cc as desktop_stop_cc,
)


app = FastAPI(title="Xiaozhi Desktop MCP HTTP Adapter")
settings = load_settings()

_PROTECTED_PREFIXES = ("/api/", "/tools/")


class SaveMemoryRequest(BaseModel):
    text: str
    tags: str = "xiaozhi,voice-memory"


class AppendNoteRequest(BaseModel):
    note_path: str
    text: str
    heading: str = ""


class AppendDailyNoteRequest(BaseModel):
    text: str
    date: str = ""
    folder: str = "daily"


class SearchNotesRequest(BaseModel):
    query: str
    limit: int = 5


class RecentMemoriesRequest(BaseModel):
    limit: int = 5


class OpenAppRequest(BaseModel):
    app_name: str


class CloseAppRequest(BaseModel):
    app_name: str


class CreateTaskRequest(BaseModel):
    title: str
    instruction: str
    project_path: str = ""
    priority: str = "normal"


class StartSessionRequest(BaseModel):
    project_path: str = ""
    cli: str = ""
    cli_args: str = ""
    session_id: str = "default"


class OpenVisibleSessionRequest(BaseModel):
    project_path: str = ""
    cli: str = ""
    cli_args: str = ""
    terminal: str = "Terminal"
    session_id: str = "default"


class OpenClaudeCodeRequest(BaseModel):
    project_path: str = ""
    cli_args: str = ""
    terminal: str = "Terminal"
    session_id: str = "default"


class SessionStatusRequest(BaseModel):
    session_id: str = "default"
    max_chars: int = 0


class FocusSessionRequest(BaseModel):
    session_id: str = "default"


class SendInstructionRequest(BaseModel):
    text: str
    session_id: str = "default"


class SendDecisionRequest(BaseModel):
    decision: str
    session_id: str = "default"
    confirm: bool = False


class SendSlashCommandRequest(BaseModel):
    command: str
    args: str = ""
    session_id: str = "default"
    confirm: bool = False


class SwitchModelRequest(BaseModel):
    model: str
    session_id: str = "default"
    confirm: bool = False


class StopSessionRequest(BaseModel):
    session_id: str = "default"


class CloseTerminalRequest(BaseModel):
    terminal: str = "Terminal"


class DesktopRememberRequest(BaseModel):
    text: str
    tags: str = "xiaozhi,voice-memory"


class DesktopOpenCcProjectRequest(BaseModel):
    project_path: str = ""
    session_id: str = "default"
    cli: str = ""
    terminal: str = "Terminal"
    cli_args: str = ""


class DesktopProjectRequest(BaseModel):
    project: str


class DesktopOpenCcProjectNamedRequest(BaseModel):
    project: str
    session_id: str = "default"
    cli: str = ""
    terminal: str = "Terminal"
    cli_args: str = ""


class DesktopAskCcProjectRequest(BaseModel):
    project: str
    text: str
    session_id: str = "default"
    cli: str = ""
    terminal: str = "Terminal"
    open_if_needed: bool = True


class DesktopAskCcRequest(BaseModel):
    text: str
    project_path: str = ""
    session_id: str = "default"
    cli: str = ""
    terminal: str = "Terminal"
    open_if_needed: bool = True


class DesktopCheckCcRequest(BaseModel):
    session_id: str = "default"
    max_chars: int = 0


class DesktopContinueCcRequest(BaseModel):
    session_id: str = "default"
    confirm: bool = False


class DesktopSessionRequest(BaseModel):
    session_id: str = "default"


class PendingActionCreateRequest(BaseModel):
    action_type: str
    params: dict[str, Any] = Field(default_factory=dict)
    title: str = ""


class PendingActionListRequest(BaseModel):
    status: str = "pending"


class PendingActionIdRequest(BaseModel):
    action_id: str


class ApiV1DispatchRequest(BaseModel):
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    request_id: str = ""


@app.middleware("http")
async def require_auth_token(request: Request, call_next):
    token = os.getenv("DESKTOP_MCP_AUTH_TOKEN", "").strip()
    if token and request.url.path.startswith(_PROTECTED_PREFIXES):
        auth_header = request.headers.get("authorization", "")
        header_token = request.headers.get("x-desktop-mcp-token", "")
        if auth_header != f"Bearer {token}" and header_token != token:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": "unauthorized",
                    "error_spoken_message": "桌面 MCP 认证失败。",
                },
            )
    return await call_next(request)


@app.get("/health")
def health() -> dict[str, Any]:
    """给 Java 侧或 curl 用的健康检查。"""
    return {
        "success": True,
        "service": "xiaozhi-desktop-mcp",
        "message": "healthy",
        "spoken_message": "桌面 MCP 服务运行正常。",
    }


@app.get("/api/v1/health")
def http_api_v1_health() -> dict:
    """Language-agnostic structured health endpoint."""
    return api_v1_health(settings)


@app.get("/api/v1/actions")
def http_api_v1_actions() -> dict:
    """Return machine-friendly API v1 action metadata."""
    return api_v1_actions_catalog()


@app.post("/api/v1/dispatch")
def http_api_v1_dispatch(req: ApiV1DispatchRequest) -> dict:
    """Language-agnostic dispatch endpoint for Java, Python, Go, and other clients."""
    return api_v1_dispatch(settings, req.action, req.params, req.request_id)


@app.post("/tools/obsidian/save-memory")
def http_save_memory(req: SaveMemoryRequest) -> dict:
    """保存语音记忆到 Obsidian。"""
    return save_memory(settings, req.text, req.tags)


@app.post("/tools/obsidian/append-note")
def http_append_note(req: AppendNoteRequest) -> dict:
    """追加内容到 Obsidian vault 内指定 Markdown 笔记。"""
    return append_note(settings, req.note_path, req.text, req.heading)


@app.post("/tools/obsidian/append-daily-note")
def http_append_daily_note(req: AppendDailyNoteRequest) -> dict:
    """追加内容到 Obsidian 每日笔记。"""
    return append_daily_note(settings, req.text, req.date, req.folder)


@app.post("/tools/obsidian/search")
def http_search_notes(req: SearchNotesRequest) -> dict:
    """搜索 Obsidian vault 内 Markdown 笔记。"""
    return search_notes(settings, req.query, req.limit)


@app.post("/tools/obsidian/recent-memories")
def http_recent_memories(req: RecentMemoriesRequest) -> dict:
    """读取最近几条语音记忆。"""
    return recent_memories(settings, req.limit)


@app.post("/tools/app/open")
def http_open_app(req: OpenAppRequest) -> dict:
    """打开白名单内 macOS App。"""
    if _is_claude_code_alias(req.app_name):
        return open_visible_session(settings, "", "claude", "", "Terminal", "default")
    return open_app(settings, req.app_name)


@app.post("/tools/app/close")
def http_close_app(req: CloseAppRequest) -> dict:
    """关闭白名单内 macOS App。"""
    return close_app(settings, req.app_name)


@app.post("/tools/cc/create-task")
def http_create_task(req: CreateTaskRequest) -> dict:
    """创建 cc/Codex 待办任务，不执行命令。"""
    return create_task(settings, req.title, req.instruction, req.project_path, req.priority)


@app.post("/tools/cc/start-session")
def http_start_session(req: StartSessionRequest) -> dict:
    """启动受管 Claude Code/Codex CLI 会话。"""
    return start_session(settings, req.project_path, req.cli, req.cli_args, req.session_id)


@app.post("/tools/cc/open-visible-session")
def http_open_visible_session(req: OpenVisibleSessionRequest) -> dict:
    """打开可见 Terminal/iTerm 窗口并启动 Claude Code/Codex。"""
    return open_visible_session(
        settings,
        req.project_path,
        req.cli,
        req.cli_args,
        req.terminal,
        req.session_id,
    )


@app.post("/tools/cc/open-claude-code")
def http_open_claude_code(req: OpenClaudeCodeRequest) -> dict:
    """默认用可见 Terminal 打开 Claude Code。"""
    return open_visible_session(
        settings,
        req.project_path,
        "claude",
        req.cli_args,
        req.terminal,
        req.session_id,
    )


@app.get("/tools/cc/sessions")
def http_list_sessions() -> dict:
    """列出当前服务进程记住的可见 Claude Code/Codex 会话。"""
    return list_sessions()


@app.post("/tools/cc/cleanup-sessions")
def http_cleanup_sessions() -> dict:
    """清理已经不存在的 Claude Code/Codex 可见会话登记。"""
    return cleanup_sessions()


@app.post("/tools/cc/session-status")
def http_session_status(req: SessionStatusRequest) -> dict:
    """查看受管 CLI 状态，只返回最近输出。"""
    return session_status(settings, req.session_id, req.max_chars)


@app.post("/tools/cc/focus-session")
def http_focus_session(req: FocusSessionRequest) -> dict:
    """把指定 Claude Code/Codex 可见会话窗口拉到前台。"""
    return focus_session(req.session_id)


@app.post("/tools/cc/send-instruction")
def http_send_instruction(req: SendInstructionRequest) -> dict:
    """向受管 CLI 发送自然语言指令。"""
    return send_instruction(settings, req.text, req.session_id)


@app.post("/tools/cc/send-decision")
def http_send_decision(req: SendDecisionRequest) -> dict:
    """向受管 CLI 发送 yes/no/cancel。"""
    return send_decision(settings, req.decision, req.session_id, req.confirm)


@app.post("/tools/cc/send-slash-command")
def http_send_slash_command(req: SendSlashCommandRequest) -> dict:
    """向受管 CLI 发送 /init、/compact、/model 等内部命令。"""
    return send_slash_command(settings, req.command, req.args, req.session_id, req.confirm)


@app.post("/tools/cc/switch-model")
def http_switch_model(req: SwitchModelRequest) -> dict:
    """切换 Claude Code/Codex 模型，底层发送 /model。"""
    return switch_model(settings, req.model, req.session_id, req.confirm)


@app.post("/tools/cc/stop-session")
def http_stop_session(req: StopSessionRequest) -> dict:
    """停止受管 CLI 会话，并关闭前台 Terminal 窗口。"""
    return stop_session(req.session_id)


@app.post("/tools/cc/close-terminal")
def http_close_terminal(req: CloseTerminalRequest) -> dict:
    """直接关闭前台 Terminal/iTerm 窗口。"""
    return close_terminal(req.terminal)


@app.post("/tools/desktop/remember")
def http_desktop_remember(req: DesktopRememberRequest) -> dict:
    """语音友好入口：保存记忆到 Obsidian。"""
    return desktop_remember(settings, req.text, req.tags)


@app.post("/tools/desktop/open-cc-project")
def http_desktop_open_cc_project(req: DesktopOpenCcProjectRequest) -> dict:
    """语音友好入口：打开项目的 Claude Code/Codex 窗口。"""
    return desktop_open_cc_project(
        settings,
        req.project_path,
        req.session_id,
        req.cli,
        req.terminal,
        req.cli_args,
    )


@app.get("/tools/desktop/projects")
def http_desktop_list_projects() -> dict:
    """列出可以被桌面 MCP 打开的白名单项目。"""
    return desktop_list_projects(settings)


@app.post("/tools/desktop/resolve-project")
def http_desktop_resolve_project(req: DesktopProjectRequest) -> dict:
    """把项目名、目录名或白名单路径解析为安全项目路径。"""
    return desktop_resolve_project(settings, req.project)


@app.post("/tools/desktop/open-cc-project-named")
def http_desktop_open_cc_project_named(req: DesktopOpenCcProjectNamedRequest) -> dict:
    """按项目名/别名打开 Claude Code/Codex 可见窗口。"""
    return desktop_open_cc_project_named(
        settings,
        req.project,
        req.session_id,
        req.cli,
        req.terminal,
        req.cli_args,
    )


@app.post("/tools/desktop/ask-cc-project")
def http_desktop_ask_cc_project(req: DesktopAskCcProjectRequest) -> dict:
    """按项目名/别名把任务交给 Claude Code/Codex。"""
    return desktop_ask_cc_project(
        settings,
        req.project,
        req.text,
        req.session_id,
        req.cli,
        req.terminal,
        req.open_if_needed,
    )


@app.post("/tools/desktop/ask-cc")
def http_desktop_ask_cc(req: DesktopAskCcRequest) -> dict:
    """语音友好入口：把任务交给 Claude Code/Codex。"""
    return desktop_ask_cc(
        settings,
        req.text,
        req.project_path,
        req.session_id,
        req.cli,
        req.terminal,
        req.open_if_needed,
    )


@app.post("/tools/desktop/check-cc")
def http_desktop_check_cc(req: DesktopCheckCcRequest) -> dict:
    """语音友好入口：查询 Claude Code/Codex 状态。"""
    return desktop_check_cc(settings, req.session_id, req.max_chars)


@app.post("/tools/desktop/continue-cc")
def http_desktop_continue_cc(req: DesktopContinueCcRequest) -> dict:
    """语音友好入口：让 Claude Code/Codex 继续。"""
    return desktop_continue_cc(settings, req.session_id, req.confirm)


@app.post("/tools/desktop/focus-cc")
def http_desktop_focus_cc(req: DesktopSessionRequest) -> dict:
    """语音友好入口：聚焦 Claude Code/Codex 窗口。"""
    return desktop_focus_cc(req.session_id)


@app.post("/tools/desktop/stop-cc")
def http_desktop_stop_cc(req: DesktopSessionRequest) -> dict:
    """语音友好入口：关闭 Claude Code/Codex 会话。"""
    return desktop_stop_cc(req.session_id)


@app.get("/tools/desktop/health-detail")
def http_desktop_health_detail() -> dict:
    """诊断桌面 MCP 环境：路径、CLI、终端 App、关键配置。"""
    return desktop_health_detail(settings)


@app.get("/tools/desktop/config-summary")
def http_desktop_config_summary() -> dict:
    """返回脱敏配置摘要，方便排查桌面 MCP 环境。"""
    return desktop_config_summary(settings)


@app.get("/tools/desktop/tool-catalog")
def http_desktop_tool_catalog() -> dict:
    """返回桌面 MCP 工具目录，帮助小智/Java 选择高层工具。"""
    return desktop_tool_catalog()


@app.post("/tools/pending-actions/create")
def http_pending_action_create(req: PendingActionCreateRequest) -> dict:
    """创建一个待确认动作；只允许白名单动作类型，不会立即执行。"""
    return create_pending_action(req.action_type, req.params, req.title)


@app.post("/tools/pending-actions/list")
def http_pending_action_list(req: PendingActionListRequest) -> dict:
    """列出待确认动作；status 为空时列出全部。"""
    return list_pending_actions(req.status)


@app.get("/tools/pending-actions")
def http_pending_actions_get() -> dict:
    """列出 pending 状态的待确认动作。"""
    return list_pending_actions("pending")


@app.post("/tools/pending-actions/confirm")
def http_pending_action_confirm(req: PendingActionIdRequest) -> dict:
    """确认并执行一个待确认动作。"""
    return confirm_pending_action(settings, req.action_id)


@app.post("/tools/pending-actions/cancel")
def http_pending_action_cancel(req: PendingActionIdRequest) -> dict:
    """取消一个待确认动作，不执行。"""
    return cancel_pending_action(req.action_id)


def main() -> None:
    host = os.getenv("DESKTOP_MCP_HTTP_HOST", "127.0.0.1")
    port = int(os.getenv("DESKTOP_MCP_HTTP_PORT", "8765"))
    token = os.getenv("DESKTOP_MCP_AUTH_TOKEN", "").strip()
    if not token and not _is_loopback_host(host):
        raise SystemExit(
            "DESKTOP_MCP_AUTH_TOKEN is required when DESKTOP_MCP_HTTP_HOST is not localhost/127.0.0.1/::1"
        )
    uvicorn.run("xiaozhi_desktop_mcp.http_server:app", host=host, port=port)


def _is_claude_code_alias(app_name: str) -> bool:
    """兼容小智把“打开 Claude Code”误路由成 open_app 的情况。"""
    normalized = app_name.strip().lower().replace(" ", "").replace("-", "")
    return normalized in {"claudecode", "claude", "cc"}


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    return normalized in {"localhost", "127.0.0.1", "::1"}


if __name__ == "__main__":
    main()
