# Changelog

## Unreleased

### Changed

- Removed legacy `/tools/...` HTTP routes. HTTP clients now use only `/api/v1/dispatch`.
- Updated tool catalog entries to expose `api_v1_action` names instead of legacy HTTP paths.
- Updated operations and maintainer docs to use API v1 dispatch examples.
- Claude Code/Codex send/continue/stop operations now require a registered session by default.
- Added explicit `allow_frontmost` opt-in for clients that intentionally target the frontmost Terminal tab.
- Added early pending-action parameter validation.
- Added pytest and ruff configuration plus core safety tests.
- Added API v1 and MCP actions for opening/closing allowlisted apps.
- Added API v1 and MCP actions for Claude Code/Codex slash commands and model switching.
- Added Obsidian note create/open actions with vault path safety.
- Added Xcode project open, build, test, clean, and recent error summary actions constrained by `XCODE_ALLOWED_PROJECTS`.

## 1.0.0 - 2026-07-01

Stable local desktop MCP/HTTP service for Xiaozhi and language-agnostic clients.

### Added

- API v1 unified HTTP interface:
  - `GET /api/v1/health`
  - `GET /api/v1/actions`
  - `POST /api/v1/dispatch`
- Language-neutral dispatch envelope for Java, Python, Go, and other clients.
- Claude Code/Codex visible Terminal/iTerm session control.
- Session registration, status, focus, cleanup, model switching, slash commands.
- Obsidian memory, append note, daily note, search, and recent memory tools.
- Project alias resolution from `CC_ALLOWED_PROJECTS`.
- Pending action queue for confirmation-based medium-risk actions.
- Desktop health checks and non-secret configuration summary.
- Tool catalog for client routing.

### Stable Boundaries

- No arbitrary shell execution.
- App operations are allowlisted by `ALLOWED_APPS`.
- Claude Code/Codex projects are constrained by `CC_ALLOWED_PROJECTS`.
- Obsidian file operations are constrained by `OBSIDIAN_VAULT`.
- Pending actions are in-memory and cleared on service restart.

### Compatibility

- HTTP clients should use `/api/v1/dispatch`.
