from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .config import Settings
from .responses import ok


class WorkflowLeaseLost(RuntimeError):
    """Raised when a stale workflow runner attempts to persist state."""


class PendingActionStore:
    """SQLite-backed pending action lifecycle with atomic single-use claims."""

    def __init__(self, settings: Settings):
        self.path = settings.state_db_path
        self.ttl_seconds = settings.pending_ttl_seconds

    def create(self, action_id: str, action_type: str, params: dict, title: str) -> dict:
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(seconds=self.ttl_seconds)
        with _connect(self.path) as connection:
            _init_schema(connection)
            connection.execute(
                """
                INSERT INTO pending_actions (
                    action_id, action_type, params, title, status,
                    created_at, expires_at, resolved_at, result
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?, NULL, NULL)
                """,
                (
                    action_id,
                    action_type,
                    json.dumps(params, ensure_ascii=False),
                    title,
                    created_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )
        return self.get(action_id) or {}

    def get(self, action_id: str) -> dict | None:
        with _connect(self.path) as connection:
            _init_schema(connection)
            row = connection.execute(
                "SELECT * FROM pending_actions WHERE action_id = ?",
                (action_id,),
            ).fetchone()
        return _pending_row(row) if row else None

    def list(self, status: str = "pending") -> list[dict]:
        self.expire_stale()
        with _connect(self.path) as connection:
            _init_schema(connection)
            if status:
                rows = connection.execute(
                    "SELECT * FROM pending_actions WHERE status = ? ORDER BY created_at",
                    (status,),
                ).fetchall()
            else:
                rows = connection.execute("SELECT * FROM pending_actions ORDER BY created_at").fetchall()
        return [_pending_row(row) for row in rows]

    def claim(self, action_id: str) -> tuple[dict | None, str]:
        with _connect(self.path) as connection:
            _init_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM pending_actions WHERE action_id = ?",
                (action_id,),
            ).fetchone()
            if not row:
                connection.rollback()
                return None, "not_found"
            record = _pending_row(row)
            if record["status"] != "pending":
                connection.rollback()
                return record, record["status"]
            if datetime.fromisoformat(record["expires_at"]) <= datetime.now(timezone.utc):
                connection.execute(
                    "UPDATE pending_actions SET status = 'expired', resolved_at = ? WHERE action_id = ?",
                    (_now_iso(), action_id),
                )
                connection.commit()
                return self.get(action_id), "expired"
            changed = connection.execute(
                "UPDATE pending_actions SET status = 'executing' WHERE action_id = ? AND status = 'pending'",
                (action_id,),
            ).rowcount
            connection.commit()
        if changed != 1:
            return self.get(action_id), "already_claimed"
        return self.get(action_id), ""

    def resolve(self, action_id: str, status: str, result: dict) -> dict | None:
        with _connect(self.path) as connection:
            _init_schema(connection)
            connection.execute(
                """
                UPDATE pending_actions
                SET status = ?, result = ?, resolved_at = ?
                WHERE action_id = ? AND status = 'executing'
                """,
                (status, json.dumps(result, ensure_ascii=False), _now_iso(), action_id),
            )
        return self.get(action_id)

    def cancel(self, action_id: str) -> tuple[dict | None, str]:
        with _connect(self.path) as connection:
            _init_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM pending_actions WHERE action_id = ?",
                (action_id,),
            ).fetchone()
            if not row:
                connection.rollback()
                return None, "not_found"
            record = _pending_row(row)
            if record["status"] != "pending":
                connection.rollback()
                return record, record["status"]
            connection.execute(
                "UPDATE pending_actions SET status = 'cancelled', resolved_at = ? WHERE action_id = ?",
                (_now_iso(), action_id),
            )
            connection.commit()
        return self.get(action_id), ""

    def expire_stale(self) -> None:
        with _connect(self.path) as connection:
            _init_schema(connection)
            now = _now_iso()
            connection.execute(
                """
                UPDATE pending_actions SET status = 'expired', resolved_at = ?
                WHERE status = 'pending' AND expires_at <= ?
                """,
                (now, now),
            )


