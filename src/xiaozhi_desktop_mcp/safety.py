from __future__ import annotations

from pathlib import Path


class SafetyError(ValueError):
    """请求越过安全边界时抛出。

    工具层会把这个异常转成 `success: false`，让小智能自然回复用户。
    """


def ensure_inside(base: Path, target: Path) -> Path:
    """确认目标路径解析后仍在 base 目录内。

    这样可以挡住 `../`、符号链接等绕出安全目录的情况。
    """
    base = base.expanduser().resolve()
    target = target.expanduser().resolve()
    if target != base and base not in target.parents:
        raise SafetyError(f"target path is outside allowed base: {target}")
    return target


def ensure_allowed_app(app_name: str, allowed_apps: frozenset[str]) -> str:
    """确认要打开的 App 在显式白名单内。"""
    normalized = app_name.strip()
    if not normalized:
        raise SafetyError("app name is empty")
    if normalized not in allowed_apps:
        allowed = ", ".join(sorted(allowed_apps))
        raise SafetyError(f"app is not allowlisted: {normalized}. allowed: {allowed}")
    return normalized


def ensure_allowed_project(project_path: str, allowed_projects: frozenset[Path]) -> Path:
    """确认 cc/Claude Code 只能在配置允许的项目目录内启动。"""
    if not project_path.strip():
        raise SafetyError("project path is empty")
    target = Path(project_path).expanduser().resolve()
    for base in allowed_projects:
        base = base.expanduser().resolve()
        if target == base or base in target.parents:
            return target
    allowed = ", ".join(str(path) for path in sorted(allowed_projects))
    raise SafetyError(f"project path is not allowlisted: {target}. allowed: {allowed}")


def ensure_allowed_cli(cli: str, allowed_clis: frozenset[str]) -> str:
    """确认只能启动配置允许的 CLI，例如 claude 或 codex。"""
    normalized = cli.strip()
    if not normalized:
        raise SafetyError("cli is empty")
    if normalized not in allowed_clis:
        allowed = ", ".join(sorted(allowed_clis))
        raise SafetyError(f"cli is not allowlisted: {normalized}. allowed: {allowed}")
    return normalized


def slash_policy(
    command: str,
    default_policy: str,
    allow: frozenset[str],
    confirm: frozenset[str],
    deny: frozenset[str],
) -> str:
    """按配置计算 slash 命令策略。

    优先级：deny > confirm > allow > default。默认可设为 allow，让个人本机模式
    先跑起来；需要收紧时再改 .env。
    """
    normalized = command.strip().split(maxsplit=1)[0]
    if not normalized.startswith("/"):
        raise SafetyError("slash command must start with /")
    if normalized in deny:
        return "deny"
    if normalized in confirm:
        return "confirm"
    if allow and normalized not in allow:
        return "deny"
    if normalized in allow:
        return "allow"
    return default_policy if default_policy in {"allow", "confirm", "deny"} else "allow"
