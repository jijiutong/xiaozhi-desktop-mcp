# Security Model

`xiaozhi-desktop-mcp` starts conservative. The goal is to make Xiaozhi useful on a Mac without turning voice recognition mistakes into dangerous system actions.

## Low Risk: Execute Directly

These actions are enabled in the first version:

- Append memories to the configured Obsidian vault.
- Create pending cc/Codex task files.
- Open applications listed in `ALLOWED_APPS`.

All generated files are written inside configured directories.

## Medium Risk: Require Confirmation Later

These actions are planned, but should create a pending action first or require explicit confirmation:

- Run an Xcode build or test command.
- Send an email after a draft is reviewed.
- Run a known, allowlisted project command.
- Trigger git operations such as commit or push.

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
