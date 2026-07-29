from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone

from xiaozhi_desktop_mcp.api_v2 import dispatch
from xiaozhi_desktop_mcp.storage import _init_schema, _migration_1, _migration_2


def test_v4_migration_preserves_v3_pending_actions_and_enables_observations(settings, monkeypatch):
    with sqlite3.connect(settings.state_db_path) as connection:
        connection.execute(
            """
            CREATE TABLE pending_actions (
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
        now = datetime.now(timezone.utc)
        connection.execute(
            """
            INSERT INTO pending_actions (
                action_id, action_type, params, title, status, created_at, expires_at, resolved_at, result
            ) VALUES (?, ?, ?, ?, 'pending', ?, ?, NULL, NULL)
            """,
            (
                "legacy-action",
                "app_close",
                json.dumps({"app_name": "Obsidian"}),
                "Legacy action",
                now.isoformat(),
                (now + timedelta(minutes=10)).isoformat(),
            ),
        )

    listed = dispatch(settings, "pending_list", {"status": "pending"}, "list", "test-client")

    def fake_tree(command, **_kwargs):
        payload = {
            "process_name": "Google Chrome",
            "window": {"title": "Example"},
            "elements": [],
            "truncated": False,
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", fake_tree)
    observed = dispatch(settings, "desktop_observe", {"app_name": "chrome"}, "observe", "test-client")

    assert listed["success"] is True
    assert [item["action_id"] for item in listed["data"]["actions"]] == ["legacy-action"]
    assert observed["success"] is True
    assert observed["data"]["observation_id"].startswith("obs_")


def test_migration_2_owns_observation_and_idempotency_schema(tmp_path):
    path = tmp_path / "migration-2.db"
    with sqlite3.connect(path) as connection:
        _migration_1(connection)
        _migration_2(connection)
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        indexes = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
        }

    assert "observations" in tables
    assert "idempotency_keys" in tables
    assert "idx_observations_expires_at" in indexes


def test_latest_migration_adds_workflow_lease_columns(tmp_path):
    path = tmp_path / "latest.db"
    with sqlite3.connect(path) as connection:
        _init_schema(connection)
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(workflows)").fetchall()
        }

    assert {"run_token", "lease_expires_at"} <= columns
