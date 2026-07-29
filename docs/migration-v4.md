# Migrating to 4.0

## Status

`4.0.0` introduces the reliable desktop-execution core. Existing API v1/v2 actions remain available. New clients can opt into observation-bound execution without changing older integrations.

## Compatibility

- `/api/v1/dispatch` and `/api/v2/dispatch` keep their existing envelopes.
- Existing action names and MCP startup commands remain available.
- Existing linear workflow definitions remain valid.
- `accessibility_action` remains supported; use `desktop_execute_step` when the caller needs stale-target protection and result verification.

## State Database Migration

On first access, the service creates `schema_migrations` and applies ordered migrations for observations, idempotency records, workflow events, and execution leases. Existing pending actions, workflows, and audit events are retained.

Before upgrading, stop the service and copy the state database:

```bash
cp ~/.local/share/xiaozhi-desktop-mcp/state.db ~/.local/share/xiaozhi-desktop-mcp/state.db.v3-backup
```

Add the optional observation TTL configuration:

```env
DESKTOP_MCP_OBSERVATION_TTL_SECONDS=120
DESKTOP_MCP_WORKFLOW_LEASE_SECONDS=300
```

The minimum accepted TTL is 10 seconds. Expired observations cannot authorize a desktop step.

Workflow runners use a renewable lease (minimum 30 seconds). After a crashed runner's lease expires, read-only steps can be replayed. A step that may have written external state is marked failed with `RECOVERY_REQUIRED` because its outcome cannot be guessed safely.

Authenticated HTTP clients can also be restricted by capability:

```env
DESKTOP_MCP_AUTH_SCOPES=screen:read,state:read,desktop:control
```

Omitting a required scope returns HTTP 403 and `SCOPE_DENIED`. Composite intents and workflows require the union of nested scopes. Local unauthenticated mode and direct MCP calls remain trusted by default.

After 4.0 has migrated and written the database, rolling back to 3.x should use the pre-upgrade backup rather than sharing the migrated file.

## Verified Execution Flow

Create an observation:

```json
{
  "action": "desktop_observe",
  "params": {"app_name": "chrome", "window_index": 1}
}
```

Create a verified action from its `observation_id`:

```json
{
  "action": "desktop_execute_step",
  "params": {
    "observation_id": "obs_...",
    "target": {"element_id": "ax:1", "role": "AXButton", "title": "保存"},
    "preconditions": {"enabled": true},
    "action": {"command": "click"},
    "expectation": {"kind": "element_absent"},
    "idempotency_key": "save-document-001",
    "timeout_ms": 5000
  }
}
```

The call returns a pending `action_id`. Confirm it separately with `pending_confirm`. Confirmation re-observes the window and target before executing once, then polls observations until the expectation succeeds or the timeout expires.

Supported expectations:

```text
element_absent
element_present
element_enabled
element_disabled
tree_changed
```

## Dynamic Workflow Additions

Existing action steps may add:

```json
{
  "action": "browser_open",
  "params": {"url": "https://example.com"},
  "retry": {"max_attempts": 2},
  "compensation": {"action": "config_summary", "params": {}}
}
```

Automatic retry is limited to explicitly read-only actions and at most three attempts. Compensation must be an explicitly declared low-risk action that does not require confirmation.

Read-only wait steps poll a structured result path with a hard attempt and interval limit:

```json
{
  "kind": "wait",
  "action": "app_status",
  "params": {"app_name": "Obsidian"},
  "until": {"field": "data.running", "equals": true},
  "max_attempts": 10,
  "interval_ms": 250
}
```

Each `workflow_execute` performs at most one wait poll. If the condition is false, the workflow persists `waiting_condition` and returns. Call `workflow_execute` again after `next_poll_at`; this avoids blocking the service and makes waiting restart-safe.

`workflow_get` now includes a redacted event timeline. Events contain lifecycle metadata and action names, never workflow parameter values.

Condition steps can inspect only `status`, `result.success`, or `result.error_code` from an earlier step. Both branches are schema-validated before the workflow is stored; no general expression evaluator is used.

## Verification

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m compileall -f src
DESKTOP_MCP_STATE_DB=/tmp/xiaozhi-v4-smoke.db .venv/bin/python scripts/mac_smoke.py
```
