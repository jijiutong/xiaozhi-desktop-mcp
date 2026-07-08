from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhi_desktop_mcp.config import Settings
from xiaozhi_desktop_mcp.tools import cc_session, pending_actions


@pytest.fixture(autouse=True)
def clear_process_state():
    cc_session._visible_sessions.clear()
    pending_actions._pending_actions.clear()
    yield
    cc_session._visible_sessions.clear()
    pending_actions._pending_actions.clear()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    vault = tmp_path / "vault"
    project = tmp_path / "project"
    vault.mkdir()
    project.mkdir()
    return Settings(
        obsidian_vault=vault,
        obsidian_memory_file="memory.md",
        cc_tasks_dir=vault / "tasks",
        desktop_config_path=tmp_path / "desktop-mcp.yaml",
        default_project_root=str(project),
        allowed_apps=frozenset({"Obsidian", "Terminal", "Google Chrome", "Music", "网易云音乐"}),
        cc_allowed_projects=frozenset({project}),
        cc_allowed_clis=frozenset({"claude", "codex"}),
        cc_default_cli="claude",
        cc_allowed_cli_args=frozenset({"-c", "--continue"}),
        cc_visible_terminals=frozenset({"Terminal"}),
        xcode_allowed_projects=frozenset({project}),
        cc_allowed_models=frozenset(),
        cc_slash_default_policy="allow",
        cc_slash_allow=frozenset(),
        cc_slash_confirm=frozenset(),
        cc_slash_deny=frozenset(),
        cc_log_enabled=False,
        cc_status_tail_chars=4000,
        cc_max_return_chars=8000,
    )
