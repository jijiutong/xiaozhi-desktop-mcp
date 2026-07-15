from __future__ import annotations

import subprocess
from pathlib import Path

from ..config import Settings
from ..responses import fail, ok
from ..safety import SafetyError, ensure_inside


def finder_open_path(settings: Settings, path: str = "", reveal: bool = False) -> dict:
    """Open or reveal a path inside known safe roots."""
    try:
        target = resolve_allowed_path(settings, path)
    except SafetyError as exc:
        return fail(str(exc), "这个路径不在允许范围内，我没有打开。")
    if not target.exists():
        return fail("path does not exist", "这个路径不存在，我没有打开。", {"path": str(target)})
    command = ["open", "-R", str(target)] if reveal else ["open", str(target)]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return fail(
            completed.stderr.strip() or completed.stdout.strip(),
            "Finder 操作没有成功。",
            {"path": str(target)},
        )
    return ok({"path": str(target), "reveal": reveal}, "已在 Finder 打开。", "finder path opened")


def resolve_allowed_path(settings: Settings, path: str) -> Path:
    value = path.strip()
    if not value:
        return settings.obsidian_vault
    target = Path(value).expanduser()
    if not target.is_absolute():
        target = settings.obsidian_vault / target
    target = target.resolve()
    for base in _allowed_roots(settings):
        try:
            return ensure_inside(base, target)
        except SafetyError:
            continue
    raise SafetyError(f"path is outside allowed roots: {target}")


def _allowed_roots(settings: Settings) -> tuple[Path, ...]:
    roots = [settings.obsidian_vault, settings.cc_tasks_dir]
    roots.extend(settings.cc_allowed_projects)
    roots.extend(settings.xcode_allowed_projects)
    return tuple(path.expanduser().resolve() for path in roots)
