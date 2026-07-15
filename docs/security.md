# Security Model

`xiaozhi-desktop-mcp` starts conservative. The goal is to make Xiaozhi useful on a Mac without turning voice recognition mistakes into dangerous system actions.

## Low Risk: Execute Directly

These actions are enabled in the first version:

- Append memories to the configured Obsidian vault.
- Create or open notes inside the configured Obsidian vault.
- Create pending cc/Codex task files.
- Open applications listed in `ALLOWED_APPS`.
- Open Xcode projects inside `XCODE_ALLOWED_PROJECTS`.
- Browser opens only http(s) URLs and only through allowlisted browser apps.
- Browser URLs containing embedded credentials are rejected.
- `DESKTOP_MCP_BROWSER_ALLOWED_DOMAINS` can restrict navigation to exact domains and their subdomains.
- Finder opens paths only inside known safe roots.
- Clipboard set/get is explicit under the `system` category.
- Screen and OCR reads are explicit tools. Window screenshots and Accessibility trees require an allowlisted App.

All generated files are written inside configured directories.

## Medium Risk: Require Confirmation Later

These actions should create a pending action first or require explicit confirmation:

- Send instructions into a Claude Code/Codex session.
- Continue or stop a Claude Code/Codex session.
- Close terminal windows or applications.
- Switch models or send slash commands.
- Run Xcode build, test, or clean.
- Focus, close, reload, or navigate a browser tab through `browser_control`.
- Type a query into NetEase Cloud Music through `music_search_app`.
- Click, type, scroll, drag, choose menus, or operate a file dialog through `accessibility_action`.

## High Risk: Deny by Default

These actions should stay disabled unless a user explicitly opts in with strong safeguards:

- Arbitrary shell commands.
- Deleting or moving user files.
- Reading secrets or credential stores.
- Deployment, payment, account, or permission changes.

## Path Rules

- Obsidian memories must stay inside `OBSIDIAN_VAULT`.
- cc/Codex task files must stay inside `CC_TASKS_DIR`.
- macOS app launching is limited by `ALLOWED_APPS`.
- Xcode project operations must stay inside `XCODE_ALLOWED_PROJECTS`.
- Finder path operations must stay inside Obsidian, task, cc project, or Xcode project roots.
- Accessibility window targets must resolve through `ALLOWED_APPS` and configured process aliases.
- File dialog selection is limited to existing paths inside the same safe roots.

## Screen and UI Privacy

- A full-display screenshot can contain private information from any visible App. Only expose the service to trusted local clients or require a strong token.
- HTTP screenshot responses contain base64 image data. Request logs and audit events do not store response images.
- Accessibility `include_values=false` is the default so text-field values are not returned unless explicitly requested. Secure text fields stay redacted even when values are requested.
- Pending Accessibility actions can contain input text or file paths because those values are needed after confirmation; protect the local state database accordingly.
- Password managers, credential stores, payments, account changes, permission changes, destructive file operations, and arbitrary coordinate clicks remain outside the supported action set.

## Generic Intent Rules

- `desktop_intent` is a router, not arbitrary execution.
- Supported categories include `desktop`, `music`, `docs`, `ai`, `dev`, `browser`, `app`, and `system`.
- Unknown category/intent pairs are rejected.
- `desktop-mcp.yaml` can describe categories for clients, but built-in actions still enforce code-level safety checks.

## HTTP Rules

- Localhost mode can run without a token for personal desktop use.
- Non-localhost HTTP binding requires `DESKTOP_MCP_AUTH_TOKEN`.
- Protected `/api/...` routes accept `Authorization: Bearer <token>` or `X-Desktop-Mcp-Token`.
- Standard Streamable HTTP MCP runs at `/mcp` by default and accepts the same
  token headers.
- HTTP responses include `X-Request-Id`; logs include request id, path, status,
  duration, client host, and auth result without printing the token.
- stdio MCP tool calls log tool name, success flag, and duration without logging
  full tool arguments.

## API v2 Rules

- Parameters are validated against the action JSON Schema before a tool can run.
- Unknown parameters and invalid enum values are rejected.
- `confirm=true` never bypasses a medium-risk action in API v2.
- Medium-risk actions must be confirmed with a separate `pending_confirm` request.
- Pending actions have a configurable TTL and can only be claimed once.
- Workflows cannot contain nested workflow-control actions.

## Persistent State and Audit

- Pending actions, workflows, and audit events are stored in `DESKTOP_MCP_STATE_DB`.
- SQLite transactions prevent duplicate confirmation from executing an action twice.
- Expired actions cannot be confirmed.
- Audit events store request id, client, action, result, duration, and parameter names only.
- Audit events never store parameter values, bearer tokens, note text, search text, or workflow payloads.
- Audit write failures are logged but do not block unrelated low-risk operations.

## Terminal Targeting

- Claude Code/Codex send, continue, slash, model, and stop operations target registered sessions by default.
- Frontmost Terminal fallback is disabled unless a client explicitly passes `allow_frontmost=true`.
- Pending actions validate required parameters before they are created.
