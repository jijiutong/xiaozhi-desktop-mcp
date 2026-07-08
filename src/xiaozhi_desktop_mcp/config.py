from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """运行时配置。

    所有字段都来自 `.env` 或进程环境变量。这里保持 immutable，避免工具执行
    过程中意外修改全局配置。
    """

    obsidian_vault: Path
    obsidian_memory_file: str
    cc_tasks_dir: Path
    desktop_config_path: Path
    default_project_root: str
    allowed_apps: frozenset[str]
    cc_allowed_projects: frozenset[Path]
    cc_allowed_clis: frozenset[str]
    cc_default_cli: str
    cc_allowed_cli_args: frozenset[str]
    cc_visible_terminals: frozenset[str]
    xcode_allowed_projects: frozenset[Path]
    cc_allowed_models: frozenset[str]
    cc_slash_default_policy: str
    cc_slash_allow: frozenset[str]
    cc_slash_confirm: frozenset[str]
    cc_slash_deny: frozenset[str]
    cc_log_enabled: bool
    cc_status_tail_chars: int
    cc_max_return_chars: int


def _split_csv(value: str) -> frozenset[str]:
    """把逗号分隔配置转成去空格后的不可变集合。"""
    return frozenset(item.strip() for item in value.split(",") if item.strip())


def _split_paths(value: str) -> frozenset[Path]:
    """把逗号分隔路径配置解析为绝对路径集合。"""
    return frozenset(Path(item).expanduser().resolve() for item in _split_csv(value))


def _bool_env(name: str, default: bool = False) -> bool:
    """读取布尔环境变量，兼容 true/1/yes/on。"""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    """读取整数环境变量，非法时回退默认值。"""
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_settings() -> Settings:
    """加载本机桌面自动化的保守默认配置。

    相对路径会解析到 Obsidian vault 下，确保语音记忆和 cc 任务默认落在用户
    看得见、能同步、能搜索的位置。
    """
    vault = Path(os.getenv("OBSIDIAN_VAULT", "~/obsidian")).expanduser().resolve()
    memory_file = os.getenv("OBSIDIAN_MEMORY_FILE", "00-Inbox/voice-memory.md")
    cc_tasks_dir_value = os.getenv("CC_TASKS_DIR", "00-Inbox/cc-tasks")
    cc_tasks_dir = Path(cc_tasks_dir_value).expanduser()
    desktop_config_path = Path(os.getenv("DESKTOP_MCP_CONFIG", "desktop-mcp.yaml")).expanduser()

    # 允许用户填绝对路径；如果是相对路径，就固定放到 Obsidian vault 内。
    if not cc_tasks_dir.is_absolute():
        cc_tasks_dir = vault / cc_tasks_dir
    cc_tasks_dir = cc_tasks_dir.resolve()
    if not desktop_config_path.is_absolute():
        desktop_config_path = Path.cwd() / desktop_config_path
    desktop_config_path = desktop_config_path.resolve()
    default_project_root = os.getenv("DEFAULT_PROJECT_ROOT", "")
    default_allowed_apps = "Obsidian,Xcode,Google Chrome,Safari,Microsoft Edge,Arc,Music,网易云音乐,Finder,Terminal"
    allowed_apps = _split_csv(os.getenv("ALLOWED_APPS", default_allowed_apps))

    # cc/Claude Code/Codex 会话配置：默认能玩，后续可以通过 .env 收紧。
    if default_project_root:
        default_project_path = Path(default_project_root).expanduser().resolve()
    else:
        default_project_path = Path.cwd().resolve()
    allowed_projects_value = os.getenv("CC_ALLOWED_PROJECTS", str(default_project_path))
    cc_allowed_projects = _split_paths(allowed_projects_value)
    cc_allowed_clis = _split_csv(os.getenv("CC_ALLOWED_CLIS", "claude,codex"))
    cc_default_cli = os.getenv("CC_DEFAULT_CLI", "claude").strip() or "claude"
    cc_allowed_cli_args = _split_csv(os.getenv("CC_ALLOWED_CLI_ARGS", "-c,--continue"))
    cc_visible_terminals = _split_csv(os.getenv("CC_VISIBLE_TERMINALS", "Terminal,iTerm"))
    xcode_allowed_projects = _split_paths(os.getenv("XCODE_ALLOWED_PROJECTS", allowed_projects_value))
    cc_allowed_models = _split_csv(os.getenv("CC_ALLOWED_MODELS", ""))
    cc_slash_default_policy = os.getenv("CC_SLASH_DEFAULT_POLICY", "allow").strip().lower()
    cc_slash_allow = _split_csv(os.getenv("CC_SLASH_ALLOW", ""))
    cc_slash_confirm = _split_csv(os.getenv("CC_SLASH_CONFIRM", ""))
    cc_slash_deny = _split_csv(os.getenv("CC_SLASH_DENY", ""))
    cc_log_enabled = _bool_env("CC_LOG_ENABLED", False)
    cc_status_tail_chars = _int_env("CC_STATUS_TAIL_CHARS", 4000)
    cc_max_return_chars = _int_env("CC_MAX_RETURN_CHARS", 8000)
    return Settings(
        obsidian_vault=vault,
        obsidian_memory_file=memory_file,
        cc_tasks_dir=cc_tasks_dir,
        desktop_config_path=desktop_config_path,
        default_project_root=default_project_root,
        allowed_apps=allowed_apps,
        cc_allowed_projects=cc_allowed_projects,
        cc_allowed_clis=cc_allowed_clis,
        cc_default_cli=cc_default_cli,
        cc_allowed_cli_args=cc_allowed_cli_args,
        cc_visible_terminals=cc_visible_terminals,
        xcode_allowed_projects=xcode_allowed_projects,
        cc_allowed_models=cc_allowed_models,
        cc_slash_default_policy=cc_slash_default_policy,
        cc_slash_allow=cc_slash_allow,
        cc_slash_confirm=cc_slash_confirm,
        cc_slash_deny=cc_slash_deny,
        cc_log_enabled=cc_log_enabled,
        cc_status_tail_chars=cc_status_tail_chars,
        cc_max_return_chars=cc_max_return_chars,
    )
