from __future__ import annotations

import json
from typing import Any

from ..config import Settings
from ..responses import ok

DEFAULT_CATEGORIES: dict[str, dict[str, Any]] = {
    "music": {
        "description": "Music playback controls.",
        "intents": ["open", "play", "pause", "toggle", "next", "previous", "search"],
        "default_app": "Music",
    },
    "docs": {
        "description": "Notes and document workflows.",
        "intents": ["remember", "search", "create", "open", "append", "daily"],
        "default_app": "Obsidian",
    },
    "ai": {
        "description": "AI assistant and coding-agent workflows.",
        "intents": ["open", "send", "continue", "status", "stop", "slash", "model"],
        "default_app": "Claude Code",
    },
    "dev": {
        "description": "Developer workflows.",
        "intents": ["open", "build", "test", "clean", "errors"],
        "default_app": "Xcode",
    },
    "browser": {
        "description": "Browser navigation and search.",
        "intents": ["open", "search"],
        "default_app": "Google Chrome",
    },
    "system": {
        "description": "Finder and clipboard utilities.",
        "intents": ["open", "reveal", "clipboard_get", "clipboard_set"],
        "default_app": "Finder",
    },
}


def category_registry(settings: Settings) -> dict:
    """Return configured desktop categories for clients and voice routers."""
    config = load_desktop_config(settings)
    categories = _merge_categories(DEFAULT_CATEGORIES, config.get("categories", {}))
    return ok(
        {"config_path": str(settings.desktop_config_path), "categories": categories, "count": len(categories)},
        f"已返回 {len(categories)} 个桌面能力分类。",
        "returned desktop category registry",
    )


def load_desktop_config(settings: Settings) -> dict[str, Any]:
    """Load optional desktop-mcp.yaml/json configuration.

    The parser intentionally accepts JSON as the fully supported machine format.
    A .yaml file may also contain JSON/YAML-compatible object syntax. If parsing
    fails, the built-in registry remains active.
    """
    path = settings.desktop_config_path
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    parsed = _parse_jsonish(text)
    return parsed if isinstance(parsed, dict) else {}


def _merge_categories(defaults: dict[str, dict[str, Any]], configured: Any) -> dict[str, dict[str, Any]]:
    categories = {name: dict(value) for name, value in defaults.items()}
    if not isinstance(configured, dict):
        return categories
    for name, value in configured.items():
        if not isinstance(value, dict):
            continue
        base = dict(categories.get(str(name), {}))
        base.update(value)
        categories[str(name)] = base
    return categories


def _parse_jsonish(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        return {}
    try:
        return yaml.safe_load(text)
    except Exception:
        return {}
