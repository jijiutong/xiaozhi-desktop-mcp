# AGENT.md

给后续 Codex/Claude Code 接手这个项目看的说明。

## 项目定位

`xiaozhi-desktop-mcp` 是本机桌面工作流服务，用来把小智接到 Mac：

- Obsidian 记忆落盘
- macOS App 打开
- cc/Codex 任务 Markdown 创建
- Claude Code/Codex 可见 Terminal 控制
- Claude Code/Codex 可见 Terminal/iTerm 启动与轻量 session 登记
- 小智语音工作流 wrapper
- Java 版小智后端 HTTP 桥接

不要把它做成新的小智服务器，也不要在这里实现 LLM/RAG/ASR/TTS。

当前稳定版本是 `3.0.0`。继续保持 `/api/v1/...` 响应 envelope 兼容，不随意改 action 名和字段名；新客户端优先使用 `/api/v2/actions` 和 `/api/v2/dispatch`。

## 当前重要文件

```text
src/xiaozhi_desktop_mcp/config.py
配置加载，所有 .env 项集中在这里。

src/xiaozhi_desktop_mcp/api_v1.py
语言无关 HTTP API dispatch。Java/Python/Go 等新客户端优先走 `/api/v1/dispatch`。

src/xiaozhi_desktop_mcp/action_registry.py
API action、风险等级、pending action 参数规则的统一元数据来源。

src/xiaozhi_desktop_mcp/api_v2.py
Schema 校验、风险策略、稳定错误码、trace 和脱敏审计入口。

src/xiaozhi_desktop_mcp/storage.py
SQLite 状态库：pending actions、workflows、audit events。

src/xiaozhi_desktop_mcp/workflows_v2.py
可持久化、可暂停确认、可恢复和取消的多步骤工作流。

src/xiaozhi_desktop_mcp/safety.py
路径、App、CLI、slash policy 等安全边界。

src/xiaozhi_desktop_mcp/server.py
stdio MCP server 入口。

src/xiaozhi_desktop_mcp/http_server.py
FastAPI HTTP adapter，Java 后端主要打这里。

src/xiaozhi_desktop_mcp/tools/cc_session.py
Claude Code/Codex 会话控制：可见 Terminal/iTerm、输入、状态、模型切换、轻量 session 登记。

src/xiaozhi_desktop_mcp/tools/cc_task.py
只创建 Markdown 任务，不执行。

src/xiaozhi_desktop_mcp/tools/apps.py
打开或关闭白名单 App。

src/xiaozhi_desktop_mcp/tools/obsidian.py
保存记忆、追加笔记、每日笔记、搜索和读取最近记忆。所有路径必须留在 `OBSIDIAN_VAULT` 内。

src/xiaozhi_desktop_mcp/tools/workflows.py
语音友好 wrapper，只编排已有安全工具，不直接执行 AppleScript 或 shell。

src/xiaozhi_desktop_mcp/tools/diagnostics.py
环境自检和脱敏配置摘要，只读检查，不启动 Claude Code，不执行项目命令。

src/xiaozhi_desktop_mcp/tools/pending_actions.py
SQLite 待确认动作生命周期。包含 TTL、原子 claim、防重复执行；只 dispatch 到白名单工具。

src/xiaozhi_desktop_mcp/tools/browser_drivers.py
Chromium/Safari 显式标签页 Driver，不提供任意 JavaScript 或坐标点击。

src/xiaozhi_desktop_mcp/tools/music_drivers.py
Apple Music/网易云音乐显式 Driver；网易云 UI 输入动作必须确认。

src/xiaozhi_desktop_mcp/tools/catalog.py
给小智/Java 侧看的工具目录，帮助选择高层 `desktop_*` 入口。

src/xiaozhi_desktop_mcp/tools/projects.py
从 `CC_ALLOWED_PROJECTS` 生成项目目录和目录名别名；解析后仍必须通过白名单校验。

src/xiaozhi_desktop_mcp/tools/perception.py
全屏/窗口截图和 macOS Vision OCR。HTTP 返回 base64，直接 MCP 截图工具返回 ImageContent。

src/xiaozhi_desktop_mcp/tools/accessibility.py
白名单 App 的 UI 树和语义操作入口；所有写操作必须先进入 pending action。
```

Java 侧桥接文件：

```text
/path/to/xiaozhi-esp32-server-java/xiaozhi-server/src/main/java/com/xiaozhi/mcpserver/DesktopWorkflowTestService.java
/path/to/xiaozhi-esp32-server-java/xiaozhi-dialogue/src/main/java/com/xiaozhi/dialogue/llm/tool/function/DesktopWorkflowFunction.java
```

## 设计原则

