# Changelog

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

- Existing `/tools/...` routes are preserved for low-level control and debugging.
- New clients should prefer `/api/v1/dispatch`.
