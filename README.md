# xiaozhi-desktop-mcp

把小智接到你的 Mac 桌面工作流：保存 Obsidian 记忆、打开 App、创建 cc/Codex 任务、启动和控制 Claude Code/Codex CLI。

当前版本：`1.0.0`。

这个项目不是小智服务器本体。它是一个本机 MCP/HTTP 工具服务，可以被 `xiaozhi-esp32-server`、Java/Python/Go 后端、`xiaozhi-mcphub` 或其他 MCP bridge 调用。

1.0 稳定边界：

- 不支持任意 shell。
- App 操作受 `ALLOWED_APPS` 限制。
- Claude Code/Codex 项目受 `CC_ALLOWED_PROJECTS` 限制。
- Obsidian 文件操作受 `OBSIDIAN_VAULT` 限制。
- pending action 是内存队列，服务重启会清空。

更多文档：

- [API v1](docs/api.md)
- [Client Examples](docs/clients.md)
- [Operations](docs/operations.md)
- [Security Model](docs/security.md)
- [Changelog](CHANGELOG.md)

工具返回会保留原始结构，同时尽量提供小智可直接播报的字段：

- 成功：优先读取 `spoken_message`。
- 失败：优先读取 `error_spoken_message`，再看 `error`。
- 状态查询：`cc_session_status` 还会返回中文 `summary`。

## 多语言接入

Java、Python、Go 等客户端推荐使用统一 HTTP API：

- `GET /api/v1/health`
- `GET /api/v1/actions`
- `POST /api/v1/dispatch`

请求格式：

```json
{
  "request_id": "optional-client-id",
  "action": "ask_cc_project",
  "params": {
    "project": "xiaozhi-desktop-mcp",
    "text": "帮我检查 README"
  }
}
```

响应格式：

```json
{
  "success": true,
  "request_id": "optional-client-id",
  "action": "ask_cc_project",
  "spoken_message": "已交给 Claude Code。",
  "error_spoken_message": "",
  "error": "",
  "data": {}
}
```

旧的 `/tools/...` 路由继续保留，适合调试和精细控制。

## 典型语音

```text
小智，记一下：这个项目先做成桌面 MCP。
小智，打开 Obsidian。
小智，打开一个可见的 Claude Code 窗口处理 xiaozhi-desktop-mcp。
小智，把 Claude Code 模型切到 sonnet。
小智，给 Claude Code 输入：帮我 review 当前项目，不要直接改文件。
```

## 能力

### 语音工作流

小智/Java 后端优先使用这些高层入口：

- `desktop_remember`
- `desktop_open_cc_project`
- `desktop_list_projects`
- `desktop_resolve_project`
- `desktop_open_cc_project_named`
- `desktop_ask_cc_project`
- `desktop_ask_cc`
- `desktop_check_cc`
- `desktop_continue_cc`
- `desktop_focus_cc`
- `desktop_stop_cc`
- `desktop_health_detail`
- `desktop_config_summary`
- `desktop_tool_catalog`
- HTTP: `POST /tools/desktop/remember`
- HTTP: `POST /tools/desktop/open-cc-project`
- HTTP: `GET /tools/desktop/projects`
- HTTP: `POST /tools/desktop/resolve-project`
- HTTP: `POST /tools/desktop/open-cc-project-named`
- HTTP: `POST /tools/desktop/ask-cc-project`
- HTTP: `POST /tools/desktop/ask-cc`
- HTTP: `POST /tools/desktop/check-cc`
- HTTP: `POST /tools/desktop/continue-cc`
- HTTP: `POST /tools/desktop/focus-cc`
- HTTP: `POST /tools/desktop/stop-cc`
- HTTP: `GET /tools/desktop/health-detail`
- HTTP: `GET /tools/desktop/config-summary`
- HTTP: `GET /tools/desktop/tool-catalog`

