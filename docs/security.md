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
- Finder opens paths only inside known safe roots.
- Clipboard set/get is explicit under the `system` category.

All generated files are written inside configured directories.

## Medium Risk: Require Confirmation Later

These actions should create a pending action first or require explicit confirmation:

- Send instructions into a Claude Code/Codex session.
- Continue or stop a Claude Code/Codex session.
- Close terminal windows or applications.
- Switch models or send slash commands.
- Run Xcode build, test, or clean.

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

## Generic Intent Rules

- `desktop_intent` is a router, not arbitrary execution.
- Supported categories are `music`, `docs`, `ai`, `dev`, `browser`, and `system`.
- Unknown category/intent pairs are rejected.
- `desktop-mcp.yaml` can describe categories for clients, but built-in actions still enforce code-level safety checks.

## HTTP Rules

- Localhost mode can run without a token for personal desktop use.
- Non-localhost HTTP binding requires `DESKTOP_MCP_AUTH_TOKEN`.
- Protected `/api/...` routes accept `Authorization: Bearer <token>` or `X-Desktop-Mcp-Token`.

## Terminal Targeting

- Claude Code/Codex send, continue, slash, model, and stop operations target registered sessions by default.
- Frontmost Terminal fallback is disabled unless a client explicitly passes `allow_frontmost=true`.
- Pending actions validate required parameters before they are created.
