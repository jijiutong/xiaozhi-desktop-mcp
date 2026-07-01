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

Legacy `/tools/...` routes remain available for debugging and fine-grained control.

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
remember
list_projects
resolve_project
open_cc_project
open_cc_project_named
ask_cc
ask_cc_project
check_cc
continue_cc
focus_cc
stop_cc
cleanup_sessions
search_obsidian
append_note
append_daily_note
recent_memories
health
config_summary
tool_catalog
pending_create
pending_list
pending_confirm
pending_cancel
```

Use `GET /api/v1/actions` for machine-readable parameters and risk levels.

## Safety Model

- No arbitrary shell command action exists.
- Project actions are constrained by `CC_ALLOWED_PROJECTS`.
- App actions are constrained by `ALLOWED_APPS`.
- Obsidian actions are constrained by `OBSIDIAN_VAULT`.
- Medium-risk actions can be routed through pending actions.

See [security.md](security.md) for more detail.
