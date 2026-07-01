from __future__ import annotations

from pathlib import Path

from ..config import Settings
from ..responses import fail, ok
from ..safety import SafetyError, ensure_allowed_project
from .workflows import ask_cc, open_cc_project


def list_projects(settings: Settings) -> dict:
    """List projects available to desktop MCP, derived from CC_ALLOWED_PROJECTS."""
    projects = [_project_entry(path, settings) for path in sorted(settings.cc_allowed_projects)]
    return ok(
        {
            "count": len(projects),
            "projects": projects,
        },
        f"当前有 {len(projects)} 个允许的项目。",
        "listed allowed projects",
    )


def resolve_project(settings: Settings, project: str) -> dict:
    """Resolve a project alias, folder name, or allowed path to a safe project path."""
    try:
        path = _resolve_project_path(settings, project)
    except SafetyError as exc:
        return fail(str(exc), "我没有找到这个允许项目。")
    return ok(
        {"project": _project_entry(path, settings)},
        f"已找到项目 {path.name}。",
        "resolved project",
    )


def open_cc_project_named(
    settings: Settings,
    project: str,
    session_id: str = "default",
    cli: str = "",
    terminal: str = "Terminal",
    cli_args: str = "",
) -> dict:
    """Resolve a project name/path, then open a visible Claude Code/Codex session."""
    try:
        path = _resolve_project_path(settings, project)
    except SafetyError as exc:
        return fail(str(exc), "我没有找到这个允许项目，所以没有打开 Claude Code。")
    result = open_cc_project(settings, str(path), session_id, cli, terminal, cli_args)
    result["project_alias"] = project
    result["resolved_project_path"] = str(path)
    return result


def ask_cc_project(
    settings: Settings,
    project: str,
    text: str,
    session_id: str = "default",
    cli: str = "",
    terminal: str = "Terminal",
    open_if_needed: bool = True,
) -> dict:
    """Resolve a project name/path, then send an instruction to Claude Code/Codex."""
    try:
        path = _resolve_project_path(settings, project)
    except SafetyError as exc:
        return fail(str(exc), "我没有找到这个允许项目，所以没有发送给 Claude Code。")
    result = ask_cc(settings, text, str(path), session_id, cli, terminal, open_if_needed)
    result["project_alias"] = project
    result["resolved_project_path"] = str(path)
    return result


def _resolve_project_path(settings: Settings, project: str) -> Path:
    query = project.strip()
    if not query:
        if settings.default_project_root:
            return ensure_allowed_project(settings.default_project_root, settings.cc_allowed_projects)
        if len(settings.cc_allowed_projects) == 1:
            return next(iter(settings.cc_allowed_projects))
        raise SafetyError("project is empty")

    direct = Path(query).expanduser()
    if direct.is_absolute() or "/" in query:
        return ensure_allowed_project(str(direct), settings.cc_allowed_projects)

    matches = []
    normalized_query = _normalize_alias(query)
    for path in settings.cc_allowed_projects:
        aliases = {_normalize_alias(path.name), _normalize_alias(str(path))}
        if normalized_query in aliases:
            matches.append(path)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        choices = ", ".join(str(path) for path in matches)
        raise SafetyError(f"project alias is ambiguous: {query}. choices: {choices}")
    allowed = ", ".join(path.name for path in sorted(settings.cc_allowed_projects))
    raise SafetyError(f"project alias is not allowlisted: {query}. allowed aliases: {allowed}")


def _project_entry(path: Path, settings: Settings) -> dict:
    resolved = path.expanduser().resolve()
    return {
        "alias": resolved.name,
        "path": str(resolved),
        "exists": resolved.exists(),
        "is_default": bool(settings.default_project_root)
        and resolved == Path(settings.default_project_root).expanduser().resolve(),
    }


def _normalize_alias(value: str) -> str:
    return value.strip().lower().replace(" ", "").replace("_", "-")
