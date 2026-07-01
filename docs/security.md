# Security Model

`xiaozhi-desktop-mcp` starts conservative. The goal is to make Xiaozhi useful on a Mac without turning voice recognition mistakes into dangerous system actions.

## Low Risk: Execute Directly

These actions are enabled in the first version:

- Append memories to the configured Obsidian vault.
- Create pending cc/Codex task files.
- Open applications listed in `ALLOWED_APPS`.

All generated files are written inside configured directories.

## Medium Risk: Require Confirmation Later

These actions should create a pending action first or require explicit confirmation:

- Send instructions into a Claude Code/Codex session.
- Continue or stop a Claude Code/Codex session.
- Close terminal windows or applications.
- Switch models or send slash commands.

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

## HTTP Rules

- Localhost mode can run without a token for personal desktop use.
- Non-localhost HTTP binding requires `DESKTOP_MCP_AUTH_TOKEN`.
- Protected `/api/...` and `/tools/...` routes accept `Authorization: Bearer <token>` or `X-Desktop-Mcp-Token`.
