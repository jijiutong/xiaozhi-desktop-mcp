from __future__ import annotations

import subprocess
from pathlib import Path

from ..config import Settings
from ..responses import fail, ok
from ..safety import SafetyError, ensure_allowed_project

_MAX_OUTPUT_CHARS = 12000
_XCODE_EXTENSIONS = {".xcodeproj", ".xcworkspace"}
_last_xcode_result: dict = {}


def open_xcode_project(settings: Settings, project_path: str = "", xcode_path: str = "") -> dict:
    """Open an allowed Xcode project or workspace."""
    try:
        container = _resolve_xcode_container(settings, project_path, xcode_path)
    except SafetyError as exc:
        return fail(str(exc), "Xcode 项目不在白名单里，我没有打开。")
    completed = subprocess.run(
        ["open", "-a", "Xcode", str(container)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return fail(
            completed.stderr.strip() or completed.stdout.strip(),
            "Xcode 项目没有打开成功。",
            {"path": str(container)},
        )
    return ok({"path": str(container)}, "已打开 Xcode 项目。", "opened Xcode project")


def xcode_build(
    settings: Settings,
    project_path: str = "",
    xcode_path: str = "",
    scheme: str = "",
    configuration: str = "",
    destination: str = "",
) -> dict:
    """Run xcodebuild build inside an allowlisted project."""
    return _run_xcodebuild(settings, "build", project_path, xcode_path, scheme, configuration, destination)


def xcode_test(
    settings: Settings,
    project_path: str = "",
    xcode_path: str = "",
    scheme: str = "",
    configuration: str = "",
    destination: str = "",
) -> dict:
    """Run xcodebuild test inside an allowlisted project."""
    return _run_xcodebuild(settings, "test", project_path, xcode_path, scheme, configuration, destination)


def xcode_clean(
    settings: Settings,
    project_path: str = "",
    xcode_path: str = "",
    scheme: str = "",
    configuration: str = "",
    destination: str = "",
) -> dict:
    """Run xcodebuild clean inside an allowlisted project."""
    return _run_xcodebuild(settings, "clean", project_path, xcode_path, scheme, configuration, destination)


def xcode_last_errors(limit: int = 20) -> dict:
    """Return recent xcodebuild error-like lines from the last run."""
    if not _last_xcode_result:
        return ok(
            {"count": 0, "errors": [], "last_result": {}},
            "还没有 Xcode 构建记录。",
            "no Xcode result recorded",
        )
    output = str(_last_xcode_result.get("output", ""))
    lines = [
        line.strip()
        for line in output.splitlines()
        if _looks_like_error_line(line)
    ]
    bounded = lines[-max(1, min(limit, 50)) :]
    return ok(
        {
            "count": len(bounded),
            "errors": bounded,
            "last_result": {
                key: value
                for key, value in _last_xcode_result.items()
                if key != "output"
            },
        },
        f"找到 {len(bounded)} 条 Xcode 错误线索。",
        "returned Xcode error lines",
    )


def _run_xcodebuild(
    settings: Settings,
    action: str,
    project_path: str,
    xcode_path: str,
    scheme: str,
    configuration: str,
    destination: str,
) -> dict:
    try:
        container = _resolve_xcode_container(settings, project_path, xcode_path)
        command = _xcodebuild_command(container, action, scheme, configuration, destination)
    except SafetyError as exc:
        return fail(str(exc), "Xcode 命令没有执行。")
    completed = subprocess.run(
        command,
        cwd=str(container.parent),
        check=False,
        capture_output=True,
        text=True,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    tail = output[-_MAX_OUTPUT_CHARS:]
    _last_xcode_result.clear()
    _last_xcode_result.update(
        {
            "action": action,
            "path": str(container),
            "command": command,
            "returncode": completed.returncode,
            "success": completed.returncode == 0,
            "output": tail,
        }
    )
    data = {
        "action": action,
        "path": str(container),
        "command": command,
        "returncode": completed.returncode,
        "output_tail": tail,
    }
    if completed.returncode != 0:
        return fail(
            f"xcodebuild {action} failed with exit code {completed.returncode}",
            f"Xcode {action} 失败。",
            data,
        )
    return ok(data, f"Xcode {action} 完成。", f"xcodebuild {action} completed")


def _resolve_xcode_container(settings: Settings, project_path: str, xcode_path: str) -> Path:
    base_value = project_path.strip() or settings.default_project_root
    if not base_value and xcode_path.strip():
        base_value = str(Path(xcode_path).expanduser().resolve().parent)
    base = ensure_allowed_project(base_value, settings.xcode_allowed_projects)
    if xcode_path.strip():
        target = Path(xcode_path).expanduser()
        if not target.is_absolute():
            target = base / target
        target = target.resolve()
        if target.suffix not in _XCODE_EXTENSIONS:
            raise SafetyError("xcode_path must point to .xcodeproj or .xcworkspace")
        if base != target and base not in target.parents:
            raise SafetyError(f"xcode path is outside allowed project: {target}")
        return target
    return _find_xcode_container(base)


def _find_xcode_container(base: Path) -> Path:
    for suffix in (".xcworkspace", ".xcodeproj"):
        matches = sorted(path for path in base.rglob(f"*{suffix}") if not _is_hidden(path, base))
        if matches:
            return matches[0]
    raise SafetyError(f"no .xcworkspace or .xcodeproj found under: {base}")


def _xcodebuild_command(
    container: Path,
    action: str,
    scheme: str,
    configuration: str,
    destination: str,
) -> list[str]:
    if action not in {"build", "test", "clean"}:
        raise SafetyError(f"unsupported xcode action: {action}")
    command = ["xcodebuild"]
    if container.suffix == ".xcworkspace":
        command.extend(["-workspace", str(container)])
    elif container.suffix == ".xcodeproj":
        command.extend(["-project", str(container)])
    else:
        raise SafetyError("xcode container must be .xcodeproj or .xcworkspace")
    if scheme.strip():
        command.extend(["-scheme", scheme.strip()])
    if configuration.strip():
        command.extend(["-configuration", configuration.strip()])
    if destination.strip():
        command.extend(["-destination", destination.strip()])
    command.append(action)
    return command


def _is_hidden(path: Path, base: Path) -> bool:
    try:
        relative = path.relative_to(base)
    except ValueError:
        return True
    return any(part.startswith(".") for part in relative.parts)


def _looks_like_error_line(line: str) -> bool:
    lower = line.lower()
    return any(
        marker in lower
        for marker in (
            " error:",
            ": error:",
            "failed",
            "failure",
            "no such module",
            "undefined symbol",
            "build input file cannot be found",
            "test failed",
        )
    )
