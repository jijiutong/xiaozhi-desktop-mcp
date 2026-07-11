# Operations

## Start

```bash
cd /path/to/xiaozhi-desktop-mcp
. .venv/bin/activate
xiaozhi-desktop-http
```

Default address:

```text
http://127.0.0.1:8765
```

## Health Checks

Simple health:

```bash
curl http://127.0.0.1:8765/health
```

API v1 health:

```bash
curl http://127.0.0.1:8765/api/v1/health
```

Detailed desktop checks:

```bash
curl -X POST http://127.0.0.1:8765/api/v1/dispatch \
  -H "Content-Type: application/json" \
  -d '{"request_id":"health-detail","action":"health","params":{}}'
```

Configuration summary:

```bash
curl -X POST http://127.0.0.1:8765/api/v1/dispatch \
  -H "Content-Type: application/json" \
  -d '{"request_id":"config-summary","action":"config_summary","params":{}}'
```

If you bind the HTTP server to a non-localhost address, set `DESKTOP_MCP_AUTH_TOKEN`.

```bash
export DESKTOP_MCP_AUTH_TOKEN="change-me"
curl -H "Authorization: Bearer change-me" http://127.0.0.1:8765/api/v1/actions
```

## Common Fixes

### Claude Code window cannot be found

Run:

```bash
curl -X POST http://127.0.0.1:8765/api/v1/dispatch \
  -H "Content-Type: application/json" \
  -d '{"request_id":"cleanup","action":"cleanup_sessions","params":{}}'
```

Then open a new visible session.

### Java/Python/Go runs in a container

`127.0.0.1:8765` points to the container itself. Configure the client to use the Mac host address or a private network address.

### iTerm warning in health checks

If `CC_VISIBLE_TERMINALS` contains `iTerm` but iTerm is not installed, remove it from `.env` or install iTerm.

### Obsidian inbox directory does not exist

The service creates directories when writing. A missing inbox directory is a warning, not always a blocker, as long as its parent is writable.

## Restart Notes

- Registered visible sessions are in memory.
- Pending actions and workflows are persisted in `DESKTOP_MCP_STATE_DB`.
- Restarting `xiaozhi-desktop-http` keeps pending actions, workflow progress, and audit events.
- Pending actions older than `DESKTOP_MCP_PENDING_TTL_SECONDS` expire automatically.
- Obsidian notes and task files are written to disk and persist.

## State Database

Default path:

```text
~/.local/share/xiaozhi-desktop-mcp/state.db
```

The database contains pending actions, workflow state, and redacted audit metadata. Stop the service before copying it for backup. Deleting it resets only runtime state; it does not delete Obsidian notes or project files.

## Browser and Accessibility Permissions

Browser tab reading uses AppleScript. NetEase Cloud Music client search uses macOS Accessibility automation. Grant Automation/Accessibility access to the terminal or service process when macOS requests it.

Safe metadata checks:

```bash
DESKTOP_MCP_STATE_DB=/tmp/xiaozhi-smoke.db .venv/bin/python scripts/mac_smoke.py
```

Read-only real App checks:

```bash
.venv/bin/python scripts/mac_smoke.py --live --browser chrome --music Music
```

## Checks Before Release

```bash
.venv/bin/python -m compileall -f src
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
```

Useful smoke tests:

```bash
curl http://127.0.0.1:8765/api/v1/actions
curl -X POST http://127.0.0.1:8765/api/v1/dispatch \
  -H "Content-Type: application/json" \
  -d '{"request_id":"smoke-1","action":"list_projects","params":{}}'
```