这些工具只编排下方已有安全工具，不新增任意 shell 能力。
自检工具只读环境，不会启动 Claude Code 或执行项目命令。
项目别名来自 `CC_ALLOWED_PROJECTS` 中的目录名，最终仍必须解析到白名单路径。

### 待确认动作

- `pending_action_create`
- `pending_action_list`
- `pending_action_confirm`
- `pending_action_cancel`
- HTTP: `POST /tools/pending-actions/create`
- HTTP: `POST /tools/pending-actions/list`
- HTTP: `GET /tools/pending-actions`
- HTTP: `POST /tools/pending-actions/confirm`
- HTTP: `POST /tools/pending-actions/cancel`

待确认动作是进程内队列，重启服务会清空。当前允许的动作类型：

- `app_close`
- `cc_close_terminal`
- `cc_continue`
- `cc_send_instruction`
- `cc_send_slash_command`
- `cc_stop`
- `cc_switch_model`

这些动作确认后只会调用现有白名单工具，不支持任意 shell。

### Obsidian

- `obsidian_save_memory`
- `obsidian_append_note`
- `obsidian_append_daily_note`
- `obsidian_search`
- `obsidian_recent_memories`
- HTTP: `POST /tools/obsidian/save-memory`
- HTTP: `POST /tools/obsidian/append-note`
- HTTP: `POST /tools/obsidian/append-daily-note`
- HTTP: `POST /tools/obsidian/search`
- HTTP: `POST /tools/obsidian/recent-memories`

把一句话追加到 Obsidian 指定笔记。
所有 Obsidian 路径都限制在 `OBSIDIAN_VAULT` 内。搜索只读 Markdown，跳过隐藏目录，并限制返回数量和片段长度。

### App

- `app_open`
- `app_close`
- HTTP: `POST /tools/app/open`
- HTTP: `POST /tools/app/close`

只打开或关闭配置白名单里的 macOS App。

### cc/Codex 任务

- `cc_create_task`
- HTTP: `POST /tools/cc/create-task`

创建 Markdown 待办任务，不执行命令。

### Claude Code / Codex CLI

- `cc_start_session`
- `cc_open_visible_session`
- `cc_open_claude_code`
- `cc_list_sessions`
- `cc_cleanup_sessions`
- `cc_session_status`
- `cc_focus_session`
- `cc_send_instruction`
- `cc_send_decision`
- `cc_send_slash_command`
- `cc_switch_model`
- `cc_stop_session`
- `cc_close_terminal`

当前默认统一走可见 Terminal：

- `cc_start_session` / `cc_open_visible_session` 都会打开 Terminal/iTerm，并登记 `session_id`。
- 打开的 tab/session 会写入稳定标题，例如 `xiaozhi-desktop-mcp:default`。
- `cc_list_sessions` 会列出当前服务进程记住的可见会话，并标记窗口是否仍存在。
- `cc_cleanup_sessions` 会清理已经不存在的会话登记。
- `cc_focus_session` 会把指定会话窗口拉到前台。
- `cc_send_instruction` / `cc_send_decision` / `cc_send_slash_command` 会优先按 `session_id` 定位已打标的 tab/session；未登记时回退到 Terminal 当前 tab。
- `cc_session_status` 会读取对应会话的文本尾部，并返回 `summary` 便于小智播报。
- `cc_stop_session` 会先发送 `/exit`，然后关闭对应会话所在窗口。
- `cc_close_terminal` 会直接关闭前台 Terminal/iTerm 窗口。

## 快速启动

```bash
cd /Users/jijiutong/plugin/smail_project/xiaozhi-desktop-mcp
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
```

启动 HTTP adapter：

```bash
xiaozhi-desktop-http
```

默认地址：

```text
http://127.0.0.1:8765
```

健康检查：

```bash
curl http://127.0.0.1:8765/health
```

API v1 动作列表：

```bash
curl http://127.0.0.1:8765/api/v1/actions
```

API v1 统一调用：

