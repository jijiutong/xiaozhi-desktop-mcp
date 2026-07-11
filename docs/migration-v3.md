# Migrating to 3.0

## Compatibility

- Existing `/api/v1/dispatch` clients keep the same request and response envelope.
- Existing action names remain available.
- MCP stdio and Streamable HTTP startup commands are unchanged.

## New State Database

3.0 persists pending actions, workflows, and redacted audit events in SQLite.

```env
DESKTOP_MCP_STATE_DB=~/.local/share/xiaozhi-desktop-mcp/state.db
DESKTOP_MCP_PENDING_TTL_SECONDS=600
DESKTOP_MCP_AUDIT_ENABLED=true
DESKTOP_MCP_AUDIT_RETENTION_DAYS=30
```

The parent directory is created automatically. Ensure the service account can write to it.

## API v2 Confirmation Change

In API v1, a legacy client can still send `confirm=true` after collecting confirmation itself.

In API v2, `confirm=true` is ignored for medium-risk actions. The call returns a pending `action_id`; execute it with a separate `pending_confirm` request. This prevents untrusted clients from self-authorizing a risky action.

## App Aliases and Drivers

Aliases are now resolved case-insensitively. Browser and music actions expose `app_capabilities` so clients can discover exact supported commands before calling them.

When the name shown to users differs from the installed `.app`/AppleScript name, configure it separately. The default NetEase mapping is:

```env
APP_AUTOMATION_ALIASES=网易云音乐=NeteaseMusic
```

Browser control can be restricted by domain:

```env
DESKTOP_MCP_BROWSER_ALLOWED_DOMAINS=example.com,docs.example.com
```

An empty value keeps the 2.x behavior and allows any `http` or `https` domain.

## Verification

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests scripts
.venv/bin/python -m compileall -f src
DESKTOP_MCP_STATE_DB=/tmp/xiaozhi-smoke.db .venv/bin/python scripts/mac_smoke.py
```
