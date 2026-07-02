# API v1

`xiaozhi-desktop-mcp` exposes a language-neutral HTTP API for Java, Python, Go, and other clients.

Base URL:

```text
http://127.0.0.1:8765
```

## Endpoints

```text
GET  /api/v1/health
GET  /api/v1/actions
POST /api/v1/dispatch
```

HTTP clients should use `POST /api/v1/dispatch`. Legacy `/tools/...` HTTP routes were removed to keep one safety policy.

New voice clients should prefer `desktop_intent` for broad desktop workflows, then fall back to specific actions when they need exact control.

If `DESKTOP_MCP_AUTH_TOKEN` is set, protected API routes require either:

```text
Authorization: Bearer <token>
```

or:

```text
X-Desktop-Mcp-Token: <token>
```

## Dispatch Request

```json
{
  "request_id": "client-generated-id",
  "action": "ask_cc_project",
  "params": {
    "project": "xiaozhi-desktop-mcp",
    "text": "帮我检查 README"
  }
}
```

`request_id` is optional and echoed back unchanged.

Action names accept hyphen or underscore forms. For example, `resolve-project` and `resolve_project` are equivalent.

## Dispatch Response

```json
{
  "success": true,
  "request_id": "client-generated-id",
  "action": "ask_cc_project",
  "spoken_message": "已交给 Claude Code。",
  "error_spoken_message": "",
  "error": "",
  "data": {}
}
```

On failure:

```json
{
  "success": false,
  "request_id": "client-generated-id",
  "action": "search_obsidian",
  "spoken_message": "",
  "error_spoken_message": "搜索关键词是空的。",
  "error": "search query is empty",
  "data": {}
}
```

Clients should display or speak `spoken_message` on success and `error_spoken_message` on failure.

## Common Actions

```text
desktop_intent
category_registry
remember
list_projects
resolve_project
open_cc_project
open_cc_project_named
ask_cc
ask_cc_project
cc_send_slash_command
cc_switch_model
check_cc
continue_cc
focus_cc
stop_cc
cleanup_sessions
app_open
app_close
search_obsidian
append_note
append_daily_note
create_note
open_note
recent_memories
xcode_open_project
xcode_build
xcode_test
xcode_clean
xcode_last_errors
health
config_summary
tool_catalog
pending_create
pending_list
pending_confirm
pending_cancel
```

Generic intent request:

```json
{
  "request_id": "voice-001",
  "action": "desktop_intent",
  "params": {
    "category": "browser",
    "intent": "search",
    "params": {
      "query": "desktop mcp"
    }
  }
}
```

Built-in categories:

```text
music    open, play, pause, toggle, next, previous, search
docs     remember, search, create, open, append, daily
ai       open, send, continue, status, focus, stop, slash, model
dev      open, build, test, clean, errors
browser  open, search
system   open, reveal, clipboard_get, clipboard_set
```

Use `GET /api/v1/actions` for machine-readable parameters and risk levels.

Medium-risk actions such as `ask_cc`, `ask_cc_project`, `continue_cc`, `stop_cc`, `app_close`, `cc_send_slash_command`, `cc_switch_model`, `xcode_build`, `xcode_test`, and `xcode_clean` create a pending action by default. Pass `"confirm": true` only when the client has already received explicit user confirmation.

Claude Code/Codex send, continue, and stop actions require a registered session by default. A client may pass `"allow_frontmost": true` only when the user explicitly wants to target the frontmost Terminal tab.

## Safety Model

- No arbitrary shell command action exists.
- Project actions are constrained by `CC_ALLOWED_PROJECTS`.
- App actions are constrained by `ALLOWED_APPS`.
- Obsidian actions are constrained by `OBSIDIAN_VAULT`.
- Xcode actions are constrained by `XCODE_ALLOWED_PROJECTS`.
- Finder path actions are constrained to Obsidian, task, and allowlisted project roots.
- Medium-risk API v1 actions are routed through pending actions unless `confirm=true` is supplied.

See [security.md](security.md) for more detail.
