from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from ..config import Settings
from ..responses import ok


def health_detail(settings: Settings) -> dict:
    """Run read-only checks for the local desktop MCP environment."""
    checks = [
        _path_check("obsidian_vault", settings.obsidian_vault, must_exist=True, writable=False),
        _path_check(
            "obsidian_memory_parent",
            settings.obsidian_vault / settings.obsidian_memory_file,
            must_exist=False,
            writable=True,
        ),
        _path_check("cc_tasks_dir", settings.cc_tasks_dir, must_exist=False, writable=True),
        _path_check("state_db", settings.state_db_path, must_exist=False, writable=True),
        _allowed_projects_check(settings),
        _cli_check(settings),
        _terminal_check(settings),
        _slash_policy_check(settings),
    ]
    failed = [check for check in checks if check["status"] == "fail"]
    warning = [check for check in checks if check["status"] == "warning"]
    overall = "ok" if not failed and not warning else "warning" if not failed else "fail"
    if overall == "ok":
        spoken = "桌面 MCP 自检通过。"
    elif overall == "warning":
        spoken = f"桌面 MCP 自检有 {len(warning)} 个提醒，但没有发现阻断问题。"
    else:
        spoken = f"桌面 MCP 自检发现 {len(failed)} 个问题，需要处理。"
    return ok(
        {
            "overall": overall,
            "checks": checks,
            "failed_count": len(failed),
            "warning_count": len(warning),
        },
        spoken,
        "desktop health detail checked",
    )


def config_summary(settings: Settings) -> dict:
    """Return a non-secret summary of runtime configuration."""
    summary = {
        "obsidian_vault": str(settings.obsidian_vault),
        "obsidian_memory_file": settings.obsidian_memory_file,
        "cc_tasks_dir": str(settings.cc_tasks_dir),
        "desktop_config_path": str(settings.desktop_config_path),
        "default_project_root": settings.default_project_root,
        "allowed_apps": sorted(settings.allowed_apps),
        "app_alias_count": len(settings.app_aliases),
        "app_process_alias_count": len(settings.app_process_aliases),
        "app_automation_alias_count": len(settings.app_automation_aliases),
        "state_db_path": str(settings.state_db_path),
        "pending_ttl_seconds": settings.pending_ttl_seconds,
        "audit_enabled": settings.audit_enabled,
        "audit_retention_days": settings.audit_retention_days,
        "browser_control_enabled": settings.browser_control_enabled,
        "browser_allowed_domains": sorted(settings.browser_allowed_domains),
        "cc_allowed_projects": sorted(str(path) for path in settings.cc_allowed_projects),
        "cc_allowed_clis": sorted(settings.cc_allowed_clis),
        "cc_default_cli": settings.cc_default_cli,
        "cc_allowed_cli_args": sorted(settings.cc_allowed_cli_args),
        "cc_visible_terminals": sorted(settings.cc_visible_terminals),
        "xcode_allowed_projects": sorted(str(path) for path in settings.xcode_allowed_projects),
        "cc_allowed_models": sorted(settings.cc_allowed_models),
        "cc_slash_default_policy": settings.cc_slash_default_policy,
        "cc_slash_allow_count": len(settings.cc_slash_allow),
        "cc_slash_confirm_count": len(settings.cc_slash_confirm),
        "cc_slash_deny_count": len(settings.cc_slash_deny),
        "cc_log_enabled": settings.cc_log_enabled,
        "cc_status_tail_chars": settings.cc_status_tail_chars,
        "cc_max_return_chars": settings.cc_max_return_chars,
    }
    return ok(
        {"config": summary},
        "已返回桌面 MCP 配置摘要。",
        "desktop config summary returned",
    )


def _path_check(name: str, path: Path, must_exist: bool, writable: bool) -> dict:
    target = path.expanduser().resolve()
    check_path = target if target.suffix == "" else target.parent
    exists = target.exists()
    if must_exist and not exists:
        return _check(name, "fail", f"path does not exist: {target}", str(target))
    if writable:
        if check_path.exists():
            writable_ok = _is_writable(check_path)
            if not writable_ok:
                return _check(name, "fail", f"path is not writable: {check_path}", str(target))
        else:
            parent = check_path.parent
            if not parent.exists():
                return _check(name, "warning", f"parent path does not exist yet: {parent}", str(target))
            if not _is_writable(parent):
                return _check(name, "fail", f"parent path is not writable: {parent}", str(target))
            return _check(
                name,
                "warning",
                f"path does not exist yet, but parent is writable: {check_path}",
                str(target),
            )
    return _check(name, "ok", "path check passed", str(target))


def _allowed_projects_check(settings: Settings) -> dict:
    if not settings.cc_allowed_projects:
        return _check("cc_allowed_projects", "fail", "CC_ALLOWED_PROJECTS is empty")
    missing = [str(path) for path in settings.cc_allowed_projects if not path.exists()]
    if missing:
        return _check("cc_allowed_projects", "warning", f"some allowed projects do not exist: {missing}")
    return _check("cc_allowed_projects", "ok", "allowed projects check passed")


def _cli_check(settings: Settings) -> dict:
    if not settings.cc_allowed_clis:
        return _check("cc_allowed_clis", "fail", "CC_ALLOWED_CLIS is empty")
    found = {cli: shutil.which(cli) for cli in sorted(settings.cc_allowed_clis)}
    missing = [cli for cli, path in found.items() if path is None]
    if missing:
        return _check("cc_allowed_clis", "warning", f"some CLI commands were not found in PATH: {missing}", found)
    return _check("cc_allowed_clis", "ok", "CLI commands found", found)


def _terminal_check(settings: Settings) -> dict:
    if not settings.cc_visible_terminals:
        return _check("cc_visible_terminals", "fail", "CC_VISIBLE_TERMINALS is empty")
    results = {}
    failures = []
    for terminal in sorted(settings.cc_visible_terminals):
        ok_result = _application_resolves(terminal)
        results[terminal] = ok_result
        if not ok_result:
            failures.append(terminal)
    if failures:
        return _check(
            "cc_visible_terminals",
            "warning",
            f"some terminal apps could not be resolved: {failures}",
            results,
        )
    return _check("cc_visible_terminals", "ok", "terminal apps resolved", results)


def _slash_policy_check(settings: Settings) -> dict:
    policy = settings.cc_slash_default_policy
    if policy not in {"allow", "confirm", "deny"}:
        return _check("cc_slash_default_policy", "warning", f"invalid slash default policy: {policy}")
    return _check("cc_slash_default_policy", "ok", "slash policy check passed", policy)


def _is_writable(path: Path) -> bool:
    try:
        return path.exists() and path.is_dir() and os.access(path, os.W_OK)
    except OSError:
        return False


def _application_resolves(app_name: str) -> bool:
    script = f'id of application "{_escape_applescript(app_name)}"'
    completed = subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True)
    return completed.returncode == 0


def _check(name: str, status: str, message: str, details=None) -> dict:
    result = {
        "name": name,
        "status": status,
        "message": message,
    }
    if details is not None:
        result["details"] = details
    return result


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