class WorkflowStore:
    """Persist resumable workflow plans in the shared state database."""

    def __init__(self, settings: Settings):
        self.path = settings.state_db_path
        self.lease_seconds = settings.workflow_lease_seconds

    def create(self, workflow_id: str, name: str, steps: list[dict]) -> dict:
        now = _now_iso()
        with _connect(self.path) as connection:
            _init_schema(connection)
            connection.execute(
                """
                INSERT INTO workflows (
                    workflow_id, name, status, steps, current_step, created_at, updated_at
                ) VALUES (?, ?, 'planned', ?, 0, ?, ?)
                """,
                (workflow_id, name, json.dumps(steps, ensure_ascii=False), now, now),
            )
        return self.get(workflow_id) or {}

    def get(self, workflow_id: str) -> dict | None:
        with _connect(self.path) as connection:
            _init_schema(connection)
            row = connection.execute(
                "SELECT * FROM workflows WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
        return _workflow_row(row) if row else None

    def append_event(
        self,
        workflow_id: str,
        event_type: str,
        *,
        step_index: int = -1,
        details: dict | None = None,
    ) -> None:
        with _connect(self.path) as connection:
            _init_schema(connection)
            connection.execute(
                """
                INSERT INTO workflow_events (
                    event_id, workflow_id, step_index, event_type, details, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid4().hex,
                    workflow_id,
                    step_index,
                    event_type,
                    json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
                    _now_iso(),
                ),
            )

    def events(self, workflow_id: str, limit: int = 100) -> list[dict]:
        safe_limit = min(max(limit, 1), 500)
        with _connect(self.path) as connection:
            _init_schema(connection)
            rows = connection.execute(
                """
                SELECT event_id, workflow_id, step_index, event_type, details, created_at
                FROM workflow_events WHERE workflow_id = ? ORDER BY id LIMIT ?
                """,
                (workflow_id, safe_limit),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "workflow_id": row["workflow_id"],
                "step_index": row["step_index"],
                "event_type": row["event_type"],
                "details": json.loads(row["details"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def update(
        self,
        workflow_id: str,
        *,
        status: str,
        steps: list[dict],
        current_step: int,
        run_token: str = "",
    ) -> dict | None:
        with _connect(self.path) as connection:
            _init_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM workflows WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if not row:
                connection.rollback()
                return None
            current = _workflow_row(row)
            if run_token and str(row["run_token"] or "") != run_token:
                connection.rollback()
                raise WorkflowLeaseLost(workflow_id)
            if current["status"] == "cancelled" and status != "cancelled":
                connection.rollback()
                if run_token:
                    raise WorkflowLeaseLost(workflow_id)
                return current
            now = datetime.now(timezone.utc)
            next_token = run_token if status == "running" else None
            lease_expires_at = (
                (now + timedelta(seconds=self.lease_seconds)).isoformat() if next_token else None
            )
            connection.execute(
                """
                UPDATE workflows
                SET status = ?, steps = ?, current_step = ?, updated_at = ?,
                    run_token = ?, lease_expires_at = ?
                WHERE workflow_id = ?
                """,
                (
                    status,
                    json.dumps(steps, ensure_ascii=False),
                    current_step,
                    now.isoformat(),
                    next_token,
                    lease_expires_at,
                    workflow_id,
                ),
            )
            connection.commit()
        return self.get(workflow_id)

    def claim_execution(self, workflow_id: str) -> tuple[dict | None, str, str, str]:
        """Atomically grant one caller ownership of workflow execution."""
        with _connect(self.path) as connection:
            _init_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM workflows WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if not row:
                connection.rollback()
                return None, "", "not_found", ""
            workflow = _workflow_row(row)
            previous_status = str(workflow["status"])
            if previous_status == "running":
                raw_expiry = str(row["lease_expires_at"] or "")
                lease_expiry = (
                    datetime.fromisoformat(raw_expiry)
                    if raw_expiry
                    else datetime.fromisoformat(str(workflow["updated_at"]))
                    + timedelta(seconds=self.lease_seconds)
                )
                if lease_expiry > datetime.now(timezone.utc):
                    connection.rollback()
                    return workflow, previous_status, previous_status, ""
                previous_status = "recovering"
            elif previous_status not in {"planned", "waiting_confirmation", "waiting_condition"}:
                connection.rollback()
                return workflow, previous_status, previous_status, ""
            run_token = uuid4().hex
            now = datetime.now(timezone.utc)
            lease_expires_at = (now + timedelta(seconds=self.lease_seconds)).isoformat()
            connection.execute(
                """
                UPDATE workflows
                SET status = 'running', updated_at = ?, run_token = ?, lease_expires_at = ?
                WHERE workflow_id = ?
                """,
                (now.isoformat(), run_token, lease_expires_at, workflow_id),
            )
            connection.commit()
        return self.get(workflow_id), previous_status, "", run_token

    def cancel(self, workflow_id: str) -> dict | None:
        with _connect(self.path) as connection:
            _init_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM workflows WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
            if not row:
                connection.rollback()
                return None
            workflow = _workflow_row(row)
            if workflow["status"] in {"completed", "failed", "cancelled"}:
                connection.rollback()
                return workflow
            connection.execute(
                """
                UPDATE workflows
                SET status = 'cancelled', updated_at = ?, run_token = NULL, lease_expires_at = NULL
                WHERE workflow_id = ?
                """,
                (_now_iso(), workflow_id),
            )
            connection.commit()
        return self.get(workflow_id)


class ObservationStore:
    """Short-lived, privacy-bounded desktop observations."""

    def __init__(self, settings: Settings):
        self.path = settings.state_db_path
        self.ttl_seconds = settings.observation_ttl_seconds

    def create(self, observation_id: str, payload: dict) -> dict:
        captured_at = datetime.now(timezone.utc)
        expires_at = captured_at + timedelta(seconds=self.ttl_seconds)
        record = {
            **payload,
            "observation_id": observation_id,
            "captured_at": captured_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        with _connect(self.path) as connection:
            _init_schema(connection)
            connection.execute("DELETE FROM observations WHERE expires_at <= ?", (_now_iso(),))
            connection.execute(
                """
                INSERT INTO observations (observation_id, payload, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    observation_id,
                    json.dumps(record, ensure_ascii=False, sort_keys=True),
                    record["captured_at"],
                    record["expires_at"],
                ),
            )
        return record

    def get(self, observation_id: str) -> dict | None:
        with _connect(self.path) as connection:
            _init_schema(connection)
            row = connection.execute(
                "SELECT payload, expires_at FROM observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
        if not row:
            return None
        record = json.loads(row["payload"])
        record["expired"] = datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc)
        return record


class IdempotencyStore:
    """Fail-closed claim records for side-effecting desktop steps."""

    def __init__(self, settings: Settings):
        self.path = settings.state_db_path

    def claim(self, key: str) -> tuple[str, dict | None]:
        with _connect(self.path) as connection:
            _init_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, result FROM idempotency_keys WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
            if row:
                connection.rollback()
                result = json.loads(row["result"]) if row["result"] else None
                return str(row["status"]), result
            connection.execute(
                """
                INSERT INTO idempotency_keys (idempotency_key, status, result, created_at, updated_at)
                VALUES (?, 'executing', NULL, ?, ?)
                """,
                (key, _now_iso(), _now_iso()),
            )
            connection.commit()
        return "claimed", None

    def resolve(self, key: str, result: dict) -> None:
        status = "completed" if result.get("success") else "failed"
        with _connect(self.path) as connection:
            _init_schema(connection)
            connection.execute(
                """
                UPDATE idempotency_keys SET status = ?, result = ?, updated_at = ?
                WHERE idempotency_key = ? AND status = 'executing'
                """,
                (status, json.dumps(result, ensure_ascii=False), _now_iso(), key),
            )


def record_audit_event(
    settings: Settings,
    *,
    request_id: str,
    client: str,
    action: str,
    success: bool,
    error_code: str,
    cost_ms: int,
    param_keys: list[str],
) -> None:
    if not settings.audit_enabled:
        return
    with _connect(settings.state_db_path) as connection:
        _init_schema(connection)
        connection.execute(
            """
            INSERT INTO audit_events (
                event_id, request_id, client, action, success, error_code,
                cost_ms, param_keys, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid4().hex,
                request_id,
                client,
                action,
                int(success),
                error_code,
                max(0, cost_ms),
                json.dumps(sorted(param_keys), ensure_ascii=False),
                _now_iso(),
            ),
        )
        cutoff = (datetime.now(timezone.utc) - timedelta(days=settings.audit_retention_days)).isoformat()
        connection.execute("DELETE FROM audit_events WHERE created_at < ?", (cutoff,))


def list_audit_events(settings: Settings, limit: int = 50) -> dict:
    safe_limit = min(max(limit, 1), 500)
    with _connect(settings.state_db_path) as connection:
        _init_schema(connection)
        rows = connection.execute(
            """
            SELECT event_id, request_id, client, action, success, error_code,
                   cost_ms, param_keys, created_at
            FROM audit_events ORDER BY id DESC LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    events = [
        {
            "event_id": row[0],
            "request_id": row[1],
            "client": row[2],
            "action": row[3],
            "success": bool(row[4]),
            "error_code": row[5],
            "cost_ms": row[6],
            "param_keys": json.loads(row[7]),
            "created_at": row[8],
        }
        for row in rows
    ]
    return ok({"events": events, "count": len(events)}, f"已返回 {len(events)} 条审计记录。", "listed audit events")


def _connect(path: Path) -> sqlite3.Connection:
    target = path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _init_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    connection.execute("BEGIN IMMEDIATE")
    try:
        applied = {int(row[0]) for row in connection.execute("SELECT version FROM schema_migrations").fetchall()}
        migrations = ((1, _migration_1), (2, _migration_2), (3, _migration_3), (4, _migration_4))
        for version, migration in migrations:
            if version in applied:
                continue
            migration(connection)
            connection.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, _now_iso()),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _migration_1(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            request_id TEXT NOT NULL,
            client TEXT NOT NULL,
            action TEXT NOT NULL,
            success INTEGER NOT NULL,
            error_code TEXT NOT NULL,
            cost_ms INTEGER NOT NULL,
            param_keys TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflows (
            workflow_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL,
            steps TEXT NOT NULL,
            current_step INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_actions (
            action_id TEXT PRIMARY KEY,
            action_type TEXT NOT NULL,
            params TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            resolved_at TEXT,
            result TEXT
        )
        """
    )


def _migration_2(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS observations (
            observation_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_observations_expires_at ON observations(expires_at)")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            idempotency_key TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            result TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _migration_3(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            workflow_id TEXT NOT NULL,
            step_index INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            details TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_events_workflow_id ON workflow_events(workflow_id, id)"
    )


def _migration_4(connection: sqlite3.Connection) -> None:
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(workflows)").fetchall()}
    if "run_token" not in columns:
        connection.execute("ALTER TABLE workflows ADD COLUMN run_token TEXT")
    if "lease_expires_at" not in columns:
        connection.execute("ALTER TABLE workflows ADD COLUMN lease_expires_at TEXT")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pending_row(row: sqlite3.Row) -> dict:
    result = {
        "action_id": row["action_id"],
        "action_type": row["action_type"],
        "params": json.loads(row["params"]),
        "title": row["title"],
        "status": row["status"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
    }
    if row["resolved_at"]:
        result["resolved_at"] = row["resolved_at"]
    if row["result"]:
        result["result"] = json.loads(row["result"])
    return result


def _workflow_row(row: sqlite3.Row) -> dict:
    return {
        "workflow_id": row["workflow_id"],
        "name": row["name"],
        "status": row["status"],
        "steps": json.loads(row["steps"]),
        "current_step": row["current_step"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
