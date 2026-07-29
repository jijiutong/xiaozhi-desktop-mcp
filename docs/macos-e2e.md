# macOS E2E Matrix

This is the release-side real desktop check for 4.0. The script prints only pass/fail metadata; it does not print screenshots or observed UI content.

## Required Host State

- Run from an interactive, logged-in macOS session.
- Grant the launching terminal or service Screen Recording, Accessibility, and Automation → System Events permissions.
- Open Google Chrome, Safari, Finder, Obsidian, Xcode, and Terminal.
- Keep the Apps in `ALLOWED_APPS` and use a disposable document/profile for write verification.

## Read-Only Matrix

```bash
DESKTOP_MCP_STATE_DB=/tmp/xiaozhi-v4-e2e.db \
.venv/bin/python scripts/mac_smoke.py --perception-live \
  --browser "Google Chrome" \
  --observe-app Safari \
  --observe-app Finder \
  --observe-app Obsidian \
  --observe-app Xcode \
  --observe-app Terminal
```

The matrix checks package/catalog loading, privacy-safe configuration, Driver capability discovery, display capture, and a stored 4.0 `desktop_observe` for every App.

## Confirmed Write Scenario

For each App, use a disposable target and run this sequence through API v2:

1. `desktop_observe` and select a unique semantic element.
2. `desktop_execute_step` with preconditions, an expectation, and a unique `idempotency_key`.
3. `pending_confirm` using the returned `action_id`.
4. Repeat the same idempotency key and verify the write is not repeated.
5. Change or close the target window and verify the old observation fails with `WINDOW_CHANGED`, `TARGET_STALE`, or `TARGET_AMBIGUOUS`.

Never use a real account, destructive file action, payment UI, password field, or permission dialog for this scenario.

## 4.0 Release Record — 2026-07-29

- Automated unit/contract/migration/recovery suite: passed (`128` tests at the final GA cut).
- Offline macOS metadata smoke: passed.
- Final interactive perception attempt from the Codex execution host: display capture passed; Chrome observation was blocked by macOS Accessibility with `osascript 不允许辅助访问 (-25211)`. The API maps this to `PERMISSION_DENIED`; grant Accessibility permission before rerunning the matrix.
- Thirty-run interactive App soak: intentionally skipped for the direct GA cut because this instance had no users. Run the matrix above before attaching a real client.

These host failures do not relax the runtime safety policy: verified writes still require a pending confirmation, and stale or ambiguous targets fail closed.
