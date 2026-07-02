from __future__ import annotations

from xiaozhi_desktop_mcp.tools.xcode import open_xcode_project, xcode_build, xcode_last_errors


def test_xcode_open_project_rejects_outside_path(settings, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    project = outside / "App.xcodeproj"
    project.mkdir()

    result = open_xcode_project(settings, str(outside), str(project))

    assert result["success"] is False
    assert "not allowlisted" in result["error"]


def test_xcode_build_finds_workspace_and_runs_command(settings, monkeypatch):
    workspace = settings.default_project_root
    project_root = next(iter(settings.xcode_allowed_projects))
    (project_root / "App.xcworkspace").mkdir()
    calls = []

    class Completed:
        returncode = 0
        stdout = "build ok"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr("xiaozhi_desktop_mcp.tools.xcode.subprocess.run", fake_run)

    result = xcode_build(settings, workspace, "", "App")

    assert result["success"] is True
    assert calls[0][0][:3] == ["xcodebuild", "-workspace", str(project_root / "App.xcworkspace")]
    assert "-scheme" in calls[0][0]


def test_xcode_last_errors_returns_recent_failure_lines():
    result = xcode_last_errors()

    assert result["success"] is True
    assert "errors" in result
