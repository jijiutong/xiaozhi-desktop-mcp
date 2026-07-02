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
            "name": "desktop_intent",
            "risk": "variable",
            "use_when": "新客户端或语音入口要按 music/docs/ai/dev/browser/system 分类执行通用桌面意图。",
            "api_v1_action": "desktop_intent",
        },
        {
            "name": "desktop_category_registry",
            "risk": "low",
            "use_when": "客户端启动时要发现通用桌面能力分类和可用意图。",
            "api_v1_action": "category_registry",
        },
        {
            "name": "app_open",
            "risk": "low",
            "use_when": "用户要打开 Xcode、Obsidian、浏览器或其他白名单 App。",
            "api_v1_action": "app_open",
        },
        {
            "name": "app_close",
            "risk": "medium",
            "use_when": "用户要关闭白名单 App。",
            "api_v1_action": "app_close",
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
            "name": "cc_send_slash_command",
            "risk": "medium",
            "use_when": "用户明确要发送 /init、/compact、/clear、/model 等 Claude Code 命令。",
            "api_v1_action": "cc_send_slash_command",
        },
        {
            "name": "cc_switch_model",
            "risk": "medium",
            "use_when": "用户要切换 Claude Code/Codex 模型。",
            "api_v1_action": "cc_switch_model",
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
            "name": "obsidian_create_note",
            "risk": "low",
            "use_when": "用户要新建一篇 Obsidian 笔记。",
            "api_v1_action": "create_note",
        },
        {
            "name": "obsidian_open_note",
            "risk": "low",
            "use_when": "用户要打开某篇 Obsidian 笔记。",
            "api_v1_action": "open_note",
        },
        {
            "name": "xcode_open_project",
            "risk": "low",
            "use_when": "用户要打开 Xcode 项目或 workspace。",
            "api_v1_action": "xcode_open_project",
        },
        {
            "name": "xcode_build",
            "risk": "medium",
            "use_when": "用户要编译 Xcode 项目。",
            "api_v1_action": "xcode_build",
        },
        {
            "name": "xcode_test",
            "risk": "medium",
            "use_when": "用户要运行 Xcode 测试。",
            "api_v1_action": "xcode_test",
        },
        {
            "name": "xcode_clean",
            "risk": "medium",
            "use_when": "用户要清理 Xcode 构建。",
            "api_v1_action": "xcode_clean",
        },
        {
            "name": "xcode_last_errors",
            "risk": "low",
            "use_when": "用户要查看最近一次 Xcode 编译/测试错误。",
            "api_v1_action": "xcode_last_errors",
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
