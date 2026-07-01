# Operations

## Start

```bash
cd /Users/jijiutong/plugin/smail_project/xiaozhi-desktop-mcp
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
curl http://127.0.0.1:8765/tools/desktop/health-detail
```

Configuration summary:

```bash
curl http://127.0.0.1:8765/tools/desktop/config-summary
```

## Common Fixes

### Claude Code window cannot be found

Run:

```bash
curl -X POST http://127.0.0.1:8765/tools/cc/cleanup-sessions
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
- Pending actions are in memory.
- Restarting `xiaozhi-desktop-http` clears both.
- Obsidian notes and task files are written to disk and persist.

## Checks Before Release

```bash
.venv/bin/python -m compileall -f src
```

Useful smoke tests:

```bash
curl http://127.0.0.1:8765/api/v1/actions
curl -X POST http://127.0.0.1:8765/api/v1/dispatch \
  -H "Content-Type: application/json" \
  -d '{"request_id":"smoke-1","action":"list_projects","params":{}}'
```