- 默认能玩，配置能锁。
- 不新增任意 shell 执行能力。
- 工具返回保持旧字段兼容，同时给小智播报用 `spoken_message` / `error_spoken_message`。
- 审计只记录参数名和执行元数据，不落参数值、token、笔记正文或搜索内容。
- review/fix/test/git status 不需要单独工具，直接用 `cc_send_instruction` 输入中文给 Claude/Codex。
- `/init`、`/compact`、`/clear`、`/model` 不需要单独包装，走 `cc_send_slash_command` 或 `cc_switch_model`。
- 小智/Java 后端优先使用 `desktop_*` wrapper；底层 `cc_*` 工具主要用于精细控制和调试。
- Java/Python/Go 等 HTTP 客户端统一使用 `/api/v1/dispatch`。
- 新增 API v1 action 时，优先更新 `action_registry.py`，再接入 `api_v1.py` 的 `_ACTION_HANDLERS`。
- 中风险动作需要在 `action_registry.py` 声明 `pending_action_type`、允许参数和必填参数。
- API v2 不信任 `confirm=true`；中风险动作必须创建 pending action 后单独确认。
- 新 App 能力优先新增显式 Driver 和 capabilities，不做任意坐标点击。
- Accessibility 元素 ID 是当前 UI 树的路径，界面变化后必须重新 observe，不能假设 ID 永久稳定。
- 全屏截图可能包含其他 App 的隐私信息；不要把图像或 UI value 写入日志和审计。
- 新增或修改公共接口时同步 `docs/api.md`、必要时同步 `docs/clients.md` 和 `CHANGELOG.md`。
- 先保持工具少而通用，不要把每句话都做成一个 action。

## 当前保留的工具

```text
desktop_remember
desktop_open_cc_project
desktop_list_projects
desktop_resolve_project
desktop_open_cc_project_named
desktop_ask_cc_project
desktop_ask_cc
desktop_check_cc
desktop_continue_cc
desktop_focus_cc
desktop_stop_cc
desktop_health_detail
desktop_config_summary
desktop_tool_catalog
desktop_screenshot
desktop_window_screenshot
desktop_ocr
accessibility_capabilities
accessibility_tree
accessibility_action
pending_action_create
pending_action_list
pending_action_confirm
pending_action_cancel
obsidian_append_note
obsidian_append_daily_note
obsidian_search
obsidian_recent_memories
cc_create_task
cc_cleanup_sessions
cc_start_session
cc_open_visible_session
cc_open_claude_code
cc_list_sessions
cc_session_status
cc_focus_session
cc_send_instruction
cc_send_decision
cc_send_slash_command
cc_switch_model
cc_stop_session
cc_close_terminal
app_open
app_close
obsidian_save_memory
```

## 测试命令

Python 编译检查：

```bash
cd /path/to/xiaozhi-desktop-mcp
. .venv/bin/activate
python -m compileall src
```

启动 HTTP adapter：

```bash
xiaozhi-desktop-http
```

打开可见 Claude：

```bash
curl -X POST http://127.0.0.1:8765/api/v1/dispatch \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "open-demo",
    "action": "open_cc_project",
    "params": {
      "project_path": "/path/to/your/project",
      "cli": "claude",
      "terminal": "Terminal",
      "session_id": "default"
    }
  }'
```

发送中文指令给可见 Terminal 会话：

```bash
curl -X POST http://127.0.0.1:8765/api/v1/dispatch \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "ask-demo",
    "action": "ask_cc",
    "params": {
      "session_id": "default",
      "text": "帮我 review 当前项目，重点看 bug 和风险。"
    }
  }'
```

关闭 Claude Code 和前台 Terminal 窗口：

```bash
curl -X POST http://127.0.0.1:8765/api/v1/dispatch \
  -H "Content-Type: application/json" \
  -d '{"request_id":"stop-demo","action":"stop_cc","params":{"session_id":"default"}}'
```

Java 编译检查：

```bash
cd /path/to/xiaozhi-esp32-server-java
mvn -pl xiaozhi-server -am -DskipTests compile
```

## 不要踩的坑

- `claude -c` 在没有历史会话时会直接退出并显示 `No conversation found to continue`。
- 当前 cc 操作默认统一走可见 Terminal，不使用后台 pty。
- `cc_open_visible_session` / `cc_start_session` 会登记 `session_id`，并给 Terminal tab 或 iTerm session 设置 `xiaozhi-desktop-mcp:<session_id>` 标题。
- `cc_send_instruction`、`cc_send_decision`、`cc_send_slash_command`、`cc_session_status` 会优先按登记过的 `session_id` 定位已打标的 tab/session；未登记时回退到 Terminal 当前选中 tab。
- `cc_focus_session` 可把已登记会话拉回前台；如果用户手动改掉 tab/session 标题，定位会失败。
- 会话列表不准时调用 `cc_cleanup_sessions` 清理失效登记。
- 排障优先调用 `desktop_health_detail`，再看 `desktop_config_summary`。
- Java/小智需要能力说明时调用 `desktop_tool_catalog`。
- 语音里用户说项目名时优先用 `desktop_ask_cc_project` 或 `desktop_open_cc_project_named`；项目别名来自 allowed project 的目录名。
- pending action、workflow 和 audit 存在 `DESKTOP_MCP_STATE_DB`；确认动作必须保持原子、单次和可过期。
- Obsidian 搜索只读 `.md` 文件，跳过隐藏目录，返回数量和片段长度都有上限。
- 改了 HTTP/MCP 工具后，需要重启 `xiaozhi-desktop-http`。
- 改了 Java 工具后，需要重启 Java server/dialogue。
- 如果 Java 运行在容器里，`127.0.0.1:8765` 指向容器自己，需要改 `desktop.mcp.base-url`。

## 下一步建议

- README 继续保持第一屏可用，不要写成论文。
- Java 工具描述可以继续优化，让 LLM 更容易选择 `desktop_workflow`。
- 后续如果要做日志/摘要/loop，先加配置开关，默认关闭。