```bash
curl -X POST http://127.0.0.1:8765/api/v1/dispatch \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "demo-1",
    "action": "list_projects",
    "params": {}
  }'
```

详细自检：

```bash
curl http://127.0.0.1:8765/tools/desktop/health-detail
```

配置摘要：

```bash
curl http://127.0.0.1:8765/tools/desktop/config-summary
```

工具目录：

```bash
curl http://127.0.0.1:8765/tools/desktop/tool-catalog
```

清理失效 cc 会话：

```bash
curl -X POST http://127.0.0.1:8765/tools/cc/cleanup-sessions
```

创建一个待确认动作：

```bash
curl -X POST http://127.0.0.1:8765/tools/pending-actions/create \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "cc_continue",
    "params": {"session_id": "default"},
    "title": "让 Claude Code 继续"
  }'
```

确认执行：

```bash
curl -X POST http://127.0.0.1:8765/tools/pending-actions/confirm \
  -H "Content-Type: application/json" \
  -d '{"action_id": "替换成返回的 action_id"}'
```

## 常用测试

打开 Obsidian：

```bash
curl -X POST http://127.0.0.1:8765/tools/app/open \
  -H "Content-Type: application/json" \
  -d '{"app_name": "Obsidian"}'
```

关闭 Obsidian：

```bash
curl -X POST http://127.0.0.1:8765/tools/app/close \
  -H "Content-Type: application/json" \
  -d '{"app_name": "Obsidian"}'
```

写一条 Obsidian 记忆：

```bash
curl -X POST http://127.0.0.1:8765/tools/obsidian/save-memory \
  -H "Content-Type: application/json" \
  -d '{
    "text": "今天测试小智桌面工作流，Obsidian 写入已经打通。",
    "tags": "xiaozhi,voice-memory"
  }'
```

搜索 Obsidian：

```bash
curl -X POST http://127.0.0.1:8765/tools/obsidian/search \
  -H "Content-Type: application/json" \
  -d '{"query": "桌面 MCP", "limit": 5}'
```

写入每日笔记：

```bash
curl -X POST http://127.0.0.1:8765/tools/obsidian/append-daily-note \
  -H "Content-Type: application/json" \
  -d '{"text": "今天继续完善小智桌面工作流。"}'
```

打开可见 Claude Code：

```bash
curl -X POST http://127.0.0.1:8765/tools/cc/open-visible-session \
  -H "Content-Type: application/json" \
  -d '{
    "project_path": "/Users/jijiutong/plugin/smail_project/xiaozhi-desktop-mcp",
    "cli": "claude",
    "cli_args": "",
    "terminal": "Terminal",
    "session_id": "default"
  }'
```

查看已登记的 cc 会话：

```bash
curl http://127.0.0.1:8765/tools/cc/sessions
```

聚焦一个 cc 会话：

```bash
curl -X POST http://127.0.0.1:8765/tools/cc/focus-session \
  -H "Content-Type: application/json" \
  -d '{"session_id": "default"}'
```

启动 Claude Code：

```bash
curl -X POST http://127.0.0.1:8765/tools/cc/start-session \
  -H "Content-Type: application/json" \
  -d '{
    "project_path": "/Users/jijiutong/plugin/smail_project/xiaozhi-desktop-mcp",
    "cli": "claude",
    "cli_args": "",
    "session_id": "default"
  }'
```

给可见 Terminal 会话输入中文：

```bash
curl -X POST http://127.0.0.1:8765/tools/cc/send-instruction \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "default",
    "text": "帮我 review 当前项目，重点看 bug 和风险，不要直接修改文件。"
  }'
```

用语音工作流把任务交给 Claude Code：

```bash
curl -X POST http://127.0.0.1:8765/tools/desktop/ask-cc \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "default",
    "project_path": "/Users/jijiutong/plugin/smail_project/xiaozhi-desktop-mcp",
    "text": "帮我 review 当前项目，重点看 bug 和风险。"
  }'
```

