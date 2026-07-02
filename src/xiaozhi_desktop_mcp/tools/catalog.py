from __future__ import annotations

from ..responses import ok


def tool_catalog() -> dict:
    """Return a compact catalog that helps Xiaozhi/Java route to the right tool."""
    tools = [
        {
            "name": "desktop_remember",
            "risk": "low",
            "use_when": "用户说记一下、保存想法、写到 Obsidian。",
            "api_v1_action": "remember",
        },
        {
            "name": "desktop_ask_cc",
            "risk": "medium",
            "use_when": "用户要把任务交给 Claude Code/Codex。",
            "api_v1_action": "ask_cc",
        },
        {
            "name": "desktop_check_cc",
            "risk": "low",
            "use_when": "用户问 cc 现在怎么样、卡在哪、完成了吗。",
            "api_v1_action": "check_cc",
        },
        {
            "name": "desktop_continue_cc",
            "risk": "medium",
            "use_when": "用户明确让 cc 继续、同意、确认。",
            "api_v1_action": "continue_cc",
        },
        {
            "name": "desktop_open_cc_project",
            "risk": "low",
            "use_when": "用户要打开某项目的 Claude Code/Codex 窗口。",
            "api_v1_action": "open_cc_project",
        },
        {
            "name": "desktop_list_projects",
            "risk": "low",
            "use_when": "用户问有哪些项目可以交给 Claude Code/Codex。",
            "api_v1_action": "list_projects",
        },
        {
            "name": "desktop_open_cc_project_named",
            "risk": "low",
            "use_when": "用户用项目名或目录名要求打开 Claude Code/Codex。",
            "api_v1_action": "open_cc_project_named",
        },
        {
            "name": "desktop_ask_cc_project",
            "risk": "medium",
            "use_when": "用户用项目名要求 Claude Code/Codex 处理任务。",
            "api_v1_action": "ask_cc_project",
        },
        {
            "name": "desktop_focus_cc",
            "risk": "low",
            "use_when": "用户要把 Claude Code/Codex 窗口切到前台。",
            "api_v1_action": "focus_cc",
        },
        {
            "name": "desktop_stop_cc",
            "risk": "medium",
            "use_when": "用户要关闭或退出 Claude Code/Codex。",
            "api_v1_action": "stop_cc",
        },
        {
            "name": "obsidian_search",
            "risk": "low",
            "use_when": "用户要在 Obsidian 里搜索笔记。",
            "api_v1_action": "search_obsidian",
        },
        {
            "name": "obsidian_append_daily_note",
            "risk": "low",
            "use_when": "用户要写入今天日记或每日笔记。",
            "api_v1_action": "append_daily_note",
        },
        {
            "name": "pending_action_create",
            "risk": "low",
            "use_when": "动作有风险，需要先创建待确认项。",
            "api_v1_action": "pending_create",
        },
        {
            "name": "pending_action_confirm",
            "risk": "medium",
            "use_when": "用户确认执行某个待确认动作。",
            "api_v1_action": "pending_confirm",
        },
        {
            "name": "desktop_health_detail",
            "risk": "low",
            "use_when": "用户要排查桌面 MCP、路径、Terminal、CLI 环境。",
            "api_v1_action": "health",
        },
        {
            "name": "cc_cleanup_sessions",
            "risk": "low",
            "use_when": "用户说清理失效 cc 会话、会话列表不准。",
            "api_v1_action": "cleanup_sessions",
        },
    ]
    return ok(
        {
            "recommended_default": "HTTP 客户端统一使用 POST /api/v1/dispatch，并传入 api_v1_action。",
            "tools": tools,
            "count": len(tools),
        },
        f"已返回 {len(tools)} 个桌面 MCP 工具说明。",
        "returned desktop tool catalog",
    )
