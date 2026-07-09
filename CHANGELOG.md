# Changelog

## Unreleased

## 3.0.0-alpha.1 - 2026-07-09

### Added

- Added App alias and process alias configuration through `desktop-mcp.yaml`, `APP_ALIASES`, and `APP_PROCESS_ALIASES`.
- Added API v2 alpha endpoints:
  - `GET /api/v2/actions`
  - `POST /api/v2/dispatch`
- Added schema-rich action metadata with parameter schema, policy, examples, and v1 backend compatibility markers.
- Added v2 dispatch trace metadata while preserving the stable v1 execution backend.

### Changed

- App open/focus/status/music controls now resolve configured aliases before allowlist checks.
- AppleScript App string interpolation now uses explicit string quoting.
- Config summaries include App alias and process alias counts.

## 2.1.0 - 2026-07-08

### Added

- Added API v1 actions for focusing allowlisted apps and checking app running status.
- Added API v1 browser open/search actions backed by the existing http(s)-only browser safety checks.
- Added API v1 music control/search actions, including NetEase Cloud Music web search support.
- Added desktop intent support for app focus/status and NetEase music search provider routing.

### Changed

- Expanded default app allowlist and desktop category registry for common browsers and NetEase Cloud Music.

## 2.0.0 - 2026-07-08

Major release that keeps `/api/v1/...` wire compatibility while making action
metadata and medium-risk confirmation rules easier to evolve safely.

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
- Added `desktop-mcp.yaml`, `category_registry`, and `desktop_intent` for generic category-based desktop workflows.
- Added built-in category adapters for music, docs, AI, dev, browser, and system intents.
- Added browser open/search, Music controls, Finder safe path open/reveal, and clipboard get/set capabilities through `desktop_intent`.
- Added a shared action registry for API catalog metadata, risk levels, and pending-action parameter rules.
- Centralized API v1 medium-risk confirmation handling through a shared pending-action helper.
- Added registry consistency tests so API action metadata and dispatch handlers cannot drift silently.

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