按项目名把任务交给 Claude Code：

```bash
curl -X POST http://127.0.0.1:8765/tools/desktop/ask-cc-project \
  -H "Content-Type: application/json" \
  -d '{
    "project": "xiaozhi-desktop-mcp",
    "session_id": "default",
    "text": "帮我检查 README 里的工具说明是否完整。"
  }'
```

列出允许项目：

```bash
curl http://127.0.0.1:8765/tools/desktop/projects
```

关闭 Claude Code 和前台 Terminal 窗口：

```bash
curl -X POST http://127.0.0.1:8765/tools/cc/stop-session \
  -H "Content-Type: application/json" \
  -d '{"session_id": "default"}'
```

只关闭前台 Terminal 窗口：

```bash
curl -X POST http://127.0.0.1:8765/tools/cc/close-terminal \
  -H "Content-Type: application/json" \
  -d '{"terminal": "Terminal"}'
```

发送 slash 命令：

```bash
curl -X POST http://127.0.0.1:8765/tools/cc/send-slash-command \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "default",
    "command": "/compact"
  }'
```

切模型：

```bash
curl -X POST http://127.0.0.1:8765/tools/cc/switch-model \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "default",
    "model": "sonnet"
  }'
```

## 配置

`.env.example` 包含完整配置。关键项：

```env
OBSIDIAN_VAULT=/Users/jijiutong/obsidian
OBSIDIAN_MEMORY_FILE=00-Inbox/voice-memory.md
CC_TASKS_DIR=00-Inbox/cc-tasks

DEFAULT_PROJECT_ROOT=/Users/jijiutong/plugin/smail_project/xiaozhi-desktop-mcp
CC_ALLOWED_PROJECTS=/Users/jijiutong/plugin/smail_project/xiaozhi-desktop-mcp,/Users/jijiutong/plugin/smail_project/xiaozhi-esp32-server-java
CC_ALLOWED_CLIS=claude,codex
CC_DEFAULT_CLI=claude
CC_ALLOWED_CLI_ARGS=-c,--continue
CC_VISIBLE_TERMINALS=Terminal,iTerm
CC_ALLOWED_MODELS=

CC_SLASH_DEFAULT_POLICY=allow
CC_SLASH_ALLOW=
CC_SLASH_CONFIRM=
CC_SLASH_DENY=

ALLOWED_APPS=Obsidian,Xcode,Google Chrome,Terminal,Codex
DESKTOP_MCP_HTTP_HOST=127.0.0.1
DESKTOP_MCP_HTTP_PORT=8765
```

默认策略是“本机玩家模式”：能用为先。要收紧时再配置 allow/confirm/deny。

## Java 版小智接入

Java 后端可以通过 HTTP 调这个服务。示例：

```bash
curl -X POST "http://192.168.58.201:8084/api/mcpTool/desktop-test" \
  -H "Authorization: Bearer 你的token" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "cc_open_visible_session",
    "project_path": "/Users/jijiutong/plugin/smail_project/xiaozhi-desktop-mcp",
    "cli": "claude",
    "cli_args": "",
    "terminal": "Terminal"
  }'
```

正式语音链路走 Java 的 `desktop_workflow` 工具，底层仍然调用本服务。

## 安全边界

- 不提供任意 shell 执行接口。
- CLI 只能在 `CC_ALLOWED_PROJECTS` 允许的项目目录里启动。
- CLI 名称和启动参数走白名单。
- slash 命令默认允许，但可以配置成 confirm 或 deny。
- 默认不落 cc 输出日志，不做摘要，不做 RAG。
- 可见 Terminal 模式由人直接接管；后台 pty 模式由工具读尾部输出和发送输入。

更多说明见 [docs/security.md](docs/security.md) 和 [docs/xiaozhi-integration.md](docs/xiaozhi-integration.md)。
