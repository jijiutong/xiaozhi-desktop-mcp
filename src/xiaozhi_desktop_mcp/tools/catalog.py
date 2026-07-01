from __future__ import annotations

from ..responses import ok


def tool_catalog() -> dict:
    """Return a compact catalog that helps Xiaozhi/Java route to the right tool."""
    tools = [
        {
            "name": "desktop_remember",
            "risk": "low",
            "use_when": "用户说记一下、保存想法、写到 Obsidian。",
            "http": "POST /tools/desktop/remember",
        },
        {
            "name": "desktop_ask_cc",
            "risk": "medium",
            "use_when": "用户要把任务交给 Claude Code/Codex。",
            "http": "POST /tools/desktop/ask-cc",
        },
        {
            "name": "desktop_check_cc",
            "risk": "low",
            "use_when": "用户问 cc 现在怎么样、卡在哪、完成了吗。",
            "http": "POST /tools/desktop/check-cc",
        },
        {
            "name": "desktop_continue_cc",
            "risk": "medium",
            "use_when": "用户明确让 cc 继续、同意、确认。",
            "http": "POST /tools/desktop/continue-cc",
        },
        {
            "name": "desktop_open_cc_project",
            "risk": "low",
            "use_when": "用户要打开某项目的 Claude Code/Codex 窗口。",
            "http": "POST /tools/desktop/open-cc-project",
        },
        {
            "name": "desktop_list_projects",
            "risk": "low",
            "use_when": "用户问有哪些项目可以交给 Claude Code/Codex。",
            "http": "GET /tools/desktop/projects",
        },
        {
            "name": "desktop_open_cc_project_named",
            "risk": "low",
            "use_when": "用户用项目名或目录名要求打开 Claude Code/Codex。",
            "http": "POST /tools/desktop/open-cc-project-named",
        },
        {
            "name": "desktop_ask_cc_project",
            "risk": "medium",
            "use_when": "用户用项目名要求 Claude Code/Codex 处理任务。",
            "http": "POST /tools/desktop/ask-cc-project",
        },
        {
            "name": "desktop_focus_cc",
            "risk": "low",
            "use_when": "用户要把 Claude Code/Codex 窗口切到前台。",
            "http": "POST /tools/desktop/focus-cc",
        },
        {
            "name": "desktop_stop_cc",
            "risk": "medium",
            "use_when": "用户要关闭或退出 Claude Code/Codex。",
            "http": "POST /tools/desktop/stop-cc",
        },
        {
            "name": "obsidian_search",
            "risk": "low",
            "use_when": "用户要在 Obsidian 里搜索笔记。",
            "http": "POST /tools/obsidian/search",
        },
        {
            "name": "obsidian_append_daily_note",
            "risk": "low",
            "use_when": "用户要写入今天日记或每日笔记。",
            "http": "POST /tools/obsidian/append-daily-note",
        },
        {
            "name": "pending_action_create",
            "risk": "low",
            "use_when": "动作有风险，需要先创建待确认项。",
            "http": "POST /tools/pending-actions/create",
        },
        {
            "name": "pending_action_confirm",
            "risk": "medium",
            "use_when": "用户确认执行某个待确认动作。",
            "http": "POST /tools/pending-actions/confirm",
        },
        {
            "name": "desktop_health_detail",
            "risk": "low",
            "use_when": "用户要排查桌面 MCP、路径、Terminal、CLI 环境。",
            "http": "GET /tools/desktop/health-detail",
        },
        {
            "name": "cc_cleanup_sessions",
            "risk": "low",
            "use_when": "用户说清理失效 cc 会话、会话列表不准。",
            "http": "POST /tools/cc/cleanup-sessions",
        },
    ]
    return ok(
        {
            "recommended_default": "优先使用 desktop_* 高层工具；需要精细控制时再用 cc_* 或 obsidian_* 底层工具。",
            "tools": tools,
            "count": len(tools),
        },
        f"已返回 {len(tools)} 个桌面 MCP 工具说明。",
        "returned desktop tool catalog",
    )
