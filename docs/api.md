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
GET  /api/v2/actions
POST /api/v2/dispatch
```

HTTP clients should use `POST /api/v1/dispatch`. Legacy `/tools/...` HTTP routes were removed to keep one safety policy.

New voice clients should prefer `desktop_intent` for broad desktop workflows, then fall back to specific actions when they need exact control.

API v2 is the recommended execution entry for new clients. It performs strict parameter validation, policy enforcement, stable error mapping, trace metadata, and redacted audit recording while preserving the v1 response envelope.

If `DESKTOP_MCP_AUTH_TOKEN` is set, protected API routes require either:

```text
Authorization: Bearer <token>
```

or:

```text
X-Desktop-Mcp-Token: <token>
```

Responses include `X-Request-Id`. Clients can pass their own `X-Request-Id`
header; otherwise the server generates one and logs it.

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

## API v2

`POST /api/v2/dispatch` accepts the same `action`, `params`, and `request_id` fields as v1, plus an optional `client` string:

```json
{
  "request_id": "client-generated-id",
  "client": "xiaozhi-java",
  "action": "browser_search",
  "params": {
    "query": "desktop mcp",
    "app_name": "chrome"
  }
}
```

The response keeps the v1 envelope and adds:

```json
{
  "api_version": "v2",
  "policy": {
    "default": "allow",
    "risk": "low"
  },
  "trace": {
    "client": "xiaozhi-java",
    "requested_action": "browser_search",
    "normalized_action": "browser_search",
    "backend": "api_v1"
  }
}
```

Failed v2 responses include a stable `error_code` such as `INVALID_PARAMS`, `POLICY_DENIED`, `PERMISSION_DENIED`, `NOT_FOUND`, `CONFLICT`, `TIMEOUT`, or `EXECUTION_FAILED`.

API v2 never treats `confirm=true` as authorization for medium-risk actions. It always creates a persistent pending action. Confirm it separately with `pending_confirm` and the returned `action_id`.

## Common Actions

```text
desktop_intent
category_registry
desktop_screenshot
desktop_window_screenshot
desktop_ocr
accessibility_capabilities
accessibility_tree
accessibility_action
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
app_focus
app_status
app_capabilities
app_close
browser_open
browser_search
browser_tabs
browser_current
browser_control
browser_capabilities
music_control
music_search
music_status
music_set_volume
music_search_app
music_capabilities
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
audit_list
workflow_plan
workflow_execute
workflow_get
workflow_cancel
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
desktop  screenshot, window_screenshot, ocr, ui_tree, ui_action, capabilities
music    open, play, pause, toggle, next, previous, search, search_app, status, volume, capabilities
docs     remember, search, create, open, append, daily
ai       open, send, continue, status, focus, stop, slash, model
dev      open, build, test, clean, errors
browser  open, search, tabs, current, control, capabilities
app      open, focus, status, close, capabilities
system   open, reveal, clipboard_get, clipboard_set
```

Use `GET /api/v1/actions` for machine-readable parameters and risk levels.

Use `GET /api/v2/actions` for parameter schemas, policy metadata, examples, and v1 compatibility markers.

Medium-risk actions such as `ask_cc`, `app_close`, `browser_control`, `music_search_app`, and Xcode actions create a persistent pending action. API v1 retains the legacy `confirm=true` behavior for compatibility; API v2 always requires the separate `pending_confirm` action.

## Desktop Perception and Accessibility

Capture a display for an HTTP client:

```json
{
  "action": "desktop_screenshot",
  "params": {"display_id": 1, "max_width": 1600}
}
```

HTTP returns PNG data in `data.image_base64`. The direct MCP `desktop_screenshot` and `desktop_window_screenshot` tools return metadata plus an MCP `ImageContent` block so a multimodal client can inspect the image directly.

Read a semantic UI tree:

```json
{
  "action": "accessibility_tree",
  "params": {
    "app_name": "chrome",
    "window_index": 1,
    "max_depth": 5,
    "max_elements": 200,
    "include_values": false
  }
}
```

Each result can include `element_id`, `role`, `subrole`, `title`, `description`, `identifier`, `enabled`, `focused`, `selected`, `actions`, and screen-space `bounds`. IDs are 1-based Accessibility child paths such as `ax:1.2`. Re-read the tree after the UI changes because an old path may no longer identify the same element.

Create a confirmed semantic action:

```json
{
  "action": "accessibility_action",
  "params": {
    "app_name": "chrome",
    "command": "input",
    "element_id": "ax:1.2",
    "text": "desktop mcp"
  }
}
```

Supported commands are `click`, `input`, `scroll`, `drag`, `menu_select`, and `file_dialog_choose`. This call creates a pending action under API v2. Use `pending_confirm` with its `action_id` to execute it. Drag requires both `element_id` and `target_element_id`. File dialog paths must already exist inside configured safe roots.

`desktop_ocr` supports `source=display|window` and returns recognized text blocks. Its normalized bounds use the macOS Vision coordinate system with the origin at the lower-left.

## Workflows

Create a validated plan without executing it:

```json
{
  "action": "workflow_plan",
  "params": {
    "name": "research and save",
    "steps": [
      {"action": "browser_open", "params": {"url": "https://example.com"}},
      {"action": "remember", "params": {"text": "Research started"}}
    ]
  }
}
```

Call `workflow_execute` with the returned `workflow_id`. A workflow pauses with `status=waiting_confirmation` when a step creates a pending action. Confirm that action, then call `workflow_execute` again to resume. Workflow and pending state survive service restarts.

## Browser Drivers

- Chrome, Edge, and Arc use the Chromium AppleScript Driver.
- Safari uses a dedicated Safari Driver.
- Read actions: `browser_tabs`, `browser_current`, `browser_capabilities`.
- Confirmed control: `browser_control` with `focus_tab`, `close_tab`, `reload`, `back`, or `forward`.
- Arbitrary JavaScript and coordinate clicking are not exposed.

## MCP v2

Standard MCP clients can call `desktop_dispatch_v2(action, params, client)` to use the same Schema, policy, pending, workflow, and audit pipeline as HTTP API v2.

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
