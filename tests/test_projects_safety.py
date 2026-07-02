from __future__ import annotations

from xiaozhi_desktop_mcp.tools.projects import resolve_project


def test_resolve_project_rejects_non_allowlisted_path(settings, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()

    result = resolve_project(settings, str(outside))

    assert result["success"] is False
    assert "not allowlisted" in result["error"]
